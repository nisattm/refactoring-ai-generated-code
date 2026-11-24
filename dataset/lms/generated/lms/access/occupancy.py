"""Access settings and occupancy (LIB-ACC-10 to LIB-ACC-13)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.access.models import DEFAULT_DAY_PASS_PRICE, AccessSettings, DayPass, Visit
from lms.access.schemas import InsideOut, OccupancyOut, SettingsOut
from lms.audit.service import changes, record
from lms.auth.models import User
from lms.core.errors import Conflict
from lms.core.money import format_amount
from lms.core.timeutil import format_datetime
from lms.members.models import Member

DEFAULTS: dict[str, Any] = {"capacity": None, "guest_entry": True, "day_passes": True, "day_pass_price": DEFAULT_DAY_PASS_PRICE}


def settings_of(db: Session, branch_id: int) -> dict[str, Any]:
    """The settings of a branch; a branch without a record has the defaults (LIB-ACC-10)."""
    row = db.get(AccessSettings, branch_id)
    if row is None:
        return dict(DEFAULTS)
    return {
        "capacity": row.capacity,
        "guest_entry": row.guest_entry,
        "day_passes": row.day_passes,
        "day_pass_price": row.day_pass_price,
    }


def settings_out(db: Session, branch_id: int) -> SettingsOut:
    values = settings_of(db, branch_id)
    return SettingsOut(
        branch_id=branch_id,
        capacity=values["capacity"],
        guest_entry=values["guest_entry"],
        day_passes=values["day_passes"],
        day_pass_price=format_amount(values["day_pass_price"]),
    )


def count_inside(db: Session, branch_id: int) -> tuple[int, int]:
    """(members, visitors) with an open visit at the branch."""
    members = db.scalar(
        sa.select(sa.func.count())
        .select_from(Visit)
        .where(Visit.branch_id == branch_id, Visit.left_at.is_(None), Visit.member_id.is_not(None))
    )
    visitors = db.scalar(
        sa.select(sa.func.count())
        .select_from(Visit)
        .where(Visit.branch_id == branch_id, Visit.left_at.is_(None), Visit.day_pass_id.is_not(None))
    )
    return members or 0, visitors or 0


def occupancy(db: Session, branch_id: int) -> int:
    members, visitors = count_inside(db, branch_id)
    return members + visitors


def update_settings(
    db: Session, now: datetime.datetime, actor: User, branch_id: int, fields: dict[str, Any]
) -> SettingsOut:
    """LIB-ACC-10, LIB-ACC-11."""
    capacity = fields.get("capacity")
    if capacity is not None:
        inside = occupancy(db, branch_id)
        if capacity < inside:
            raise Conflict(
                "The capacity is below the current occupancy",
                code="CAPACITY_BELOW_OCCUPANCY",
                details={"occupancy": inside},
            )
    old = settings_of(db, branch_id)
    new = {**old, **fields}
    row = db.get(AccessSettings, branch_id)
    if row is None:
        row = AccessSettings(branch_id=branch_id)
        db.add(row)
    row.capacity = new["capacity"]
    row.guest_entry = new["guest_entry"]
    row.day_passes = new["day_passes"]
    row.day_pass_price = new["day_pass_price"]
    db.flush()

    def plain(values: dict[str, Any]) -> dict[str, Any]:
        return {k: format_amount(v) if isinstance(v, Decimal) else v for k, v in values.items()}

    record(
        db,
        at=now,
        event="access_settings_changed",
        actor_user_id=actor.id,
        entity_type="access_settings",
        entity_id=branch_id,
        details=changes(plain(old), plain(new)),
    )
    return settings_out(db, branch_id)


def occupancy_out(db: Session, branch_id: int) -> OccupancyOut:
    """LIB-ACC-12."""
    members, visitors = count_inside(db, branch_id)
    inside = members + visitors
    capacity = settings_of(db, branch_id)["capacity"]
    return OccupancyOut(
        branch_id=branch_id,
        inside=inside,
        members=members,
        visitors=visitors,
        capacity=capacity,
        free=None if capacity is None else max(capacity - inside, 0),
    )


def inside_stmt(branch_id: int) -> sa.Select[tuple[Visit]]:
    """LIB-ACC-13: the open visits of the branch."""
    return (
        sa.select(Visit)
        .where(Visit.branch_id == branch_id, Visit.left_at.is_(None))
        .order_by(Visit.entered_at, Visit.id)
    )


def inside_out(db: Session, visit: Visit) -> InsideOut:
    member = db.get(Member, visit.member_id) if visit.member_id is not None else None
    code = db.scalar(sa.select(DayPass.code).where(DayPass.id == visit.day_pass_id)) if visit.day_pass_id else None
    return InsideOut(
        visit_id=visit.id,
        member_id=member.id if member is not None else None,
        full_name=member.full_name if member is not None else None,
        day_pass_code=code,
        entered_at=format_datetime(visit.entered_at),
    )
