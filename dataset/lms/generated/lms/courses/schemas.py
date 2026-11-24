"""Request and response schemas of module 21 (section 29)."""

from __future__ import annotations

import datetime
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, ValidationInfo, field_validator

from lms.core.errors import ValidationFailed
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.courses.models import Course, Enrollment, ReadingListItem, ReserveLoan
from lms.rooms.schemas import DateValue

CourseStatus = Literal["draft", "active", "closed"]
EnrollmentStatus = Literal["enrolled", "dropped"]
ItemKind = Literal["required", "recommended"]
LoanPeriod = Literal["2h", "1d", "3d"]
ReserveLoanStatus = Literal["open", "returned", "lost"]
Id = StrictInt

_CODE_RE = re.compile(r"^[A-Za-z]{2,4}[0-9]{3}$")
_TERM_RE = re.compile(r"^(\d{4})-(fall|spring|summer)$")

Title = Annotated[str, Field(min_length=1, max_length=200)]
EnrollmentLimit = Annotated[StrictInt, Field(ge=1, le=300)]
CopiesWanted = Annotated[StrictInt, Field(ge=1, le=5)]
Note = Annotated[str, Field(max_length=500)]

MIN_SPAN_DAYS = 6
MAX_SPAN_DAYS = 179


def check_span(starts_on: datetime.date, ends_on: datetime.date) -> str | None:
    days = (ends_on - starts_on).days
    if not MIN_SPAN_DAYS <= days <= MAX_SPAN_DAYS:
        return "ends_on must be 6 to 179 days after starts_on"
    return None


# --- requests -----------------------------------------------------------------------------------


class CourseCreateIn(RequestModel):
    code: str
    title: Title
    term: str
    instructor_id: Id
    branch_id: Id
    starts_on: DateValue
    ends_on: DateValue
    enrollment_limit: EnrollmentLimit = 100

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not _CODE_RE.match(value):
            raise ValueError("code must be 2-4 letters A-Z followed by 3 digits")
        return value.upper()

    @field_validator("term")
    @classmethod
    def _term(cls, value: str) -> str:
        match = _TERM_RE.match(value)
        if match is None or not 2000 <= int(match.group(1)) <= 2100:
            raise ValueError('term must be "<year>-fall", "<year>-spring" or "<year>-summer" with a year 2000-2100')
        return value

    @field_validator("ends_on")
    @classmethod
    def _span(cls, value: datetime.date, info: ValidationInfo) -> datetime.date:
        starts_on = info.data.get("starts_on")
        if starts_on is not None:
            problem = check_span(starts_on, value)
            if problem is not None:
                raise ValueError(problem)
        return value


class CoursePatchIn(RequestModel):
    """Any subset of the fields; ``code``, ``term`` and ``branch_id`` cannot be changed (unknown here, so ``422``)."""

    title: Title = None  # type: ignore[assignment]
    instructor_id: Id = None  # type: ignore[assignment]
    starts_on: DateValue = None  # type: ignore[assignment]
    ends_on: DateValue = None  # type: ignore[assignment]
    enrollment_limit: EnrollmentLimit = None  # type: ignore[assignment]


class EnrollIn(RequestModel):
    member_ids: Annotated[list[Id], Field(min_length=1, max_length=100)]

    @field_validator("member_ids")
    @classmethod
    def _distinct(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("member_ids must be distinct")
        return value


class ItemCreateIn(RequestModel):
    book_id: Id
    kind: ItemKind = "required"
    loan_period: LoanPeriod = "2h"
    copies_wanted: CopiesWanted = 1
    note: Note = ""


class ItemPatchIn(RequestModel):
    """Any subset of the fields; ``null`` is not accepted for any of them."""

    kind: ItemKind = None  # type: ignore[assignment]
    loan_period: LoanPeriod = None  # type: ignore[assignment]
    copies_wanted: CopiesWanted = None  # type: ignore[assignment]
    note: Note = None  # type: ignore[assignment]


class OrderIn(RequestModel):
    item_ids: list[Id]


class PlaceCopyIn(RequestModel):
    copy_id: Id


class ReserveLoanCreateIn(RequestModel):
    member_id: Id
    copy_id: Id | None = None
    barcode: str | None = None

    def check(self) -> None:
        """LIB-CRS-24: exactly one of ``copy_id`` and ``barcode``."""
        if (self.copy_id is None) == (self.barcode is None):
            raise ValidationFailed.single("copy_id", "exactly one of copy_id and barcode is required")
        if self.barcode is not None and not self.barcode:
            raise ValidationFailed.single("barcode", "barcode must not be empty")


class ReserveReturnIn(RequestModel):
    branch_id: Id


# --- responses ----------------------------------------------------------------------------------


def _dt(value: datetime.datetime | None) -> str | None:
    return None if value is None else format_datetime(value)


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    term: str
    instructor_id: int
    branch_id: int
    starts_on: datetime.date
    ends_on: datetime.date
    enrollment_limit: int
    status: str
    created_at: str
    activated_at: str | None
    closed_at: str | None
    enrolled: int
    items: int
    copies_on_reserve: int


class CourseClosedOut(CourseOut):
    released_copies: int


class MemberCourseOut(CourseOut):
    role: str


def course_fields(course: Course, *, enrolled: int, items: int, copies_on_reserve: int) -> dict:
    return {
        "id": course.id,
        "code": course.code,
        "title": course.title,
        "term": course.term,
        "instructor_id": course.instructor_id,
        "branch_id": course.branch_id,
        "starts_on": course.starts_on,
        "ends_on": course.ends_on,
        "enrollment_limit": course.enrollment_limit,
        "status": course.status,
        "created_at": format_datetime(course.created_at),
        "activated_at": _dt(course.activated_at),
        "closed_at": _dt(course.closed_at),
        "enrolled": enrolled,
        "items": items,
        "copies_on_reserve": copies_on_reserve,
    }


class EnrollmentOut(BaseModel):
    id: int
    course_id: int
    member_id: int
    member_no: str
    full_name: str
    status: str
    enrolled_at: str
    dropped_at: str | None
    drop_reason: str | None


def enrollment_out(enrollment: Enrollment, member_no: str, full_name: str) -> EnrollmentOut:
    return EnrollmentOut(
        id=enrollment.id,
        course_id=enrollment.course_id,
        member_id=enrollment.member_id,
        member_no=member_no,
        full_name=full_name,
        status=enrollment.status,
        enrolled_at=format_datetime(enrollment.enrolled_at),
        dropped_at=_dt(enrollment.dropped_at),
        drop_reason=enrollment.drop_reason,
    )


class SkippedOut(BaseModel):
    member_id: int
    error_code: str


class EnrollResultOut(BaseModel):
    enrolled: list[int]
    skipped: list[SkippedOut]


class ItemOut(BaseModel):
    id: int
    course_id: int
    book_id: int
    kind: str
    loan_period: str
    copies_wanted: int
    note: str
    position: int | None
    status: str
    added_at: str
    book_title: str
    copies_on_reserve: int
    available_now: int
    next_due_at: str | None


def item_fields(
    item: ReadingListItem, *, book_title: str, copies_on_reserve: int, available_now: int, next_due_at: datetime.datetime | None
) -> ItemOut:
    return ItemOut(
        id=item.id,
        course_id=item.course_id,
        book_id=item.book_id,
        kind=item.kind,
        loan_period=item.loan_period,
        copies_wanted=item.copies_wanted,
        note=item.note,
        position=item.position,
        status=item.status,
        added_at=format_datetime(item.added_at),
        book_title=book_title,
        copies_on_reserve=copies_on_reserve,
        available_now=available_now,
        next_due_at=_dt(next_due_at),
    )


class PlacedCopyOut(BaseModel):
    copy_id: int
    barcode: str
    item_id: int
    course_id: int
    on_loan: bool


class ReserveLoanOut(BaseModel):
    id: int
    copy_id: int
    item_id: int
    course_id: int
    member_id: int
    lent_at: str
    due_at: str
    renewed: bool
    status: str
    returned_at: str | None
    late_minutes: int | None
    fee_id: int | None
    book_title: str
    course_code: str
    is_overdue: bool
    accrued_late_fee: str


class ProcessOut(BaseModel):
    overdue_notices: int
    closed_courses: int
    released_copies: int
    pending_courses: int


class CourseReservesSummaryOut(BaseModel):
    courses_enrolled: int
    courses_teaching: int
    open_reserve_loans: int
    overdue_reserve_loans: int


class CourseReportOut(BaseModel):
    course_id: int
    code: str
    title: str
    term: str
    status: str
    enrolled: int
    items: int
    items_unfilled: int
    loans: int
    borrowers: int
    late_returns: int
    fees_charged: str


def reserve_loan_dt(loan: ReserveLoan) -> tuple[str, str, str | None]:
    return format_datetime(loan.lent_at), format_datetime(loan.due_at), _dt(loan.returned_at)
