"""Business logic of module 9: catalog search (LIB-SRCH-01 to LIB-SRCH-08).

The whole search runs in SQL so that a catalog of 100,000 books stays fast: titles, authors and
publishers have stored normalized keys; subtitles are normalized by the ``lms_normalize`` SQL function.
"""

from __future__ import annotations

from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.catalog.models import Author, Book, BookAuthor, Copy, Publisher
from lms.catalog.service import book_out
from lms.catalog.status import GONE_STATUSES
from lms.core.pagination import Page, PageParams
from lms.core.text import normalize
from lms.loans.models import Loan
from lms.search.schemas import SearchItemOut

SortKey = Literal["relevance", "title", "year_desc", "year_asc", "popularity"]


def _contains(column: sa.ColumnElement[str | None], needle: str) -> sa.ColumnElement[bool]:
    return sa.func.instr(column, needle) > 0


def _author_contains(needle: str) -> sa.ColumnElement[bool]:
    return sa.exists().where(
        BookAuthor.book_id == Book.id,
        Author.id == BookAuthor.author_id,
        _contains(Author.name_key, needle),
    )


def tokens_of(q: str | None) -> list[str]:
    """LIB-SRCH-02: the normalized white-space separated tokens of ``q``."""
    return [normalize(t) for t in (q or "").split()]


def _token_match(token: str) -> sa.ColumnElement[bool]:
    return sa.or_(
        _contains(Book.title_key, token),
        _contains(sa.func.lms_normalize(Book.subtitle), token),
        _author_contains(token),
        _contains(Publisher.name_key, token),
        _contains(Book.isbn, token),
    )


def _token_score(token: str) -> sa.ColumnElement[int]:
    """LIB-SRCH-05: the highest applicable value for one token."""
    return sa.case(
        (Book.isbn == token, 10),
        (_contains(Book.title_key, token), 3),
        (_author_contains(token), 2),
        (
            sa.or_(_contains(sa.func.lms_normalize(Book.subtitle), token), _contains(Publisher.name_key, token)),
            1,
        ),
        else_=0,
    )


def _loan_counts() -> sa.Subquery:
    return (
        sa.select(Copy.book_id.label("book_id"), sa.func.count(Loan.id).label("loan_count"))
        .join(Loan, Loan.copy_id == Copy.id)
        .group_by(Copy.book_id)
        .subquery()
    )


def search_books(
    db: Session,
    page: PageParams,
    *,
    q: str | None,
    author: str | None,
    publisher: str | None,
    language: str | None,
    year_from: int | None,
    year_to: int | None,
    classification_prefix: str | None,
    branch_id: int | None,
    available_only: bool,
    sort: SortKey,
) -> Page[SearchItemOut]:
    tokens = tokens_of(q)
    conditions: list[sa.ColumnElement[bool]] = [_token_match(t) for t in tokens]

    if author:
        conditions.append(_author_contains(normalize(author)))
    if publisher:
        conditions.append(_contains(Publisher.name_key, normalize(publisher)))
    if language:
        conditions.append(Book.language == language)
    if year_from is not None:
        conditions.append(Book.publication_year >= year_from)
    if year_to is not None:
        conditions.append(Book.publication_year <= year_to)
    if classification_prefix:
        conditions.append(Book.classification.startswith(classification_prefix, autoescape=True))

    # LIB-SRCH-04
    if available_only:
        copy_filter = [Copy.book_id == Book.id, Copy.status == "available"]
        if branch_id is not None:
            copy_filter.append(Copy.current_branch_id == branch_id)
        conditions.append(sa.exists().where(*copy_filter))
    elif branch_id is not None:
        conditions.append(
            sa.exists().where(
                Copy.book_id == Book.id, Copy.current_branch_id == branch_id, Copy.status.not_in(GONE_STATUSES)
            )
        )

    score: sa.ColumnElement[int] = sa.literal(0)
    if tokens:
        score = sum((_token_score(t) for t in tokens[1:]), _token_score(tokens[0]))

    base = sa.select(Book.id.label("id"), Book.title_key.label("title_key"), score.label("score")).join(
        Publisher, Publisher.id == Book.publisher_id
    )
    if conditions:
        base = base.where(*conditions)

    if sort == "popularity":
        counts = _loan_counts()
        base = base.outerjoin(counts, counts.c.book_id == Book.id)
        order = [sa.func.coalesce(counts.c.loan_count, 0).desc(), Book.title_key, Book.id]
    elif sort == "title":
        order = [Book.title_key, Book.id]
    elif sort == "year_desc":
        order = [Book.publication_year.desc(), Book.title_key, Book.id]
    elif sort == "year_asc":
        order = [Book.publication_year, Book.title_key, Book.id]
    else:
        order = [sa.literal_column("score").desc(), Book.title_key, Book.id]

    total = db.scalar(sa.select(sa.func.count()).select_from(base.order_by(None).subquery())) or 0
    rows = db.execute(base.order_by(*order).limit(page.page_size).offset(page.offset)).all()

    book_ids = [r.id for r in rows]
    loan_counts: dict[int, int] = {}
    if book_ids:
        loan_counts = {
            book_id: count
            for book_id, count in db.execute(
                sa.select(Copy.book_id, sa.func.count(Loan.id))
                .join(Loan, Loan.copy_id == Copy.id)
                .where(Copy.book_id.in_(book_ids))
                .group_by(Copy.book_id)
            )
        }
    books = {b.id: b for b in db.scalars(sa.select(Book).where(Book.id.in_(book_ids)))} if book_ids else {}
    items = [
        SearchItemOut(book=book_out(db, books[r.id]), score=int(r.score), loan_count=loan_counts.get(r.id, 0))
        for r in rows
    ]
    return Page[SearchItemOut](items=items, page=page.page, page_size=page.page_size, total=total)
