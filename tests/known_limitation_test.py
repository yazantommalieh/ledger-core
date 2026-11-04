"""THE ONE FAILING TEST. It is meant to fail, and it must stay red.

It is excluded from the default discovery pattern so that `make test` is green
and `make test-known-limitation` is red on purpose; see README.md.

What it probes
--------------
The ledger is append-only and every *derived* entry (an overdraft fee) is just
another entry with no recorded causal link to the entry that triggered it. So
when the trigger (E7) is reversed (E9), nothing in the design knows that the
three fees E7 caused are now fees for an overdraft that, by value date, never
happened.

Run it with:

    python3 -m unittest tests.known_limitation_test
"""
import unittest
from decimal import Decimal as D

from ledger.engine import Engine
from ledger.ledger import Kind, Ledger
from ledger.scenario import ACCOUNTS, EVENTS, WINDOW_DAYS


class ReversalShouldUnwindWhatItCaused(unittest.TestCase):
    """Fails by design. See the annotations on each assertion."""

    def test_reversing_the_cause_unwinds_its_consequences(self):
        eng = Engine(Ledger(ACCOUNTS), EVENTS, WINDOW_DAYS)
        eng.run()
        lg = eng.ledger

        # After E9, every day from Day 2 onward is positive again by value date.
        # So by the fee rule's own definition ("that day's closing ledger balance
        # ... is negative") Days 2, 4 and 5 are no longer overdraft days.
        for day in (2, 4, 5):
            self.assertGreater(lg.balance("ACC-001", day), 0)

        # 1) WHAT FAILS: the three fees are still charged.
        #    WHAT IT REVEALS: "once per day per account" is implemented as a
        #    one-way latch (fee_for(account, day) is not None). The assessment
        #    can add a fee when a day turns negative, but has no symmetric step
        #    for a day that turns positive again. The design has no concept of a
        #    fee being *wrong*, only of it being *present*.
        fees = lg.entries_of_kind(Kind.FEE, "ACC-001")
        self.assertEqual(len(fees), 0, f"fees still booked for days {[f.value_date for f in fees]}")

        # 2) WHAT FAILS: the customer is AED 75.10 poorer than the transactions
        #    alone justify (390.93 vs 466.03 — the extra 0.10 is the interest the
        #    75.00 would have earned: schedule 0.10/0.10/0.26/0.19/0.19/0.19 = 1.03).
        #    WHAT IT REVEALS: in an append-only ledger the only honest fix is a
        #    compensating FEE_REVERSAL entry per fee, booked when a re-assessment
        #    finds an existing fee whose day is no longer negative. That needs
        #    (a) a causal ref from fee -> triggering day so the reversal can be
        #    targeted, and (b) a decision about whether fee reversals are
        #    automatic or a human/ops action. Neither exists here. This is the
        #    thing that makes criterion 6 *almost* right: the intent (undo the
        #    damage) is sound; the mechanism ("values return") is not available
        #    in an append-only log.
        self.assertEqual(lg.balance("ACC-001", 6), D("466.03"))

        # 3) WHAT FAILS: Auth-B stays DECLINED although, by value date, there
        #    was AED 465.00 available when it was asked.
        #    WHAT IT REVEALS: authorizations are point-in-time decisions made on
        #    the ledger as known at that moment, and the design does not revisit
        #    them. That is the right call for a card network (the merchant got
        #    a decline and moved on), but it means a backdated error is not
        #    fully harmless to the customer even after it is reversed.
        self.assertEqual(lg.auth_state("Auth-B"), "ACTIVE")


if __name__ == "__main__":
    unittest.main()
