import dataclasses
import unittest
from decimal import Decimal as D

from ledger.ledger import Decision, Entry, Kind, Ledger, LedgerError


def make():
    return Ledger({"ACC-001": "AED", "ACC-002": "BHD"})


class AppendOnlyTests(unittest.TestCase):
    def test_records_are_frozen(self):
        lg = make()
        e = lg.append_entry("ACC-001", Kind.CREDIT, D("1.00"), 1, 1, "X")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.amount = D("2.00")  # type: ignore[misc]

    def test_views_are_snapshots_not_handles(self):
        lg = make()
        lg.append_entry("ACC-001", Kind.CREDIT, D("1.00"), 1, 1, "X")
        view = lg.entries
        self.assertIsInstance(view, tuple)
        lg.append_entry("ACC-001", Kind.CREDIT, D("1.00"), 1, 1, "Y")
        self.assertEqual(len(view), 1)
        self.assertEqual(len(lg.entries), 2)

    def test_no_mutating_api_exists(self):
        names = {n for n in dir(Ledger) if not n.startswith("_")}
        for forbidden in ("delete", "remove", "update", "pop", "clear", "set_"):
            self.assertFalse(any(forbidden in n for n in names), forbidden)

    def test_seq_is_monotonic_across_logs(self):
        lg = make()
        a = lg.append_entry("ACC-001", Kind.CREDIT, D("1.00"), 1, 1, "X")
        b = lg.append_error(1, "Y", "CODE", "msg")
        c = lg.append_auth("A", "ACC-001", D("1.00"), 1, 1, "Z", Decision.APPROVED, D("1.00"), D("0.00"))
        self.assertEqual((a.seq, b.seq, c.seq), (1, 2, 3))


class ValidationTests(unittest.TestCase):
    def test_precision_is_enforced_on_entry(self):
        lg = make()
        with self.assertRaises(LedgerError):
            lg.append_entry("ACC-001", Kind.CREDIT, D("1.005"), 1, 1, "X")
        with self.assertRaises(LedgerError):
            lg.append_entry("ACC-002", Kind.CREDIT, D("3.3333"), 1, 1, "X")

    def test_future_value_dates_rejected(self):
        lg = make()
        with self.assertRaises(LedgerError):
            lg.append_entry("ACC-001", Kind.CREDIT, D("1.00"), value_date=3, posting_day=2, origin_event="X")

    def test_unknown_account(self):
        lg = make()
        with self.assertRaises(LedgerError):
            lg.append_entry("ACC-999", Kind.CREDIT, D("1.00"), 1, 1, "X")


class BalanceTests(unittest.TestCase):
    def test_balance_is_by_value_date(self):
        lg = make()
        lg.append_entry("ACC-001", Kind.CREDIT, D("1200.00"), 1, 1, "E1")
        lg.append_entry("ACC-001", Kind.DEBIT, D("-950.00"), 1, 1, "E2")
        lg.append_entry("ACC-001", Kind.CREDIT, D("400.00"), 3, 3, "E4")
        self.assertEqual(lg.balance("ACC-001", 1), D("250.00"))
        self.assertEqual(lg.balance("ACC-001", 2), D("250.00"))
        self.assertEqual(lg.balance("ACC-001", 3), D("650.00"))

    def test_backdated_entry_restates_history_but_not_the_as_of_view(self):
        lg = make()
        lg.append_entry("ACC-001", Kind.CREDIT, D("1200.00"), 1, 1, "E1")
        lg.append_entry("ACC-001", Kind.DEBIT, D("-950.00"), 1, 1, "E2")
        lg.append_entry("ACC-001", Kind.DEBIT, D("-620.00"), value_date=2, posting_day=5, origin_event="E7")
        # restated Day 2
        self.assertEqual(lg.balance("ACC-001", 2), D("-370.00"))
        # Day 2 as the Day 2 close actually saw it
        self.assertEqual(lg.balance("ACC-001", 2, as_of_posting_day=2), D("250.00"))
        # Day 2 as known at end of Day 5
        self.assertEqual(lg.balance("ACC-001", 2, as_of_posting_day=5), D("-370.00"))

    def test_opening_balance_is_zero_at_currency_precision(self):
        lg = make()
        self.assertEqual(str(lg.balance("ACC-002", 6)), "0.000")
        self.assertEqual(str(lg.balance("ACC-001", 6)), "0.00")


class HoldTests(unittest.TestCase):
    def test_hold_reduces_available_not_ledger(self):
        lg = make()
        lg.append_entry("ACC-001", Kind.CREDIT, D("250.00"), 1, 1, "E1")
        lg.append_auth("Auth-A", "ACC-001", D("200.00"), 2, 2, "E3", Decision.APPROVED, D("250.00"), D("50.00"))
        self.assertEqual(lg.balance("ACC-001", 2), D("250.00"))
        self.assertEqual(lg.available("ACC-001", 2), D("50.00"))
        self.assertEqual(lg.auth_state("Auth-A"), "ACTIVE")

    def test_settlement_releases_hold(self):
        lg = make()
        lg.append_entry("ACC-001", Kind.CREDIT, D("650.00"), 1, 1, "E1")
        lg.append_auth("Auth-A", "ACC-001", D("200.00"), 2, 2, "E3", Decision.APPROVED, D("650.00"), D("450.00"))
        lg.append_entry("ACC-001", Kind.SETTLEMENT, D("-185.00"), 4, 4, "E5", ref="Auth-A")
        self.assertEqual(lg.auth_state("Auth-A"), "SETTLED")
        self.assertEqual(lg.held("ACC-001"), D("0.00"))
        self.assertEqual(lg.available("ACC-001", 4), D("465.00"))
        # ...but on Day 3 the hold was still active
        self.assertEqual(lg.held("ACC-001", as_of_posting_day=3), D("200.00"))

    def test_declined_auth_holds_nothing(self):
        lg = make()
        lg.append_auth("Auth-B", "ACC-001", D("90.00"), 5, 5, "E8", Decision.DECLINED, D("-155.00"), D("-245.00"))
        self.assertEqual(lg.auth_state("Auth-B"), "DECLINED")
        self.assertEqual(lg.held("ACC-001"), D("0.00"))

    def test_unknown_auth(self):
        self.assertEqual(make().auth_state("Auth-Z"), "UNKNOWN")


class FeeLookupTests(unittest.TestCase):
    def test_fee_for_day_keyed_on_value_date(self):
        lg = make()
        self.assertIsNone(lg.fee_for("ACC-001", 2))
        lg.append_entry("ACC-001", Kind.FEE, D("-25.00"), value_date=2, posting_day=5,
                        origin_event=None, ref="overdraft:2")
        self.assertIsNotNone(lg.fee_for("ACC-001", 2))
        self.assertIsNone(lg.fee_for("ACC-001", 5))


if __name__ == "__main__":
    unittest.main()
