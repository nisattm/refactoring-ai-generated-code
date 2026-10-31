"""Search endpoint (section 15.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from lms.auth.deps import AnyUser
from lms.core.db import SessionDep
from lms.core.errors import ValidationFailed
from lms.core.pagination import Page, PageDep
from lms.search import service
from lms.search.schemas import SearchItemOut

router = APIRouter(prefix="/search", tags=["search"])

MAX_Q_LENGTH = 200


@router.get("/books", response_model=Page[SearchItemOut])
def search_books(
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    q: Annotated[str | None, Query()] = None,
    author: Annotated[str | None, Query()] = None,
    publisher: Annotated[str | None, Query()] = None,
    language: Annotated[str | None, Query()] = None,
    year_from: Annotated[int | None, Query()] = None,
    year_to: Annotated[int | None, Query()] = None,
    classification_prefix: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    available_only: Annotated[bool, Query()] = False,
    sort: Annotated[service.SortKey, Query()] = "relevance",
) -> Page[SearchItemOut]:
    q = q.strip() if q is not None else None
    if q is not None and len(q) > MAX_Q_LENGTH:
        raise ValidationFailed.single("q", f"q must be at most {MAX_Q_LENGTH} characters")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValidationFailed.single("year_from", "year_from must not be greater than year_to")
    return service.search_books(
        db,
        page,
        q=q,
        author=author.strip() if author is not None else None,
        publisher=publisher.strip() if publisher is not None else None,
        language=language.strip() if language is not None else None,
        year_from=year_from,
        year_to=year_to,
        classification_prefix=classification_prefix.strip() if classification_prefix is not None else None,
        branch_id=branch_id,
        available_only=available_only,
        sort=sort,
    )
