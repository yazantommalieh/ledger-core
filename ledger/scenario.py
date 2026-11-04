"""The assignment's accounts and event stream, as data.

Stream order is the replay order. ``posting_day`` is the "Day N" the event is
booked on; ``value_date`` is the day it is effective. E7 and E9 are backdated.
E10 is one event that posts as three instalments.
"""
from decimal import Decimal as D

from .events import Authorization, Credit, Debit, Reversal, Settlement

WINDOW_DAYS = 6

ACCOUNTS = {
    "ACC-001": "AED",  # opening 0.00
    "ACC-002": "BHD",  # opening 0.000
}

EVENTS = [
    Credit("E1", posting_day=1, account="ACC-001", amount=D("1200.00"), value_date=1),
    Debit("E2", posting_day=1, account="ACC-001", amount=D("950.00"), value_date=1),
    Authorization("E3", posting_day=2, account="ACC-001", auth_id="Auth-A", amount=D("200.00"), value_date=2),
    Credit("E4", posting_day=3, account="ACC-001", amount=D("400.00"), value_date=3),
    Settlement("E5", posting_day=4, account="ACC-001", auth_id="Auth-A", amount=D("185.00"), value_date=4),
    Settlement("E6", posting_day=4, account="ACC-001", auth_id="Auth-Z", amount=D("180.00"), value_date=4),
    Debit("E7", posting_day=5, account="ACC-001", amount=D("620.00"), value_date=2),       # backdated
    Authorization("E8", posting_day=5, account="ACC-001", auth_id="Auth-B", amount=D("90.00"), value_date=5),
    Reversal("E9", posting_day=6, account="ACC-001", target_event_id="E7", value_date=2),   # backdated
    Credit("E10", posting_day=5, account="ACC-002", amount=D("10.000"), value_date=5, instalments=3),
]
