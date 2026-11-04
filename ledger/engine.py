"""Replay engine: applies the event stream day by day and runs end-of-day.

v1 — naive: end-of-day looks only at the *current* day's closing balance for
the overdraft fee, and records that day's interest accrual as computed on
that day. Kept simple on purpose; the scenario tests will tell us whether it
survives backdated entries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .events import Authorization, Credit, Debit, Event, Reversal, Settlement
from .ledger import Decision, Entry, Kind, Ledger, Severity
from .money import quantize, split_equal, zero

# Overdraft fee per currency. Only AED is specified by the assignment.
OVERDRAFT_FEE: dict[str, Decimal] = {"AED": Decimal("25.00")}

# 0.04% per day, as a fraction.
DAILY_INTEREST_RATE = Decimal("0.0004")


@dataclass
class DayReport:
    day: int
    processed: list[str] = field(default_factory=list)   # one line per event
    fees: list[Entry] = field(default_factory=list)
    accruals: dict[str, Decimal] = field(default_factory=dict)
    interest: list[Entry] = field(default_factory=list)
    closing: dict[str, Decimal] = field(default_factory=dict)
    available: dict[str, Decimal] = field(default_factory=dict)
    auth_states: dict[str, str] = field(default_factory=dict)
    errors: list = field(default_factory=list)


class Engine:
    def __init__(self, ledger: Ledger, events: list[Event], window_days: int,
                 fee_table: dict[str, Decimal] = OVERDRAFT_FEE,
                 rate: Decimal = DAILY_INTEREST_RATE):
        self.ledger = ledger
        self.events = list(events)
        self.window_days = window_days
        self.fee_table = fee_table
        self.rate = rate
        self.reports: list[DayReport] = []
        self._accruals: dict[str, dict[int, Decimal]] = {a: {} for a in ledger.accounts}

    # ----- driver ----------------------------------------------------------

    def run(self) -> list[DayReport]:
        for day in range(1, self.window_days + 1):
            self.run_day(day)
        return self.reports

    def run_day(self, day: int) -> DayReport:
        report = DayReport(day)
        errors_before = len(self.ledger.errors)
        report.processed = self.run_events(day)
        report.fees = self.end_of_day_fees(day)
        report.accruals = self.end_of_day_accrual(day)
        if day == self.window_days:
            report.interest = self.capitalize_interest(day)
        for acct in self.ledger.accounts:
            report.closing[acct] = self.ledger.balance(acct, day, as_of_posting_day=day)
            report.available[acct] = self.ledger.available(acct, day)
        report.auth_states = {a.auth_id: self.ledger.auth_state(a.auth_id) for a in self.ledger.auths}
        report.errors = list(self.ledger.errors[errors_before:])
        self.reports.append(report)
        return report

    def run_events(self, day: int) -> list[str]:
        lines = []
        for ev in self.events:
            if ev.posting_day == day:
                lines.append(self.apply(ev))
        return lines

    # ----- event application --------------------------------------------------

    def apply(self, ev: Event) -> str:
        if isinstance(ev, Credit):
            return self._credit(ev)
        if isinstance(ev, Debit):
            return self._debit(ev)
        if isinstance(ev, Authorization):
            return self._authorize(ev)
        if isinstance(ev, Settlement):
            return self._settle(ev)
        if isinstance(ev, Reversal):
            return self._reverse(ev)
        raise TypeError(f"unknown event type {type(ev).__name__}")

    def _credit(self, ev: Credit) -> str:
        ccy = self.ledger.currency(ev.account)
        parts = split_equal(ev.amount, ev.instalments, ccy)
        for i, part in enumerate(parts, 1):
            memo = f"instalment {i}/{len(parts)}" if len(parts) > 1 else ""
            self.ledger.append_entry(ev.account, Kind.CREDIT, part, ev.value_date, ev.posting_day, ev.id, memo=memo)
        detail = " + ".join(str(p) for p in parts) if len(parts) > 1 else str(parts[0])
        return f"{ev.id} CREDIT {ev.account} {ccy} {detail} value_date Day {ev.value_date} -> POSTED"

    def _debit(self, ev: Debit) -> str:
        # Debits are never declined: they are cleared items. Going negative is
        # what the overdraft fee is for. (Authorizations are the gate, not debits.)
        ccy = self.ledger.currency(ev.account)
        self.ledger.append_entry(ev.account, Kind.DEBIT, -ev.amount, ev.value_date, ev.posting_day, ev.id)
        tag = " (BACKDATED)" if ev.value_date < ev.posting_day else ""
        return f"{ev.id} DEBIT {ev.account} {ccy} {ev.amount} value_date Day {ev.value_date}{tag} -> POSTED"

    def _authorize(self, ev: Authorization) -> str:
        if self.ledger.auth(ev.auth_id) is not None:
            self.ledger.append_error(ev.posting_day, ev.id, "DUPLICATE_AUTH",
                                     f"authorization id {ev.auth_id} already exists")
            return f"{ev.id} AUTHORIZATION {ev.auth_id} -> REJECTED (duplicate id)"
        before = self.ledger.available(ev.account, ev.posting_day)
        after = before - ev.amount
        decision = Decision.APPROVED if after >= 0 else Decision.DECLINED
        self.ledger.append_auth(ev.auth_id, ev.account, ev.amount, ev.value_date, ev.posting_day,
                                ev.id, decision, before, after)
        return (f"{ev.id} AUTHORIZATION {ev.auth_id} hold {ev.amount} on {ev.account} "
                f"(available {before} -> {after}) -> {decision.value}")

    def _settle(self, ev: Settlement) -> str:
        auth = self.ledger.auth(ev.auth_id)
        if auth is None or auth.decision is not Decision.APPROVED:
            why = "no such authorization" if auth is None else "authorization was declined"
            self.ledger.append_error(ev.posting_day, ev.id, "NO_AUTH",
                                     f"settlement of {ev.auth_id} for {ev.amount}: {why}; "
                                     f"rejected, no funds moved")
            return f"{ev.id} SETTLEMENT {ev.auth_id} {ev.amount} -> REJECTED ({why})"
        if self.ledger.settlement_of(ev.auth_id) is not None:
            self.ledger.append_error(ev.posting_day, ev.id, "ALREADY_SETTLED",
                                     f"{ev.auth_id} already settled; rejected")
            return f"{ev.id} SETTLEMENT {ev.auth_id} {ev.amount} -> REJECTED (already settled)"
        self.ledger.append_entry(ev.account, Kind.SETTLEMENT, -ev.amount, ev.value_date,
                                 ev.posting_day, ev.id, ref=ev.auth_id)
        note = ""
        if ev.amount > auth.amount:
            self.ledger.append_error(ev.posting_day, ev.id, "OVER_SETTLEMENT",
                                     f"{ev.auth_id} settled {ev.amount} against a {auth.amount} hold",
                                     Severity.WARNING)
            note = " (over hold, flagged)"
        return (f"{ev.id} SETTLEMENT {ev.auth_id} settles {ev.amount} against hold {auth.amount}"
                f" -> POSTED, hold released{note}")

    def _reverse(self, ev: Reversal) -> str:
        targets = self.ledger.entries_for_event(ev.target_event_id)
        if not targets:
            self.ledger.append_error(ev.posting_day, ev.id, "NO_TARGET",
                                     f"nothing posted for {ev.target_event_id}; reversal rejected")
            return f"{ev.id} REVERSAL of {ev.target_event_id} -> REJECTED (no such posting)"
        if any(t.kind is Kind.REVERSAL for t in targets):
            self.ledger.append_error(ev.posting_day, ev.id, "REVERSAL_OF_REVERSAL",
                                     f"{ev.target_event_id} is itself a reversal; rejected")
            return f"{ev.id} REVERSAL of {ev.target_event_id} -> REJECTED (reversal of a reversal)"
        if self.ledger.reversals_of(ev.target_event_id):
            self.ledger.append_error(ev.posting_day, ev.id, "ALREADY_REVERSED",
                                     f"{ev.target_event_id} already reversed; rejected")
            return f"{ev.id} REVERSAL of {ev.target_event_id} -> REJECTED (already reversed)"
        if any(t.value_date != ev.value_date for t in targets):
            self.ledger.append_error(ev.posting_day, ev.id, "VALUE_DATE_MISMATCH",
                                     f"reversal value_date {ev.value_date} != target's; rejected")
            return f"{ev.id} REVERSAL of {ev.target_event_id} -> REJECTED (value_date mismatch)"
        total = zero(self.ledger.currency(ev.account))
        for t in targets:
            self.ledger.append_entry(t.account, Kind.REVERSAL, -t.amount, t.value_date,
                                     ev.posting_day, ev.id, ref=ev.target_event_id)
            total += -t.amount
        return (f"{ev.id} REVERSAL of {ev.target_event_id}: {total:+} value_date Day {ev.value_date}"
                f" (BACKDATED) -> POSTED" if ev.value_date < ev.posting_day else
                f"{ev.id} REVERSAL of {ev.target_event_id}: {total:+} value_date Day {ev.value_date} -> POSTED")

    # ----- end of day -----------------------------------------------------------

    def end_of_day_fees(self, day: int) -> list[Entry]:
        booked = []
        for acct, ccy in self.ledger.accounts.items():
            if self.ledger.fee_for(acct, day) is not None:
                continue
            if self.ledger.balance(acct, day, as_of_posting_day=day) < 0:
                fee = self.fee_table.get(ccy)
                if fee is None:
                    self.ledger.append_error(day, f"EOD-{day}", "FEE_NOT_CONFIGURED",
                                             f"{acct} overdrawn on Day {day} but no {ccy} fee configured")
                    continue
                booked.append(self.ledger.append_entry(
                    acct, Kind.FEE, -fee, day, day, None, ref=f"overdraft:{day}",
                    memo=f"overdraft fee for Day {day}"))
        return booked

    def end_of_day_accrual(self, day: int) -> dict[str, Decimal]:
        out = {}
        for acct, ccy in self.ledger.accounts.items():
            bal = self.ledger.balance(acct, day, as_of_posting_day=day)
            acc = quantize(bal * self.rate, ccy) if bal > 0 else zero(ccy)
            self._accruals[acct][day] = acc
            out[acct] = acc
        return out

    def capitalize_interest(self, day: int) -> list[Entry]:
        booked = []
        for acct, ccy in self.ledger.accounts.items():
            total = sum(self._accruals[acct].values(), zero(ccy))
            if total:
                booked.append(self.ledger.append_entry(
                    acct, Kind.INTEREST, total, day, day, None, ref=f"interest:{day}",
                    memo=f"capitalised daily interest Days 1-{day}"))
        return booked

    def accrual_schedule(self, acct: str) -> dict[int, Decimal]:
        return dict(self._accruals[acct])
