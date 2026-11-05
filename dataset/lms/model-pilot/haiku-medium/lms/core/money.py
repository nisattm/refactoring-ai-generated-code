"""Money rules (LIB-COM-11 to LIB-COM-13, LIB-CORE-08)."""

import decimal

CENT = decimal.Decimal("0.01")


def round_money(value: decimal.Decimal) -> decimal.Decimal:
    """Round to two places, half up. Apply only to a final result (LIB-CORE-08)."""
    return value.quantize(CENT, rounding=decimal.ROUND_HALF_UP)


def format_amount(value: decimal.Decimal) -> str:
    """API form of an amount: a string with exactly two decimal places, e.g. "12.50"."""
    return str(round_money(value))
