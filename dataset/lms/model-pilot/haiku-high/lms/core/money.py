"""Money rules (LIB-COM-11 to LIB-COM-13, LIB-CORE-08)."""

import decimal
import re

CENT = decimal.Decimal("0.01")

# Plain decimal string with at most two decimal places. [0-9] (not \d) so that
# only ASCII digits are accepted.
_AMOUNT_RE = re.compile(r"-?[0-9]+(\.[0-9]{1,2})?")


def round_money(value: decimal.Decimal) -> decimal.Decimal:
    """LIB-COM-12: round to two places, ROUND_HALF_UP. Apply to final results only (LIB-CORE-08)."""
    return value.quantize(CENT, rounding=decimal.ROUND_HALF_UP)


def format_money(value: decimal.Decimal) -> str:
    """LIB-COM-13: JSON representation with exactly two decimal places, e.g. "12.50"."""
    return str(round_money(value))


def parse_amount(value: object, *, allow_negative: bool = False) -> decimal.Decimal:
    """LIB-COM-13: accept an amount only as a string with at most two decimal places.

    Numbers, malformed strings, too many decimals, and negative values (unless
    allowed) raise ValueError.
    """
    if not isinstance(value, str) or not _AMOUNT_RE.fullmatch(value):
        raise ValueError("must be an amount given as a string with at most two decimal places")
    amount = decimal.Decimal(value)
    if amount < 0 and not allow_negative:
        raise ValueError("must not be negative")
    return round_money(amount)
