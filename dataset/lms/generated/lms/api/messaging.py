"""Announcement and message thread endpoints (section 35.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from lms.api.common import is_member, own_member, request_now
from lms.auth.deps import AnyUser, Principal, StaffOnly, require_roles
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound, ValidationFailed
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.messaging import announcements, process, threads, usage
from lms.messaging.models import Thread
from lms.messaging.schemas import (
    AnnouncementCreateIn,
    AnnouncementOut,
    AnnouncementPatchIn,
    AnnouncementStatus,
    AssignIn,
    Category,
    FeedPage,
    MessageIn,
    MessageOut,
    ProcessOut,
    RateIn,
    ReadOut,
    StatsOut,
    ThreadCreateIn,
    ThreadOut,
    ThreadStatus,
    message_out,
)

router = APIRouter(tags=["messaging"])

AnnouncementId = Annotated[int, Path(ge=1)]
ThreadId = Annotated[int, Path(ge=1)]

MemberOnly = Annotated[Principal, Depends(require_roles("member"))]


def _announcement_not_found(announcement_id: int) -> NotFound:
    return NotFound(
        f"Announcement {announcement_id} does not exist",
        details={"resource": "announcement", "id": announcement_id},
    )


# --- announcements ------------------------------------------------------------------------------


@router.post("/announcements", response_model=AnnouncementOut, status_code=201, response_model_exclude_unset=True)
def create_announcement(
    body: AnnouncementCreateIn, request: Request, db: SessionDep, staff: StaffOnly
) -> AnnouncementOut:
    now = request_now(request)
    announcement = announcements.create_announcement(db, now, staff.user, body.model_dump())
    return announcements.announcement_out(announcement, now)


@router.get("/announcements", response_model=FeedPage | Page[AnnouncementOut], response_model_exclude_unset=True)
def list_announcements(
    request: Request,
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    status: Annotated[AnnouncementStatus | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    live: Annotated[bool | None, Query()] = None,
    scheduled: Annotated[bool | None, Query()] = None,
) -> FeedPage | Page[AnnouncementOut]:
    now = request_now(request)
    if is_member(principal):
        member = own_member(db, principal)
        feed = usage.live_for_member(db, now, member)
        seen = usage.read_ids(db, member.id)
        chunk = paginate_sequence(feed, page)
        return FeedPage(
            items=[announcements.member_out(db, now, a, a.id in seen) for a in chunk.items],
            page=chunk.page,
            page_size=chunk.page_size,
            total=chunk.total,
            unread=sum(1 for a in feed if a.id not in seen),
        )
    stmt = announcements.list_stmt(now, status=status, branch_id=branch_id, live=live, scheduled=scheduled)
    return paginate(db, stmt, page, lambda a: announcements.announcement_out(a, now))


@router.get("/announcements/{announcement_id}", response_model=AnnouncementOut, response_model_exclude_unset=True)
def get_announcement(
    announcement_id: AnnouncementId, request: Request, db: SessionDep, principal: AnyUser
) -> AnnouncementOut:
    now = request_now(request)
    announcement = announcements.get_announcement_or_404(db, announcement_id)
    if not is_member(principal):
        return announcements.announcement_out(announcement, now)
    member = own_member(db, principal)
    if not announcements.member_visible(announcement, member, now):
        raise _announcement_not_found(announcement_id)
    announcements.mark_read(db, now, announcement, member)
    return announcements.member_out(db, now, announcement, True)


@router.patch("/announcements/{announcement_id}", response_model=AnnouncementOut, response_model_exclude_unset=True)
def update_announcement(
    announcement_id: AnnouncementId,
    body: AnnouncementPatchIn,
    request: Request,
    db: SessionDep,
    staff: StaffOnly,
) -> AnnouncementOut:
    now = request_now(request)
    announcement = announcements.get_announcement_or_404(db, announcement_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    announcements.update_announcement(db, now, staff.user, announcement, fields)
    return announcements.announcement_out(announcement, now)


@router.post(
    "/announcements/{announcement_id}/publish", response_model=AnnouncementOut, response_model_exclude_unset=True
)
def publish_announcement(
    announcement_id: AnnouncementId, request: Request, db: SessionDep, staff: StaffOnly
) -> AnnouncementOut:
    now = request_now(request)
    announcement = announcements.get_announcement_or_404(db, announcement_id)
    announcements.publish(db, now, staff.user, announcement)
    return announcements.announcement_out(announcement, now)


@router.post(
    "/announcements/{announcement_id}/withdraw", response_model=AnnouncementOut, response_model_exclude_unset=True
)
def withdraw_announcement(
    announcement_id: AnnouncementId, request: Request, db: SessionDep, staff: StaffOnly
) -> AnnouncementOut:
    now = request_now(request)
    announcement = announcements.get_announcement_or_404(db, announcement_id)
    announcements.withdraw(db, now, staff.user, announcement)
    return announcements.announcement_out(announcement, now)


@router.post("/announcements/{announcement_id}/read", response_model=ReadOut)
def read_announcement(
    announcement_id: AnnouncementId, request: Request, db: SessionDep, principal: MemberOnly
) -> ReadOut:
    now = request_now(request)
    announcement = announcements.get_announcement_or_404(db, announcement_id)
    member = own_member(db, principal)
    if not announcements.member_visible(announcement, member, now):
        raise _announcement_not_found(announcement_id)
    return announcements.read_out(announcement, announcements.mark_read(db, now, announcement, member))


@router.get("/announcements/{announcement_id}/stats", response_model=StatsOut)
def announcement_stats(announcement_id: AnnouncementId, db: SessionDep, _: StaffOnly) -> StatsOut:
    return announcements.stats(db, announcements.get_announcement_or_404(db, announcement_id))


# --- threads ------------------------------------------------------------------------------------


def _thread_for(db: SessionDep, thread_id: int, principal: Principal, *, hide: bool = False) -> Thread:
    """LIB-AUTH-25: a member's access to another member's thread is ``403``; reading it is ``404`` (LIB-MSG-17)."""
    thread = threads.get_thread_or_404(db, thread_id)
    if is_member(principal) and thread.member_id != principal.user.member_id:
        if hide:
            raise NotFound(f"Thread {thread_id} does not exist", details={"resource": "thread", "id": thread_id})
        raise Forbidden("Only your own threads can be accessed")
    return thread


@router.post("/threads", response_model=ThreadOut, status_code=201, response_model_exclude_unset=True)
def create_thread(body: ThreadCreateIn, request: Request, db: SessionDep, principal: MemberOnly) -> ThreadOut:
    now = request_now(request)
    member = own_member(db, principal)
    thread = threads.create_thread(
        db, now, request.app.state.settings.holidays, principal.user, member, body.model_dump()
    )
    return threads.to_out(db, now, thread, staff=False, with_messages=True)


@router.get("/threads", response_model=Page[ThreadOut], response_model_exclude_unset=True)
def list_threads(
    request: Request,
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    status: Annotated[ThreadStatus | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    assigned_to: Annotated[str | None, Query()] = None,
    category: Annotated[Category | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
) -> Page[ThreadOut]:
    now = request_now(request)
    if is_member(principal):
        own = own_member(db, principal)
        stmt = threads.list_stmt(now, staff=False, member_id=own.id, status=status)
        return paginate(db, stmt, page, lambda t: threads.to_out(db, now, t, staff=False))
    assignee: int | None = None
    if assigned_to is not None:
        if assigned_to == "me":
            assignee = principal.user.id
        else:
            try:
                assignee = int(assigned_to)
            except ValueError:
                raise ValidationFailed.single("assigned_to", 'assigned_to must be a user id or "me"') from None
    stmt = threads.list_stmt(
        now,
        staff=True,
        member_id=member_id,
        status=status,
        branch_id=branch_id,
        assigned_to=assignee,
        category=category,
        overdue=overdue,
    )
    return paginate(db, stmt, page, lambda t: threads.to_out(db, now, t, staff=True))


@router.get("/threads/{thread_id}", response_model=ThreadOut, response_model_exclude_unset=True)
def get_thread(thread_id: ThreadId, request: Request, db: SessionDep, principal: AnyUser) -> ThreadOut:
    now = request_now(request)
    thread = _thread_for(db, thread_id, principal, hide=True)
    staff = not is_member(principal)
    threads.mark_read(db, now, thread, staff)
    return threads.to_out(db, now, thread, staff=staff, with_messages=True)


@router.post("/threads/{thread_id}/messages", response_model=MessageOut, status_code=201)
def add_message(
    thread_id: ThreadId, body: MessageIn, request: Request, db: SessionDep, principal: AnyUser
) -> MessageOut:
    if is_member(principal) and body.internal:
        raise ValidationFailed.single("internal", "members cannot send internal notes")
    thread = _thread_for(db, thread_id, principal)
    message = threads.reply(
        db, request_now(request), request.app.state.settings.holidays, principal.user, thread, body.body, body.internal
    )
    return message_out(message)


@router.post("/threads/{thread_id}/assign", response_model=ThreadOut, response_model_exclude_unset=True)
def assign_thread(
    thread_id: ThreadId, body: AssignIn, request: Request, db: SessionDep, staff: StaffOnly
) -> ThreadOut:
    now = request_now(request)
    thread = threads.get_thread_or_404(db, thread_id)
    threads.assign(db, now, staff.user, thread, body.user_id)
    return threads.to_out(db, now, thread, staff=True)


@router.post("/threads/{thread_id}/close", response_model=ThreadOut, response_model_exclude_unset=True)
def close_thread(thread_id: ThreadId, request: Request, db: SessionDep, principal: AnyUser) -> ThreadOut:
    now = request_now(request)
    thread = _thread_for(db, thread_id, principal)
    threads.close(db, now, principal.user, thread)
    return threads.to_out(db, now, thread, staff=not is_member(principal))


@router.post("/threads/{thread_id}/reopen", response_model=ThreadOut, response_model_exclude_unset=True)
def reopen_thread(thread_id: ThreadId, request: Request, db: SessionDep, principal: MemberOnly) -> ThreadOut:
    now = request_now(request)
    thread = _thread_for(db, thread_id, principal)
    threads.reopen(db, now, request.app.state.settings.holidays, principal.user, thread)
    return threads.to_out(db, now, thread, staff=False)


@router.post("/threads/{thread_id}/rate", response_model=ThreadOut, response_model_exclude_unset=True)
def rate_thread(
    thread_id: ThreadId, body: RateIn, request: Request, db: SessionDep, principal: MemberOnly
) -> ThreadOut:
    now = request_now(request)
    thread = _thread_for(db, thread_id, principal)
    threads.rate(db, now, principal.user, thread, body.rating)
    return threads.to_out(db, now, thread, staff=False)


# --- processing ---------------------------------------------------------------------------------


@router.post("/messaging/process", response_model=ProcessOut)
def process_messaging(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    return process.process(db, request_now(request), staff.user)
