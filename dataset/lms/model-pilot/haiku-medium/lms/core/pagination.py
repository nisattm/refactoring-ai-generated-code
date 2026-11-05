"""Pagination of list endpoints (LIB-COM-18 to LIB-COM-20, LIB-CORE-10)."""

from collections.abc import Callable, Sequence
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class PageParams:
    def __init__(
        self,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> None:
        self.page = page
        self.page_size = page_size


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def paginate(rows: Sequence[object], params: PageParams, render: Callable[[object], T]) -> Page[T]:
    """Slice an already ordered list. A page past the last one has no items (LIB-COM-19)."""
    start = (params.page - 1) * params.page_size
    window = rows[start : start + params.page_size]
    return Page[T](
        items=[render(row) for row in window],
        page=params.page,
        page_size=params.page_size,
        total=len(rows),
    )
