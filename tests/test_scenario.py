"""Acceptance tests against the assignment's event stream.

Each criterion from the brief has a test. Accepted criteria are asserted as
written. Rejected criteria (see REJECTED.md) are asserted in their *corrected*
form, with the original wording quoted so the contradiction is visible.
"""
import unittest
from decimal import Decimal as D

from ledger.engine import Engine
from ledger.ledger import Kind, Ledger, Severity
from ledger.scenario import ACCOUNTS, EVENTS, WINDOW_DAYS


def fresh() -> Engine:
    return Engine(Ledger(ACCOUNTS), EVENTS, WINDOW_DAYS)


def run_through(day: int, close_last_day: bool = True) -> Engine:
    """Replay up to ``day``; optionally stop *before* that day's close."""
    eng = fresh()
    for d in range(1, day):
        eng.run_day(d)
    if close_last_day:
        eng.run_day(day)
    else:
        eng.run_events(day)
    return eng


class Criterion1_Day2BalanceAtEndOfDay5(unittest.TestCase):
    """ACCEPTED. 'The Day 2 closing ledger balance, evaluated at end of Day 5
    and before any fee is assessed, is AED -370.00.'"""

    def test_day2_restated_before_day5_close(self):
        eng = run_through(5, close_last_day=False)
        self.assertEqual(eng.ledger.balance("ACC-001", 2, as_of_posting_day=5), D("-370.00"))

    def test_day2_as_seen_on_day2_was_positive(self):
        # the same question asked on Day 2 had a different, equally correct answer
        eng = run_through(2)
        self.assertEqual(eng.ledger.balance("ACC-001", 2, as_of_posting_day=2), D("250.00"))


class Criterion2_FeesCausedByE7(unittest.TestCase):
    """REJECTED as written: 'E7 causes exactly one overdraft fee, on Day 2.'
    E7 makes Days 2, 4 and 5 negative (Day 3 recovers to +5.00 after the Day 2
    fee). Three fees, all assessed in the Day 5 close."""

    def test_three_fees_for_days_2_4_5(self):
        eng = run_through(5)
        fees = eng.ledger.entries_of_kind(Kind.FEE, "ACC-001")
        self.assertEqual([f.value_date for f in fees], [2, 4, 5])
        self.assertTrue(all(f.posting_day == 5 for f in fees))
        self.assertTrue(all(f.amount == D("-25.00") for f in fees))

    def test_day3_is_not_fee_d(self):
        eng = run_through(5)
        self.assertEqual(eng.ledger.balance("ACC-001", 3), D("5.00"))
        self.assertIsNone(eng.ledger.fee_for("ACC-001", 3))

    def test_no_fees_before_e7(self):
        eng = run_through(4)
        self.assertEqual(eng.ledger.entries_of_kind(Kind.FEE), ())

    def test_fee_assessment_is_idempotent(self):
        eng = run_through(5)
        n = len(eng.ledger.entries)
        self.assertEqual(eng.end_of_day_fees(5), [])
        self.assertEqual(len(eng.ledger.entries), n)


class Criterion3_AuthASettlement(unittest.TestCase):
    """ACCEPTED. 'The Day 4 settlement of Auth-A must be accepted.'"""

    def test_accepted_and_hold_released(self):
        eng = run_through(4)
        s = eng.ledger.settlement_of("Auth-A")
        self.assertIsNotNone(s)
        self.assertEqual(s.amount, D("-185.00"))
        self.assertEqual(eng.ledger.auth_state("Auth-A"), "SETTLED")
        self.assertEqual(eng.ledger.held("ACC-001"), D("0.00"))
        self.assertEqual(eng.ledger.balance("ACC-001", 4), D("465.00"))


class Criterion4_OrphanSettlement(unittest.TestCase):
    """ACCEPTED (as a policy choice — see AMBIGUITIES.md for the force-post
    counter-argument). 'Any settlement referencing an authorization ID not
    present in the ledger must be rejected and the funds must not leave.'"""

    def test_e6_rejected_no_funds_moved(self):
        eng = run_through(4)
        self.assertEqual(eng.ledger.entries_for_event("E6"), ())
        errs = [e for e in eng.ledger.errors if e.event_id == "E6"]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].code, "NO_AUTH")
        self.assertIs(errs[0].severity, Severity.ERROR)
        self.assertEqual(eng.ledger.balance("ACC-001", 4), D("465.00"))  # 650 - 185, not - 180


class Criterion5_AuthB(unittest.TestCase):
    """The statement 'a hold reduces available balance but not ledger balance'
    is ACCEPTED and holds for every authorization. Its premise is false: Auth-B
    is DECLINED, because by the time E8 arrives E7 has already dragged the
    available balance to -155.00."""

    def test_auth_b_declined(self):
        eng = run_through(5, close_last_day=False)
        a = eng.ledger.auth("Auth-B")
        self.assertEqual(a.decision.value, "DECLINED")
        self.assertEqual(a.available_before, D("-155.00"))
        self.assertEqual(a.available_after, D("-245.00"))
        self.assertEqual(eng.ledger.auth_state("Auth-B"), "DECLINED")

    def test_holds_never_touch_ledger_balance(self):
        eng = run_through(1)
        before = eng.ledger.balance("ACC-001", 2)
        eng.run_day(2)  # Auth-A approved here
        self.assertEqual(eng.ledger.balance("ACC-001", 2), before)
        self.assertEqual(eng.ledger.available("ACC-001", 2), before - D("200.00"))

    def test_declined_auth_is_not_reopened_by_e9(self):
        eng = run_through(6)
        self.assertEqual(eng.ledger.auth_state("Auth-B"), "DECLINED")


class Criterion6_ReversalDoesNotRewindHistory(unittest.TestCase):
    """REJECTED as written: 'After E9, all balances and fees return to their
    pre-E7 values.' E9 is a compensating entry. The transactional balances
    return; the three fees E7 triggered remain in the append-only log, so every
    value-dated balance from Day 2 on is 25/50/75 lower than pre-E7."""

    def test_e9_is_a_posting_not_a_deletion(self):
        eng = run_through(6)
        self.assertEqual(len(eng.ledger.entries_for_event("E7")), 1)  # still there
        rev = eng.ledger.reversals_of("E7")
        self.assertEqual(len(rev), 1)
        self.assertEqual(rev[0].amount, D("620.00"))
        self.assertEqual(rev[0].value_date, 2)
        self.assertEqual(rev[0].posting_day, 6)

    def test_fees_survive_the_reversal(self):
        eng = run_through(6)
        self.assertEqual(len(eng.ledger.entries_of_kind(Kind.FEE, "ACC-001")), 3)

    def test_balances_are_pre_e7_minus_cumulative_fees(self):
        pre = run_through(4).ledger
        post = run_through(6).ledger
        expected_fee_drag = {1: 0, 2: 25, 3: 25, 4: 50}
        for day, drag in expected_fee_drag.items():
            self.assertEqual(post.balance("ACC-001", day), pre.balance("ACC-001", day) - D(drag))


class Criterion7_Instalments(unittest.TestCase):
    """REJECTED as written: 'The three BHD instalments must each be BHD 3.334.'
    3 x 3.334 = 10.002. They are 3.333 / 3.333 / 3.334."""

    def test_instalments_conserve_the_credit(self):
        eng = run_through(5)
        parts = [e.amount for e in eng.ledger.entries_for_event("E10")]
        self.assertEqual(parts, [D("3.333"), D("3.333"), D("3.334")])
        self.assertEqual(sum(parts), D("10.000"))
        self.assertEqual(eng.ledger.balance("ACC-002", 5), D("10.000"))


class Criterion8_InterestRemainder(unittest.TestCase):
    """REJECTED as written: 'If the rounded daily interest accruals do not sum
    to the capitalised total, the remainder is discarded.' The capitalised
    total IS the sum of the rounded daily accruals; there is no remainder."""

    def test_schedule_sums_exactly_to_capitalised_credit(self):
        eng = run_through(6)
        for acct in ("ACC-001", "ACC-002"):
            sched = eng.reports[-1].interest_schedule[acct]
            credit = eng.ledger.entries_of_kind(Kind.INTEREST, acct)[0].amount
            self.assertEqual(sum(acc for _, acc in sched.values()), credit)

    def test_expected_schedule_and_total(self):
        eng = run_through(6)
        sched = eng.reports[-1].interest_schedule["ACC-001"]
        self.assertEqual([str(acc) for _, acc in sched.values()], ["0.10", "0.09", "0.25", "0.17", "0.16", "0.16"])
        self.assertEqual(eng.ledger.entries_of_kind(Kind.INTEREST, "ACC-001")[0].amount, D("0.93"))
        self.assertEqual(eng.ledger.entries_of_kind(Kind.INTEREST, "ACC-002")[0].amount, D("0.008"))

    def test_interest_is_derived_from_restated_history_not_snapshots(self):
        # The Day 2 accrual is on the restated 225.00, not the 250.00 the Day 2 close saw.
        eng = run_through(6)
        bal, acc = eng.reports[-1].interest_schedule["ACC-001"][2]
        self.assertEqual((bal, acc), (D("225.00"), D("0.09")))

    def test_no_accrual_on_negative_days(self):
        eng = run_through(5)
        sched = eng.interest_schedule("ACC-001", 5)
        self.assertEqual([str(acc) for _, acc in sched.values()], ["0.10", "0.00", "0.00", "0.00", "0.00"])


class WindowEndState(unittest.TestCase):
    def test_final_balances(self):
        eng = run_through(6)
        self.assertEqual(eng.ledger.balance("ACC-001", 6), D("390.93"))
        self.assertEqual(eng.ledger.balance("ACC-002", 6), D("10.008"))

    def test_restated_history(self):
        eng = run_through(6)
        self.assertEqual([str(eng.ledger.balance("ACC-001", d)) for d in range(1, 7)],
                         ["250.00", "225.00", "625.00", "415.00", "390.00", "390.93"])

    def test_record_counts_and_append_only(self):
        eng = run_through(6)
        lg = eng.ledger
        # 2 (E1,E2) + 1 (E4) + 1 (E5) + 1 (E7) + 3 (E10) + 3 fees + 1 (E9) + 2 interest = 14
        self.assertEqual(len(lg.entries), 14)
        self.assertEqual([e.seq for e in lg.entries], sorted(e.seq for e in lg.entries))
        self.assertEqual(len(lg.auths), 2)
        self.assertEqual(len(lg.errors), 1)

    def test_day_reports_show_restatements(self):
        eng = run_through(6)
        d5, d6 = eng.reports[4], eng.reports[5]
        self.assertEqual(sorted(d5.restated["ACC-001"]), [2, 3, 4])
        self.assertEqual(sorted(d6.restated["ACC-001"]), [2, 3, 4, 5])
        self.assertNotIn("ACC-002", d5.restated)

    def test_stream_order_within_a_day_is_preserved(self):
        # Day 5 events in stream order are E7, E8, E10. E9 precedes E10 in the
        # listing but is posted on Day 6, so it runs after — see AMBIGUITIES.md.
        eng = run_through(6)
        day5 = [line.split()[0] for line in eng.reports[4].processed]
        day6 = [line.split()[0] for line in eng.reports[5].processed]
        self.assertEqual(day5, ["E7", "E8", "E10"])
        self.assertEqual(day6, ["E9"])


if __name__ == "__main__":
    unittest.main()
