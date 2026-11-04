"""The append-only ledger store and the queries that derive state from it.

Three logs, all append-only, all made of frozen records:

* ``entries`` — monetary postings (credits, debits, settlements, reversals,
  fees, interest). A posting has a signed ``amount``, a ``value_date`` and a
  ``posting_day``. Balances are *sums over entries*, filtered by value date and
  optionally by "as known at" posting day. Nothing caches a running balance.
* ``auths`` — authorization decisions (APPROVED or DECLINED), one record per
  authorization event. Whether a hold is still *active* is derived: an
  approved auth with no settlement entry referencing it.
* ``errors`` — rejected or flagged events. Rejection is itself a record.

There is no update or delete anywhere in this module. "Fixing" anything means
appending a compensating record. That is what makes E9 a *reversal entry*
rather than the removal of E7, and it is why the fees E7 triggered do not
vanish when E7 is reversed (see REJECTED.md, criterion 6).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable

from .money import quantize, zero


class Kind(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    SETTLEMENT = "SETTLEMENT"
    REVERSAL = "REVERSAL"
    FEE = "FEE"
    INTEREST = "INTEREST"


class Decision(str, Enum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class Severity(str, Enum):
    ERROR = "error"      # event rejected, nothing posted
    WARNING = "warning"  # event posted, but something is off and is recorded


@dataclass(frozen=True)
class Entry:
    seq: int                 # position in the log, 1-based, never reused
    account: str
    kind: Kind
    amount: Decimal          # signed: credits > 0, debits < 0
    currency: str
    value_date: int
    posting_day: int
    origin_event: str | None # event id that caused this entry (None for system entries)
    ref: str | None = None   # auth_id for settlements, reversed event id for reversals,
                             # "overdraft:<day>" for fees, "interest:<day>" for capitalisation
    memo: str = ""


@dataclass(frozen=True)
class AuthRecord:
    seq: int
    auth_id: str
    account: str
    amount: Decimal
    currency: str
    value_date: int
    posting_day: int
    origin_event: str
    decision: Decision
    available_before: Decimal
    available_after: Decimal  # what available would be / is after the hold


@dataclass(frozen=True)
class ErrorRecord:
    seq: int
    posting_day: int
    event_id: str
    code: str
    message: str
    severity: Severity = Severity.ERROR


class LedgerError(Exception):
    """Raised for programming errors (unknown account, wrong precision), never for
    business rejections — those are appended as ErrorRecords."""


class Ledger:
    """Append-only store. Public attributes are tuples (snapshots); the only
    way in is through the ``append_*`` methods."""

    def __init__(self, accounts: dict[str, str]):
        # account id -> currency code. Opening balances are 0 in every case in
        # scope; a non-zero opening balance would be an ordinary CREDIT entry
        # with value_date 0.
        self._accounts = dict(accounts)
        self._entries: list[Entry] = []
        self._auths: list[AuthRecord] = []
        self._errors: list[ErrorRecord] = []
        self._seq = 0

    # ----- identity -------------------------------------------------------

    @property
    def accounts(self) -> dict[str, str]:
        return dict(self._accounts)

    def currency(self, account: str) -> str:
        try:
            return self._accounts[account]
        except KeyError as exc:
            raise LedgerError(f"unknown account {account}") from exc

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # ----- appends (the only writes) ---------------------------------------

    def append_entry(self, account: str, kind: Kind, amount: Decimal, value_date: int,
                     posting_day: int, origin_event: str | None, ref: str | None = None,
                     memo: str = "") -> Entry:
        currency = self.currency(account)
        if amount != quantize(amount, currency):
            raise LedgerError(f"{amount} is not at {currency} precision")
        if value_date > posting_day:
            # Future-dated postings are out of scope for this exercise; refusing
            # them keeps "balance as of day d" unambiguous. See AMBIGUITIES.md.
            raise LedgerError(f"value_date {value_date} after posting_day {posting_day}")
        entry = Entry(self._next_seq(), account, kind, quantize(amount, currency), currency,
                      value_date, posting_day, origin_event, ref, memo)
        self._entries.append(entry)
        return entry

    def append_auth(self, auth_id: str, account: str, amount: Decimal, value_date: int,
                    posting_day: int, origin_event: str, decision: Decision,
                    available_before: Decimal, available_after: Decimal) -> AuthRecord:
        rec = AuthRecord(self._next_seq(), auth_id, account, amount, self.currency(account),
                         value_date, posting_day, origin_event, decision,
                         available_before, available_after)
        self._auths.append(rec)
        return rec

    def append_error(self, posting_day: int, event_id: str, code: str, message: str,
                     severity: Severity = Severity.ERROR) -> ErrorRecord:
        rec = ErrorRecord(self._next_seq(), posting_day, event_id, code, message, severity)
        self._errors.append(rec)
        return rec

    # ----- read-only views --------------------------------------------------

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries)

    @property
    def auths(self) -> tuple[AuthRecord, ...]:
        return tuple(self._auths)

    @property
    def errors(self) -> tuple[ErrorRecord, ...]:
        return tuple(self._errors)

    # ----- balance queries ------------------------------------------------

    def _visible(self, account: str, value_date_upto: int,
                 as_of_posting_day: int | None) -> Iterable[Entry]:
        for e in self._entries:
            if e.account != account or e.value_date > value_date_upto:
                continue
            if as_of_posting_day is not None and e.posting_day > as_of_posting_day:
                continue
            yield e

    def balance(self, account: str, value_date_upto: int,
                as_of_posting_day: int | None = None) -> Decimal:
        """Closing ledger balance for ``value_date_upto``: the sum of every
        entry with value_date <= that day.

        ``as_of_posting_day`` restricts the view to what the ledger *knew* at
        the end of that posting day. ``balance("ACC-001", 2)`` is the Day 2
        balance as finally restated; ``balance("ACC-001", 2, as_of_posting_day=2)``
        is what the Day 2 close actually showed at the time. They differ once a
        backdated entry lands (E7).
        """
        total = zero(self.currency(account))
        for e in self._visible(account, value_date_upto, as_of_posting_day):
            total += e.amount
        return total

    def entries_for_event(self, event_id: str) -> tuple[Entry, ...]:
        return tuple(e for e in self._entries if e.origin_event == event_id)

    def reversals_of(self, event_id: str) -> tuple[Entry, ...]:
        return tuple(e for e in self._entries if e.kind is Kind.REVERSAL and e.ref == event_id)

    # ----- authorizations / holds --------------------------------------------

    def auth(self, auth_id: str) -> AuthRecord | None:
        for a in self._auths:
            if a.auth_id == auth_id:
                return a
        return None

    def settlement_of(self, auth_id: str) -> Entry | None:
        for e in self._entries:
            if e.kind is Kind.SETTLEMENT and e.ref == auth_id:
                return e
        return None

    def auth_state(self, auth_id: str) -> str:
        a = self.auth(auth_id)
        if a is None:
            return "UNKNOWN"
        if a.decision is Decision.DECLINED:
            return "DECLINED"
        return "SETTLED" if self.settlement_of(auth_id) else "ACTIVE"

    def active_holds(self, account: str, as_of_posting_day: int | None = None) -> tuple[AuthRecord, ...]:
        """Approved authorizations with no settlement yet — these reduce
        available balance but never the ledger balance."""
        out = []
        for a in self._auths:
            if a.account != account or a.decision is not Decision.APPROVED:
                continue
            if as_of_posting_day is not None and a.posting_day > as_of_posting_day:
                continue
            s = self.settlement_of(a.auth_id)
            if s is not None and (as_of_posting_day is None or s.posting_day <= as_of_posting_day):
                continue
            out.append(a)
        return tuple(out)

    def held(self, account: str, as_of_posting_day: int | None = None) -> Decimal:
        total = zero(self.currency(account))
        for a in self.active_holds(account, as_of_posting_day):
            total += a.amount
        return total

    def available(self, account: str, day: int) -> Decimal:
        """Available balance on ``day`` = ledger balance (value_date <= day, as
        known on ``day``) minus active holds. This is the authorization test."""
        return self.balance(account, day, as_of_posting_day=day) - self.held(account, day)

    # ----- fees / interest -----------------------------------------------------

    def fee_for(self, account: str, day: int) -> Entry | None:
        """The overdraft fee assessed *for* ``day`` (its value_date), if any.
        'Once per day per account' is enforced by this lookup."""
        for e in self._entries:
            if e.account == account and e.kind is Kind.FEE and e.value_date == day:
                return e
        return None

    def entries_of_kind(self, kind: Kind, account: str | None = None) -> tuple[Entry, ...]:
        return tuple(e for e in self._entries
                     if e.kind is kind and (account is None or e.account == account))
