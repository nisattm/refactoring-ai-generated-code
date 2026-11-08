"""Partners (LIB-ILL-01 to LIB-ILL-04)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.core.money import format_amount
from lms.core.text import normalize
from lms.ill.models import IllOutgoing, IllPartner, IllRequest
from lms.ill.schemas import PartnerOut, partner_out


def get_partner_or_404(db: Session, partner_id: int) -> IllPartner:
    partner = db.get(IllPartner, partner_id)
    if partner is None:
        raise NotFound(f"Partner {partner_id} does not exist", details={"resource": "ill_partner", "id": partner_id})
    return partner


def require_partner(db: Session, partner_id: int) -> IllPartner:
    """A partner referenced from a request body: ``404 NOT_FOUND`` if missing (LIB-COM-29)."""
    partner = db.get(IllPartner, partner_id)
    if partner is None:
        raise reference_not_found("partner_id", partner_id)
    return partner


def require_active(partner: IllPartner) -> None:
    """LIB-ILL-03."""
    if not partner.is_active:
        raise Conflict(
            f"Partner {partner.code} is inactive", code="PARTNER_INACTIVE", details={"id": partner.id}
        )


def _shown(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: (format_amount(v) if k in ("request_fee", "daily_late_fee") else v) for k, v in fields.items()}


def create_partner(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    code: str,
    name: str,
    email: str,
    request_fee: Any,
    daily_late_fee: Any,
    max_outgoing: int,
) -> IllPartner:
    """LIB-ILL-01."""
    if db.scalar(sa.select(IllPartner.id).where(IllPartner.code == code)) is not None:
        raise Conflict("A partner with this code already exists", details={"field": "code"})
    partner = IllPartner(
        code=code,
        name=name,
        email=email,
        request_fee=request_fee,
        daily_late_fee=daily_late_fee,
        max_outgoing=max_outgoing,
        is_active=True,
    )
    db.add(partner)
    db.flush()
    record(
        db,
        at=now,
        event="ill_partner_created",
        actor_user_id=actor.id,
        entity_type="ill_partner",
        entity_id=partner.id,
        details=_shown(
            {
                "code": code,
                "name": name,
                "email": email,
                "request_fee": request_fee,
                "daily_late_fee": daily_late_fee,
                "max_outgoing": max_outgoing,
            }
        ),
    )
    return partner


def update_partner(
    db: Session, now: datetime.datetime, actor: User, partner: IllPartner, fields: dict[str, Any]
) -> IllPartner:
    """LIB-ILL-02. ``fields`` holds only the fields present in the request."""
    diff = changes({name: getattr(partner, name) for name in fields}, fields)
    for name, value in fields.items():
        setattr(partner, name, value)
    if diff:
        shown = {k: {f: (format_amount(v) if k in ("request_fee", "daily_late_fee") else v) for f, v in d.items()} for k, d in diff.items()}
        record(
            db,
            at=now,
            event="ill_partner_updated",
            actor_user_id=actor.id,
            entity_type="ill_partner",
            entity_id=partner.id,
            details=shown,
        )
    return partner


def counts(db: Session, partner_id: int) -> tuple[int, int]:
    """``open_incoming`` and ``open_outgoing`` (LIB-ILL-04)."""
    incoming = db.scalar(
        sa.select(sa.func.count()).select_from(IllRequest).where(
            IllRequest.partner_id == partner_id, IllRequest.status.in_(("sent", "received", "on_loan"))
        )
    )
    outgoing = db.scalar(
        sa.select(sa.func.count()).select_from(IllOutgoing).where(
            IllOutgoing.partner_id == partner_id, IllOutgoing.status.in_(("requested", "shipped"))
        )
    )
    return incoming or 0, outgoing or 0


def to_out(db: Session, partner: IllPartner) -> PartnerOut:
    incoming, outgoing = counts(db, partner.id)
    return partner_out(partner, incoming, outgoing)


def matches(partner: IllPartner, needle: str) -> bool:
    return needle in normalize(partner.code) or needle in normalize(partner.name)
