"""Pagination (LIB-COM-18 to LIB-COM-20)."""
import re
from collections.abc import Sequence
from typing import Any

from fastapi import Query

from .errors import ValidationFailed

_INT_RE = re.compile(r"^[+-]?\d+$")


def page_params(page: str | None = Query(None), page_size: str | None = Query(None)) -> tuple[int, int]:
    """FastAPI dependency returning validated (page, page_size)."""
    fields: list[dict[str, str]] = []
    values: list[int] = []
    for name, raw, default, lo, hi in (
        ("page", page, 1, 1, None),
        ("page_size", page_size, 20, 1, 100),
    ):
        if raw is None:
            values.append(default)
            continue
        if not _INT_RE.match(raw.strip()):
            fields.append({"field": name, "problem": "must be an integer"})
            continue
        v = int(raw)
        if v < lo or (hi is not None and v > hi):
            problem = f"must be between {lo} and {hi}" if hi is not None else f"must be at least {lo}"
            fields.append({"field": name, "problem": problem})
            continue
        values.append(v)
    if fields:
        raise ValidationFailed(fields)
    return values[0], values[1]


def paginate(items: Sequence[Any], page: int, page_size: int) -> dict[str, Any]:
    start = (page - 1) * page_size
    return {
        "items": list(items[start : start + page_size]),
        "page": page,
        "page_size": page_size,
        "total": len(items),
    }
