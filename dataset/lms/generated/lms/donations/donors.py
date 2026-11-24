"""Donors, merging, history and the donor wall (LIB-DON-01 to LIB-DON-07, LIB-DON-34, LIB-DON-40)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.core.errors import Conflict, ValidationFailed
from lms.core.lookup import get_or_404
from lms.core.money import ZERO, format_amount
from lms.core.text import normalize
from lms.core.timeutil import format_datetime
from lms.donations import usage
from lms.donations.models import Donation, Donor, Receiving
from lms.donations.rules import LEVEL_RANK, level_of
from lms.donations.schemas import DonorOut, HistoryOut, WallDonorOut, WallOut, YearOut
from lms.members.models import Member


def get_donor_or_404(db: Session, donor_id: int) -> Donor:
    return get_or_404(db, Donor, donor_id, label="Donor", resource="donor")


def donor_out(donor: Donor, year_value) -> DonorOut:
    return DonorOut(
        id=donor.id,
        kind=donor.kind,
        name=donor.name,
        email=donor.email,
        phone=donor.phone,
        member_id=donor.member_id,
        anonymous=donor.anonymous,
        is_active=donor.is_active,
        merged_into_id=donor.merged_into_id,
        created_at=format_datetime(donor.created_at),
        level=level_of(year_value),
        value_this_year=format_amount(year_value),
    )


def to_out(db: Session, now: datetime.datetime, donor: Donor) -> DonorOut:
    return donor_out(donor, usage.donor_year_value(db, donor.id, now.year))


def _check_email_free(db: Session, email: str | None, *, own_id: int | None = None) -> None:
    if email is None:
        return
    stmt = sa.select(Donor.id).where(Donor.email_key == normalize(email))
    if own_id is not None:
        stmt = stmt.where(Donor.id != own_id)
    if db.scalar(stmt) is not None:
        raise Conflict("A donor with this e-mail address already exists", details={"field": "email"})


def _snapshot(donor: Donor) -> dict[str, Any]:
    return {
        "name": donor.name,
        "email": donor.email,
        "phone": donor.phone,
        "anonymous": donor.anonymous,
        "is_active": donor.is_active,
    }


def new_donor(
    db: Session,
    now: datetime.datetime,
    *,
    kind: str,
    name: str,
    email: str | None,
    phone: str | None,
    member_id: int | None,
    anonymous: bool,
) -> Donor:
    donor = Donor(
        kind=kind,
        name=name,
        name_key=normalize(name),
        email=email,
        email_key=normalize(email) if email is not None else None,
        phone=phone,
        member_id=member_id,
        anonymous=anonymous,
        is_active=True,
        created_at=now,
    )
    db.add(donor)
    db.flush()
    return donor


def create_donor(db: Session, now: datetime.datetime, actor: User, data: dict[str, Any]) -> Donor:
    """LIB-DON-01, LIB-DON-02."""
    member_id = data.get("member_id")
    if member_id is not None:
        if data["kind"] != "person":
            raise ValidationFailed.single("kind", "a donor with a member_id must be of kind person")
        if db.get(Member, member_id) is None:
            raise ValidationFailed.single("member_id", f"member {member_id} does not exist")
    _check_email_free(db, data.get("email"))
    if member_id is not None and usage.donor_of_member(db, member_id) is not None:
        raise Conflict("The member already has a donor", details={"field": "member_id"})
    donor = new_donor(
        db,
        now,
        kind=data["kind"],
        name=data["name"],
        email=data.get("email"),
        phone=data.get("phone"),
        member_id=member_id,
        anonymous=data.get("anonymous", False),
    )
    record(
        db,
        at=now,
        event="donor_created",
        actor_user_id=actor.id,
        entity_type="donor",
        entity_id=donor.id,
        details={"kind": donor.kind, "name": donor.name, "member_id": member_id, "anonymous": donor.anonymous},
    )
    return donor


def member_donor(db: Session, now: datetime.datetime, actor: User, member: Member) -> Donor:
    """LIB-DON-02: the member's own donor, created when missing."""
    donor = usage.donor_of_member(db, member.id)
    if donor is not None:
        return donor
    email = member.email
    if db.scalar(sa.select(Donor.id).where(Donor.email_key == normalize(email))) is not None:
        email = None
    donor = new_donor(
        db,
        now,
        kind="person",
        name=member.full_name,
        email=email,
        phone=None,
        member_id=member.id,
        anonymous=False,
    )
    record(
        db,
        at=now,
        event="donor_created",
        actor_user_id=actor.id,
        entity_type="donor",
        entity_id=donor.id,
        details={"kind": "person", "name": donor.name, "member_id": member.id, "anonymous": False},
    )
    return donor


def update_donor(db: Session, now: datetime.datetime, actor: User, donor: Donor, fields: dict[str, Any]) -> Donor:
    """LIB-DON-04, LIB-DON-05."""
    if donor.merged_into_id is not None:
        raise Conflict("The donor was merged", code="DONOR_MERGED", details={"id": donor.id})
    if "email" in fields:
        _check_email_free(db, fields["email"], own_id=donor.id)
    if fields.get("is_active") is False and donor.is_active:
        open_ids = usage.open_donation_ids(db, donor.id)
        if open_ids:
            raise Conflict(
                "The donor has open donations",
                code="DONOR_HAS_OPEN_DONATIONS",
                details={"donation_ids": open_ids},
            )
    diff = changes(_snapshot(donor), fields)
    for name, value in fields.items():
        setattr(donor, name, value)
    if "name" in fields:
        donor.name_key = normalize(donor.name)
    if "email" in fields:
        donor.email_key = normalize(donor.email) if donor.email is not None else None
    if diff:
        record(
            db,
            at=now,
            event="donor_updated",
            actor_user_id=actor.id,
            entity_type="donor",
            entity_id=donor.id,
            details=diff,
        )
    return donor


def merge(db: Session, now: datetime.datetime, actor: User, donor: Donor, target: Donor) -> Donor:
    """LIB-DON-06."""
    if donor.merged_into_id is not None or target.merged_into_id is not None:
        raise Conflict("A donor was already merged", code="DONOR_MERGED", details={"id": donor.id})
    if donor.member_id is not None and target.member_id is not None:
        raise Conflict(
            "Both donors belong to a member", code="DONOR_MERGE_CONFLICT", details={"id": donor.id}
        )
    if donor.member_id is not None and target.kind != "person":
        raise Conflict(
            "A donor of a member cannot be merged into an organization",
            code="DONOR_MERGE_CONFLICT",
            details={"id": donor.id},
        )
    moved = [d.id for d in db.scalars(sa.select(Donation).where(Donation.donor_id == donor.id).order_by(Donation.id))]
    db.execute(sa.update(Donation).where(Donation.donor_id == donor.id).values(donor_id=target.id))
    moved_member = donor.member_id if target.member_id is None else None
    moved_email = (donor.email, donor.email_key) if target.email is None and donor.email is not None else None
    if moved_member is not None:
        donor.member_id = None
    if moved_email is not None:
        donor.email = None
        donor.email_key = None
    donor.is_active = False
    donor.merged_into_id = target.id
    db.flush()
    if moved_member is not None:
        target.member_id = moved_member
    if moved_email is not None:
        target.email, target.email_key = moved_email
    db.flush()
    record(
        db,
        at=now,
        event="donors_merged",
        actor_user_id=actor.id,
        entity_type="donor",
        entity_id=donor.id,
        details={"into_donor_id": target.id, "donation_ids": moved},
    )
    return target


def list_donors(
    db: Session,
    now: datetime.datetime,
    *,
    q: str | None,
    kind: str | None,
    is_active: bool | None,
    level: str | None,
) -> list[DonorOut]:
    """LIB-DON-03: all matching donors in order, with their level of the current year."""
    stmt = sa.select(Donor).order_by(Donor.name_key, Donor.id)
    needle = normalize(q.strip()) if q is not None else ""
    if needle:
        stmt = stmt.where(
            sa.or_(
                Donor.name_key.contains(needle, autoescape=True), Donor.email_key.contains(needle, autoescape=True)
            )
        )
    if kind is not None:
        stmt = stmt.where(Donor.kind == kind)
    if is_active is not None:
        stmt = stmt.where(Donor.is_active.is_(is_active))
    values = usage.year_values(db, now.year)
    result = [donor_out(d, values.get(d.id, ZERO)) for d in db.scalars(stmt)]
    if level is not None:
        result = [d for d in result if d.level == level]
    return result


def history(db: Session, donor: Donor) -> HistoryOut:
    """LIB-DON-07."""
    donations = db.scalars(sa.select(Donation).where(Donation.donor_id == donor.id)).all()
    receivings = db.execute(
        sa.select(Receiving.copies, Receiving.value, Receiving.received_on)
        .join(Donation, Donation.id == Receiving.donation_id)
        .where(Donation.donor_id == donor.id)
    ).all()
    per_year: dict[int, Any] = {}
    for _, value, day in receivings:
        per_year[day.year] = per_year.get(day.year, ZERO) + value
    days = [day for _, _, day in receivings]
    return HistoryOut(
        donor_id=donor.id,
        donations=len(donations),
        open_donations=sum(1 for d in donations if d.is_open),
        copies_received=sum(c for c, _, _ in receivings),
        value_received=format_amount(sum((v for _, v, _ in receivings), ZERO)),
        first_received_on=min(days).isoformat() if days else None,
        last_received_on=max(days).isoformat() if days else None,
        years=[
            YearOut(year=y, value=format_amount(v), level=level_of(v)) for y, v in sorted(per_year.items())
        ],
    )


def wall(db: Session, year: int) -> WallOut:
    """LIB-DON-34, LIB-DON-40."""
    values = usage.year_values(db, year)
    shown: list[tuple[int, str, int, WallDonorOut]] = []
    anonymous = 0
    donors = db.scalars(sa.select(Donor).where(Donor.id.in_(list(values)), Donor.merged_into_id.is_(None)))
    for donor in donors:
        level = level_of(values[donor.id])
        if level == "none":
            continue
        if donor.anonymous:
            anonymous += 1
        else:
            shown.append((-LEVEL_RANK[level], donor.name_key, donor.id, WallDonorOut(name=donor.name, level=level)))
    shown.sort(key=lambda row: row[:3])
    return WallOut(year=year, donors=[row[3] for row in shown], anonymous_count=anonymous)
