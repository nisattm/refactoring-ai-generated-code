"""Catalog endpoints (section 8.3)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request, Response

from lms.auth.deps import AnyUser, StaffOnly
from lms.catalog import service
from lms.catalog.isbn import normalize_isbn
from lms.catalog.models import Author, Book, BookAuthor, Copy, Publisher
from lms.catalog.schemas import (
    AuthorOut,
    BookCreateIn,
    BookOut,
    BookPatchIn,
    CopyCreateIn,
    CopyOut,
    CopyPatchIn,
    NameIn,
    NamePatchIn,
    PublisherOut,
    WithdrawIn,
    copy_out,
)
from lms.catalog.status import CopyStatus
from lms.core.clock import local_now, today
from lms.core.db import SessionDep
from lms.core.errors import ValidationFailed
from lms.core.pagination import Page, PageDep, paginate
from lms.core.text import normalize

router = APIRouter(tags=["catalog"])

AuthorId = Annotated[int, Path(ge=1)]
PublisherId = Annotated[int, Path(ge=1)]
BookId = Annotated[int, Path(ge=1)]
CopyId = Annotated[int, Path(ge=1)]


def _now(request: Request):  # noqa: ANN202
    return local_now(request.app.state.settings.clock)


def _name_search(stmt: sa.Select, model: type[Author] | type[Publisher], q: str | None) -> sa.Select:
    needle = normalize(q.strip()) if q is not None else ""
    if needle:
        stmt = stmt.where(model.name_key.contains(needle, autoescape=True))
    return stmt


# --- authors ----------------------------------------------------------------------


@router.post("/authors", response_model=AuthorOut, status_code=201)
def create_author(body: NameIn, db: SessionDep, _: StaffOnly) -> AuthorOut:
    author = service.create_author(db, body.name)
    return AuthorOut(id=author.id, name=author.name)


@router.get("/authors", response_model=Page[AuthorOut])
def list_authors(db: SessionDep, _: AnyUser, page: PageDep, q: Annotated[str | None, Query()] = None) -> Page[AuthorOut]:
    stmt = _name_search(sa.select(Author).order_by(Author.name_key, Author.id), Author, q)
    return paginate(db, stmt, page, lambda a: AuthorOut(id=a.id, name=a.name))


@router.get("/authors/{author_id}", response_model=AuthorOut)
def get_author(author_id: AuthorId, db: SessionDep, _: AnyUser) -> AuthorOut:
    author = service.get_author_or_404(db, author_id)
    return AuthorOut(id=author.id, name=author.name)


@router.patch("/authors/{author_id}", response_model=AuthorOut)
def update_author(author_id: AuthorId, body: NamePatchIn, db: SessionDep, _: StaffOnly) -> AuthorOut:
    author = service.update_author(service.get_author_or_404(db, author_id), body.name)
    return AuthorOut(id=author.id, name=author.name)


@router.delete("/authors/{author_id}", status_code=204)
def delete_author(author_id: AuthorId, db: SessionDep, _: StaffOnly) -> Response:
    service.delete_author(db, service.get_author_or_404(db, author_id))
    return Response(status_code=204)


# --- publishers -------------------------------------------------------------------


@router.post("/publishers", response_model=PublisherOut, status_code=201)
def create_publisher(body: NameIn, db: SessionDep, _: StaffOnly) -> PublisherOut:
    publisher = service.create_publisher(db, body.name)
    return PublisherOut(id=publisher.id, name=publisher.name)


@router.get("/publishers", response_model=Page[PublisherOut])
def list_publishers(
    db: SessionDep, _: AnyUser, page: PageDep, q: Annotated[str | None, Query()] = None
) -> Page[PublisherOut]:
    stmt = _name_search(sa.select(Publisher).order_by(Publisher.name_key, Publisher.id), Publisher, q)
    return paginate(db, stmt, page, lambda p: PublisherOut(id=p.id, name=p.name))


@router.get("/publishers/{publisher_id}", response_model=PublisherOut)
def get_publisher(publisher_id: PublisherId, db: SessionDep, _: AnyUser) -> PublisherOut:
    publisher = service.get_publisher_or_404(db, publisher_id)
    return PublisherOut(id=publisher.id, name=publisher.name)


@router.patch("/publishers/{publisher_id}", response_model=PublisherOut)
def update_publisher(publisher_id: PublisherId, body: NamePatchIn, db: SessionDep, _: StaffOnly) -> PublisherOut:
    publisher = service.update_publisher(db, service.get_publisher_or_404(db, publisher_id), body.name)
    return PublisherOut(id=publisher.id, name=publisher.name)


@router.delete("/publishers/{publisher_id}", status_code=204)
def delete_publisher(publisher_id: PublisherId, db: SessionDep, _: StaffOnly) -> Response:
    service.delete_publisher(db, service.get_publisher_or_404(db, publisher_id))
    return Response(status_code=204)


# --- books ------------------------------------------------------------------------


@router.post("/books", response_model=BookOut, status_code=201)
def create_book(body: BookCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> BookOut:
    now = _now(request)
    service.check_publication_year(body.publication_year, now.date())
    book = service.create_book(db, now, staff.user, **body.model_dump())
    return service.book_out(db, book)


@router.get("/books", response_model=Page[BookOut])
def list_books(
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    isbn: Annotated[str | None, Query()] = None,
    author_id: Annotated[int | None, Query()] = None,
    publisher_id: Annotated[int | None, Query()] = None,
    language: Annotated[str | None, Query()] = None,
    classification_prefix: Annotated[str | None, Query()] = None,
) -> Page[BookOut]:
    stmt = sa.select(Book).order_by(Book.title_key, Book.id)
    if isbn is not None:
        try:
            stmt = stmt.where(Book.isbn == normalize_isbn(isbn.strip()))
        except ValueError as exc:
            raise ValidationFailed.single("isbn", str(exc)) from None
    if author_id is not None:
        stmt = stmt.where(Book.id.in_(sa.select(BookAuthor.book_id).where(BookAuthor.author_id == author_id)))
    if publisher_id is not None:
        stmt = stmt.where(Book.publisher_id == publisher_id)
    if language is not None:
        stmt = stmt.where(Book.language == language.strip())
    if classification_prefix is not None and classification_prefix.strip():
        stmt = stmt.where(Book.classification.startswith(classification_prefix.strip(), autoescape=True))
    return paginate(db, stmt, page, lambda b: service.book_out(db, b))


@router.get("/books/{book_id}", response_model=BookOut)
def get_book(book_id: BookId, db: SessionDep, _: AnyUser) -> BookOut:
    return service.book_out(db, service.get_book_or_404(db, book_id))


@router.patch("/books/{book_id}", response_model=BookOut)
def update_book(book_id: BookId, body: BookPatchIn, request: Request, db: SessionDep, staff: StaffOnly) -> BookOut:
    now = _now(request)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    if "publication_year" in fields:
        service.check_publication_year(fields["publication_year"], now.date())
    book = service.get_book_or_404(db, book_id)
    return service.book_out(db, service.update_book(db, now, staff.user, book, fields))


@router.delete("/books/{book_id}", status_code=204)
def delete_book(book_id: BookId, request: Request, db: SessionDep, staff: StaffOnly) -> Response:
    service.delete_book(db, _now(request), staff.user, service.get_book_or_404(db, book_id))
    return Response(status_code=204)


# --- copies -----------------------------------------------------------------------


@router.post("/books/{book_id}/copies", response_model=CopyOut, status_code=201)
def add_copy(book_id: BookId, body: CopyCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> CopyOut:
    now = _now(request)
    acquired_on = body.acquired_on if body.acquired_on is not None else now.date()
    service.check_acquired_on(acquired_on, now.date())
    book = service.get_book_or_404(db, book_id)
    copy = service.add_copy(
        db,
        now,
        staff.user,
        book,
        barcode=body.barcode,
        home_branch_id=body.home_branch_id,
        price=body.price,
        acquired_on=acquired_on,
        shelf_location=body.shelf_location,
    )
    return copy_out(copy)


@router.get("/books/{book_id}/copies", response_model=Page[CopyOut])
def list_copies(
    book_id: BookId,
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    status: Annotated[CopyStatus | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[CopyOut]:
    book = service.get_book_or_404(db, book_id)
    stmt = sa.select(Copy).where(Copy.book_id == book.id).order_by(Copy.id)
    if status is not None:
        stmt = stmt.where(Copy.status == status)
    if branch_id is not None:
        stmt = stmt.where(Copy.current_branch_id == branch_id)
    return paginate(db, stmt, page, copy_out)


@router.get("/copies/by-barcode/{barcode}", response_model=CopyOut)
def get_copy_by_barcode(barcode: str, db: SessionDep, _: AnyUser) -> CopyOut:
    return copy_out(service.get_copy_by_barcode_or_404(db, barcode.strip()))


@router.get("/copies/{copy_id}", response_model=CopyOut)
def get_copy(copy_id: CopyId, db: SessionDep, _: AnyUser) -> CopyOut:
    return copy_out(service.get_copy_or_404(db, copy_id))


@router.patch("/copies/{copy_id}", response_model=CopyOut)
def update_copy(copy_id: CopyId, body: CopyPatchIn, request: Request, db: SessionDep, staff: StaffOnly) -> CopyOut:
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    copy = service.get_copy_or_404(db, copy_id)
    return copy_out(service.update_copy(db, _now(request), staff.user, copy, fields))


@router.post("/copies/{copy_id}/withdraw", response_model=CopyOut)
def withdraw_copy(copy_id: CopyId, body: WithdrawIn, request: Request, db: SessionDep, staff: StaffOnly) -> CopyOut:
    copy = service.get_copy_or_404(db, copy_id)
    return copy_out(service.withdraw_copy(db, _now(request), staff.user, copy, body.reason))


@router.post("/copies/{copy_id}/repair", response_model=CopyOut)
def repair_copy(copy_id: CopyId, request: Request, db: SessionDep, staff: StaffOnly) -> CopyOut:
    copy = service.get_copy_or_404(db, copy_id)
    return copy_out(service.repair_copy(db, _now(request), staff.user, copy))
