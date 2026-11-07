"""Resources and licenses (LIB-DIG-01 to LIB-DIG-14)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes
from lms.auth.models import User
from lms.catalog.models import Book
from lms.core.errors import NotFound, ValidationFailed
from lms.core.text import normalize
from lms.digital import state
from lms.digital.models import DigitalHold, DigitalLicense, DigitalResource
from lms.digital.queue import cancel_hold, move_queue
from lms.digital.rules import DEFAULT_LOAN_DAYS
from lms.digital.schemas import (
    LicenseCreateIn,
    LicensePatchIn,
    LicenseRenewIn,
    ResourceCreateIn,
    ResourceOut,
    resource_out,
)
from lms.core.money import format_amount
from lms.purchasing.models import PurchaseOrder

ORDER_STATUSES_FOR_LICENSE = ("ordered", "partially_received", "received")


def _problem(field: str, text: str) -> dict[str, str]:
    return {"field": field, "problem": text}


# --- resources -------------------------------------------------------------------------------


def counts_out(db: Session, resource: DigitalResource, now: datetime.datetime) -> ResourceOut:
    """LIB-DIG-04."""
    capacity = state.capacity_at(db, resource.id, now)
    if resource.kind == "ebook":
        in_use = state.active_loan_count(db, resource.id, now)
        available = state.free_copies(db, resource.id, now)
        waiting = state.waiting_count(db, resource.id)
    else:
        in_use = len(state.open_sessions(db, resource.id, now))
        available = state.free_seats(db, resource.id, now)
        waiting = 0
    return resource_out(resource, capacity=capacity, in_use=in_use, available=available, waiting_holds=waiting)


def create_resource(db: Session, now: datetime.datetime, actor: User, body: ResourceCreateIn) -> DigitalResource:
    """LIB-DIG-01."""
    problems: list[dict[str, str]] = []
    if body.kind == "database":
        if body.book_id is not None:
            problems.append(_problem("book_id", "book_id is only allowed for an ebook"))
        if body.loan_days is not None:
            problems.append(_problem("loan_days", "loan_days is only allowed for an ebook"))
    elif body.book_id is not None and db.get(Book, body.book_id) is None:
        problems.append(_problem("book_id", f"book {body.book_id} does not exist"))
    if problems:
        raise ValidationFailed(problems)
    loan_days = None
    if body.kind == "ebook":
        loan_days = body.loan_days if body.loan_days is not None else DEFAULT_LOAN_DAYS
    resource = DigitalResource(
        kind=body.kind,
        title=body.title,
        title_key=normalize(body.title),
        provider=body.provider,
        book_id=body.book_id,
        loan_days=loan_days,
        is_active=True,
        created_at=now,
    )
    db.add(resource)
    db.flush()
    state.audit(
        db,
        now,
        actor.id,
        "digital_resource_created",
        "digital_resource",
        resource.id,
        kind=resource.kind,
        title=resource.title,
        provider=resource.provider,
        book_id=resource.book_id,
        loan_days=resource.loan_days,
    )
    return resource


def update_resource(
    db: Session, now: datetime.datetime, actor: User, resource: DigitalResource, fields: dict[str, Any]
) -> DigitalResource:
    """LIB-DIG-02, LIB-DIG-03."""
    problems: list[dict[str, str]] = []
    if resource.kind == "database":
        if fields.get("book_id") is not None:
            problems.append(_problem("book_id", "book_id is only allowed for an ebook"))
        if fields.get("loan_days") is not None:
            problems.append(_problem("loan_days", "loan_days is only allowed for an ebook"))
        fields.pop("book_id", None)
        fields.pop("loan_days", None)
    else:
        if "loan_days" in fields and fields["loan_days"] is None:
            problems.append(_problem("loan_days", "loan_days must not be null for an ebook"))
        if fields.get("book_id") is not None and db.get(Book, fields["book_id"]) is None:
            problems.append(_problem("book_id", f"book {fields['book_id']} does not exist"))
    for name in ("title", "provider", "is_active"):
        if name in fields and fields[name] is None:
            problems.append(_problem(name, f"{name} must not be null"))
    if problems:
        raise ValidationFailed(problems)

    old = {name: getattr(resource, name) for name in fields}
    for name, value in fields.items():
        setattr(resource, name, value)
    if "title" in fields:
        resource.title_key = normalize(resource.title)
    diff = changes(old, {name: getattr(resource, name) for name in fields})
    if diff:
        state.audit(db, now, actor.id, "digital_resource_updated", "digital_resource", resource.id, **diff)
    if old.get("is_active") is True and resource.is_active is False:
        _on_deactivated(db, now, actor.id, resource)
    return resource


def _on_deactivated(db: Session, now: datetime.datetime, actor_id: int, resource: DigitalResource) -> None:
    """LIB-DIG-03."""
    holds = db.scalars(
        sa.select(DigitalHold)
        .where(DigitalHold.resource_id == resource.id, DigitalHold.status.in_(("waiting", "ready")))
        .order_by(DigitalHold.created_at, DigitalHold.id)
    )
    for hold in list(holds):
        cancel_hold(db, now, actor_id, hold, "resource_inactive")
    for session in state.open_sessions(db, resource.id, now):
        session.closed_at = now


def resource_list_stmt(
    *, kind: str | None, is_active: bool | None, q: str | None, book_id: int | None
) -> sa.Select[tuple[DigitalResource]]:
    stmt = sa.select(DigitalResource).order_by(DigitalResource.title_key, DigitalResource.id)
    if kind is not None:
        stmt = stmt.where(DigitalResource.kind == kind)
    if is_active is not None:
        stmt = stmt.where(DigitalResource.is_active == is_active)
    if book_id is not None:
        stmt = stmt.where(DigitalResource.book_id == book_id)
    if q is not None and q.strip():
        needle = normalize(q.strip())
        stmt = stmt.where(
            sa.or_(
                DigitalResource.title_key.contains(needle, autoescape=True),
                sa.func.lms_normalize(DigitalResource.provider).contains(needle, autoescape=True),
            )
        )
    return stmt


def calendar(db: Session, resource: DigitalResource, first: datetime.date, last: datetime.date) -> list[tuple[datetime.date, int]]:
    """LIB-DIG-13."""
    licenses = state.licenses_of(db, resource.id)
    days: list[tuple[datetime.date, int]] = []
    day = first
    while day <= last:
        days.append((day, sum(lic.copies for lic in licenses if lic.counts_on(day))))
        day += datetime.timedelta(days=1)
    return days


# --- licenses --------------------------------------------------------------------------------


def get_license_or_404(db: Session, license_id: int) -> DigitalLicense:
    lic = db.get(DigitalLicense, license_id)
    if lic is None:
        raise NotFound(f"Digital license {license_id} does not exist", details={"resource": "digital_license", "id": license_id})
    return lic


def _copies_problem(resource: DigitalResource, copies: int) -> dict[str, str] | None:
    upper = 100 if resource.kind == "ebook" else 500
    if not 1 <= copies <= upper:
        unit = "copies" if resource.kind == "ebook" else "seats"
        return _problem("copies", f"copies must be 1-{upper} {unit} for this resource")
    return None


def _check_order(db: Session, order_id: int | None, problems: list[dict[str, str]]) -> PurchaseOrder | None:
    if order_id is None:
        return None
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        problems.append(_problem("order_id", f"purchase order {order_id} does not exist"))
    return order


def _require_order_status(order: PurchaseOrder | None) -> None:
    """LIB-DIG-06."""
    if order is not None and order.status not in ORDER_STATUSES_FOR_LICENSE:
        raise state.error(
            "INVALID_ORDER_STATUS",
            f"Purchase order {order.id} has status {order.status} and cannot be used for a license",
            id=order.id,
            status=order.status,
        )


def _license_audit(db: Session, now: datetime.datetime, actor_id: int, lic: DigitalLicense) -> None:
    state.audit(
        db,
        now,
        actor_id,
        "digital_license_added",
        "digital_license",
        lic.id,
        resource_id=lic.resource_id,
        model=lic.model,
        copies=lic.copies,
        starts_on=lic.starts_on.isoformat(),
        ends_on=lic.ends_on.isoformat() if lic.ends_on is not None else None,
        cost=format_amount(lic.cost),
        order_id=lic.order_id,
    )


def add_license(
    db: Session, now: datetime.datetime, actor: User, resource: DigitalResource, body: LicenseCreateIn
) -> DigitalLicense:
    """LIB-DIG-05, LIB-DIG-06."""
    problems: list[dict[str, str]] = []
    if (problem := _copies_problem(resource, body.copies)) is not None:
        problems.append(problem)
    if body.model == "perpetual":
        if body.ends_on is not None:
            problems.append(_problem("ends_on", "a perpetual license has no ends_on"))
    elif body.ends_on is None:
        problems.append(_problem("ends_on", "ends_on is required for a subscription"))
    elif body.ends_on < body.starts_on:
        problems.append(_problem("ends_on", "ends_on must not be before starts_on"))
    order = _check_order(db, body.order_id, problems)
    if problems:
        raise ValidationFailed(problems)
    _require_order_status(order)
    lic = DigitalLicense(
        resource_id=resource.id,
        model=body.model,
        copies=body.copies,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        cost=body.cost,
        order_id=body.order_id,
    )
    db.add(lic)
    db.flush()
    _license_audit(db, now, actor.id, lic)
    move_queue(db, now, actor.id, resource)
    return lic


def update_license(
    db: Session, now: datetime.datetime, actor: User, lic: DigitalLicense, body: LicensePatchIn
) -> DigitalLicense:
    """LIB-DIG-10."""
    fields = body.model_fields_set
    resource = state.get_resource_or_404(db, lic.resource_id)
    today = now.date()
    problems: list[dict[str, str]] = []
    if "copies" in fields and (problem := _copies_problem(resource, body.copies)) is not None:
        problems.append(problem)
    if "ends_on" in fields and body.ends_on is None and lic.model == "subscription":
        problems.append(_problem("ends_on", "ends_on is required for a subscription"))
    if "ends_on" in fields and body.ends_on is not None and lic.model == "perpetual":
        problems.append(_problem("ends_on", "a perpetual license has no ends_on"))
    if problems:
        raise ValidationFailed(problems)

    status = lic.status_on(today)
    if ("copies" in fields or "cost" in fields) and status != "pending":
        raise state.error("INVALID_LICENSE_STATUS", "copies and cost can only be changed while the license is pending", status=status)
    changes_ends = "ends_on" in fields and body.ends_on is not None
    if changes_ends and status not in ("pending", "active"):
        raise state.error("INVALID_LICENSE_STATUS", "ends_on can only be changed while the license is pending or active", status=status)
    if changes_ends:
        assert body.ends_on is not None
        if body.ends_on < today or body.ends_on < lic.starts_on:
            raise ValidationFailed.single("ends_on", "ends_on must not be before today or before starts_on")
    if "copies" in fields:
        lic.copies = body.copies
    if "cost" in fields:
        lic.cost = body.cost
    if changes_ends:
        lic.ends_on = body.ends_on
    db.flush()
    move_queue(db, now, actor.id, resource)
    return lic


def cancel_license(db: Session, now: datetime.datetime, actor: User, lic: DigitalLicense) -> DigitalLicense:
    """LIB-DIG-07."""
    status = lic.status_on(now.date())
    if status in ("cancelled", "ended"):
        raise state.error("INVALID_LICENSE_STATUS", f"The license is {status}", status=status)
    lic.cancelled_on = now.date()
    state.audit(
        db, now, actor.id, "digital_license_cancelled", "digital_license", lic.id,
        resource_id=lic.resource_id, cancelled_on=lic.cancelled_on.isoformat(),
    )
    return lic


def is_renewed(db: Session, lic: DigitalLicense) -> bool:
    """A license of the resource that is not cancelled starts the day after ``lic`` ends (LIB-DIG-11)."""
    if lic.ends_on is None:
        return False
    stmt = sa.select(DigitalLicense.id).where(
        DigitalLicense.resource_id == lic.resource_id,
        DigitalLicense.cancelled_on.is_(None),
        DigitalLicense.starts_on == lic.ends_on + datetime.timedelta(days=1),
    )
    return db.scalar(stmt.limit(1)) is not None


def renew_license(
    db: Session, now: datetime.datetime, actor: User, lic: DigitalLicense, body: LicenseRenewIn
) -> DigitalLicense:
    """LIB-DIG-11."""
    resource = state.get_resource_or_404(db, lic.resource_id)
    problems: list[dict[str, str]] = []
    order = _check_order(db, body.order_id, problems)
    if problems:
        raise ValidationFailed(problems)
    status = lic.status_on(now.date())
    if lic.model != "subscription":
        raise state.error("NOT_A_SUBSCRIPTION", "Only a subscription can be renewed")
    if status not in ("active", "ended"):
        raise state.error("INVALID_LICENSE_STATUS", f"The license is {status}", status=status)
    if is_renewed(db, lic):
        raise state.error("ALREADY_RENEWED", "The subscription was already renewed")
    assert lic.ends_on is not None
    starts_on = lic.ends_on + datetime.timedelta(days=1)
    if body.ends_on < starts_on:
        raise ValidationFailed.single("ends_on", "ends_on must not be before the start of the renewal")
    _require_order_status(order)
    new = DigitalLicense(
        resource_id=lic.resource_id,
        model="subscription",
        copies=lic.copies,
        starts_on=starts_on,
        ends_on=body.ends_on,
        cost=body.cost,
        order_id=body.order_id,
    )
    db.add(new)
    db.flush()
    _license_audit(db, now, actor.id, new)
    move_queue(db, now, actor.id, resource)
    return new


def license_list(db: Session, resource_id: int, today: datetime.date, status: str | None) -> list[DigitalLicense]:
    """LIB-DIG-08."""
    items = state.licenses_of(db, resource_id)
    if status is not None:
        items = [lic for lic in items if lic.status_on(today) == status]
    return items


def expiring_licenses(db: Session, today: datetime.date, days: int) -> list[tuple[DigitalLicense, str]]:
    """LIB-DIG-12."""
    last = today + datetime.timedelta(days=days)
    stmt = (
        sa.select(DigitalLicense, DigitalResource.title)
        .join(DigitalResource, DigitalResource.id == DigitalLicense.resource_id)
        .where(DigitalLicense.model == "subscription", DigitalLicense.ends_on >= today, DigitalLicense.ends_on <= last)
        .order_by(DigitalLicense.ends_on, DigitalLicense.id)
    )
    result = []
    for lic, title in db.execute(stmt):
        if lic.status_on(today) == "active" and not is_renewed(db, lic):
            result.append((lic, title))
    return result
