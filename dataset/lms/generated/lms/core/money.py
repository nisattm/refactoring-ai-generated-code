"""Money rules (LIB-COM-11 to LIB-COM-13, LIB-CORE-08)."""

from __future__ import annotations

import decimal
import re
from typing import Annotated, Any

import sqlalchemy as sa
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import PydanticCustomError, core_schema

D = decimal.Decimal
CENT = D("0.01")
ZERO = D("0.00")

_AMOUNT_RE = re.compile(r"^[+-]?\d+(\.\d{1,2})?$")


def quantize(value: decimal.Decimal | int | str) -> decimal.Decimal:
    """Round to two places with ROUND_HALF_UP. Apply to the final result only (LIB-CORE-08)."""
    if not isinstance(value, decimal.Decimal):
        value = D(value)
    return value.quantize(CENT, rounding=decimal.ROUND_HALF_UP)


def format_amount(value: decimal.Decimal) -> str:
    """Amount as a string with exactly two decimal places."""
    return format(quantize(value), "f")


def parse_amount(text: str) -> decimal.Decimal:
    """Parse a request amount: a string with at most two decimal places."""
    if not isinstance(text, str) or not _AMOUNT_RE.match(text.strip()):
        raise ValueError("amount must be a string with at most two decimal places")
    return quantize(D(text.strip()))


class _MoneyAnnotation:
    """Pydantic type: accepts only strings with <= 2 decimals, serializes as ``"12.50"``."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        def validate(value: Any) -> decimal.Decimal:
            if isinstance(value, decimal.Decimal):
                if value != quantize(value):
                    raise PydanticCustomError("amount_precision", "amount must have at most two decimal places")
                return quantize(value)
            if not isinstance(value, str):
                raise PydanticCustomError("amount_type", "amount must be a string such as \"12.50\"")
            try:
                return parse_amount(value)
            except ValueError:
                raise PydanticCustomError(
                    "amount_format", "amount must be a string with at most two decimal places"
                ) from None

        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(format_amount, return_schema=core_schema.str_schema()),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> dict[str, Any]:
        return {"type": "string", "pattern": r"^-?\d+(\.\d{1,2})?$", "examples": ["12.50"]}


Money = Annotated[decimal.Decimal, _MoneyAnnotation]


class MoneyType(sa.TypeDecorator[decimal.Decimal]):
    """Stores a Decimal amount exactly, as integer hundredths (never a float)."""

    impl = sa.BigInteger
    cache_ok = True

    def process_bind_param(self, value: decimal.Decimal | None, dialect: Any) -> int | None:
        if value is None:
            return None
        return int(quantize(value) * 100)

    def process_result_value(self, value: int | None, dialect: Any) -> decimal.Decimal | None:
        if value is None:
            return None
        return D(value).scaleb(-2).quantize(CENT)
