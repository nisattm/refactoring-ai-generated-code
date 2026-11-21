"""Course reserve endpoints (section 29.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from lms.api.common import patch_fields, require_own_or_staff
from lms.auth.deps import AnyUser, CurrentPrincipal, Principal, StaffOnly
from lms.catalog.schemas import CopyOut, copy_out
from lms.catalog.service import get_copy_or_404
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.courses import courses as course_service
from lms.courses import loans as loan_service
from lms.courses import process as process_service
from lms.courses import reading_list
from lms.courses import reserve as reserve_service
from lms.courses.models import Course
from lms.courses.schemas import (
    CourseClosedOut,
    CourseCreateIn,
    CourseOut,
    CoursePatchIn,
    CourseStatus,
    EnrollIn,
    EnrollmentOut,
    EnrollmentStatus,
    EnrollResultOut,
    ItemCreateIn,
    ItemOut,
    ItemPatchIn,
    MemberCourseOut,
    OrderIn,
    PlaceCopyIn,
    PlacedCopyOut,
    ProcessOut,
    ReserveLoanCreateIn,
    ReserveLoanOut,
    ReserveLoanStatus,
    ReserveReturnIn,
)
from lms.members.service import get_member_or_404

router = APIRouter(tags=["courses"])

CourseId = Annotated[int, Path(ge=1)]
EnrollmentId = Annotated[int, Path(ge=1)]
ItemId = Annotated[int, Path(ge=1)]
CopyId = Annotated[int, Path(ge=1)]
LoanId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]


def _is_staff(principal: Principal) -> bool:
    return principal.user.role != "member"


def _course_not_found(course_id: int) -> NotFound:
    return NotFound(f"Course {course_id} does not exist", details={"resource": "course", "id": course_id})


def _readable_course(db, principal: Principal, course_id: int) -> Course:  # noqa: ANN001
    """LIB-CRS-05: a member sees only the courses in which they are enrolled or the instructor."""
    course = course_service.get_course_or_404(db, course_id)
    if not _is_staff(principal) and course_service.member_role(db, course, principal.user.member_id) is None:
        raise _course_not_found(course_id)
    return course


def _require_instructor_or_staff(principal: Principal, course: Course) -> None:
    """LIB-CRS-18: another member calling an instructor endpoint receives ``403 FORBIDDEN``."""
    if not _is_staff(principal) and principal.user.member_id != course.instructor_id:
        raise Forbidden("Only the instructor of the course can do this")


def _own_or_staff(principal: Principal, member_id: int) -> None:
    require_own_or_staff(principal, member_id, "Only your own course data can be accessed")


# --- courses ---------------------------------------------------------------------------------


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> CourseOut:
    course = course_service.create_course(db, local_now(request.app.state.settings.clock), staff.user, body.model_dump())
    return course_service.to_out(db, course)


@router.get("/courses", response_model=Page[CourseOut])
def list_courses(
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    term: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    instructor_id: Annotated[int | None, Query()] = None,
    status: Annotated[CourseStatus | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> Page[CourseOut]:
    stmt = course_service.course_list_stmt(
        member_id=principal.user.member_id,
        only_member=not _is_staff(principal),
        term=term,
        branch_id=branch_id,
        instructor_id=instructor_id,
        status=status,
    )
    if q is None or not q.strip():
        return paginate(db, stmt, page, lambda c: course_service.to_out(db, c))
    matches = [c for c in db.scalars(stmt) if course_service.matches_query(c, q)]
    chunk = paginate_sequence(matches, page)
    return Page[CourseOut](
        items=[course_service.to_out(db, c) for c in chunk.items],
        page=chunk.page,
        page_size=chunk.page_size,
        total=chunk.total,
    )


@router.get("/courses/{course_id}", response_model=CourseOut)
def get_course(course_id: CourseId, db: SessionDep, principal: AnyUser) -> CourseOut:
    return course_service.to_out(db, _readable_course(db, principal, course_id))


@router.patch("/courses/{course_id}", response_model=CourseOut)
def update_course(
    course_id: CourseId, body: CoursePatchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> CourseOut:
    fields = patch_fields(body)
    course = course_service.get_course_or_404(db, course_id)
    course_service.update_course(db, local_now(request.app.state.settings.clock), staff.user, course, fields)
    return course_service.to_out(db, course)


@router.post("/courses/{course_id}/activate", response_model=CourseOut)
def activate_course(course_id: CourseId, request: Request, db: SessionDep, staff: StaffOnly) -> CourseOut:
    course = course_service.get_course_or_404(db, course_id)
    course_service.activate_course(db, local_now(request.app.state.settings.clock), staff.user, course)
    return course_service.to_out(db, course)


@router.post("/courses/{course_id}/close", response_model=CourseClosedOut)
def close_course(course_id: CourseId, request: Request, db: SessionDep, staff: StaffOnly) -> CourseClosedOut:
    settings = request.app.state.settings
    course = course_service.get_course_or_404(db, course_id)
    released = course_service.close_course(db, local_now(settings.clock), staff.user, settings.holidays, course)
    return CourseClosedOut(**course_service.to_out(db, course).model_dump(), released_copies=released)


# --- enrollments -----------------------------------------------------------------------------


@router.post("/courses/{course_id}/enrollments", response_model=EnrollResultOut)
def enroll(course_id: CourseId, body: EnrollIn, request: Request, db: SessionDep, staff: StaffOnly) -> EnrollResultOut:
    course = course_service.get_course_or_404(db, course_id)
    return course_service.enroll(db, local_now(request.app.state.settings.clock), staff.user, course, body.member_ids)


@router.get("/courses/{course_id}/enrollments", response_model=Page[EnrollmentOut])
def list_enrollments(
    course_id: CourseId,
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    status: Annotated[EnrollmentStatus | None, Query()] = None,
) -> Page[EnrollmentOut]:
    course = course_service.get_course_or_404(db, course_id)
    _require_instructor_or_staff(principal, course)
    stmt = course_service.enrollment_list_stmt(course.id, status)
    return paginate(db, stmt, page, lambda e: course_service.to_enrollment_out(db, e))


@router.post("/enrollments/{enrollment_id}/drop", response_model=EnrollmentOut)
def drop_enrollment(enrollment_id: EnrollmentId, request: Request, db: SessionDep, staff: StaffOnly) -> EnrollmentOut:
    enrollment = course_service.get_enrollment_or_404(db, enrollment_id)
    course_service.drop(db, local_now(request.app.state.settings.clock), staff.user, enrollment)
    return course_service.to_enrollment_out(db, enrollment)


@router.get("/members/{member_id}/courses", response_model=Page[MemberCourseOut])
def list_member_courses(
    member_id: MemberId, db: SessionDep, principal: CurrentPrincipal, page: PageDep
) -> Page[MemberCourseOut]:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = course_service.course_list_stmt(member_id=member.id, only_member=True)

    def convert(course: Course) -> MemberCourseOut:
        role = course_service.member_role(db, course, member.id)
        assert role is not None
        return MemberCourseOut(**course_service.to_out(db, course).model_dump(), role=role)

    return paginate(db, stmt, page, convert)


# --- reading lists ---------------------------------------------------------------------------


@router.post("/courses/{course_id}/reading-list", response_model=ItemOut, status_code=201)
def add_item(course_id: CourseId, body: ItemCreateIn, request: Request, db: SessionDep, principal: AnyUser) -> ItemOut:
    course = course_service.get_course_or_404(db, course_id)
    _require_instructor_or_staff(principal, course)
    item = reading_list.add_item(
        db, local_now(request.app.state.settings.clock), principal.user, course, body.model_dump()
    )
    return reading_list.item_out(db, item)


@router.get("/courses/{course_id}/reading-list", response_model=Page[ItemOut])
def read_reading_list(
    course_id: CourseId,
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    include_removed: Annotated[bool, Query()] = False,
) -> Page[ItemOut]:
    course = _readable_course(db, principal, course_id)
    items = reading_list.list_items(db, course.id, include_removed=include_removed and _is_staff(principal))
    chunk = paginate_sequence(items, page)
    return Page[ItemOut](
        items=[reading_list.item_out(db, i) for i in chunk.items],
        page=chunk.page,
        page_size=chunk.page_size,
        total=chunk.total,
    )


@router.put("/courses/{course_id}/reading-list/order", response_model=Page[ItemOut])
def order_reading_list(course_id: CourseId, body: OrderIn, db: SessionDep, principal: AnyUser) -> Page[ItemOut]:
    course = course_service.get_course_or_404(db, course_id)
    _require_instructor_or_staff(principal, course)
    items = reading_list.order_items(db, course, body.item_ids)
    return Page[ItemOut](
        items=[reading_list.item_out(db, i) for i in items], page=1, page_size=100, total=len(items)
    )


def _item_for_instructor(db, principal: Principal, item_id: int):  # noqa: ANN001, ANN202
    item = reserve_service.get_item_or_404(db, item_id)
    course = db.get(Course, item.course_id)
    assert course is not None
    _require_instructor_or_staff(principal, course)
    return item


@router.patch("/reading-list-items/{item_id}", response_model=ItemOut)
def update_item(item_id: ItemId, body: ItemPatchIn, request: Request, db: SessionDep, principal: AnyUser) -> ItemOut:
    item = _item_for_instructor(db, principal, item_id)
    fields = patch_fields(body)
    reading_list.update_item(db, local_now(request.app.state.settings.clock), principal.user, item, fields)
    return reading_list.item_out(db, item)


@router.post("/reading-list-items/{item_id}/remove", response_model=ItemOut)
def remove_item(item_id: ItemId, request: Request, db: SessionDep, principal: AnyUser) -> ItemOut:
    settings = request.app.state.settings
    item = _item_for_instructor(db, principal, item_id)
    reading_list.remove_item(db, local_now(settings.clock), principal.user, settings.holidays, item)
    return reading_list.item_out(db, item)


# --- copies on reserve -----------------------------------------------------------------------


@router.post("/reading-list-items/{item_id}/copies", response_model=PlacedCopyOut, status_code=201)
def place_copy(item_id: ItemId, body: PlaceCopyIn, request: Request, db: SessionDep, staff: StaffOnly) -> PlacedCopyOut:
    item = reserve_service.get_item_or_404(db, item_id)
    return reserve_service.place_by_hand(db, local_now(request.app.state.settings.clock), staff.user, item, body.copy_id)


@router.post("/copies/{copy_id}/unreserve", response_model=CopyOut)
def unreserve_copy(copy_id: CopyId, request: Request, db: SessionDep, staff: StaffOnly) -> CopyOut:
    settings = request.app.state.settings
    copy = get_copy_or_404(db, copy_id)
    return copy_out(reserve_service.unreserve(db, local_now(settings.clock), staff.user, settings.holidays, copy))


# --- reserve loans ---------------------------------------------------------------------------


@router.post("/reserve-loans", response_model=ReserveLoanOut, status_code=201)
def lend(body: ReserveLoanCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> ReserveLoanOut:
    body.check()
    settings = request.app.state.settings
    now = local_now(settings.clock)
    loan = loan_service.lend(
        db, now, staff.user, settings.holidays, member_id=body.member_id, copy_id=body.copy_id, barcode=body.barcode
    )
    return loan_service.to_out(db, loan, now)


@router.get("/reserve-loans", response_model=Page[ReserveLoanOut])
def list_loans(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    course_id: Annotated[int | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
    status: Annotated[ReserveLoanStatus | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> Page[ReserveLoanOut]:
    now = local_now(request.app.state.settings.clock)
    stmt = loan_service.loan_list_stmt(now, course_id=course_id, member_id=member_id, status=status, overdue=overdue)
    return paginate(db, stmt, page, lambda ln: loan_service.to_out(db, ln, now))


@router.get("/members/{member_id}/reserve-loans", response_model=Page[ReserveLoanOut])
def list_member_loans(
    member_id: MemberId,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    course_id: Annotated[int | None, Query()] = None,
    status: Annotated[ReserveLoanStatus | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> Page[ReserveLoanOut]:
    now = local_now(request.app.state.settings.clock)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = loan_service.loan_list_stmt(now, course_id=course_id, member_id=member.id, status=status, overdue=overdue)
    return paginate(db, stmt, page, lambda ln: loan_service.to_out(db, ln, now))


@router.post("/reserve-loans/{loan_id}/renew", response_model=ReserveLoanOut)
def renew_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> ReserveLoanOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    loan = loan_service.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    loan_service.renew(db, now, principal.user, settings.holidays, loan)
    return loan_service.to_out(db, loan, now)


@router.post("/reserve-loans/{loan_id}/return", response_model=ReserveLoanOut)
def return_loan(
    loan_id: LoanId, body: ReserveReturnIn, request: Request, db: SessionDep, staff: StaffOnly
) -> ReserveLoanOut:
    now = local_now(request.app.state.settings.clock)
    loan = loan_service.get_loan_or_404(db, loan_id)
    loan_service.return_loan(db, now, staff.user, loan, body.branch_id)
    return loan_service.to_out(db, loan, now)


@router.post("/reserve-loans/{loan_id}/report-lost", response_model=ReserveLoanOut)
def report_lost(loan_id: LoanId, request: Request, db: SessionDep, staff: StaffOnly) -> ReserveLoanOut:
    now = local_now(request.app.state.settings.clock)
    loan = loan_service.get_loan_or_404(db, loan_id)
    loan_service.report_lost(db, now, staff.user, loan)
    return loan_service.to_out(db, loan, now)


# --- processing ------------------------------------------------------------------------------


@router.post("/course-reserves/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    settings = request.app.state.settings
    return process_service.process(db, local_now(settings.clock), staff.user, settings.holidays)
