"""Pagination rules (LIB-COM-18 to LIB-COM-20)."""

import typing

import sqlalchemy
from sqlalchemy.orm import Session

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def paginate(
    session: Session,
    statement: sqlalchemy.Select,
    page: int,
    page_size: int,
) -> tuple[list[typing.Any], int]:
    """Return one page of `statement` and the total number of matching rows.

    The caller orders `statement` (LIB-COM-20). A page beyond the last page gives
    an empty list (LIB-COM-19).
    """
    total = session.scalar(
        sqlalchemy.select(sqlalchemy.func.count()).select_from(statement.order_by(None).subquery())
    )
    rows = session.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), int(total or 0)


def page_body(
    items: list[typing.Any], *, page: int, page_size: int, total: int
) -> dict[str, typing.Any]:
    """LIB-COM-19: {"items": [...], "page": 1, "page_size": 20, "total": 57}."""
    return {"items": items, "page": page, "page_size": page_size, "total": total}
