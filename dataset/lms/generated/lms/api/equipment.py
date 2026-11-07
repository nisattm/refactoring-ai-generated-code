"""Equipment loan endpoints (section 24.4)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel

from lms.auth.deps import AdminOnly, AnyUser, CurrentPrincipal, Principal, StaffOnly
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, ValidationFailed, reference_not_found
from lms.core.pagination import Page, PageDep, paginate
from lms.core.timeutil import parse_date
from lms.equipment import inventory, lending
from lms.equipment import reservations as reservation_service
from lms.equipment.models import EquipmentLoan, EquipmentTraining, EquipmentType
from lms.equipment.schemas import (
    AvailabilityOut,
    EquipmentLoanOut,
    ItemCreateIn,
    ItemOut,
    ItemPatchIn,
    ItemStatus,
    LoanCreateIn,
    LoanStatus,
    ProcessOut,
    ReservationCreateIn,
    ReservationOut,
    ReservationStatus,
    ReturnIn,
    TrainingIn,
    TrainingOut,
    TypeCreateIn,
    TypeOut,
    TypePatchIn,
    type_range_problems,
    item_out,
    loan_out,
    reservation_out,
    training_out,
    type_out,
)
from lms.branches.models import Branch
from lms.members.models import Member
from lms.members.service import get_member_or_404

router = APIRouter(tags=["equipment"])

TypeId = Annotated[int, Path(ge=1)]
ItemId = Annotated[int, Path(ge=1)]
LoanId = Annotated[int, Path(ge=1)]
ReservationId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]


def _optional_date(name: str, raw: str | None) -> datetime.date | None:
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, "expected a valid date in the form YYYY-MM-DD") from None


def _fields_of(body: BaseModel) -> dict[str, Any]:
    """The parsed values of a request body (``model_dump`` would serialize amounts to strings)."""
    return {name: getattr(body, name) for name in type(body).model_fields}


def _own_member_id(principal: Principal) -> int:
    member_id = principal.user.member_id
    if member_id is None:
        raise Forbidden("The authenticated user has no member record")
    return member_id


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden("Only your own equipment data can be accessed")


def _loan_out(db: SessionDep, loan: EquipmentLoan, now: datetime.datetime) -> EquipmentLoanOut:
    asset_tag, type_code = lending.loan_with_labels(db, loan)
    return loan_out(loan, asset_tag, type_code, now, lending.accrued_for(db, loan, now))


def _type_out(db: SessionDep, equipment_type: EquipmentType) -> TypeOut:
    total, available = inventory.item_counts(db, equipment_type.id)
    return type_out(equipment_type, total, available)


# --- types -----------------------------------------------------------------------------------


@router.post("/equipment-types", response_model=TypeOut, status_code=201)
def create_type(body: TypeCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> TypeOut:
    now = local_now(request.app.state.settings.clock)
    equipment_type = inventory.create_type(db, now, admin.user, **_fields_of(body))
    return _type_out(db, equipment_type)


@router.get("/equipment-types", response_model=Page[TypeOut])
def list_types(
    db: SessionDep, _: AnyUser, page: PageDep, is_active: Annotated[bool | None, Query()] = None
) -> Page[TypeOut]:
    stmt = sa.select(EquipmentType).order_by(EquipmentType.code, EquipmentType.id)
    if is_active is not None:
        stmt = stmt.where(EquipmentType.is_active == is_active)
    return paginate(db, stmt, page, lambda t: _type_out(db, t))


@router.get("/equipment-types/{type_id}", response_model=TypeOut)
def get_type(type_id: TypeId, db: SessionDep, _: AnyUser) -> TypeOut:
    return _type_out(db, inventory.get_type_or_404(db, type_id))


@router.patch("/equipment-types/{type_id}", response_model=TypeOut)
def update_type(type_id: TypeId, body: TypePatchIn, request: Request, db: SessionDep, admin: AdminOnly) -> TypeOut:
    now = local_now(request.app.state.settings.clock)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    problems = type_range_problems(None, fields.get("period"), fields.get("hourly_late_fee"), fields.get("max_open_per_member"))
    if problems:
        raise ValidationFailed(problems)
    equipment_type = inventory.get_type_or_404(db, type_id)
    return _type_out(db, inventory.update_type(db, now, admin.user, equipment_type, fields))


@router.get("/equipment-types/{type_id}/availability", response_model=AvailabilityOut)
def type_availability(
    type_id: TypeId,
    request: Request,
    db: SessionDep,
    _: AnyUser,
    branch_id: Annotated[int | None, Query()] = None,
    date: Annotated[str | None, Query()] = None,
) -> AvailabilityOut:
    settings = request.app.state.settings
    problems: list[dict[str, str]] = []
    if branch_id is None:
        problems.append({"field": "branch_id", "problem": "field required"})
    day: datetime.date | None = None
    if date is None:
        problems.append({"field": "date", "problem": "field required"})
    else:
        try:
            day = parse_date(date.strip())
        except ValueError:
            problems.append({"field": "date", "problem": "expected a valid date in the form YYYY-MM-DD"})
    if problems:
        raise ValidationFailed(problems)
    assert branch_id is not None and day is not None
    equipment_type = inventory.get_type_or_404(db, type_id)
    if db.get(Branch, branch_id) is None:
        raise reference_not_found("branch_id", branch_id)
    return reservation_service.availability(db, local_now(settings.clock), settings.holidays, equipment_type, branch_id, day)


# --- items -----------------------------------------------------------------------------------


@router.post("/equipment-items", response_model=ItemOut, status_code=201)
def create_item(body: ItemCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> ItemOut:
    now = local_now(request.app.state.settings.clock)
    return item_out(inventory.create_item(db, now, admin.user, **_fields_of(body)))


@router.get("/equipment-items", response_model=Page[ItemOut])
def list_items(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    type_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[ItemStatus | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> Page[ItemOut]:
    stmt = inventory.item_list_stmt(type_id=type_id, branch_id=branch_id, status=status, q=q)
    return paginate(db, stmt, page, item_out)


@router.get("/equipment-items/{item_id}", response_model=ItemOut)
def get_item(item_id: ItemId, db: SessionDep, _: StaffOnly) -> ItemOut:
    return item_out(inventory.get_item_or_404(db, item_id))


@router.patch("/equipment-items/{item_id}", response_model=ItemOut)
def update_item(item_id: ItemId, body: ItemPatchIn, request: Request, db: SessionDep, admin: AdminOnly) -> ItemOut:
    now = local_now(request.app.state.settings.clock)
    item = inventory.get_item_or_404(db, item_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return item_out(inventory.update_item(db, now, admin.user, item, fields))


@router.post("/equipment-items/{item_id}/retire", response_model=ItemOut)
def retire_item(item_id: ItemId, request: Request, db: SessionDep, admin: AdminOnly) -> ItemOut:
    now = local_now(request.app.state.settings.clock)
    item = inventory.get_item_or_404(db, item_id)
    return item_out(inventory.retire_item(db, now, admin.user, item))


@router.post("/equipment-items/{item_id}/repair-done", response_model=ItemOut)
def repair_done(item_id: ItemId, request: Request, db: SessionDep, staff: StaffOnly) -> ItemOut:
    now = local_now(request.app.state.settings.clock)
    item = inventory.get_item_or_404(db, item_id)
    return item_out(inventory.repair_done(db, now, staff.user, item))


# --- training --------------------------------------------------------------------------------


@router.post("/members/{member_id}/equipment-trainings", response_model=TrainingOut, status_code=201)
def record_training(
    member_id: MemberId, body: TrainingIn, request: Request, db: SessionDep, staff: StaffOnly
) -> TrainingOut:
    now = local_now(request.app.state.settings.clock)
    if body.completed_on > now.date():
        raise ValidationFailed.single("completed_on", "completed_on must not be after today")
    member = get_member_or_404(db, member_id)
    training = inventory.record_training(
        db, now, staff.user, member, type_id=body.type_id, completed_on=body.completed_on
    )
    return training_out(training)


@router.get("/members/{member_id}/equipment-trainings", response_model=Page[TrainingOut])
def list_trainings(member_id: MemberId, db: SessionDep, principal: CurrentPrincipal, page: PageDep) -> Page[TrainingOut]:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = sa.select(EquipmentTraining).where(EquipmentTraining.member_id == member.id).order_by(EquipmentTraining.id)
    return paginate(db, stmt, page, training_out)


# --- loans -----------------------------------------------------------------------------------


@router.post("/equipment-loans", response_model=EquipmentLoanOut, status_code=201)
def create_loan(body: LoanCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> EquipmentLoanOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    if (body.item_id is None) == (body.reservation_id is None):
        raise ValidationFailed.single("item_id", "exactly one of item_id and reservation_id is required")
    loan = lending.lend(
        db, now, staff.user, settings.holidays, member_id=body.member_id, item_id=body.item_id, reservation_id=body.reservation_id
    )
    return _loan_out(db, loan, now)


@router.get("/equipment-loans", response_model=Page[EquipmentLoanOut])
def list_loans(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    member_id: Annotated[int | None, Query()] = None,
    status: Annotated[LoanStatus | None, Query()] = None,
    type_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> Page[EquipmentLoanOut]:
    now = local_now(request.app.state.settings.clock)
    stmt = lending.loan_list_stmt(
        now, member_id=member_id, status=status, type_id=type_id, branch_id=branch_id, overdue=overdue
    )
    return paginate(db, stmt, page, lambda loan: _loan_out(db, loan, now))


@router.get("/equipment-loans/{loan_id}", response_model=EquipmentLoanOut)
def get_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> EquipmentLoanOut:
    now = local_now(request.app.state.settings.clock)
    loan = lending.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    return _loan_out(db, loan, now)


@router.get("/members/{member_id}/equipment-loans", response_model=Page[EquipmentLoanOut])
def list_member_loans(
    member_id: MemberId,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[LoanStatus | None, Query()] = None,
    type_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> Page[EquipmentLoanOut]:
    now = local_now(request.app.state.settings.clock)
    member: Member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = lending.loan_list_stmt(
        now, member_id=member.id, status=status, type_id=type_id, branch_id=branch_id, overdue=overdue
    )
    return paginate(db, stmt, page, lambda loan: _loan_out(db, loan, now))


@router.post("/equipment-loans/{loan_id}/return", response_model=EquipmentLoanOut)
def return_loan(loan_id: LoanId, body: ReturnIn, request: Request, db: SessionDep, staff: StaffOnly) -> EquipmentLoanOut:
    now = local_now(request.app.state.settings.clock)
    if body.condition == "damaged":
        if body.damage_fee is None:
            raise ValidationFailed.single("damage_fee", "damage_fee is required for a damaged return")
        if body.damage_fee < Decimal("0.00"):
            raise ValidationFailed.single("damage_fee", "damage_fee must not be negative")
    elif body.damage_fee is not None:
        raise ValidationFailed.single("damage_fee", "damage_fee must be absent for a good return")
    loan = lending.get_loan_or_404(db, loan_id)
    lending.return_loan(db, now, staff.user, loan, condition=body.condition, damage_fee=body.damage_fee)
    return _loan_out(db, loan, now)


@router.post("/equipment-loans/{loan_id}/extend", response_model=EquipmentLoanOut)
def extend_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> EquipmentLoanOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    loan = lending.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    lending.extend(db, now, principal.user, settings.holidays, loan)
    return _loan_out(db, loan, now)


@router.post("/equipment-loans/{loan_id}/report-lost", response_model=EquipmentLoanOut)
def report_lost(loan_id: LoanId, request: Request, db: SessionDep, staff: StaffOnly) -> EquipmentLoanOut:
    now = local_now(request.app.state.settings.clock)
    loan = lending.get_loan_or_404(db, loan_id)
    lending.report_lost(db, now, staff.user, loan)
    return _loan_out(db, loan, now)


# --- reservations ----------------------------------------------------------------------------


@router.post("/equipment-reservations", response_model=ReservationOut, status_code=201)
def create_reservation(
    body: ReservationCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> ReservationOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    if principal.user.role == "member":
        if body.member_id is not None:
            raise ValidationFailed.single("member_id", "members reserve for themselves and must not send member_id")
        member_id = _own_member_id(principal)
    else:
        if body.member_id is None:
            raise ValidationFailed.single("member_id", "member_id is required for librarians and admins")
        member_id = body.member_id
    reservation = reservation_service.create_reservation(
        db,
        now,
        principal.user,
        settings.holidays,
        type_id=body.type_id,
        branch_id=body.branch_id,
        member_id=member_id,
        starts_at=body.starts_at,
    )
    return reservation_out(reservation)


@router.get("/equipment-reservations", response_model=Page[ReservationOut])
def list_reservations(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[ReservationStatus | None, Query()] = None,
    type_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
) -> Page[ReservationOut]:
    stmt = reservation_service.reservation_list_stmt(
        member_id=member_id,
        status=status,
        type_id=type_id,
        branch_id=branch_id,
        first=_optional_date("from", first),
        last=_optional_date("to", to),
    )
    return paginate(db, stmt, page, reservation_out)


@router.get("/equipment-reservations/{reservation_id}", response_model=ReservationOut)
def get_reservation(reservation_id: ReservationId, db: SessionDep, principal: CurrentPrincipal) -> ReservationOut:
    reservation = reservation_service.get_reservation_or_404(db, reservation_id)
    _own_or_staff(principal, reservation.member_id)
    return reservation_out(reservation)


@router.get("/members/{member_id}/equipment-reservations", response_model=Page[ReservationOut])
def list_member_reservations(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[ReservationStatus | None, Query()] = None,
    type_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[ReservationOut]:
    first_date = _optional_date("from", first)
    last_date = _optional_date("to", to)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = reservation_service.reservation_list_stmt(
        member_id=member.id, status=status, type_id=type_id, branch_id=branch_id, first=first_date, last=last_date
    )
    return paginate(db, stmt, page, reservation_out)


@router.post("/equipment-reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_reservation(
    reservation_id: ReservationId, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> ReservationOut:
    now = local_now(request.app.state.settings.clock)
    reservation = reservation_service.get_reservation_or_404(db, reservation_id)
    _own_or_staff(principal, reservation.member_id)
    reservation_service.cancel(db, now, principal.user, reservation, by_member=principal.user.role == "member")
    return reservation_out(reservation)


@router.post("/equipment/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    now = local_now(request.app.state.settings.clock)
    expired, notices = reservation_service.process(db, now, staff.user)
    return ProcessOut(expired_reservations=expired, overdue_notices=notices)
