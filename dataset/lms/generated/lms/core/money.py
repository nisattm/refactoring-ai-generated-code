"""Money helpers (LIB-COM-11 to LIB-COM-13)."""
import decimal
import re

from .errors import validation_error

_CENT = decimal.Decimal("0.01")
_AMOUNT_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")


def quantize(value: decimal.Decimal) -> decimal.Decimal:
    """Round the final result of a calculation to two places, ROUND_HALF_UP."""
    return value.quantize(_CENT, rounding=decimal.ROUND_HALF_UP)


def format_amount(value: decimal.Decimal) -> str:
    return format(quantize(value), "f")


def parse_amount(value: object, field: str, *, allow_negative: bool = False) -> decimal.Decimal:
    if not isinstance(value, str) or not _AMOUNT_RE.match(value.strip()):
        raise validation_error(field, "must be a string with at most two decimal places")
    amount = decimal.Decimal(value.strip())
    if amount < 0 and not allow_negative:
        raise validation_error(field, "must not be negative")
    return quantize(amount)
