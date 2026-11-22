"""Reservation endpoints (section 10.2)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from lms.auth.deps import CurrentPrincipal, StaffOnly, ensure_own_or_staff
from lms.catalog.models import Book
from lms.core.context import HolidaysDep, NowDep, PathId
from lms.core.db import SessionDep, get_or_404
from lms.core.errors import Forbidden, ValidationFailed
from lms.core.pagination import Page, PageDep, paginate
from lms.members.service import get_member_or_404
from lms.reservations import service
from lms.reservations.models import ACTIVE_STATUSES, Reservation
from lms.reservations.schemas import (
    ExpiredOut,
    ReservationCreateIn,
    ReservationOut,
    ReservationStatus,
    reservation_out,
)

router = APIRouter(tags=["reservations"])

_OWN_RESERVATIONS_ONLY = "Only your own reservations can be accessed"


def _page_out(db: Session, stmt: sa.Select[tuple[Reservation]], page) -> Page[ReservationOut]:  # noqa: ANN001
    return paginate(db, stmt, page, lambda r: reservation_out(r, service.queue_position(db, r)))


@router.post("/reservations", response_model=ReservationOut, status_code=201)
def create_reservation(
    body: ReservationCreateIn, now: NowDep, holidays: HolidaysDep, db: SessionDep, principal: CurrentPrincipal
) -> ReservationOut:
    user = principal.user
    if user.role == "member":
        if body.member_id is not None:
            raise ValidationFailed.single("member_id", "a member reserves for themselves and must not send member_id")
        if user.member_id is None:
            raise Forbidden("The user has no member record")
        member_id = user.member_id
    else:
        if body.member_id is None:
            raise ValidationFailed.single("member_id", "member_id is required")
        member_id = body.member_id
    reservation = service.create_reservation(
        db,
        now,
        user,
        holidays,
        member_id=member_id,
        book_id=body.book_id,
        pickup_branch_id=body.pickup_branch_id,
    )
    return reservation_out(reservation, service.queue_position(db, reservation))


@router.get("/reservations", response_model=Page[ReservationOut])
def list_reservations(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    member_id: Annotated[int | None, Query()] = None,
    book_id: Annotated[int | None, Query()] = None,
    pickup_branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[ReservationStatus | None, Query()] = None,
) -> Page[ReservationOut]:
    stmt = sa.select(Reservation).order_by(Reservation.id)
    for column, value in (
        (Reservation.member_id, member_id),
        (Reservation.book_id, book_id),
        (Reservation.pickup_branch_id, pickup_branch_id),
        (Reservation.status, status),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    return _page_out(db, stmt, page)


@router.post("/reservations/process-expired", response_model=ExpiredOut)
def process_expired(now: NowDep, holidays: HolidaysDep, db: SessionDep, staff: StaffOnly) -> ExpiredOut:
    return ExpiredOut(expired=service.process_expired(db, now, staff.user, holidays))


@router.get("/reservations/{reservation_id}", response_model=ReservationOut)
def get_reservation(reservation_id: PathId, db: SessionDep, principal: CurrentPrincipal) -> ReservationOut:
    reservation = service.get_reservation_or_404(db, reservation_id)
    ensure_own_or_staff(principal, reservation.member_id, _OWN_RESERVATIONS_ONLY)
    return reservation_out(reservation, service.queue_position(db, reservation))


@router.get("/members/{member_id}/reservations", response_model=Page[ReservationOut])
def list_member_reservations(
    member_id: PathId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    book_id: Annotated[int | None, Query()] = None,
    pickup_branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[ReservationStatus | None, Query()] = None,
) -> Page[ReservationOut]:
    member = get_member_or_404(db, member_id)
    ensure_own_or_staff(principal, member.id, _OWN_RESERVATIONS_ONLY)
    stmt = sa.select(Reservation).where(Reservation.member_id == member.id).order_by(Reservation.id)
    for column, value in (
        (Reservation.book_id, book_id),
        (Reservation.pickup_branch_id, pickup_branch_id),
        (Reservation.status, status),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    return _page_out(db, stmt, page)


@router.get("/books/{book_id}/reservations", response_model=Page[ReservationOut])
def list_book_reservations(book_id: PathId, db: SessionDep, _: StaffOnly, page: PageDep) -> Page[ReservationOut]:
    get_or_404(db, Book, book_id, "book")
    stmt = (
        sa.select(Reservation)
        .where(Reservation.book_id == book_id, Reservation.status.in_(ACTIVE_STATUSES))
        .order_by(Reservation.created_at, Reservation.id)
    )
    return _page_out(db, stmt, page)


@router.post("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_reservation(
    reservation_id: PathId, now: NowDep, holidays: HolidaysDep, db: SessionDep, principal: CurrentPrincipal
) -> ReservationOut:
    reservation = service.get_reservation_or_404(db, reservation_id)
    ensure_own_or_staff(principal, reservation.member_id, _OWN_RESERVATIONS_ONLY)
    reason = "member_request" if principal.user.role == "member" else "staff_request"
    service.cancel_reservation(db, now, principal.user, holidays, reservation, reason)
    return reservation_out(reservation, service.queue_position(db, reservation))
