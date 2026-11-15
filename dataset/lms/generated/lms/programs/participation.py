"""Joining, leaving and reading participations (sections 34.5 and 34.7)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict, NotFound
from lms.core.money import format_amount
from lms.core.timeutil import format_datetime
from lms.events.rules import EVENT_RULES
from lms.fines import service as fines
from lms.members.models import Member
from lms.programs import ranking
from lms.programs.models import Participation, Program
from lms.programs.programs import counts
from lms.programs.rules import DEBT_BLOCK, PROGRAM_LIMIT
from lms.programs.schemas import (
    CertificateOut,
    LeaderboardOut,
    MemberProgramOut,
    ParticipantOut,
    ParticipationOut,
    participation_out,
)


def find(db: Session, program_id: int, member_id: int) -> Participation | None:
    return db.scalar(
        sa.select(Participation).where(Participation.program_id == program_id, Participation.member_id == member_id)
    )


def out(db: Session, participation: Participation) -> ParticipationOut:
    return participation_out(participation, ranking.ranks(db, participation.program_id).get(participation.id))


# --- join and leave -----------------------------------------------------------------------------


def join(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    actor: User,
    program: Program,
    member: Member,
    public: bool | None,
) -> Participation:
    """LIB-RDP-10 to LIB-RDP-12."""
    today = now.date()
    if program.status != "published":
        raise Conflict("The program is not open", code="PROGRAM_NOT_OPEN", details={"status": program.status})
    if program.ends_on < today:
        raise Conflict("The program has ended", code="PROGRAM_ENDED", details={"ends_on": program.ends_on.isoformat()})
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if today > member.valid_until:
        raise Conflict("The membership has expired", code="MEMBERSHIP_EXPIRED")
    if program.audience not in EVENT_RULES[member.membership_type].audiences:
        raise Conflict(
            "The program is not open to this membership type",
            code="PROGRAM_NOT_FOR_TYPE",
            details={"audience": program.audience},
        )
    existing = find(db, program.id, member.id)
    if existing is not None and existing.status in ("active", "completed"):
        raise Conflict("The member already joined", code="ALREADY_JOINED", details={"participation_id": existing.id})
    participants, _ = counts(db, program.id)
    if program.max_participants is not None and participants >= program.max_participants:
        raise Conflict("The program is full", code="PROGRAM_FULL", details={"max_participants": program.max_participants})
    debt = fines.outstanding_fees(db, member.id) + fines.accrued_late_fees(db, member.id, now, holidays)
    if debt >= DEBT_BLOCK:
        raise Conflict(
            "The member's debt blocks joining", code="MEMBER_BLOCKED_BY_DEBT", details={"total_debt": format_amount(debt)}
        )
    active_elsewhere = db.scalar(
        sa.select(sa.func.count())
        .select_from(Participation)
        .where(
            Participation.member_id == member.id,
            Participation.status == "active",
            Participation.program_id != program.id,
        )
    )
    if (active_elsewhere or 0) >= PROGRAM_LIMIT:
        raise Conflict(
            "The member takes part in too many programs", code="PROGRAM_LIMIT_REACHED", details={"limit": PROGRAM_LIMIT}
        )

    if existing is not None:  # LIB-RDP-13: the old participation, with its entries, becomes active again
        existing.status = "active"
        existing.left_at = None
        existing.leave_reason = None
        if public is not None:
            existing.public = public
        participation = existing
    else:
        participation = Participation(
            program_id=program.id,
            member_id=member.id,
            status="active",
            joined_at=now,
            public=True if public is None else public,
            points=0,
            books=0,
            level="none",
        )
        db.add(participation)
    db.flush()
    record(
        db,
        at=now,
        event="program_joined",
        actor_user_id=actor.id,
        entity_type="program_participation",
        entity_id=participation.id,
        details={"program_id": program.id, "member_id": member.id},
    )
    return participation


def leave(db: Session, now: datetime.datetime, actor: User, program: Program, member: Member) -> Participation:
    """LIB-RDP-13, LIB-RDP-37."""
    participation = find(db, program.id, member.id)
    if participation is None:
        raise NotFound(
            "The member has not joined this program",
            details={"resource": "participation", "program_id": program.id, "member_id": member.id},
        )
    if participation.status != "active":
        raise Conflict(
            "The participation is not active",
            code="PARTICIPATION_NOT_ACTIVE",
            details={"status": participation.status},
        )
    if program.status == "closed":
        raise Conflict(
            "The program status does not allow this", code="INVALID_PROGRAM_STATUS", details={"status": program.status}
        )
    participation.status = "left"
    participation.left_at = now
    participation.leave_reason = "member_request"
    record(
        db,
        at=now,
        event="program_left",
        actor_user_id=actor.id,
        entity_type="program_participation",
        entity_id=participation.id,
        details={"program_id": program.id, "member_id": member.id, "leave_reason": "member_request"},
    )
    return participation


# --- reading ------------------------------------------------------------------------------------


def member_programs_stmt(member_id: int) -> sa.Select[tuple[Participation]]:
    """LIB-RDP-15."""
    return (
        sa.select(Participation)
        .where(Participation.member_id == member_id)
        .order_by(Participation.joined_at.desc(), Participation.id.desc())
    )


def member_program_out(db: Session, participation: Participation, rank_cache: dict[int, dict[int, int]]) -> MemberProgramOut:
    program = db.get(Program, participation.program_id)
    assert program is not None
    if program.id not in rank_cache:
        rank_cache[program.id] = ranking.ranks(db, program.id)
    rank = rank_cache[program.id].get(participation.id) if participation.status != "left" else None
    return MemberProgramOut(
        participation_id=participation.id,
        program_id=program.id,
        program_name=program.name,
        status=participation.status,
        points=participation.points,
        books=participation.books,
        level=participation.level,
        goal_books=program.goal_books,
        rank=rank,
    )


def participants(db: Session, program_id: int, status: str | None) -> list[ParticipantOut]:
    """LIB-RDP-47."""
    items, rank_of = ranking.order_all(db, program_id, status)
    names = _names(db, [p.member_id for p in items])
    return [
        ParticipantOut(
            participation_id=p.id,
            member_id=p.member_id,
            full_name=names[p.member_id],
            status=p.status,
            points=p.points,
            books=p.books,
            level=p.level,
            rank=rank_of.get(p.id),
            public=p.public,
            reward_waived=format_amount(p.reward_waived),
        )
        for p in items
    ]


def _names(db: Session, member_ids: list[int]) -> dict[int, str]:
    if not member_ids:
        return {}
    rows = db.execute(sa.select(Member.id, Member.full_name).where(Member.id.in_(set(member_ids)))).all()
    return {member_id: name for member_id, name in rows}


def display_name(full_name: str) -> str:
    """LIB-RDP-27: the first word and the initial of the last word (``"Ayşe Y."``)."""
    words = full_name.split()
    if not words:
        return full_name
    if len(words) == 1:
        return words[0]
    return f"{words[0]} {words[-1][0]}."


def leaderboard(db: Session, program_id: int, *, staff: bool) -> list[LeaderboardOut]:
    """LIB-RDP-27."""
    items = ranking.ranked(db, program_id)
    names = _names(db, [p.member_id for p in items])
    return [
        LeaderboardOut(
            rank=position,
            name=display_name(names[p.member_id]) if p.public else "Anonymous",
            points=p.points,
            books=p.books,
            level=p.level,
            member_id=p.member_id if staff else None,
        )
        for position, p in enumerate(items, start=1)
    ]


def certificate(db: Session, participation: Participation) -> CertificateOut:
    """LIB-RDP-34."""
    if participation.completed_at is None or participation.completion_no is None:
        raise Conflict("The participation is not completed", code="NOT_COMPLETED", details={"status": participation.status})
    program = db.get(Program, participation.program_id)
    member = db.get(Member, participation.member_id)
    assert program is not None and member is not None
    return CertificateOut(
        certificate_no=f"RP-{program.id}-{participation.completion_no}",
        member_name=member.full_name,
        program_name=program.name,
        completed_at=format_datetime(participation.completed_at),
        level=participation.level,
        books=participation.books,
        points=participation.points,
    )
