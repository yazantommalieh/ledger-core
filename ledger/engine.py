"""Replay engine: applies the event stream day by day and runs end-of-day.

Each day: apply that day's events in stream order, then run the close:

1. overdraft fees — re-assessed for every day up to today against the ledger
   as known now (backdated entries can turn an already-closed day negative);
2. on the last day, interest — the daily accrual schedule is derived from the
   final value-dated history and capitalised as one credit.

Nothing in the engine holds state of its own beyond the reports it emits;
everything it needs is a query on the ledger. That is deliberate: a cached
running balance or a stored per-day accrual is exactly the kind of state a
backdated entry silently invalidates (engine v1 did both — see REJECTED.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .events import Authorization, Credit, Debit, Event, Reversal, Settlement
from .ledger import Decision, Entry, Kind, Ledger, LedgerError, Severity
from .money import is_exact, quantize, split_equal, zero

# Overdraft fee per currency. Only AED is specified by the assignment.
OVERDRAFT_FEE: dict[str, Decimal] = {"AED": Decimal("25.00")}

# 0.04% per day, as a fraction.
DAILY_INTEREST_RATE = Decimal("0.0004")


@dataclass
class DayReport:
    day: int
    is_last: bool = False
    processed: list[str] = field(default_factory=list)   # one line per event
    fees: list[Entry] = field(default_factory=list)
    restated: dict[str, dict[int, tuple[Decimal, Decimal]]] = field(default_factory=dict)
    accrued_to_date: dict[str, Decimal] = field(default_factory=dict)   # provisional
    interest_schedule: dict[str, dict[int, tuple[Decimal, Decimal]]] = field(default_factory=dict)
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
        self._seen_event_ids: set[str] = set()

    # ----- driver ----------------------------------------------------------

    def run(self) -> list[DayReport]:
        for day in range(1, self.window_days + 1):
            self.run_day(day)
        return self.reports

    def run_day(self, day: int) -> DayReport:
        report = DayReport(day, is_last=(day == self.window_days))
        errors_before = len(self.ledger.errors)
        before = {acct: {k: self.ledger.balance(acct, k, as_of_posting_day=day - 1) for k in range(1, day)}
                  for acct in self.ledger.accounts}
        report.processed = self.run_events(day)
        report.fees = self.end_of_day_fees(day)
        for acct in self.ledger.accounts:
            after = {k: self.ledger.balance(acct, k, as_of_posting_day=day) for k in range(1, day)}
            diff = {k: (before[acct][k], after[k]) for k in after if after[k] != before[acct][k]}
            if diff:
                report.restated[acct] = diff
            report.accrued_to_date[acct] = sum(
                (acc for _, acc in self.interest_schedule(acct, day).values()), zero(self.ledger.currency(acct)))
        if day == self.window_days:
            for acct in self.ledger.accounts:
                report.interest_schedule[acct] = self.interest_schedule(acct, day)
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
        # Every monetary amount on an input event must already be at the account's
        # precision. Over-precise input is an upstream bug, not something to round
        # quietly (AMBIGUITIES.md §21). Checked here, once, for all event types —
        # the store checks entries too, but holds are not entries, and credits
        # pass through split_equal, which would otherwise round for them.
        amount = getattr(ev, "amount", None)
        if amount is not None and not is_exact(amount, self.ledger.currency(ev.account)):
            raise LedgerError(f"{ev.id}: {amount} is not at {self.ledger.currency(ev.account)} precision")
        # Amounts are magnitudes; direction comes from the event type. A negative
        # credit is a debit in disguise and a zero posting is noise, so both are
        # structural errors in the stream, like a duplicate event id.
        if amount is not None and amount <= 0:
            raise LedgerError(f"{ev.id}: amount must be positive, got {amount}")
        if ev.id in self._seen_event_ids:
            raise LedgerError(f"duplicate event id {ev.id}")
        self._seen_event_ids.add(ev.id)
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
        if auth.account != ev.account:
            self.ledger.append_error(ev.posting_day, ev.id, "ACCOUNT_MISMATCH",
                                     f"settlement names {ev.account} but {ev.auth_id} was authorized on "
                                     f"{auth.account}; rejected")
            return f"{ev.id} SETTLEMENT {ev.auth_id} {ev.amount} -> REJECTED (account mismatch)"
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
        if any(t.account != ev.account for t in targets):
            self.ledger.append_error(ev.posting_day, ev.id, "ACCOUNT_MISMATCH",
                                     f"reversal names {ev.account} but {ev.target_event_id} posted to "
                                     f"{targets[0].account}; rejected")
            return f"{ev.id} REVERSAL of {ev.target_event_id} -> REJECTED (account mismatch)"
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
        """Re-assess the overdraft fee for every day up to and including today.

        A backdated entry can turn an earlier day's close negative after that
        day has already been closed. The rule is defined on "that day's closing
        ledger balance (all entries with value_date <= that day)", so the only
        faithful implementation is to re-evaluate every past day against the
        ledger as known *now* and book the fee for any day that is negative and
        not yet fee'd. Days are walked in ascending order so a fee booked for
        Day 2 (value_date 2) is already in the balance when Day 3 is examined —
        the cascade is real and intended.

        Once-per-day-per-account is the ``fee_for`` lookup, which makes the
        whole routine idempotent: running it twice books nothing new.
        """
        booked = []
        for assessed_day in range(1, day + 1):
            for acct, ccy in self.ledger.accounts.items():
                if self.ledger.fee_for(acct, assessed_day) is not None:
                    continue
                if self.ledger.balance(acct, assessed_day, as_of_posting_day=day) >= 0:
                    continue
                fee = self.fee_table.get(ccy)
                if fee is None:
                    # Once per (account, assessed day), like the fee it stands in for;
                    # otherwise every later close re-reports the same overdraft.
                    marker = f"FEE:{acct}:D{assessed_day}"
                    if not any(e.event_id == marker for e in self.ledger.errors):
                        self.ledger.append_error(day, marker, "FEE_NOT_CONFIGURED",
                                                 f"{acct} overdrawn on Day {assessed_day} but no {ccy} fee configured")
                    continue
                booked.append(self.ledger.append_entry(
                    acct, Kind.FEE, -fee, value_date=assessed_day, posting_day=day,
                    origin_event=None, ref=f"overdraft:{assessed_day}",
                    memo=f"overdraft fee for Day {assessed_day}, assessed in Day {day} close"))
        return booked

    def interest_schedule(self, acct: str, upto_day: int) -> dict[int, tuple[Decimal, Decimal]]:
        """Day -> (closing balance, rounded accrual), derived from the ledger as
        known at the end of ``upto_day``. Accrues only on positive balances.
        Computed on demand, never stored: after a backdated entry the schedule
        for earlier days changes, and that is the correct behaviour.
        """
        ccy = self.ledger.currency(acct)
        out = {}
        for k in range(1, upto_day + 1):
            bal = self.ledger.balance(acct, k, as_of_posting_day=upto_day)
            # Day k's accrual is on day k's close *before* any interest capitalised
            # on day k: that credit is the result of the schedule, not an input to
            # it. Subtracting it here makes the schedule stable whether it is asked
            # for before or after capitalisation. Interest capitalised on an earlier
            # day is ordinary balance and does earn (there is none in this window).
            for e in self.ledger.entries_of_kind(Kind.INTEREST, acct):
                if e.value_date == k and e.posting_day <= upto_day:
                    bal -= e.amount
            acc = quantize(bal * self.rate, ccy) if bal > 0 else zero(ccy)
            out[k] = (bal, acc)
        return out

    def capitalize_interest(self, day: int) -> list[Entry]:
        """Book one INTEREST credit per account equal to the *sum of the rounded
        daily accruals*. Equality with the schedule is therefore structural,
        not something that needs a remainder rule (criterion 8 is rejected on
        exactly this point — there is no remainder to discard).

        The accrual for ``day`` itself is taken on ``day``'s closing balance
        before this credit lands; the credit has value_date ``day`` and is not
        considered by the overdraft check, which ran before it.
        """
        booked = []
        for acct, ccy in self.ledger.accounts.items():
            if any(e.ref == f"interest:{day}" for e in self.ledger.entries_of_kind(Kind.INTEREST, acct)):
                continue  # already capitalised for this day: idempotent, like the fee run
            schedule = self.interest_schedule(acct, day)
            total = sum((acc for _, acc in schedule.values()), zero(ccy))
            assert total == quantize(total, ccy)
            if total:
                booked.append(self.ledger.append_entry(
                    acct, Kind.INTEREST, total, day, day, None, ref=f"interest:{day}",
                    memo=f"capitalised daily interest Days 1-{day}"))
        return booked
