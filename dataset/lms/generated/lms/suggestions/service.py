"""Suggesting, changing, withdrawing and supporting (LIB-SUG-01 to LIB-SUG-14, LIB-SUG-46)."""

from __future__ import annotations

import dataclasses
import datetime
from collections import defaultdict
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.isbn import normalize_isbn
from lms.catalog.models import Book
from lms.catalog.service import is_lendable
from lms.core.db import get_or_404, get_reference
from lms.core.errors import Conflict, NotFound, ValidationFailed
from lms.core.money import format_amount
from lms.core.text import normalize
from lms.core.timeutil import format_datetime
from lms.members.models import Member
from lms.suggestions import rules
from lms.suggestions.models import OPEN_STATUSES, Suggestion, Support
from lms.suggestions.schemas import SuggestionOut, SupporterOut

# --- reading --------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Viewer:
    """Who reads suggestions: staff see everything; a member sees ``mine`` and ``supported_by_me`` and no
    ``member_id`` of other members' suggestions (LIB-SUG-02, LIB-SUG-12)."""

    member_id: int | None = None  # None for staff
    hide_member_id: bool = False

    @property
    def is_staff(self) -> bool:
        return self.member_id is None


STAFF = Viewer()


def get_suggestion_or_404(db: Session, suggestion_id: int) -> Suggestion:
    return get_or_404(db, Suggestion, suggestion_id, "Suggestion", "suggestion")


def _weight_case() -> Any:
    return sa.case(rules.WEIGHTS, value=Member.membership_type, else_=0)


def score_expr() -> Any:
    """LIB-SUG-12: the score of a suggestion as an SQL expression, for ordering."""
    owner = sa.select(_weight_case()).where(Member.id == Suggestion.member_id).correlate(Suggestion).scalar_subquery()
    supporters = (
        sa.select(sa.func.coalesce(sa.func.sum(_weight_case()), 0))
        .select_from(Support)
        .join(Member, Member.id == Support.member_id)
        .where(Support.suggestion_id == Suggestion.id)
        .correlate(Suggestion)
        .scalar_subquery()
    )
    return sa.func.coalesce(owner, 0) + supporters


def stats(db: Session, suggestions: list[Suggestion]) -> dict[int, tuple[int, int]]:
    """``{suggestion_id: (score, supporters)}`` (LIB-SUG-02)."""
    if not suggestions:
        return {}
    ids = [s.id for s in suggestions]
    score: dict[int, int] = defaultdict(int)
    count: dict[int, int] = defaultdict(int)
    owners = db.execute(
        sa.select(Member.id, Member.membership_type).where(Member.id.in_({s.member_id for s in suggestions}))
    )
    type_of = dict(owners.all())
    for s in suggestions:
        score[s.id] += rules.WEIGHTS.get(type_of[s.member_id], 0)
    rows = db.execute(
        sa.select(Support.suggestion_id, Member.membership_type)
        .join(Member, Member.id == Support.member_id)
        .where(Support.suggestion_id.in_(ids))
    )
    for suggestion_id, membership_type in rows:
        score[suggestion_id] += rules.WEIGHTS.get(membership_type, 0)
        count[suggestion_id] += 1
    return {i: (score[i], count[i]) for i in ids}


def to_outs(db: Session, suggestions: list[Suggestion], viewer: Viewer) -> list[SuggestionOut]:
    figures = stats(db, suggestions)
    supported: set[int] = set()
    if not viewer.is_staff and suggestions:
        supported = set(
            db.scalars(
                sa.select(Support.suggestion_id).where(
                    Support.member_id == viewer.member_id, Support.suggestion_id.in_([s.id for s in suggestions])
                )
            )
        )
    outs = []
    for s in suggestions:
        score, supporters = figures[s.id]
        fields: dict[str, Any] = dict(
            id=s.id,
            title=s.title,
            author_text=s.author_text,
            isbn=s.isbn,
            publication_year=s.publication_year,
            reason=s.reason,
            branch_id=s.branch_id,
            status=s.status,
            reject_reason=s.reject_reason,
            review_note=s.review_note,
            book_id=s.book_id,
            quantity=s.quantity,
            estimated_price=format_amount(s.estimated_price) if s.estimated_price is not None else None,
            purchase_order_id=s.purchase_order_id,
            merged_into_id=s.merged_into_id,
            withdraw_reason=s.withdraw_reason,
            submitted_at=format_datetime(s.submitted_at),
            reviewed_at=format_datetime(s.reviewed_at) if s.reviewed_at is not None else None,
            ordered_at=format_datetime(s.ordered_at) if s.ordered_at is not None else None,
            available_at=format_datetime(s.available_at) if s.available_at is not None else None,
            score=score,
            supporters=supporters,
        )
        if viewer.is_staff:
            fields["member_id"] = s.member_id
        else:
            mine = s.member_id == viewer.member_id
            if mine and not viewer.hide_member_id:
                fields["member_id"] = s.member_id
            fields["mine"] = mine
            fields["supported_by_me"] = s.id in supported
        outs.append(SuggestionOut(**fields))
    return outs


def to_out(db: Session, suggestion: Suggestion, viewer: Viewer) -> SuggestionOut:
    return to_outs(db, [suggestion], viewer)[0]


def list_stmt(
    viewer: Viewer,
    *,
    status: str | None,
    branch_id: int | None,
    member_id: int | None,
    q: str | None,
    isbn: str | None,
) -> sa.Select[tuple[Suggestion]]:
    """LIB-SUG-12."""
    stmt = sa.select(Suggestion).order_by(score_expr().desc(), Suggestion.submitted_at, Suggestion.id)
    if not viewer.is_staff:
        stmt = stmt.where(Suggestion.status.in_(OPEN_STATUSES))
    elif member_id is not None:
        stmt = stmt.where(Suggestion.member_id == member_id)
    if status is not None:
        stmt = stmt.where(Suggestion.status == status)
    if branch_id is not None:
        stmt = stmt.where(Suggestion.branch_id == branch_id)
    needle = normalize(q.strip()) if q is not None else ""
    if needle:
        stmt = stmt.where(
            sa.or_(
                sa.func.lms_normalize(Suggestion.title).contains(needle, autoescape=True),
                sa.func.lms_normalize(Suggestion.author_text).contains(needle, autoescape=True),
            )
        )
    if isbn is not None:
        try:
            stmt = stmt.where(Suggestion.isbn == normalize_isbn(isbn.strip()))
        except ValueError as exc:
            raise ValidationFailed.single("isbn", str(exc)) from None
    return stmt


def member_suggestions(db: Session, member_id: int, viewer: Viewer) -> tuple[list[SuggestionOut], list[SuggestionOut]]:
    """LIB-SUG-11."""
    own = list(db.scalars(sa.select(Suggestion).where(Suggestion.member_id == member_id).order_by(Suggestion.id.desc())))
    supported = list(
        db.scalars(
            sa.select(Suggestion)
            .join(Support, Support.suggestion_id == Suggestion.id)
            .where(Support.member_id == member_id, Suggestion.status.in_(OPEN_STATUSES))
            .order_by(Suggestion.id.desc())
        )
    )
    return to_outs(db, own, viewer), to_outs(db, supported, viewer)


def supporters_stmt(suggestion_id: int) -> sa.Select[Any]:
    """LIB-SUG-10."""
    return (
        sa.select(Support, Member)
        .join(Member, Member.id == Support.member_id)
        .where(Support.suggestion_id == suggestion_id)
        .order_by(Support.created_at, Support.member_id)
    )


def supporter_out(row: Any) -> SupporterOut:
    support, member = row
    return SupporterOut(
        member_id=member.id,
        full_name=member.full_name,
        membership_type=member.membership_type,
        reserve_on_arrival=support.reserve_on_arrival,
        created_at=format_datetime(support.created_at),
    )


def supporters_of(db: Session, suggestion_id: int) -> list[Support]:
    """The supports of a suggestion in support order."""
    return list(
        db.scalars(
            sa.select(Support).where(Support.suggestion_id == suggestion_id).order_by(Support.created_at, Support.id)
        )
    )


# --- checks ---------------------------------------------------------------------------------


def invalid_status(suggestion: Suggestion, action: str) -> Conflict:
    """LIB-SUG-46 and the other ``INVALID_SUGGESTION_STATUS`` cases."""
    return Conflict(
        f"Suggestion {suggestion.id} has status {suggestion.status}: {action} is not allowed",
        code="INVALID_SUGGESTION_STATUS",
        details={"id": suggestion.id, "status": suggestion.status},
    )


def check_may_take_part(member: Member) -> None:
    """LIB-SUG-03 steps 1 and 2, LIB-SUG-07."""
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if member.membership_type == "guest":
        raise Conflict(
            "Guests cannot suggest or support books",
            code="MEMBERSHIP_TYPE_NOT_ALLOWED",
            details={"membership_type": member.membership_type},
        )


def require_known_branch(db: Session, branch_id: int) -> Branch:
    """An unknown branch is a ``422`` here (LIB-SUG-01)."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise ValidationFailed.single("branch_id", f"branch {branch_id} does not exist")
    return branch


def check_year(year: int | None, today: datetime.date) -> None:
    if year is not None and year > today.year:
        raise ValidationFailed.single("publication_year", f"publication_year must be between {rules.MIN_YEAR} and {today.year}")


def _check_branch_active(branch: Branch) -> None:
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "branch_id", "id": branch.id},
        )


def _check_isbn_free(db: Session, isbn: str, own_id: int | None) -> None:
    """LIB-SUG-03 steps 5 and 6."""
    book_id = db.scalar(sa.select(Book.id).where(Book.isbn == isbn))
    if book_id is not None and is_lendable(db, book_id):
        raise Conflict(
            "The library already owns this book", code="BOOK_ALREADY_OWNED", details={"book_id": book_id}
        )
    stmt = sa.select(Suggestion.id).where(Suggestion.isbn == isbn, Suggestion.status.in_(OPEN_STATUSES))
    if own_id is not None:
        stmt = stmt.where(Suggestion.id != own_id)
    duplicate = db.scalar(stmt.order_by(Suggestion.id).limit(1))
    if duplicate is not None:
        raise Conflict(
            "An open suggestion for this ISBN exists", code="DUPLICATE_SUGGESTION", details={"suggestion_id": duplicate}
        )


def _check_recently_rejected(db: Session, member_id: int, isbn: str, today: datetime.date) -> None:
    """LIB-SUG-03 step 7."""
    last = db.scalar(
        sa.select(sa.func.max(Suggestion.reviewed_at)).where(
            Suggestion.member_id == member_id, Suggestion.isbn == isbn, Suggestion.status == "rejected"
        )
    )
    if last is None:
        return
    until = last.date() + datetime.timedelta(days=rules.REJECTED_DAYS)
    if today < until:
        raise Conflict(
            "The same ISBN was rejected recently",
            code="SUGGESTION_RECENTLY_REJECTED",
            details={"until": until.isoformat()},
        )


# --- suggest, change, withdraw ------------------------------------------------------------------


def suggest(
    db: Session,
    now: datetime.datetime,
    actor: User,
    member: Member,
    branch: Branch,
    *,
    title: str,
    author_text: str,
    isbn: str | None,
    publication_year: int | None,
    reason: str,
) -> Suggestion:
    """LIB-SUG-01, LIB-SUG-03."""
    check_may_take_part(member)
    _check_branch_active(branch)
    limit = rules.OPEN_LIMITS[member.membership_type]
    open_count = db.scalar(
        sa.select(sa.func.count())
        .select_from(Suggestion)
        .where(Suggestion.member_id == member.id, Suggestion.status.in_(OPEN_STATUSES))
    )
    if (open_count or 0) >= limit:
        raise Conflict(
            "The member has reached the limit of open suggestions",
            code="SUGGESTION_LIMIT_REACHED",
            details={"limit": limit},
        )
    if isbn is not None:
        _check_isbn_free(db, isbn, None)
        _check_recently_rejected(db, member.id, isbn, now.date())
    suggestion = Suggestion(
        member_id=member.id,
        title=title,
        author_text=author_text,
        isbn=isbn,
        publication_year=publication_year,
        reason=reason,
        branch_id=branch.id,
        status="submitted",
        review_note="",
        submitted_at=now,
    )
    db.add(suggestion)
    db.flush()
    record(
        db,
        at=now,
        event="suggestion_submitted",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=suggestion.id,
        details={
            "member_id": member.id,
            "title": title,
            "author_text": author_text,
            "isbn": isbn,
            "publication_year": publication_year,
            "reason": reason,
            "branch_id": branch.id,
        },
    )
    return suggestion


def update(
    db: Session, now: datetime.datetime, actor: User, suggestion: Suggestion, fields: dict[str, Any]
) -> Suggestion:
    """LIB-SUG-05. ``fields`` holds only the fields present in the request."""
    if suggestion.status != "submitted":
        raise invalid_status(suggestion, "change")
    if "branch_id" in fields and fields["branch_id"] != suggestion.branch_id:
        _check_branch_active(db.get(Branch, fields["branch_id"]))  # type: ignore[arg-type]
    isbn = fields.get("isbn")
    if isbn is not None and isbn != suggestion.isbn:
        _check_isbn_free(db, isbn, suggestion.id)
    diff = changes({name: getattr(suggestion, name) for name in fields}, fields)
    for name, value in fields.items():
        setattr(suggestion, name, value)
    if diff:
        record(
            db,
            at=now,
            event="suggestion_updated",
            actor_user_id=actor.id,
            entity_type="suggestion",
            entity_id=suggestion.id,
            details=diff,
        )
    return suggestion


def withdraw(db: Session, now: datetime.datetime, actor: User, suggestion: Suggestion, *, by_member: bool) -> Suggestion:
    """LIB-SUG-06, LIB-SUG-14."""
    allowed = ("submitted",) if by_member else ("submitted", "approved")
    if suggestion.status not in allowed:
        raise invalid_status(suggestion, "withdraw")
    if by_member:
        supporters = db.scalar(
            sa.select(sa.func.count()).select_from(Support).where(Support.suggestion_id == suggestion.id)
        )
        if (supporters or 0) >= rules.SUPPORTERS_TO_KEEP:
            raise Conflict(
                "The suggestion has too many supporters to be withdrawn by the member",
                code="SUGGESTION_HAS_SUPPORTERS",
                details={"id": suggestion.id, "supporters": supporters},
            )
    old = suggestion.status
    suggestion.status = "withdrawn"
    suggestion.withdraw_reason = "member_request"
    record(
        db,
        at=now,
        event="suggestion_withdrawn",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=suggestion.id,
        details={"status": {"old": old, "new": "withdrawn"}, "withdraw_reason": "member_request"},
    )
    return suggestion


# --- support ----------------------------------------------------------------------------------


def support(
    db: Session, now: datetime.datetime, actor: User, member: Member, suggestion: Suggestion, reserve_on_arrival: bool
) -> Support:
    """LIB-SUG-07, LIB-SUG-13."""
    check_may_take_part(member)
    if not suggestion.is_open:
        raise invalid_status(suggestion, "support")
    if suggestion.member_id == member.id:
        raise Conflict("A member cannot support their own suggestion", code="CANNOT_SUPPORT_OWN")
    existing = db.scalar(
        sa.select(Support.id).where(Support.suggestion_id == suggestion.id, Support.member_id == member.id)
    )
    if existing is not None:
        raise Conflict("The member already supports this suggestion", code="ALREADY_SUPPORTED")
    supported = db.scalar(
        sa.select(sa.func.count())
        .select_from(Support)
        .join(Suggestion, Suggestion.id == Support.suggestion_id)
        .where(Support.member_id == member.id, Suggestion.status.in_(OPEN_STATUSES))
    )
    if (supported or 0) >= rules.SUPPORT_LIMIT:
        raise Conflict(
            "The member has reached the limit of supported suggestions",
            code="SUPPORT_LIMIT_REACHED",
            details={"limit": rules.SUPPORT_LIMIT},
        )
    row = Support(
        suggestion_id=suggestion.id, member_id=member.id, reserve_on_arrival=reserve_on_arrival, created_at=now
    )
    db.add(row)
    db.flush()
    record(
        db,
        at=now,
        event="suggestion_supported",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=suggestion.id,
        details={"member_id": member.id, "reserve_on_arrival": reserve_on_arrival},
    )
    return row


def remove_support(db: Session, now: datetime.datetime, actor: User, member: Member, suggestion: Suggestion) -> None:
    """LIB-SUG-08."""
    row = db.scalar(
        sa.select(Support).where(Support.suggestion_id == suggestion.id, Support.member_id == member.id)
    )
    if row is None:
        raise NotFound(
            "The member does not support this suggestion",
            details={"resource": "support", "suggestion_id": suggestion.id, "member_id": member.id},
        )
    if not suggestion.is_open:
        raise invalid_status(suggestion, "stop supporting")
    db.delete(row)
    db.flush()
    record(
        db,
        at=now,
        event="suggestion_support_removed",
        actor_user_id=actor.id,
        entity_type="suggestion",
        entity_id=suggestion.id,
        details={"member_id": member.id},
    )


def get_member_or_reference_404(db: Session, member_id: int) -> Member:
    return get_reference(db, Member, "member_id", member_id)
