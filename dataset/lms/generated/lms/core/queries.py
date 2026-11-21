"""Helpers for building list queries."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa


def filter_equal(stmt: sa.Select[Any], *filters: tuple[Any, Any]) -> sa.Select[Any]:
    """Add ``column == value`` for every ``(column, value)`` pair whose value is not ``None``."""
    for column, value in filters:
        if value is not None:
            stmt = stmt.where(column == value)
    return stmt
