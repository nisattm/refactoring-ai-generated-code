"""Pagination (LIB-COM-18 to LIB-COM-20)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any, Generic, TypeVar

import sqlalchemy as sa
from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


PageDep = Annotated[PageParams, Depends(page_params)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def paginate(
    session: Session,
    stmt: sa.Select[Any],
    params: PageParams,
    convert: Callable[[Any], T] = lambda row: row,
) -> Page[T]:
    """Run ``stmt`` (already ordered; default order is ``id`` ascending, LIB-COM-20) for one page."""
    total = session.scalar(sa.select(sa.func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.scalars(stmt.limit(params.page_size).offset(params.offset)).all()
    return Page[T](items=[convert(r) for r in rows], page=params.page, page_size=params.page_size, total=total)


def paginate_sequence(items: Sequence[T], params: PageParams) -> Page[T]:
    """Paginate an already ordered in-memory sequence."""
    chunk = items[params.offset : params.offset + params.page_size]
    return Page[T](items=list(chunk), page=params.page, page_size=params.page_size, total=len(items))
