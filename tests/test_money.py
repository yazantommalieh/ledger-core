import unittest
from decimal import Decimal

from ledger.money import UnknownCurrency, fmt, is_exact, quantize, split_equal, unit, zero


class PrecisionTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(unit("AED"), Decimal("0.01"))
        self.assertEqual(unit("BHD"), Decimal("0.001"))

    def test_quantize_is_half_up(self):
        # 0.04% of 415.00 = 0.166 -> 0.17 (not 0.16 as banker's rounding would give on .165)
        self.assertEqual(quantize(Decimal("0.166"), "AED"), Decimal("0.17"))
        self.assertEqual(quantize(Decimal("0.165"), "AED"), Decimal("0.17"))
        self.assertEqual(quantize(Decimal("0.164"), "AED"), Decimal("0.16"))
        self.assertEqual(quantize(Decimal("0.0045"), "BHD"), Decimal("0.005"))

    def test_quantize_keeps_sign(self):
        self.assertEqual(quantize(Decimal("-0.165"), "AED"), Decimal("-0.17"))

    def test_is_exact(self):
        self.assertTrue(is_exact(Decimal("3.334"), "BHD"))
        self.assertFalse(is_exact(Decimal("3.3334"), "BHD"))
        self.assertFalse(is_exact(Decimal("1.005"), "AED"))

    def test_unknown_currency_is_an_error_not_a_default(self):
        with self.assertRaises(UnknownCurrency):
            unit("USD")

    def test_zero(self):
        self.assertEqual(str(zero("BHD")), "0.000")
        self.assertEqual(str(zero("AED")), "0.00")

    def test_fmt(self):
        self.assertEqual(fmt(Decimal("1200.00"), "AED"), "AED 1,200.00")
        self.assertEqual(fmt(Decimal("-370.00"), "AED"), "AED -370.00")
        self.assertEqual(fmt(Decimal("10.000"), "BHD"), "BHD 10.000")


class SplitTests(unittest.TestCase):
    def test_bhd_ten_in_three(self):
        # The E10 case. Criterion 7 ("each 3.334") is rejected: 3 x 3.334 = 10.002.
        self.assertEqual(
            split_equal(Decimal("10.000"), 3, "BHD"),
            [Decimal("3.333"), Decimal("3.333"), Decimal("3.334")],
        )

    def test_exact_division_has_no_remainder(self):
        self.assertEqual(split_equal(Decimal("9.000"), 3, "BHD"), [Decimal("3.000")] * 3)

    def test_conservation_over_many_values(self):
        for cents in range(1, 500):
            total = Decimal(cents).scaleb(-2)
            for n in (1, 2, 3, 7):
                parts = split_equal(total, n, "AED")
                self.assertEqual(sum(parts), total)
                self.assertEqual(len(parts), n)
                # all but the last are identical; the last differs by < n units
                self.assertEqual(len(set(parts[:-1])), 1 if n > 1 else 0)
                self.assertLess(parts[-1] - parts[0], Decimal(n) * unit("AED"))

    def test_single_part(self):
        self.assertEqual(split_equal(Decimal("10.000"), 1, "BHD"), [Decimal("10.000")])

    def test_zero_parts_rejected(self):
        with self.assertRaises(ValueError):
            split_equal(Decimal("1.00"), 0, "AED")


if __name__ == "__main__":
    unittest.main()
