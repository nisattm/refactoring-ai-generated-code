"""Courses and enrollments (LIB-CRS-01 to LIB-CRS-11)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Copy
from lms.core.db import get_or_404
from lms.core.errors import Conflict, ValidationFailed
from lms.core.text import normalize
from lms.courses import placement
from lms.courses.models import Course, Enrollment, ReadingListItem, ReserveLoan
from lms.courses.reserve import take_all_off_reserve
from lms.courses.schemas import (
    CourseOut,
    EnrollmentOut,
    EnrollResultOut,
    SkippedOut,
    check_span,
    course_fields,
    enrollment_out,
)
from lms.courses.usage import drop_enrollment
from lms.members.models import Member
from lms.notifications.service import notify_course


def _error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_course_or_404(db: Session, course_id: int) -> Course:
    return get_or_404(db, Course, course_id, "Course", "course")


# --- representation and visibility ------------------------------------------------------------


def count_enrolled(db: Session, course_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(Enrollment).where(
        Enrollment.course_id == course_id, Enrollment.status == "enrolled"
    )
    return db.scalar(stmt) or 0


def count_items(db: Session, course_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(ReadingListItem).where(
        ReadingListItem.course_id == course_id, ReadingListItem.status != "removed"
    )
    return db.scalar(stmt) or 0


def to_out(db: Session, course: Course) -> CourseOut:
    return CourseOut(
        **course_fields(
            course,
            enrolled=count_enrolled(db, course.id),
            items=count_items(db, course.id),
            copies_on_reserve=placement.count_reserved_for_course(db, course.id),
        )
    )


def is_enrolled(db: Session, course_id: int, member_id: int) -> bool:
    stmt = sa.select(Enrollment.id).where(
        Enrollment.course_id == course_id, Enrollment.member_id == member_id, Enrollment.status == "enrolled"
    )
    return db.scalar(stmt.limit(1)) is not None


def member_role(db: Session, course: Course, member_id: int | None) -> str | None:
    """``"instructor"``, ``"student"`` or ``None`` when the member may not see the course (LIB-CRS-05)."""
    if member_id is None:
        return None
    if course.instructor_id == member_id:
        return "instructor"
    return "student" if is_enrolled(db, course.id, member_id) else None


def _visible_to_member(member_id: int | None) -> sa.ColumnElement[bool]:
    enrolled = sa.select(Enrollment.course_id).where(Enrollment.member_id == member_id, Enrollment.status == "enrolled")
    return sa.or_(Course.instructor_id == member_id, Course.id.in_(enrolled))


def course_list_stmt(
    *,
    member_id: int | None = None,
    only_member: bool = False,
    term: str | None = None,
    branch_id: int | None = None,
    instructor_id: int | None = None,
    status: str | None = None,
) -> sa.Select[tuple[Course]]:
    """LIB-CRS-05 (``q`` is applied by the caller). With ``only_member`` the courses are limited to those the
    member is enrolled in or teaches."""
    stmt = sa.select(Course).order_by(Course.term, Course.code, Course.id)
    if only_member:
        stmt = stmt.where(_visible_to_member(member_id))
    if term is not None:
        stmt = stmt.where(Course.term == term)
    if branch_id is not None:
        stmt = stmt.where(Course.branch_id == branch_id)
    if instructor_id is not None:
        stmt = stmt.where(Course.instructor_id == instructor_id)
    if status is not None:
        stmt = stmt.where(Course.status == status)
    return stmt


def matches_query(course: Course, q: str) -> bool:
    needle = normalize(q.strip())
    return not needle or needle in normalize(course.code) or needle in normalize(course.title)


# --- LIB-CRS-02 ---------------------------------------------------------------------------------


def check_course(
    db: Session, branch: Branch, instructor: Member, code: str, term: str, *, exclude_id: int | None = None
) -> None:
    """The three checks of LIB-CRS-02, in order."""
    if not branch.is_active:
        raise _error("BRANCH_INACTIVE", f"Branch {branch.code} is inactive", field="branch_id", id=branch.id)
    if instructor.status == "passive" or instructor.membership_type != "academic":
        raise _error(
            "INSTRUCTOR_NOT_ACADEMIC", "The instructor must be an active academic member", field="instructor_id", id=instructor.id
        )
    stmt = sa.select(Course.id).where(Course.code == code, Course.term == term)
    if exclude_id is not None:
        stmt = stmt.where(Course.id != exclude_id)
    if db.scalar(stmt.limit(1)) is not None:
        raise Conflict("A course with this code and term already exists", details={"field": "code"})


def _course_details(course: Course) -> dict[str, Any]:
    return {
        "code": course.code,
        "title": course.title,
        "term": course.term,
        "instructor_id": course.instructor_id,
        "branch_id": course.branch_id,
        "starts_on": course.starts_on.isoformat(),
        "ends_on": course.ends_on.isoformat(),
        "enrollment_limit": course.enrollment_limit,
    }


# --- LIB-CRS-01 ---------------------------------------------------------------------------------


def create_course(db: Session, now: datetime.datetime, actor: User, fields: dict[str, Any]) -> Course:
    problems: list[dict[str, str]] = []
    if fields["ends_on"] < now.date():
        problems.append({"field": "ends_on", "problem": "ends_on must not be before today"})
    instructor = db.get(Member, fields["instructor_id"])
    if instructor is None:
        problems.append({"field": "instructor_id", "problem": f"member {fields['instructor_id']} does not exist"})
    branch = db.get(Branch, fields["branch_id"])
    if branch is None:
        problems.append({"field": "branch_id", "problem": f"branch {fields['branch_id']} does not exist"})
    if problems:
        raise ValidationFailed(problems)
    assert instructor is not None and branch is not None
    check_course(db, branch, instructor, fields["code"], fields["term"])
    course = Course(**fields, status="draft", created_at=now)
    db.add(course)
    db.flush()
    record(
        db,
        at=now,
        event="course_created",
        actor_user_id=actor.id,
        entity_type="course",
        entity_id=course.id,
        details=_course_details(course),
    )
    return course


# --- LIB-CRS-03 ---------------------------------------------------------------------------------


def update_course(db: Session, now: datetime.datetime, actor: User, course: Course, fields: dict[str, Any]) -> Course:
    if "instructor_id" in fields and db.get(Member, fields["instructor_id"]) is None:
        raise ValidationFailed.single("instructor_id", f"member {fields['instructor_id']} does not exist")
    starts_on = fields.get("starts_on", course.starts_on)
    ends_on = fields.get("ends_on", course.ends_on)
    if "starts_on" in fields or "ends_on" in fields:
        problem = check_span(starts_on, ends_on)
        if problem is not None:
            raise ValidationFailed.single("ends_on", problem)
    if course.status == "closed":
        raise _error("INVALID_COURSE_STATUS", "The course is closed", status=course.status)
    branch = db.get(Branch, course.branch_id)
    instructor = db.get(Member, fields.get("instructor_id", course.instructor_id))
    assert branch is not None and instructor is not None
    check_course(db, branch, instructor, course.code, course.term, exclude_id=course.id)
    limit = fields.get("enrollment_limit")
    if limit is not None:
        enrolled = count_enrolled(db, course.id)
        if limit < enrolled:
            raise _error(
                "ENROLLMENT_LIMIT_BELOW_ENROLLED", "The limit is below the number of enrolled members", enrolled=enrolled
            )
    old = _course_details(course)
    for name, value in fields.items():
        setattr(course, name, value)
    diff = changes(old, _course_details(course))
    record(
        db,
        at=now,
        event="course_updated",
        actor_user_id=actor.id,
        entity_type="course",
        entity_id=course.id,
        details=diff,
    )
    return course


# --- LIB-CRS-04 ---------------------------------------------------------------------------------


def activate_course(db: Session, now: datetime.datetime, actor: User, course: Course) -> Course:
    if course.status != "draft":
        raise _error("INVALID_COURSE_STATUS", "The course is not a draft", status=course.status)
    if course.ends_on < now.date():
        raise _error("COURSE_ENDED", "The course has already ended", ends_on=course.ends_on.isoformat())
    if count_items(db, course.id) == 0:
        raise _error("COURSE_READING_LIST_EMPTY", "The course has no reading list items")
    course.status = "active"
    course.activated_at = now
    record(
        db,
        at=now,
        event="course_activated",
        actor_user_id=actor.id,
        entity_type="course",
        entity_id=course.id,
        details={"code": course.code},
    )
    for member_id in placement.enrolled_member_ids(db, course.id):
        notify_course(
            db,
            now,
            member_id,
            "course_activated",
            f"The course {course.code} ({course.title}) is now active.",
            course_id=course.id,
        )
    return course


# --- LIB-CRS-06 ---------------------------------------------------------------------------------


def open_loan_ids(db: Session, course_id: int) -> list[int]:
    return placement.open_loan_ids(db, ReserveLoan.course_id == course_id)


def close_course(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], course: Course
) -> int:
    """LIB-CRS-06. Returns the number of released copies."""
    if course.status not in ("draft", "active"):
        raise _error("INVALID_COURSE_STATUS", "The course is closed", status=course.status)
    loan_ids = open_loan_ids(db, course.id)
    if loan_ids:
        raise _error("COURSE_HAS_OPEN_LOANS", "The course has open reserve loans", loan_ids=loan_ids)
    return finish_close(db, now, actor, holidays, course)


def finish_close(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], course: Course
) -> int:
    released = take_all_off_reserve(db, now, actor.id, holidays, Copy.reserve_course_id == course.id)
    course.status = "closed"
    course.closed_at = now
    record(
        db,
        at=now,
        event="course_closed",
        actor_user_id=actor.id,
        entity_type="course",
        entity_id=course.id,
        details={"code": course.code, "released_copies": released},
    )
    return released


# --- enrollment (LIB-CRS-08 to LIB-CRS-11) ----------------------------------------------------------


def _skip_reason(db: Session, course: Course, member: Member | None, today: datetime.date) -> str | None:
    if member is None:
        return "NOT_FOUND"
    if member.membership_type != "student":
        return "NOT_A_STUDENT"
    if member.status == "passive":
        return "MEMBER_PASSIVE"
    if member.valid_until < today:
        return "MEMBERSHIP_EXPIRED"
    if is_enrolled(db, course.id, member.id):
        return "ALREADY_ENROLLED"
    if count_enrolled(db, course.id) >= course.enrollment_limit:
        return "ENROLLMENT_FULL"
    return None


def enroll(
    db: Session, now: datetime.datetime, actor: User, course: Course, member_ids: list[int]
) -> EnrollResultOut:
    """LIB-CRS-08."""
    if course.status == "closed":
        raise _error("INVALID_COURSE_STATUS", "The course is closed", status=course.status)
    enrolled: list[int] = []
    skipped: list[SkippedOut] = []
    for member_id in member_ids:
        member = db.get(Member, member_id)
        reason = _skip_reason(db, course, member, now.date())
        if reason is not None:
            skipped.append(SkippedOut(member_id=member_id, error_code=reason))
            continue
        enrollment = Enrollment(course_id=course.id, member_id=member_id, status="enrolled", enrolled_at=now)
        db.add(enrollment)
        db.flush()
        enrolled.append(member_id)
        record(
            db,
            at=now,
            event="course_enrollment_created",
            actor_user_id=actor.id,
            entity_type="course_enrollment",
            entity_id=enrollment.id,
            details={"course_id": course.id, "member_id": member_id},
        )
        notify_course(
            db,
            now,
            member_id,
            "course_enrolled",
            f"You were enrolled in the course {course.code} ({course.title}).",
            course_id=course.id,
        )
    return EnrollResultOut(enrolled=enrolled, skipped=skipped)


def get_enrollment_or_404(db: Session, enrollment_id: int) -> Enrollment:
    return get_or_404(db, Enrollment, enrollment_id, "Enrollment", "enrollment")


def drop(db: Session, now: datetime.datetime, actor: User, enrollment: Enrollment) -> Enrollment:
    """LIB-CRS-10."""
    if enrollment.status != "enrolled":
        raise _error("ENROLLMENT_NOT_ACTIVE", "The enrollment is not active", status=enrollment.status)
    loan_ids = placement.open_loan_ids(
        db, ReserveLoan.course_id == enrollment.course_id, ReserveLoan.member_id == enrollment.member_id
    )
    if loan_ids:
        raise _error("MEMBER_HAS_RESERVE_LOANS", "The member has open reserve loans of the course", loan_ids=loan_ids)
    drop_enrollment(db, now, actor.id, enrollment, "staff_request")
    return enrollment


def to_enrollment_out(db: Session, enrollment: Enrollment) -> EnrollmentOut:
    member = db.get(Member, enrollment.member_id)
    assert member is not None
    return enrollment_out(enrollment, member.member_no, member.full_name)


def enrollment_list_stmt(course_id: int, status: str | None) -> sa.Select[tuple[Enrollment]]:
    stmt = (
        sa.select(Enrollment)
        .where(Enrollment.course_id == course_id)
        .order_by(Enrollment.enrolled_at, Enrollment.id)
    )
    if status is not None:
        stmt = stmt.where(Enrollment.status == status)
    return stmt
