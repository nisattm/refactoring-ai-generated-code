"""Gate scans, closing visits and the daily process (LIB-ACC-14 to LIB-ACC-24, LIB-ACC-45, LIB-ACC-52)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any, NoReturn

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.cards import expire_cards
from lms.access.models import AccessAlert, AccessBan, Card, DayPass, DeniedScan, Visit
from lms.access.occupancy import occupancy, settings_of
from lms.access.schemas import ProcessOut, ScanOut
from lms.access.usage import find_card, open_visit_of_member
from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.clock import LOCAL_TZ
from lms.core.errors import Conflict, NotFound
from lms.equipment.rules import desk_open
from lms.members.models import Member
from lms.notifications.service import notify_access
from lms.staff.schedule import load_schedule


def _deny(
    db: Session,
    now: datetime.datetime,
    branch_id: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    card: Card | None = None,
    day_pass: DayPass | None = None,
) -> NoReturn:
    """A refused entry scan is stored with its error code (LIB-ACC-45); the refusal itself keeps its
    changes (LIB-TECH-08 exception, like a failed login): they are committed before the error is raised."""
    db.add(
        DeniedScan(
            branch_id=branch_id,
            code=code,
            card_id=card.id if card is not None else None,
            day_pass_id=day_pass.id if day_pass is not None else None,
            at=now,
        )
    )
    if card is not None and code == "CARD_NOT_ACTIVE" and card.status == "lost":  # LIB-ACC-21
        db.add(AccessAlert(card_id=card.id, branch_id=branch_id, at=now))
        notify_access(
            db,
            now,
            card.member_id,
            "lost_card_used",
            f"Your lost library card {card.card_no} was used at the gate.",
            card_id=card.id,
        )
    db.commit()
    raise Conflict(message, code=code, details=details or {})


def branch_open_now(
    db: Session, now: datetime.datetime, holidays: Container[datetime.date], branch_id: int
) -> bool:
    """LIB-STF-09: the branch is open on the date and within its hours."""
    return desk_open(now, holidays, load_schedule(db, branch_id))


def _open_visit_of_pass(db: Session, day_pass_id: int) -> Visit | None:
    stmt = sa.select(Visit).where(Visit.day_pass_id == day_pass_id, Visit.left_at.is_(None))
    return db.scalar(stmt.limit(1))


def _scanned(
    db: Session, now: datetime.datetime, actor: User, direction: str, result: str, visit: Visit
) -> ScanOut:
    record(
        db,
        at=now,
        event="access_scanned",
        actor_user_id=actor.id,
        entity_type="visit",
        entity_id=visit.id,
        details={
            "branch_id": visit.branch_id,
            "direction": direction,
            "result": result,
            "member_id": visit.member_id,
            "day_pass_id": visit.day_pass_id,
            "card_id": visit.card_id,
        },
    )
    return ScanOut(result=result, visit_id=visit.id, member_id=visit.member_id, day_pass_id=visit.day_pass_id)


def _leave(db: Session, now: datetime.datetime, branch: Branch, visit: Visit | None) -> Visit:
    """LIB-ACC-17: close the open visit of the scanned person (``exit``)."""
    if visit is None:
        raise Conflict("The person is not inside", code="NOT_INSIDE")
    if visit.branch_id != branch.id:
        raise Conflict(
            "The person is inside another branch", code="WRONG_BRANCH", details={"branch_id": visit.branch_id}
        )
    visit.left_at = now
    visit.closed_by = "exit"
    return visit


def scan(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    branch: Branch,
    direction: str,
    card_no: str | None,
    pass_code: str | None,
) -> ScanOut:
    """LIB-ACC-14 to LIB-ACC-19."""
    if card_no is not None:
        card = find_card(db, card_no)
        if card is None:
            raise NotFound(f"Card {card_no} does not exist", details={"resource": "card", "card_no": card_no})
        if direction == "out":
            visit = _leave(db, now, branch, open_visit_of_member(db, card.member_id))
            return _scanned(db, now, actor, direction, "left", visit)
        visit = _enter_member(db, now, holidays, branch, card)
        return _scanned(db, now, actor, direction, "entered", visit)

    assert pass_code is not None
    day_pass = db.scalar(sa.select(DayPass).where(DayPass.code == pass_code))
    if day_pass is None:
        raise NotFound(f"Day pass {pass_code} does not exist", details={"resource": "day_pass", "code": pass_code})
    if direction == "out":
        visit = _leave(db, now, branch, _open_visit_of_pass(db, day_pass.id))
        return _scanned(db, now, actor, direction, "left", visit)
    visit = _enter_pass(db, now, holidays, branch, day_pass)
    return _scanned(db, now, actor, direction, "entered", visit)


def _check_capacity(db: Session, now: datetime.datetime, branch: Branch, **who: Any) -> None:
    capacity = settings_of(db, branch.id)["capacity"]
    if capacity is not None and occupancy(db, branch.id) >= capacity:
        _deny(db, now, branch.id, "BRANCH_FULL", "The branch is full", {"capacity": capacity}, **who)


def _enter_member(
    db: Session, now: datetime.datetime, holidays: Container[datetime.date], branch: Branch, card: Card
) -> Visit:
    """LIB-ACC-15, LIB-ACC-16."""
    today = now.date()
    if card.status != "active":
        _deny(db, now, branch.id, "CARD_NOT_ACTIVE", "The card is not active", {"status": card.status}, card=card)
    member = db.get(Member, card.member_id)
    assert member is not None
    if member.status == "passive":
        _deny(db, now, branch.id, "MEMBER_PASSIVE", "The member is passive", card=card)
    if today > member.valid_until:
        _deny(db, now, branch.id, "MEMBERSHIP_EXPIRED", "The membership has expired", card=card)
    if not branch.is_active:
        _deny(
            db,
            now,
            branch.id,
            "BRANCH_INACTIVE",
            f"Branch {branch.code} is inactive",
            {"field": "branch_id", "id": branch.id},
            card=card,
        )
    if not branch_open_now(db, now, holidays, branch.id):
        _deny(db, now, branch.id, "BRANCH_NOT_OPEN", "The branch is not open now", {"branch_id": branch.id}, card=card)
    ban = db.scalar(
        sa.select(AccessBan)
        .where(
            AccessBan.member_id == member.id,
            AccessBan.lifted_at.is_(None),
            AccessBan.starts_on <= today,
            AccessBan.ends_on >= today,
        )
        .order_by(AccessBan.ends_on.desc(), AccessBan.id.desc())
        .limit(1)
    )
    if ban is not None:
        _deny(
            db,
            now,
            branch.id,
            "ACCESS_BANNED",
            "The member is banned from entering",
            {"ends_on": ban.ends_on.isoformat()},
            card=card,
        )
    if member.membership_type == "guest" and not settings_of(db, branch.id)["guest_entry"]:
        _deny(db, now, branch.id, "GUEST_ENTRY_NOT_ALLOWED", "Guests may not enter this branch", card=card)
    inside = open_visit_of_member(db, member.id)
    if inside is not None:
        _deny(
            db,
            now,
            branch.id,
            "ALREADY_INSIDE",
            "The member is already inside",
            {"branch_id": inside.branch_id},
            card=card,
        )
    _check_capacity(db, now, branch, card=card)
    visit = Visit(branch_id=branch.id, member_id=member.id, card_id=card.id, entered_at=now)
    db.add(visit)
    db.flush()
    return visit


def _enter_pass(
    db: Session, now: datetime.datetime, holidays: Container[datetime.date], branch: Branch, day_pass: DayPass
) -> Visit:
    """LIB-ACC-19."""
    if day_pass.branch_id != branch.id:
        _deny(
            db,
            now,
            branch.id,
            "WRONG_BRANCH",
            "The day pass belongs to another branch",
            {"branch_id": day_pass.branch_id},
            day_pass=day_pass,
        )
    if day_pass.valid_on != now.date():
        _deny(
            db,
            now,
            branch.id,
            "PASS_NOT_VALID_TODAY",
            "The day pass is not valid today",
            {"valid_on": day_pass.valid_on.isoformat()},
            day_pass=day_pass,
        )
    if day_pass.status != "unused":
        _deny(
            db,
            now,
            branch.id,
            "PASS_NOT_USABLE",
            "The day pass cannot be used",
            {"status": day_pass.status},
            day_pass=day_pass,
        )
    if not branch_open_now(db, now, holidays, branch.id):
        _deny(
            db,
            now,
            branch.id,
            "BRANCH_NOT_OPEN",
            "The branch is not open now",
            {"branch_id": branch.id},
            day_pass=day_pass,
        )
    _check_capacity(db, now, branch, day_pass=day_pass)
    day_pass.status = "used"
    visit = Visit(branch_id=branch.id, day_pass_id=day_pass.id, entered_at=now)
    db.add(visit)
    db.flush()
    return visit


# --- closing --------------------------------------------------------------------------------------


def get_visit_or_404(db: Session, visit_id: int) -> Visit:
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise NotFound(f"Visit {visit_id} does not exist", details={"resource": "visit", "id": visit_id})
    return visit


def close_by_hand(db: Session, now: datetime.datetime, actor: User, visit: Visit) -> Visit:
    """LIB-ACC-20."""
    if visit.left_at is not None:
        raise Conflict("The visit is already ended", code="VISIT_NOT_OPEN")
    visit.left_at = now
    visit.closed_by = "staff"
    record(
        db,
        at=now,
        event="visit_closed",
        actor_user_id=actor.id,
        entity_type="visit",
        entity_id=visit.id,
        details={"branch_id": visit.branch_id, "member_id": visit.member_id, "day_pass_id": visit.day_pass_id},
    )
    return visit


def close_after_hours(db: Session, now: datetime.datetime, holidays: Container[datetime.date]) -> int:
    """LIB-ACC-22: open visits of a branch that is not open now are ended at closing time."""
    visits = db.scalars(sa.select(Visit).where(Visit.left_at.is_(None)).order_by(Visit.id)).all()
    open_cache: dict[int, bool] = {}
    closed = 0
    for visit in visits:
        if visit.branch_id not in open_cache:
            open_cache[visit.branch_id] = branch_open_now(db, now, holidays, visit.branch_id)
        if open_cache[visit.branch_id]:
            continue
        closes_at = load_schedule(db, visit.branch_id).closes_at
        closing = datetime.datetime.combine(visit.entered_at.astimezone(LOCAL_TZ).date(), closes_at, LOCAL_TZ)
        visit.left_at = min(closing, now)
        visit.closed_by = "closing"
        closed += 1
    db.flush()
    return closed


def expire_passes(db: Session, today: datetime.date) -> int:
    """LIB-ACC-24: ``unused`` passes with ``valid_on`` before today become ``cancelled``."""
    passes = db.scalars(sa.select(DayPass).where(DayPass.status == "unused", DayPass.valid_on < today)).all()
    for day_pass in passes:
        day_pass.status = "cancelled"
    db.flush()
    return len(passes)


def process(db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date]) -> ProcessOut:
    """LIB-ACC-08, LIB-ACC-22, LIB-ACC-24."""
    result = ProcessOut(
        visits_closed=close_after_hours(db, now, holidays),
        cards_expired=expire_cards(db, now.date()),
        passes_expired=expire_passes(db, now.date()),
    )
    record(
        db,
        at=now,
        event="access_processed",
        actor_user_id=actor.id,
        entity_type="access",
        entity_id=None,
        details=result.model_dump(),
    )
    return result
