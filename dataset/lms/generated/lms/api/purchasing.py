"""Purchasing endpoints (section 18.2)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from lms.auth.deps import StaffOnly
from lms.core.context import HolidaysDep, NowDep, PathId
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, paginate
from lms.purchasing import service
from lms.purchasing.schemas import (
    OrderCreateIn,
    OrderOut,
    OrderPatchIn,
    ReceiveIn,
    SupplierCreateIn,
    SupplierOut,
    SupplierPatchIn,
    order_out,
    supplier_out,
)

router = APIRouter(tags=["purchasing"])

OrderStatus = Literal["draft", "ordered", "partially_received", "received", "cancelled"]


def _order(db, order) -> OrderOut:  # noqa: ANN001
    return order_out(order, service.order_lines(db, order.id))


# --- suppliers ----------------------------------------------------------------------


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierCreateIn, now: NowDep, db: SessionDep, staff: StaffOnly) -> SupplierOut:
    return supplier_out(
        service.create_supplier(db, now, staff.user, name=body.name, email=body.email, phone=body.phone)
    )


@router.get("/suppliers", response_model=Page[SupplierOut])
def list_suppliers(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    q: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[SupplierOut]:
    return paginate(db, service.supplier_list_stmt(q, is_active), page, supplier_out)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: PathId, db: SessionDep, _: StaffOnly) -> SupplierOut:
    return supplier_out(service.get_supplier_or_404(db, supplier_id))


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: PathId, body: SupplierPatchIn, now: NowDep, db: SessionDep, staff: StaffOnly
) -> SupplierOut:
    supplier = service.get_supplier_or_404(db, supplier_id)
    return supplier_out(service.update_supplier(db, now, staff.user, supplier, body.provided_fields()))


# --- purchase orders ----------------------------------------------------------------


@router.post("/purchase-orders", response_model=OrderOut, status_code=201)
def create_order(body: OrderCreateIn, now: NowDep, db: SessionDep, staff: StaffOnly) -> OrderOut:
    order = service.create_order(
        db, now, staff.user, supplier_id=body.supplier_id, branch_id=body.branch_id, lines=body.lines
    )
    return _order(db, order)


@router.get("/purchase-orders", response_model=Page[OrderOut])
def list_orders(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[OrderStatus | None, Query()] = None,
    supplier_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[OrderOut]:
    stmt = service.order_list_stmt(status=status, supplier_id=supplier_id, branch_id=branch_id)
    return paginate(db, stmt, page, lambda order: _order(db, order))


@router.get("/purchase-orders/{order_id}", response_model=OrderOut)
def get_order(order_id: PathId, db: SessionDep, _: StaffOnly) -> OrderOut:
    return _order(db, service.get_order_or_404(db, order_id))


@router.patch("/purchase-orders/{order_id}", response_model=OrderOut)
def update_order(order_id: PathId, body: OrderPatchIn, now: NowDep, db: SessionDep, staff: StaffOnly) -> OrderOut:
    order = service.get_order_or_404(db, order_id)
    return _order(db, service.update_order(db, now, staff.user, order, body.provided_fields()))


@router.post("/purchase-orders/{order_id}/submit", response_model=OrderOut)
def submit_order(order_id: PathId, now: NowDep, db: SessionDep, staff: StaffOnly) -> OrderOut:
    return _order(db, service.submit_order(db, now, staff.user, service.get_order_or_404(db, order_id)))


@router.post("/purchase-orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: PathId, now: NowDep, db: SessionDep, staff: StaffOnly) -> OrderOut:
    return _order(db, service.cancel_order(db, now, staff.user, service.get_order_or_404(db, order_id)))


@router.post("/purchase-orders/{order_id}/receive", response_model=OrderOut)
def receive_order(
    order_id: PathId, body: ReceiveIn, now: NowDep, holidays: HolidaysDep, db: SessionDep, staff: StaffOnly
) -> OrderOut:
    order = service.get_order_or_404(db, order_id)
    return _order(db, service.receive_order(db, now, staff.user, holidays, order, body.lines))
