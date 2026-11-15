"""Constants and pure rules of module 24 (sections 32.1, 32.3 and 32.5)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from lms.core.text import normalize

SHELF_STATUSES = ("available", "on_hold", "damaged", "on_reserve")  # 32.1
APPLY_ADMIN_LIMIT = 10  # LIB-INV-19: more missing lines than this are applied only by an admin
COUNT_EXPIRY_DAYS = 7  # LIB-INV-23
MISSING_LOST_DAYS = 90  # LIB-INV-23

PROBLEM_RESULTS = ("unknown", "duplicate", "found_lost", "withdrawn", "wrong_branch", "unexpected_status", "out_of_scope")


def in_prefix(shelf_location: str | None, prefix: str | None) -> bool:
    """32.1: a copy without ``shelf_location`` is outside a count with a prefix."""
    if prefix is None:
        return True
    if shelf_location is None:
        return False
    return normalize(shelf_location).startswith(normalize(prefix))


def prefixes_overlap(a: str | None, b: str | None) -> bool:
    """LIB-INV-03: one of the counts has no prefix, or one prefix starts with the other."""
    if a is None or b is None:
        return True
    x, y = normalize(a), normalize(b)
    return x.startswith(y) or y.startswith(x)


def accuracy(found: int, missing: int) -> str:
    """LIB-INV-15."""
    if found + missing == 0:
        return "100.0"
    value = (Decimal(found) * 100 / Decimal(found + missing)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(value, "f")
