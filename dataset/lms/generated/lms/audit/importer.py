"""Import of a JSON dataset (LIB-IO-01 to LIB-IO-06, LIB-IO-10, LIB-IO-11, LIB-IF-11)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.orm import Session

from lms.audit.exchange_schemas import FORMAT_VERSION, LISTS, RECORD_MODELS
from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Author, Book, BookAuthor, Copy, Publisher
from lms.core.calendar import working_days_between
from lms.core.errors import Conflict, ValidationFailed
from lms.core.text import normalize
from lms.loans.models import Loan
from lms.members.models import Member
from lms.members.service import type_field_problems
from lms.members.types import MEMBERSHIP_TYPES

MAX_PROBLEMS = 100
# LIB-IO-05: not a valid ``scrypt$salt$hash`` value, so no password ever matches.
UNUSABLE_PASSWORD_HASH = "!"


class _Problems:
    """Collects at most ``MAX_PROBLEMS`` problems (LIB-IO-03)."""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, field: str, problem: str) -> None:
        if len(self.items) < MAX_PROBLEMS:
            self.items.append({"field": field, "problem": problem})

    def __bool__(self) -> bool:
        return bool(self.items)


def _path(name: str, index: int, field: str | None = None) -> str:
    return f"{name}[{index}]" if field is None else f"{name}[{index}].{field}"


def _error_field(name: str, index: int, loc: tuple[Any, ...]) -> str:
    return _path(name, index, ".".join(str(part) for part in loc) or None)


# --- structure ------------------------------------------------------------------------


def _parse(data: Any, problems: _Problems) -> dict[str, list[Any]]:
    """Validate the document layout and every record on its own. Returns the valid records
    (``None`` in place of an invalid one, so list positions stay meaningful)."""
    parsed: dict[str, list[Any]] = {name: [] for name in LISTS}
    if not isinstance(data, dict):
        problems.add("body", "the dataset must be a JSON object")
        return parsed
    version = data.get("format_version")
    if "format_version" not in data:
        problems.add("format_version", "field required")
    elif isinstance(version, bool) or version != FORMAT_VERSION:
        problems.add("format_version", f"format_version must be {FORMAT_VERSION}")
    for key in data:
        if key != "format_version" and key not in LISTS:
            problems.add(str(key), "unknown field")
    for name in LISTS:
        if name not in data:
            problems.add(name, "field required")
            continue
        items = data[name]
        if not isinstance(items, list):
            problems.add(name, "must be a list")
            continue
        model = RECORD_MODELS[name]
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                problems.add(_path(name, index), "must be an object")
                parsed[name].append(None)
                continue
            try:
                parsed[name].append(model.model_validate(item))
            except ValidationError as exc:
                parsed[name].append(None)
                seen: set[str] = set()
                for err in exc.errors():
                    field = _error_field(name, index, tuple(err["loc"]))
                    if field not in seen:
                        seen.add(field)
                        problems.add(field, str(err["msg"]))
    return parsed


# --- references and consistency ---------------------------------------------------------


def _raw_ids(data: Any, name: str) -> set[int]:
    items = data.get(name) if isinstance(data, dict) else None
    if not isinstance(items, list):
        return set()
    return {
        item["id"]
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), int) and not isinstance(item["id"], bool)
    }


def _check_unique(
    parsed: dict[str, list[Any]], name: str, key: Any, field: str, problem: str, problems: _Problems
) -> None:
    seen: set[Any] = set()
    for index, rec in enumerate(parsed[name]):
        if rec is None:
            continue
        value = key(rec)
        if value is None:
            continue
        if value in seen:
            problems.add(_path(name, index, field), problem)
        seen.add(value)


def _check_consistency(
    parsed: dict[str, list[Any]], data: Any, today: datetime.date, problems: _Problems
) -> None:
    ids = {name: _raw_ids(data, name) for name in LISTS}
    for name in LISTS:
        _check_unique(parsed, name, lambda r: r.id, "id", "id is used more than once", problems)

    _check_unique(parsed, "branches", lambda r: r.code, "code", "code is already used", problems)
    _check_unique(parsed, "publishers", lambda r: normalize(r.name), "name", "name is already used", problems)
    _check_unique(parsed, "books", lambda r: r.isbn, "isbn", "isbn is already used", problems)
    _check_unique(parsed, "copies", lambda r: r.barcode, "barcode", "barcode is already used", problems)
    _check_unique(parsed, "members", lambda r: r.email, "email", "email is already used", problems)
    _check_unique(
        parsed,
        "members",
        lambda r: normalize(r.university_id) if r.university_id is not None else None,
        "university_id",
        "university_id is already used",
        problems,
    )

    def ref(name: str, index: int, field: str, value: int | None, target: str) -> None:
        if value is not None and value not in ids[target]:
            problems.add(_path(name, index, field), f"{target} id {value} does not exist")

    for index, book in enumerate(parsed["books"]):
        if book is None:
            continue
        ref("books", index, "publisher_id", book.publisher_id, "publishers")
        for author_id in book.author_ids:
            if author_id not in ids["authors"]:
                problems.add(_path("books", index, "author_ids"), f"author {author_id} does not exist")
        if book.publication_year > today.year:
            problems.add(_path("books", index, "publication_year"), f"publication_year must not be after {today.year}")

    for index, copy in enumerate(parsed["copies"]):
        if copy is None:
            continue
        ref("copies", index, "book_id", copy.book_id, "books")
        ref("copies", index, "home_branch_id", copy.home_branch_id, "branches")
        ref("copies", index, "current_branch_id", copy.current_branch_id, "branches")
        if copy.acquired_on > today:
            problems.add(_path("copies", index, "acquired_on"), "acquired_on must not be after today")
        if copy.current_branch_id is None and copy.status in ("available", "on_loan", "damaged"):
            problems.add(
                _path("copies", index, "current_branch_id"), f"a copy with status {copy.status} needs a current branch"
            )

    members: dict[int, Any] = {}
    for index, member in enumerate(parsed["members"]):
        if member is None:
            continue
        members[member.id] = member
        ref("members", index, "home_branch_id", member.home_branch_id, "branches")
        for issue in type_field_problems(member.membership_type, member.phone, member.university_id):
            problems.add(_path("members", index, issue["field"]), issue["problem"])
        if member.valid_until < member.membership_start:
            problems.add(_path("members", index, "valid_until"), "valid_until must not be before membership_start")

    copies = {copy.id: copy for copy in parsed["copies"] if copy is not None}
    open_or_lost_copies: set[int] = set()
    for index, loan in enumerate(parsed["loans"]):
        if loan is None:
            continue
        ref("loans", index, "copy_id", loan.copy_id, "copies")
        ref("loans", index, "member_id", loan.member_id, "members")
        ref("loans", index, "branch_id", loan.branch_id, "branches")
        ref("loans", index, "return_branch_id", loan.return_branch_id, "branches")
        if loan.due_date < loan.loan_date:
            problems.add(_path("loans", index, "due_date"), "due_date must not be before loan_date")
        if loan.status == "returned":
            if loan.returned_on is None:
                problems.add(_path("loans", index, "returned_on"), "returned_on is required for a returned loan")
            elif loan.returned_on < loan.loan_date:
                problems.add(_path("loans", index, "returned_on"), "returned_on must not be before loan_date")
            if loan.return_branch_id is None:
                problems.add(_path("loans", index, "return_branch_id"), "return_branch_id is required for a returned loan")
            continue
        if loan.returned_on is not None:
            problems.add(_path("loans", index, "returned_on"), f"returned_on must be null for a {loan.status} loan")
        if loan.return_branch_id is not None:
            problems.add(_path("loans", index, "return_branch_id"), f"return_branch_id must be null for a {loan.status} loan")
        if loan.copy_id in open_or_lost_copies:
            problems.add(_path("loans", index, "copy_id"), "the copy already has an open or lost loan")
        open_or_lost_copies.add(loan.copy_id)
        copy = copies.get(loan.copy_id)
        if copy is None:
            continue
        if loan.status == "open" and copy.status != "on_loan":
            problems.add(_path("loans", index, "copy_id"), "the copy of an open loan must have status on_loan")
        if loan.status == "lost" and (copy.status not in ("lost", "withdrawn") or copy.current_branch_id is not None):
            problems.add(
                _path("loans", index, "copy_id"),
                "the copy of a lost loan must have status lost and no current branch",
            )


# --- writing ------------------------------------------------------------------------------


def _is_empty(db: Session) -> bool:
    return all(db.scalar(sa.select(model.id).limit(1)) is None for model in (Branch, Book, Member))


def _write(
    db: Session,
    now: datetime.datetime,
    created_by: int,
    holidays: Container[datetime.date],
    parsed: dict[str, list[Any]],
) -> dict[str, int]:
    db.add_all(
        Branch(id=r.id, code=r.code, name=r.name, address=r.address, is_active=r.is_active, created_at=now)
        for r in parsed["branches"]
    )
    db.add_all(Author(id=r.id, name=r.name, name_key=normalize(r.name)) for r in parsed["authors"])
    db.add_all(Publisher(id=r.id, name=r.name, name_key=normalize(r.name)) for r in parsed["publishers"])
    db.flush()
    db.add_all(
        Book(
            id=r.id,
            isbn=r.isbn,
            title=r.title,
            title_key=normalize(r.title),
            subtitle=r.subtitle,
            publisher_id=r.publisher_id,
            publication_year=r.publication_year,
            language=r.language,
            classification=r.classification,
            created_at=now,
        )
        for r in parsed["books"]
    )
    db.flush()
    db.add_all(
        BookAuthor(book_id=r.id, author_id=author_id, position=position)
        for r in parsed["books"]
        for position, author_id in enumerate(r.author_ids)
    )
    db.add_all(
        Copy(
            id=r.id,
            book_id=r.book_id,
            barcode=r.barcode,
            home_branch_id=r.home_branch_id,
            current_branch_id=r.current_branch_id,
            price=r.price,
            status=r.status,
            acquired_on=r.acquired_on,
            shelf_location=r.shelf_location,
        )
        for r in parsed["copies"]
    )
    db.flush()

    users: dict[int, User] = {}
    for r in parsed["members"]:
        users[r.id] = User(
            email=r.email,
            email_key=normalize(r.email),
            full_name=r.full_name,
            role="member",
            password_hash=UNUSABLE_PASSWORD_HASH,
            is_active=True,
            failed_login_count=0,
            created_at=now,
        )
    db.add_all(users.values())
    db.flush()
    db.add_all(
        Member(
            id=r.id,
            full_name=r.full_name,
            email=r.email,
            phone=r.phone,
            membership_type=r.membership_type,
            university_id=r.university_id,
            university_id_key=normalize(r.university_id) if r.university_id is not None else None,
            home_branch_id=r.home_branch_id,
            status=r.status,
            membership_start=r.membership_start,
            valid_until=r.valid_until,
            user_id=users[r.id].id,
            created_at=now,
        )
        for r in parsed["members"]
    )
    db.flush()
    for member_id, user in users.items():
        user.member_id = member_id

    types = {r.id: MEMBERSHIP_TYPES[r.membership_type] for r in parsed["members"]}
    today = now.date()
    loans = []
    for r in parsed["loans"]:
        terms = types[r.member_id]
        late_days = None
        if r.status == "returned":
            assert r.returned_on is not None
            late_days = working_days_between(r.due_date, r.returned_on, holidays)
        elif r.status == "lost":
            late_days = working_days_between(r.due_date, today, holidays)
        loans.append(
            Loan(
                id=r.id,
                copy_id=r.copy_id,
                member_id=r.member_id,
                branch_id=r.branch_id,
                loan_date=r.loan_date,
                due_date=r.due_date,
                loan_period_days=terms.loan_period_days,
                max_renewals=terms.max_renewals,
                daily_fee=terms.daily_fee,
                renewal_count=r.renewal_count,
                status=r.status,
                returned_on=r.returned_on,
                return_branch_id=r.return_branch_id,
                condition_on_return="good" if r.status == "returned" else None,
                late_days=late_days,
                created_by=created_by,
            )
        )
    db.add_all(loans)
    db.flush()
    return {name: len(parsed[name]) for name in LISTS}


def import_data(
    db: Session,
    now: datetime.datetime,
    actor_user_id: int | None,
    holidays: Container[datetime.date],
    data: Any,
) -> dict[str, int]:
    """Import ``data`` into the transaction of ``db``; returns the counts (LIB-IO-01).

    Raises ``ValidationFailed`` (LIB-IO-03) or ``Conflict`` with code ``DATABASE_NOT_EMPTY`` (LIB-IO-02).
    Check order: layout and records (422), then an empty database (409), then checks against stored users (422).
    """
    problems = _Problems()
    parsed = _parse(data, problems)
    _check_consistency(parsed, data, now.date(), problems)
    if problems:
        raise ValidationFailed(problems.items)
    if not _is_empty(db):
        raise Conflict(
            "Import is allowed only when the database has no branch, book or member", code="DATABASE_NOT_EMPTY"
        )

    taken = set(db.scalars(sa.select(User.email_key)))
    for index, member in enumerate(parsed["members"]):
        if normalize(member.email) in taken:
            problems.add(_path("members", index, "email"), "a user with this e-mail address already exists")
    if problems:
        raise ValidationFailed(problems.items)

    created_by = actor_user_id
    if created_by is None:
        created_by = db.scalar(sa.select(User.id).where(User.role == "admin").order_by(User.id).limit(1))
    assert created_by is not None
    counts = _write(db, now, created_by, holidays, parsed)
    record(
        db,
        at=now,
        event="data_imported",
        actor_user_id=actor_user_id,
        entity_type="dataset",
        entity_id=None,
        details=dict(counts),
    )
    return counts
