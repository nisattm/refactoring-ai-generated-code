"""Parsing of query and path parameters that arrive as raw text (LIB-COM-04, LIB-CORE-06)."""

from __future__ import annotations

import datetime
import re

from lms.core.errors import ValidationFailed
from lms.core.timeutil import parse_date

INVALID_DATE_PROBLEM = "expected a valid date in the form YYYY-MM-DD"
_INT_RE = re.compile(r"^[+-]?\d+$")


def optional_date(name: str, raw: str | None) -> datetime.date | None:
    """An optional ``YYYY-MM-DD`` parameter; an invalid value is a ``422`` for ``name``."""
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, INVALID_DATE_PROBLEM) from None


class ParamParser:
    """Collects parse problems so that every invalid parameter is reported (LIB-CORE-06)."""

    def __init__(self) -> None:
        self.problems: list[dict[str, str]] = []

    def date(self, name: str, raw: str | None) -> datetime.date | None:
        if raw is None:
            self.problems.append({"field": name, "problem": "field required"})
            return None
        try:
            return parse_date(raw.strip())
        except ValueError:
            self.problems.append({"field": name, "problem": INVALID_DATE_PROBLEM})
            return None

    def integer(self, name: str, raw: str | None, low: int, high: int) -> int | None:
        if raw is None:
            self.problems.append({"field": name, "problem": "field required"})
            return None
        text = raw.strip()
        if not _INT_RE.match(text) or not low <= int(text) <= high:
            self.problems.append({"field": name, "problem": f"expected an integer between {low} and {high}"})
            return None
        return int(text)

    def check(self) -> None:
        if self.problems:
            raise ValidationFailed(self.problems)
