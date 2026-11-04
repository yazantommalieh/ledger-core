"""Input events — what the outside world tells the ledger.

Each event carries two dates:

* ``posting_day`` — the day the ledger *learns* about it (the day it sits in
  the stream). Events are replayed in stream order, grouped by posting day.
* ``value_date`` — the day the event is *effective* for balance purposes.

They usually coincide. When they don't (E7: posted Day 5, value Day 2) the
event is *backdated* and rewrites history as seen by value date. That one
distinction is the whole problem.

Events are frozen: the stream is an immutable input, never edited.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Event:
    id: str
    posting_day: int
    account: str


@dataclass(frozen=True)
class Credit(Event):
    amount: Decimal
    value_date: int
    instalments: int = 1  # >1 means "post as N equal instalments" (E10)


@dataclass(frozen=True)
class Debit(Event):
    amount: Decimal
    value_date: int


@dataclass(frozen=True)
class Authorization(Event):
    auth_id: str
    amount: Decimal  # hold amount
    value_date: int


@dataclass(frozen=True)
class Settlement(Event):
    auth_id: str
    amount: Decimal  # may differ from the hold (E5: 185 against a 200 hold)
    value_date: int


@dataclass(frozen=True)
class Reversal(Event):
    target_event_id: str
    value_date: int  # the stream states it; the ledger checks it matches the target
