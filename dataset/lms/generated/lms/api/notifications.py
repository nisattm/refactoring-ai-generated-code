"""Notification endpoints (section 14.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from lms.auth.deps import CurrentPrincipal, Principal, StaffOnly, require_roles
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden
from lms.core.pagination import Page, PageDep, paginate
from lms.members.service import get_member_or_404
from lms.notifications import service
from lms.notifications.schemas import (
    NotificationOut,
    NotificationType,
    ReadAllOut,
    RemindersOut,
    UnreadCountOut,
    notification_out,
)

router = APIRouter(tags=["notifications"])

MemberId = Annotated[int, Path(ge=1)]
NotificationId = Annotated[int, Path(ge=1)]

MemberOnly = Annotated[Principal, Depends(require_roles("member"))]


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25: a member may only address their own notifications."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden("Only your own notifications can be accessed")


@router.get("/members/{member_id}/notifications", response_model=Page[NotificationOut])
def list_member_notifications(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    unread: Annotated[bool | None, Query()] = None,
    type: Annotated[NotificationType | None, Query()] = None,
) -> Page[NotificationOut]:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = service.notification_list_stmt(member_id=member.id, unread=unread, type_=type)
    return paginate(db, stmt, page, notification_out)


@router.get("/members/{member_id}/notifications/unread-count", response_model=UnreadCountOut)
def unread_count(member_id: MemberId, db: SessionDep, principal: CurrentPrincipal) -> UnreadCountOut:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    return UnreadCountOut(unread=service.unread_count(db, member.id))


@router.post("/members/{member_id}/notifications/read-all", response_model=ReadAllOut)
def read_all(member_id: MemberId, request: Request, db: SessionDep, principal: MemberOnly) -> ReadAllOut:
    now = local_now(request.app.state.settings.clock)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    return ReadAllOut(updated=service.mark_all_read(db, now, member.id))


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    member_id: Annotated[int | None, Query()] = None,
    unread: Annotated[bool | None, Query()] = None,
    type: Annotated[NotificationType | None, Query()] = None,
) -> Page[NotificationOut]:
    stmt = service.notification_list_stmt(member_id=member_id, unread=unread, type_=type)
    return paginate(db, stmt, page, notification_out)


@router.post("/notifications/run-reminders", response_model=RemindersOut)
def run_reminders(request: Request, db: SessionDep, staff: StaffOnly) -> RemindersOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    due, overdue = service.run_reminders(db, now, staff.user, settings.holidays)
    return RemindersOut(due_reminders=due, overdue_notices=overdue)


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def read_notification(
    notification_id: NotificationId, request: Request, db: SessionDep, principal: MemberOnly
) -> NotificationOut:
    now = local_now(request.app.state.settings.clock)
    notification = service.get_notification_or_404(db, notification_id)
    _own_or_staff(principal, notification.member_id)
    return notification_out(service.mark_read(now, notification))
