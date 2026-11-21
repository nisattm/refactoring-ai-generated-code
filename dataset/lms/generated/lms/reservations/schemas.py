"""Request and response schemas of module 6 (section 10)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, StrictInt

from lms.core.schemas import RequestModel
from lms.core.timeutil import format_date_or_none, format_datetime, format_datetime_or_none
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
        ready_on=format_date_or_none(reservation.ready_on),
        hold_until=format_date_or_none(reservation.hold_until),
        closed_at=format_datetime_or_none(reservation.closed_at),
        cancel_reason=reservation.cancel_reason,
        queue_position=queue_position,
    )
