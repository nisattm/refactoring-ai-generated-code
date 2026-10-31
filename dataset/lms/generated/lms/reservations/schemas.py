"""Request and response schemas of module 6 (section 10)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, StrictInt

from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.reservations.models import Reservation

ReservationStatus = Literal["waiting", "in_transit", "ready", "fulfilled", "cancelled", "expired"]


class ReservationCreateIn(RequestModel):
    book_id: StrictInt
    pickup_branch_id: StrictInt
    member_id: StrictInt | None = None


class ReservationOut(BaseModel):
    id: int
    book_id: int
    member_id: int
    pickup_branch_id: int
    status: str
    created_at: str
    copy_id: int | None
    ready_on: str | None
    hold_until: str | None
    closed_at: str | None
    cancel_reason: str | None
    queue_position: int | None


class ExpiredOut(BaseModel):
    expired: int


def reservation_out(reservation: Reservation, queue_position: int | None) -> ReservationOut:
    return ReservationOut(
        id=reservation.id,
        book_id=reservation.book_id,
        member_id=reservation.member_id,
        pickup_branch_id=reservation.pickup_branch_id,
        status=reservation.status,
        created_at=format_datetime(reservation.created_at),
        copy_id=reservation.copy_id,
        ready_on=reservation.ready_on.isoformat() if reservation.ready_on is not None else None,
        hold_until=reservation.hold_until.isoformat() if reservation.hold_until is not None else None,
        closed_at=format_datetime(reservation.closed_at) if reservation.closed_at is not None else None,
        cancel_reason=reservation.cancel_reason,
        queue_position=queue_position,
    )
