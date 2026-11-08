"""Request and response schemas of module 18 (section 26)."""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, StrictBool, StrictInt, field_validator, model_validator

from lms.catalog.isbn import normalize_isbn
from lms.core.money import Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.text import is_valid_email
from lms.core.timeutil import format_datetime, parse_date
from lms.ill.accrual import is_overdue, late_fee_on
from lms.ill.models import IllOutgoing, IllPartner, IllRequest

RequestStatus = Literal[
    "requested", "sent", "rejected", "received", "on_loan", "returned", "uncollected", "closed", "cancelled", "lost"
]
OutgoingStatus = Literal["requested", "shipped", "declined", "returned", "lost"]

_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")

Id = StrictInt
Name = Annotated[str, Field(min_length=1, max_length=200)]

MAX_REQUEST_FEE = Decimal("50.00")
MAX_DAILY_LATE_FEE = Decimal("10.00")
MIN_REPLACEMENT_COST = Decimal("0.01")
MAX_REPLACEMENT_COST = Decimal("100000.00")


def _parse_date_value(value: Any) -> datetime.date:
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    return parse_date(value)


DateValue = Annotated[datetime.date, BeforeValidator(_parse_date_value)]


def _email(value: str) -> str:
    value = value.lower()
    if len(value) > 254 or not is_valid_email(value):
        raise ValueError("invalid e-mail address")
    return value


def fee_range_problems(
    request_fee: Decimal | None, daily_late_fee: Decimal | None, max_outgoing: int | None
) -> list[dict[str, str]]:
    """The value rules of 26.1 for partners; ``None`` skips a field."""
    problems: list[dict[str, str]] = []
    if request_fee is not None and not Decimal("0.00") <= request_fee <= MAX_REQUEST_FEE:
        problems.append({"field": "request_fee", "problem": "request_fee must be between 0.00 and 50.00"})
    if daily_late_fee is not None and not Decimal("0.00") <= daily_late_fee <= MAX_DAILY_LATE_FEE:
        problems.append({"field": "daily_late_fee", "problem": "daily_late_fee must be between 0.00 and 10.00"})
    if max_outgoing is not None and not 1 <= max_outgoing <= 20:
        problems.append({"field": "max_outgoing", "problem": "max_outgoing must be between 1 and 20"})
    return problems


# --- partners ---------------------------------------------------------------------

class _RangeChecks:
    @field_validator("request_fee", "daily_late_fee", "max_outgoing", check_fields=False)
    @classmethod
    def _ranges(cls, value, info):  # noqa: ANN001, ANN202
        kwargs = {info.field_name: value}
        problems = fee_range_problems(
            kwargs.get("request_fee"), kwargs.get("daily_late_fee"), kwargs.get("max_outgoing")
        )
        if problems:
            raise ValueError(problems[0]["problem"])
        return value



class PartnerCreateIn(_RangeChecks, RequestModel):
    code: str
    name: Name
    email: str
    request_fee: Money
    daily_late_fee: Money
    max_outgoing: Id

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not _CODE_RE.match(value):
            raise ValueError("code must be 2-10 characters from A-Z and 0-9")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _email(value)


class PartnerPatchIn(_RangeChecks, RequestModel):
    """Any subset of the fields; ``null`` is not accepted for any of them."""

    name: Name = None  # type: ignore[assignment]
    email: str = None  # type: ignore[assignment]
    request_fee: Money = None  # type: ignore[assignment]
    daily_late_fee: Money = None  # type: ignore[assignment]
    max_outgoing: Id = None  # type: ignore[assignment]
    is_active: StrictBool = None  # type: ignore[assignment]

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _email(value)


class PartnerOut(BaseModel):
    id: int
    code: str
    name: str
    email: str
    request_fee: str
    daily_late_fee: str
    max_outgoing: int
    is_active: bool
    open_incoming: int
    open_outgoing: int


def partner_out(p: IllPartner, open_incoming: int = 0, open_outgoing: int = 0) -> PartnerOut:
    return PartnerOut(
        id=p.id,
        code=p.code,
        name=p.name,
        email=p.email,
        request_fee=format_amount(p.request_fee),
        daily_late_fee=format_amount(p.daily_late_fee),
        max_outgoing=p.max_outgoing,
        is_active=p.is_active,
        open_incoming=open_incoming,
        open_outgoing=open_outgoing,
    )


# --- incoming requests --------------------------------------------------------------


class RequestCreateIn(RequestModel):
    member_id: Id | None = None
    title: Name
    author: Name
    isbn: str | None = None

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, value: str | None) -> str | None:
        return normalize_isbn(value) if value is not None else None


class SendIn(RequestModel):
    partner_id: Id


class RejectIn(RequestModel):
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class ReceiveIn(RequestModel):
    partner_due_on: DateValue
    replacement_cost: Money
    pickup_branch_id: Id

    @field_validator("replacement_cost")
    @classmethod
    def _cost(cls, value: Decimal) -> Decimal:
        if not MIN_REPLACEMENT_COST <= value <= MAX_REPLACEMENT_COST:
            raise ValueError("replacement_cost must be between 0.01 and 100000.00")
        return value


class BranchIn(RequestModel):
    branch_id: Id


class RenewalAnswerIn(RequestModel):
    approved: StrictBool
    partner_due_on: DateValue | None = None

    @model_validator(mode="after")
    def _date_needed(self) -> RenewalAnswerIn:
        if self.approved and self.partner_due_on is None:
            raise ValueError("partner_due_on is required when the renewal is approved")
        return self


class RequestOut(BaseModel):
    id: int
    member_id: int
    title: str
    author: str
    isbn: str | None
    status: str
    partner_id: int | None
    tried_partner_ids: list[int]
    pickup_branch_id: int | None
    received_on: str | None
    collect_until: str | None
    partner_due_on: str | None
    due_on: str | None
    replacement_cost: str | None
    renewal: str
    collected_on: str | None
    returned_on: str | None
    closed_on: str | None
    cancel_reason: str | None
    reject_reason: str | None
    created_at: str
    overdue: bool
    accrued_late_fee: str


def _date_str(value: datetime.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def request_out(r: IllRequest, today: datetime.date) -> RequestOut:
    overdue = is_overdue(r, today)
    return RequestOut(
        id=r.id,
        member_id=r.member_id,
        title=r.title,
        author=r.author,
        isbn=r.isbn,
        status=r.status,
        partner_id=r.partner_id,
        tried_partner_ids=list(r.tried_partner_ids or []),
        pickup_branch_id=r.pickup_branch_id,
        received_on=_date_str(r.received_on),
        collect_until=_date_str(r.collect_until),
        partner_due_on=_date_str(r.partner_due_on),
        due_on=_date_str(r.due_on),
        replacement_cost=format_amount(r.replacement_cost) if r.replacement_cost is not None else None,
        renewal=r.renewal,
        collected_on=_date_str(r.collected_on),
        returned_on=_date_str(r.returned_on),
        closed_on=_date_str(r.closed_on),
        cancel_reason=r.cancel_reason,
        reject_reason=r.reject_reason,
        created_at=format_datetime(r.created_at),
        overdue=overdue,
        accrued_late_fee=format_amount(late_fee_on(r, today) if overdue else Decimal("0.00")),
    )


# --- outgoing requests --------------------------------------------------------------


class OutgoingCreateIn(RequestModel):
    partner_id: Id
    book_id: Id


class ShipIn(RequestModel):
    copy_id: Id


class OutgoingOut(BaseModel):
    id: int
    partner_id: int
    book_id: int
    status: str
    copy_id: int | None
    shipped_on: str | None
    due_on: str | None
    returned_on: str | None
    amount_due: str | None
    created_at: str
    overdue: bool
    book_title: str
    barcode: str | None


def outgoing_overdue(o: IllOutgoing, today: datetime.date) -> bool:
    return o.status == "shipped" and o.due_on is not None and today > o.due_on


def outgoing_out(o: IllOutgoing, today: datetime.date, book_title: str, barcode: str | None) -> OutgoingOut:
    return OutgoingOut(
        id=o.id,
        partner_id=o.partner_id,
        book_id=o.book_id,
        status=o.status,
        copy_id=o.copy_id,
        shipped_on=_date_str(o.shipped_on),
        due_on=_date_str(o.due_on),
        returned_on=_date_str(o.returned_on),
        amount_due=format_amount(o.amount_due) if o.amount_due is not None else None,
        created_at=format_datetime(o.created_at),
        overdue=outgoing_overdue(o, today),
        book_title=book_title,
        barcode=barcode,
    )


# --- other --------------------------------------------------------------------------


class ProcessOut(BaseModel):
    uncollected: int
    overdue_outgoing: int


class IllSummaryOut(BaseModel):
    open_requests: int
    on_loan: int
    overdue: int


class IllActivityOut(BaseModel):
    partner_id: int
    partner_code: str
    sent: int
    rejected: int
    received: int
    late_returns: int
    outgoing_shipped: int
    outgoing_returned: int
    outgoing_lost: int
    amount_due: str
