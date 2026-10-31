"""Business logic of module 12: purchasing (LIB-PUR-01 to LIB-PUR-09)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Book
from lms.catalog.service import add_copy
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.core.money import format_amount
from lms.core.text import normalize
from lms.purchasing.models import PurchaseOrder, PurchaseOrderLine, Supplier
from lms.purchasing.schemas import LineIn, ReceiveLineIn

# --- suppliers ------------------------------------------------------------------


def get_supplier_or_404(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFound(f"Supplier {supplier_id} does not exist", details={"resource": "supplier", "id": supplier_id})
    return supplier


def _check_unique_name(db: Session, name: str, *, own_id: int | None = None) -> None:
    stmt = sa.select(Supplier.id).where(Supplier.name_key == normalize(name))
    if own_id is not None:
        stmt = stmt.where(Supplier.id != own_id)
    if db.scalar(stmt) is not None:
        raise Conflict("A supplier with this name already exists", details={"field": "name"})


def create_supplier(
    db: Session, now: datetime.datetime, actor: User, *, name: str, email: str | None, phone: str | None
) -> Supplier:
    """LIB-PUR-01."""
    _check_unique_name(db, name)
    supplier = Supplier(name=name, name_key=normalize(name), email=email, phone=phone, is_active=True)
    db.add(supplier)
    db.flush()
    record(
        db,
        at=now,
        event="supplier_created",
        actor_user_id=actor.id,
        entity_type="supplier",
        entity_id=supplier.id,
        details={"name": name, "email": email, "phone": phone},
    )
    return supplier


def update_supplier(
    db: Session, now: datetime.datetime, actor: User, supplier: Supplier, fields: dict[str, Any]
) -> Supplier:
    """LIB-PUR-01. ``fields`` holds only the fields present in the request."""
    if "name" in fields:
        _check_unique_name(db, fields["name"], own_id=supplier.id)
    diff = changes({name: getattr(supplier, name) for name in fields}, fields)
    for name, value in fields.items():
        setattr(supplier, name, value)
    if "name" in fields:
        supplier.name_key = normalize(supplier.name)
    if diff:
        record(
            db,
            at=now,
            event="supplier_updated",
            actor_user_id=actor.id,
            entity_type="supplier",
            entity_id=supplier.id,
            details=diff,
        )
    return supplier


def supplier_list_stmt(q: str | None, is_active: bool | None) -> sa.Select[tuple[Supplier]]:
    stmt = sa.select(Supplier).order_by(Supplier.name_key, Supplier.id)
    needle = normalize(q.strip()) if q is not None else ""
    if needle:
        stmt = stmt.where(Supplier.name_key.contains(needle, autoescape=True))
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active == is_active)
    return stmt


# --- orders: helpers --------------------------------------------------------------


def get_order_or_404(db: Session, order_id: int) -> PurchaseOrder:
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise NotFound(
            f"Purchase order {order_id} does not exist", details={"resource": "purchase_order", "id": order_id}
        )
    return order


def order_lines(db: Session, order_id: int) -> list[PurchaseOrderLine]:
    return list(
        db.scalars(
            sa.select(PurchaseOrderLine).where(PurchaseOrderLine.order_id == order_id).order_by(PurchaseOrderLine.id)
        )
    )


def _invalid_status(order: PurchaseOrder, action: str) -> Conflict:
    return Conflict(
        f"Purchase order {order.id} has status {order.status}: {action} is not allowed",
        code="INVALID_ORDER_STATUS",
        details={"id": order.id, "status": order.status},
    )


def _require_books(db: Session, lines: list[LineIn]) -> None:
    for index, line in enumerate(lines):
        if db.get(Book, line.book_id) is None:
            raise NotFound(
                f"book_id {line.book_id} does not exist",
                details={"field": f"lines[{index}].book_id", "id": line.book_id},
            )


def _check_branch_active(branch: Branch, field: str) -> None:
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": field, "id": branch.id}
        )


def _check_supplier_active(supplier: Supplier) -> None:
    if not supplier.is_active:
        raise Conflict("The supplier is inactive", code="SUPPLIER_INACTIVE", details={"id": supplier.id})


def _lines_details(lines: list[LineIn] | list[PurchaseOrderLine]) -> list[dict[str, Any]]:
    return [
        {"book_id": ln.book_id, "quantity": ln.quantity, "unit_price": format_amount(ln.unit_price)} for ln in lines
    ]


def _add_lines(db: Session, order: PurchaseOrder, lines: list[LineIn]) -> None:
    db.add_all(
        PurchaseOrderLine(
            order_id=order.id, book_id=ln.book_id, quantity=ln.quantity, unit_price=ln.unit_price, received_quantity=0
        )
        for ln in lines
    )
    db.flush()


# --- orders: create and edit ----------------------------------------------------


def create_order(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    supplier_id: int,
    branch_id: int,
    lines: list[LineIn],
) -> PurchaseOrder:
    """LIB-PUR-02."""
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise reference_not_found("supplier_id", supplier_id)
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found("branch_id", branch_id)
    _require_books(db, lines)
    _check_branch_active(branch, "branch_id")  # LIB-BR-04: before all other 409 checks
    _check_supplier_active(supplier)

    order = PurchaseOrder(
        supplier_id=supplier_id, branch_id=branch_id, status="draft", created_by=actor.id, created_at=now
    )
    db.add(order)
    db.flush()
    _add_lines(db, order, lines)
    record(
        db,
        at=now,
        event="purchase_order_created",
        actor_user_id=actor.id,
        entity_type="purchase_order",
        entity_id=order.id,
        details={"supplier_id": supplier_id, "branch_id": branch_id, "lines": _lines_details(lines)},
    )
    return order


def update_order(
    db: Session, now: datetime.datetime, actor: User, order: PurchaseOrder, fields: dict[str, Any]
) -> PurchaseOrder:
    """LIB-PUR-03. ``fields`` holds only the fields present in the request."""
    supplier = branch = None
    if "supplier_id" in fields:
        supplier = db.get(Supplier, fields["supplier_id"])
        if supplier is None:
            raise reference_not_found("supplier_id", fields["supplier_id"])
    if "branch_id" in fields:
        branch = db.get(Branch, fields["branch_id"])
        if branch is None:
            raise reference_not_found("branch_id", fields["branch_id"])
    if "lines" in fields:
        _require_books(db, fields["lines"])
    if branch is not None:
        _check_branch_active(branch, "branch_id")  # LIB-BR-04: before all other 409 checks
    if order.status != "draft":
        raise _invalid_status(order, "editing")
    if supplier is not None:
        _check_supplier_active(supplier)

    diff: dict[str, dict[str, Any]] = {}
    for name in ("supplier_id", "branch_id"):
        if name in fields:
            diff.update(changes({name: getattr(order, name)}, {name: fields[name]}))
            setattr(order, name, fields[name])
    if "lines" in fields:
        old = _lines_details(order_lines(db, order.id))
        new = _lines_details(fields["lines"])
        if old != new:
            diff["lines"] = {"old": old, "new": new}
        db.execute(sa.delete(PurchaseOrderLine).where(PurchaseOrderLine.order_id == order.id))
        db.flush()
        _add_lines(db, order, fields["lines"])
    if diff:
        record(
            db,
            at=now,
            event="purchase_order_updated",
            actor_user_id=actor.id,
            entity_type="purchase_order",
            entity_id=order.id,
            details=diff,
        )
    return order


# --- orders: status changes -------------------------------------------------------


def submit_order(db: Session, now: datetime.datetime, actor: User, order: PurchaseOrder) -> PurchaseOrder:
    """LIB-PUR-04."""
    if order.status != "draft":
        raise _invalid_status(order, "submit")
    lines = order_lines(db, order.id)
    if not lines:
        raise Conflict("The purchase order has no lines", code="ORDER_EMPTY", details={"id": order.id})
    order.status = "ordered"
    order.ordered_on = now.date()
    record(
        db,
        at=now,
        event="purchase_order_submitted",
        actor_user_id=actor.id,
        entity_type="purchase_order",
        entity_id=order.id,
        details={"ordered_on": order.ordered_on.isoformat(), "lines": len(lines)},
    )
    return order


def cancel_order(db: Session, now: datetime.datetime, actor: User, order: PurchaseOrder) -> PurchaseOrder:
    """LIB-PUR-05."""
    if order.status not in ("draft", "ordered"):
        raise _invalid_status(order, "cancel")
    old = order.status
    order.status = "cancelled"
    record(
        db,
        at=now,
        event="purchase_order_cancelled",
        actor_user_id=actor.id,
        entity_type="purchase_order",
        entity_id=order.id,
        details={"status": {"old": old, "new": "cancelled"}},
    )
    return order


def receive_order(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    order: PurchaseOrder,
    request_lines: list[ReceiveLineIn],
) -> PurchaseOrder:
    """LIB-PUR-06 to LIB-PUR-08."""
    lines = {line.id: line for line in order_lines(db, order.id)}
    for index, received in enumerate(request_lines):
        if received.line_id not in lines:
            raise NotFound(
                f"line_id {received.line_id} is not a line of this order",
                details={"field": f"lines[{index}].line_id", "id": received.line_id},
            )
    branch = db.get(Branch, order.branch_id)
    assert branch is not None
    _check_branch_active(branch, "branch_id")  # LIB-BR-04: before all other 409 checks
    if order.status not in ("ordered", "partially_received"):
        raise _invalid_status(order, "receive")

    for received in request_lines:
        line = lines[received.line_id]
        if line.received_quantity + len(received.barcodes) > line.quantity:
            raise Conflict(
                f"Line {line.id} would receive more than the ordered quantity",
                code="RECEIVE_EXCEEDS_ORDERED",
                details={
                    "line_id": line.id,
                    "quantity": line.quantity,
                    "received_quantity": line.received_quantity,
                    "requested": len(received.barcodes),
                },
            )
    seen: set[str] = set()
    for received in request_lines:
        for barcode in received.barcodes:
            if barcode in seen:
                raise Conflict("The barcode is repeated in the request", details={"field": "barcodes", "value": barcode})
            seen.add(barcode)

    today = now.date()
    new_copies: list[dict[str, Any]] = []
    for received in request_lines:
        line = lines[received.line_id]
        book = db.get(Book, line.book_id)
        assert book is not None
        for barcode in received.barcodes:
            copy = add_copy(
                db,
                now,
                actor,
                book,
                barcode=barcode,
                home_branch_id=order.branch_id,
                price=line.unit_price,
                acquired_on=today,
                shelf_location=None,
                holidays=holidays,
            )
            new_copies.append({"line_id": line.id, "copy_id": copy.id, "barcode": barcode})
        line.received_quantity += len(received.barcodes)

    old = order.status
    order.status = "received" if all(ln.received_quantity == ln.quantity for ln in lines.values()) else "partially_received"
    record(
        db,
        at=now,
        event="purchase_order_received",
        actor_user_id=actor.id,
        entity_type="purchase_order",
        entity_id=order.id,
        details={"copies": new_copies, "status": {"old": old, "new": order.status}},
    )
    return order


def order_list_stmt(
    *, status: str | None, supplier_id: int | None, branch_id: int | None
) -> sa.Select[tuple[PurchaseOrder]]:
    """LIB-PUR-09."""
    stmt = sa.select(PurchaseOrder).order_by(PurchaseOrder.id.desc())
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if branch_id is not None:
        stmt = stmt.where(PurchaseOrder.branch_id == branch_id)
    return stmt
