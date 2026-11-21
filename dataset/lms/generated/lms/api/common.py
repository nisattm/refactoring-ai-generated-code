"""Helpers shared by the routers: request context, path ids, query-parameter parsing and CSV responses."""

from __future__ import annotations

import datetime
import re
from typing import Annotated

from fastapi import Path, Request, Response

from lms.core.clock import local_now, today
from lms.core.errors import ValidationFailed
from lms.core.settings import Settings
from lms.core.timeutil import parse_date

# A path parameter that holds an entity id.
IdPath = Annotated[int, Path(ge=1)]

CSV_TYPE = "text/csv; charset=utf-8"

DATE_PROBLEM = "expected a valid date in the form YYYY-MM-DD"

_INT_RE = re.compile(r"^[+-]?\d+$")


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def now_of(request: Request) -> datetime.datetime:
    """The current local date-time of the application's clock."""
    return local_now(settings_of(request).clock)


def today_of(request: Request) -> datetime.date:
    """LIB-COM-02: the local date of the application's clock."""
    return today(settings_of(request).clock)


def csv_response(text: str) -> Response:
    return Response(content=text.encode("utf-8"), media_type=CSV_TYPE)


def optional_date(name: str, raw: str | None) -> datetime.date | None:
    """A date in a query parameter that may be absent; ``422`` if it is present but invalid."""
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, DATE_PROBLEM) from None


class QueryParams:
    """Parses required query parameters and collects every problem, so that all invalid parameters are
    reported together (LIB-CORE-06). Call ``check`` after the last parameter."""

    def __init__(self) -> None:
        self.problems: list[dict[str, str]] = []

    def date(self, name: str, raw: str | None) -> datetime.date | None:
        if raw is None:
            self.problems.append({"field": name, "problem": "field required"})
            return None
        try:
            return parse_date(raw.strip())
        except ValueError:
            self.problems.append({"field": name, "problem": DATE_PROBLEM})
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
