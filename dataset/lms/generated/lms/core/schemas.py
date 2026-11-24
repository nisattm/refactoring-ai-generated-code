"""Base class for request bodies (LIB-COM-15, LIB-COM-23) and shared field types."""

from __future__ import annotations

import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict

from lms.core.timeutil import parse_date


class RequestModel(BaseModel):
    """Rejects unknown fields (422) and trims text (LIB-COM-15)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _parse_date_value(value: Any) -> datetime.date:
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    return parse_date(value)


DateValue = Annotated[datetime.date, BeforeValidator(_parse_date_value)]
