"""Money arithmetic: per-currency precision, rounding, and equal-instalment splits.

Every monetary amount in this codebase is a ``decimal.Decimal`` already
quantized to its currency's precision. Floats are never used — binary floats
cannot represent 0.10 exactly, and a ledger that drifts by a fils is a ledger
that is wrong. All constants here are explained in NUMBERS.md.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

# ISO 4217 minor-unit exponents for the currencies in scope.
# A currency that is not in this table is a configuration error, not a
# default-to-2dp situation; see NUMBERS.md and AMBIGUITIES.md.
PRECISION: dict[str, int] = {
    "AED": 2,  # fils
    "BHD": 3,  # fils (1/1000 dinar)
}

# Commercial rounding (half away from zero on the magnitude).
ROUNDING = ROUND_HALF_UP


class UnknownCurrency(KeyError):
    pass


def unit(currency: str) -> Decimal:
    """Smallest representable amount: Decimal('0.01') for AED, '0.001' for BHD."""
    try:
        return Decimal(1).scaleb(-PRECISION[currency])
    except KeyError as exc:
        raise UnknownCurrency(currency) from exc


def quantize(amount: Decimal | int | str, currency: str, rounding: str = ROUNDING) -> Decimal:
    """Round ``amount`` to the currency's precision."""
    return Decimal(amount).quantize(unit(currency), rounding=rounding)


def zero(currency: str) -> Decimal:
    return quantize(0, currency)


def is_exact(amount: Decimal, currency: str) -> bool:
    """True when ``amount`` carries no more decimals than the currency allows."""
    return amount == quantize(amount, currency)


def split_equal(total: Decimal | str, parts: int, currency: str) -> list[Decimal]:
    """Split ``total`` into ``parts`` instalments that sum exactly to ``total``.

    Each instalment is ``total / parts`` rounded DOWN to the currency unit;
    whatever remainder that leaves (always fewer than ``parts`` units) is added
    to the LAST instalment. For BHD 10.000 in 3 parts this gives
    3.333 / 3.333 / 3.334 — never 3.334 x3, which would create 0.002 from
    nothing. See AMBIGUITIES.md for why "last" rather than "first".
    """
    if parts < 1:
        raise ValueError("parts must be >= 1")
    total = quantize(total, currency)
    base = quantize(total / parts, currency, rounding=ROUND_DOWN)
    instalments = [base] * parts
    instalments[-1] = base + (total - base * parts)
    assert sum(instalments) == total, "instalments must conserve the total"
    return instalments


def fmt(amount: Decimal, currency: str) -> str:
    """Human formatting with thousands separators at the currency's precision."""
    return f"{currency} {amount:,.{PRECISION[currency]}f}"
