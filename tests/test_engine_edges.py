"""Engine behaviour on inputs the assignment's stream does not exercise."""
import unittest
from decimal import Decimal as D

from ledger.engine import Engine
from ledger.events import Authorization, Credit, Debit, Reversal, Settlement
from ledger.ledger import Kind, Ledger, Severity


def engine(events, days=3, accounts=None):
    return Engine(Ledger(accounts or {"A": "AED", "B": "BHD"}), events, days)


class RejectionPaths(unittest.TestCase):
    def test_settlement_of_declined_auth_rejected(self):
        eng = engine([
            Authorization("a1", 1, "A", auth_id="X", amount=D("10.00"), value_date=1),   # declined: balance 0
            Settlement("s1", 2, "A", auth_id="X", amount=D("10.00"), value_date=2),
        ])
        eng.run()
        self.assertEqual(eng.ledger.auth_state("X"), "DECLINED")
        self.assertEqual([e.code for e in eng.ledger.errors], ["NO_AUTH"])
        self.assertEqual(eng.ledger.balance("A", 3), D("0.00"))

    def test_double_settlement_rejected(self):
        eng = engine([
            Credit("c", 1, "A", amount=D("100.00"), value_date=1),
            Authorization("a1", 1, "A", auth_id="X", amount=D("10.00"), value_date=1),
            Settlement("s1", 2, "A", auth_id="X", amount=D("10.00"), value_date=2),
            Settlement("s2", 2, "A", auth_id="X", amount=D("10.00"), value_date=2),
        ])
        eng.run()
        self.assertEqual([e.code for e in eng.ledger.errors], ["ALREADY_SETTLED"])
        self.assertEqual(eng.ledger.balance("A", 2), D("90.00"))  # Day 2: before Day-3 interest lands

    def test_duplicate_auth_id_rejected(self):
        eng = engine([
            Credit("c", 1, "A", amount=D("100.00"), value_date=1),
            Authorization("a1", 1, "A", auth_id="X", amount=D("10.00"), value_date=1),
            Authorization("a2", 1, "A", auth_id="X", amount=D("10.00"), value_date=1),
        ])
        eng.run()
        self.assertEqual([e.code for e in eng.ledger.errors], ["DUPLICATE_AUTH"])
        self.assertEqual(eng.ledger.held("A"), D("10.00"))

    def test_over_settlement_posts_but_is_flagged(self):
        eng = engine([
            Credit("c", 1, "A", amount=D("100.00"), value_date=1),
            Authorization("a1", 1, "A", auth_id="X", amount=D("10.00"), value_date=1),
            Settlement("s1", 2, "A", auth_id="X", amount=D("12.00"), value_date=2),
        ])
        eng.run()
        self.assertEqual(eng.ledger.balance("A", 2), D("88.00"))  # Day 2: before Day-3 interest lands
        w = eng.ledger.errors[0]
        self.assertEqual((w.code, w.severity), ("OVER_SETTLEMENT", Severity.WARNING))

    def test_reversal_of_unknown_event_rejected(self):
        eng = engine([Reversal("r", 1, "A", target_event_id="nope", value_date=1)])
        eng.run()
        self.assertEqual([e.code for e in eng.ledger.errors], ["NO_TARGET"])

    def test_reversal_twice_rejected(self):
        eng = engine([
            Credit("c", 1, "A", amount=D("5.00"), value_date=1),
            Reversal("r1", 2, "A", target_event_id="c", value_date=1),
            Reversal("r2", 2, "A", target_event_id="c", value_date=1),
        ])
        eng.run()
        self.assertEqual([e.code for e in eng.ledger.errors], ["ALREADY_REVERSED"])
        self.assertEqual(eng.ledger.balance("A", 3), D("0.00"))

    def test_reversal_of_a_reversal_rejected(self):
        eng = engine([
            Credit("c", 1, "A", amount=D("5.00"), value_date=1),
            Reversal("r1", 2, "A", target_event_id="c", value_date=1),
            Reversal("r2", 3, "A", target_event_id="r1", value_date=1),
        ])
        eng.run()
        self.assertEqual([e.code for e in eng.ledger.errors], ["REVERSAL_OF_REVERSAL"])

    def test_reversal_with_wrong_value_date_rejected(self):
        eng = engine([
            Debit("d", 1, "A", amount=D("5.00"), value_date=1),
            Reversal("r1", 2, "A", target_event_id="d", value_date=2),
        ])
        eng.run()
        self.assertEqual([e.code for e in eng.ledger.errors], ["VALUE_DATE_MISMATCH"])

    def test_reversal_of_instalment_credit_reverses_every_part(self):
        eng = engine([
            Credit("c", 1, "B", amount=D("10.000"), value_date=1, instalments=3),
            Reversal("r", 2, "B", target_event_id="c", value_date=1),
        ])
        eng.run()
        self.assertEqual(len(eng.ledger.reversals_of("c")), 3)
        self.assertEqual(eng.ledger.balance("B", 3), D("0.000"))


class FeeRules(unittest.TestCase):
    def test_zero_balance_is_not_overdrawn(self):
        eng = engine([Credit("c", 1, "A", amount=D("5.00"), value_date=1),
                      Debit("d", 1, "A", amount=D("5.00"), value_date=1)])
        eng.run()
        self.assertEqual(eng.ledger.entries_of_kind(Kind.FEE), ())

    def test_fee_once_per_day_even_if_still_negative_next_close(self):
        eng = engine([Debit("d", 1, "A", amount=D("5.00"), value_date=1)], days=3)
        eng.run()
        fees = eng.ledger.entries_of_kind(Kind.FEE, "A")
        self.assertEqual([f.value_date for f in fees], [1, 2, 3])   # one per day, not one per close per day
        self.assertEqual(eng.ledger.balance("A", 3), D("-80.00"))

    def test_fee_for_unconfigured_currency_is_an_error_not_a_guess(self):
        eng = engine([Debit("d", 1, "B", amount=D("1.000"), value_date=1)], days=1)
        eng.run()
        self.assertEqual(eng.ledger.entries_of_kind(Kind.FEE), ())
        self.assertEqual([e.code for e in eng.ledger.errors], ["FEE_NOT_CONFIGURED"])

    def test_backdated_credit_can_retract_nothing(self):
        # A backdated credit that makes a day positive after a fee was booked does not
        # remove the fee: once-per-day is one way. (Same property as E9 — see the
        # failing test in known_limitation_test.py for the design question this raises.)
        eng = engine([
            Debit("d", 1, "A", amount=D("5.00"), value_date=1),
            Credit("c", 2, "A", amount=D("100.00"), value_date=1),
        ], days=2)
        eng.run()
        self.assertEqual(eng.ledger.balance("A", 1), D("70.00"))
        self.assertEqual(len(eng.ledger.entries_of_kind(Kind.FEE)), 1)


class InterestRules(unittest.TestCase):
    def test_interest_only_on_positive_days(self):
        eng = engine([Credit("c", 2, "A", amount=D("1000.00"), value_date=2)], days=3)
        eng.run()
        sched = eng.reports[-1].interest_schedule["A"]
        self.assertEqual([str(a) for _, a in sched.values()], ["0.00", "0.40", "0.40"])
        self.assertEqual(eng.ledger.balance("A", 3), D("1000.80"))

    def test_last_day_accrual_excludes_the_capitalisation_itself(self):
        eng = engine([Credit("c", 1, "A", amount=D("1000.00"), value_date=1)], days=1)
        eng.run()
        # 0.04% of 1000 = 0.40; the credit lands after the accrual was taken
        self.assertEqual(eng.ledger.entries_of_kind(Kind.INTEREST)[0].amount, D("0.40"))

    def test_nothing_booked_when_total_is_zero(self):
        eng = engine([], days=2)
        eng.run()
        self.assertEqual(eng.ledger.entries_of_kind(Kind.INTEREST), ())


if __name__ == "__main__":
    unittest.main()


class FoundByReview(unittest.TestCase):
    """Each of these pins a fix for something an independent review of the first
    complete version turned up (WORKLOG.md, 2026-11-04 afternoon)."""

    def test_over_precise_credit_is_refused_not_rounded(self):
        from ledger.ledger import LedgerError
        eng = engine([Credit("c", 1, "A", amount=D("1.005"), value_date=1)], days=1)
        with self.assertRaises(LedgerError):
            eng.run()

    def test_over_precise_hold_is_refused(self):
        from ledger.ledger import LedgerError
        eng = engine([Authorization("a", 1, "A", auth_id="X", amount=D("0.001"), value_date=1)], days=1)
        with self.assertRaises(LedgerError):
            eng.run()

    def test_unconfigured_fee_error_is_once_per_day_not_once_per_close(self):
        eng = engine([Debit("d", 1, "B", amount=D("1.000"), value_date=1)], days=3)
        eng.run()
        codes = [e.code for e in eng.ledger.errors]
        self.assertEqual(codes, ["FEE_NOT_CONFIGURED"] * 3)      # Days 1, 2, 3 — not 1+2+3 = 6
        self.assertEqual(len({e.event_id for e in eng.ledger.errors}), 3)

    def test_capitalisation_is_idempotent(self):
        eng = engine([Credit("c", 1, "A", amount=D("1000.00"), value_date=1)], days=1)
        eng.run()
        self.assertEqual(eng.capitalize_interest(1), [])
        self.assertEqual(len(eng.ledger.entries_of_kind(Kind.INTEREST)), 1)

    def test_schedule_is_the_same_before_and_after_capitalisation(self):
        eng = engine([Credit("c", 1, "A", amount=D("1000.00"), value_date=1)], days=1)
        eng.run_events(1)
        eng.end_of_day_fees(1)
        before = eng.interest_schedule("A", 1)
        eng.capitalize_interest(1)
        self.assertEqual(eng.interest_schedule("A", 1), before)
        self.assertEqual(before[1], (D("1000.00"), D("0.40")))

    def test_reversal_naming_the_wrong_account_is_rejected(self):
        eng = engine([
            Credit("c", 1, "A", amount=D("5.00"), value_date=1),
            Reversal("r", 2, "B", target_event_id="c", value_date=1),
        ])
        eng.run()
        self.assertEqual([e.code for e in eng.ledger.errors], ["ACCOUNT_MISMATCH"])
        self.assertEqual(eng.ledger.reversals_of("c"), ())

    def test_reversed_settlement_returns_funds_but_does_not_reinstate_the_hold(self):
        # Documented design gap, pinned so it cannot change silently (AMBIGUITIES.md §29).
        eng = engine([
            Credit("c", 1, "A", amount=D("100.00"), value_date=1),
            Authorization("a", 1, "A", auth_id="X", amount=D("10.00"), value_date=1),
            Settlement("s", 2, "A", auth_id="X", amount=D("10.00"), value_date=2),
            Reversal("r", 3, "A", target_event_id="s", value_date=2),
        ])
        eng.run()
        self.assertEqual(eng.ledger.balance("A", 2), D("100.00"))
        self.assertEqual(eng.ledger.auth_state("X"), "SETTLED")
        self.assertEqual(eng.ledger.held("A"), D("0.00"))

    def test_window_end_flag_follows_window_length(self):
        eng = engine([Credit("c", 1, "A", amount=D("100.00"), value_date=1),
                      Authorization("a", 1, "A", auth_id="X", amount=D("10.00"), value_date=1)], days=2)
        eng.run()
        self.assertFalse(eng.reports[0].is_last)
        self.assertTrue(eng.reports[1].is_last)
