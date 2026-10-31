"""Request and response schemas of module 12 (section 18)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator, model_validator

from lms.catalog.schemas import check_barcode
from lms.core.money import Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.members.schemas import check_email, check_phone
from lms.purchasing.models import PurchaseOrder, PurchaseOrderLine, Supplier

MAX_LINES = 50
MIN_UNIT_PRICE = Decimal("0.01")
MAX_UNIT_PRICE = Decimal("100000.00")

SupplierName = Annotated[str, Field(min_length=1, max_length=200)]


class _SupplierChecks:
    @field_validator("email", check_fields=False)
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else check_email(value)

    @field_validator("phone", check_fields=False)
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return check_phone(value)


class SupplierCreateIn(_SupplierChecks, RequestModel):
    name: SupplierName
    email: str | None = None
    phone: str | None = None


class SupplierPatchIn(_SupplierChecks, RequestModel):
    """Any subset of the fields. ``email`` and ``phone`` may be ``null``; the others may not."""

    name: SupplierName = None  # type: ignore[assignment]
    email: str | None = None
    phone: str | None = None
    is_active: StrictBool = None  # type: ignore[assignment]


class SupplierOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    is_active: bool


def supplier_out(supplier: Supplier) -> SupplierOut:
    return SupplierOut(
        id=supplier.id, name=supplier.name, email=supplier.email, phone=supplier.phone, is_active=supplier.is_active
    )


# --- orders -------------------------------------------------------------------


class LineIn(RequestModel):
    book_id: StrictInt
    quantity: Annotated[StrictInt, Field(ge=1, le=100)]
    unit_price: Money

    @field_validator("unit_price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        if not MIN_UNIT_PRICE <= value <= MAX_UNIT_PRICE:
            raise ValueError("unit_price must be between 0.01 and 100000.00")
        return value


def _distinct_books(lines: list[LineIn]) -> list[LineIn]:
    if len({line.book_id for line in lines}) != len(lines):
        raise ValueError("a book may appear only once per order")
    return lines


Lines = Annotated[list[LineIn], Field(max_length=MAX_LINES)]


class OrderCreateIn(RequestModel):
    supplier_id: StrictInt
    branch_id: StrictInt
    lines: Lines = Field(default_factory=list)

    @field_validator("lines")
    @classmethod
    def _lines(cls, value: list[LineIn]) -> list[LineIn]:
        return _distinct_books(value)


class OrderPatchIn(RequestModel):
    supplier_id: StrictInt = None  # type: ignore[assignment]
    branch_id: StrictInt = None  # type: ignore[assignment]
    lines: Lines = None  # type: ignore[assignment]

    @field_validator("lines")
    @classmethod
    def _lines(cls, value: list[LineIn]) -> list[LineIn]:
        return _distinct_books(value)


class ReceiveLineIn(RequestModel):
    line_id: StrictInt
    barcodes: Annotated[list[str], Field(min_length=1)]

    @field_validator("barcodes")
    @classmethod
    def _barcodes(cls, value: list[str]) -> list[str]:
        return [check_barcode(v) for v in value]


class ReceiveIn(RequestModel):
    lines: Annotated[list[ReceiveLineIn], Field(min_length=1)]

    @model_validator(mode="after")
    def _distinct_lines(self) -> ReceiveIn:
        ids = [line.line_id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("lines must not repeat a line_id")
        return self


class LineOut(BaseModel):
    id: int
    book_id: int
    quantity: int
    unit_price: str
    received_quantity: int


class OrderOut(BaseModel):
    id: int
    supplier_id: int
    branch_id: int
    status: str
    lines: list[LineOut]
    created_by: int
    created_at: str
    ordered_on: str | None
    total: str


def line_out(line: PurchaseOrderLine) -> LineOut:
    return LineOut(
        id=line.id,
        book_id=line.book_id,
        quantity=line.quantity,
        unit_price=format_amount(line.unit_price),
        received_quantity=line.received_quantity,
    )


def order_out(order: PurchaseOrder, lines: list[PurchaseOrderLine]) -> OrderOut:
    total = sum((line.quantity * line.unit_price for line in lines), Decimal("0"))
    return OrderOut(
        id=order.id,
        supplier_id=order.supplier_id,
        branch_id=order.branch_id,
        status=order.status,
        lines=[line_out(line) for line in lines],
        created_by=order.created_by,
        created_at=format_datetime(order.created_at),
        ordered_on=order.ordered_on.isoformat() if order.ordered_on is not None else None,
        total=format_amount(total),
    )
