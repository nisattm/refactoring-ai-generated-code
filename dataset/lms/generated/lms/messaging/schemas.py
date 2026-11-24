"""Request and response schemas of module 27 (section 35)."""

from __future__ import annotations

import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, StrictBool, StrictInt, field_validator

from lms.core.clock import LOCAL_TZ
from lms.core.money import format_amount
from lms.core.schemas import RequestModel, reject_null
from lms.core.timeutil import format_datetime, parse_datetime
from lms.messaging.models import MEMBERSHIP_TYPES, Announcement, Message, Thread

Priority = Literal["normal", "important"]
AnnouncementStatus = Literal["draft", "published", "withdrawn"]
Category = Literal["general", "loan", "fee", "room", "other"]
ThreadStatus = Literal["open", "answered", "closed"]

# The examples of LIB-MSG-13 name the types in the plural; both forms are accepted and kept as sent.
_ALIASES = {"students": "student", "academics": "academic", "guests": "guest"}


def audience_key(value: str) -> str:
    """The membership type (7.1) an audience value stands for."""
    return _ALIASES.get(value, value)


def _parse_dt(value: Any) -> datetime.datetime:
    if isinstance(value, datetime.datetime) and value.tzinfo is not None:
        return value.astimezone(LOCAL_TZ)
    return parse_datetime(value).astimezone(LOCAL_TZ)


DateTimeValue = Annotated[datetime.datetime, BeforeValidator(_parse_dt)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
Body = Annotated[str, Field(min_length=1, max_length=5000)]
Subject = Annotated[str, Field(min_length=1, max_length=200)]
MessageBody = Annotated[str, Field(min_length=1, max_length=2000)]


def _check_audience(value: list[str]) -> list[str]:
    if not value:
        raise ValueError("audience must not be empty")
    keys = []
    for item in value:
        key = audience_key(item)
        if key not in MEMBERSHIP_TYPES:
            raise ValueError(f"unknown membership type {item!r}; allowed: {', '.join(MEMBERSHIP_TYPES)}")
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError("audience must not contain duplicates")
    return value


# --- requests --------------------------------------------------------------------------------


class AnnouncementCreateIn(RequestModel):
    title: Title
    body: Body
    branch_id: StrictInt | None = None
    audience: list[str] = list(MEMBERSHIP_TYPES)
    priority: Priority = "normal"
    pinned: StrictBool = False
    publish_at: DateTimeValue | None = None
    expires_at: DateTimeValue | None = None

    @field_validator("audience")
    @classmethod
    def _audience(cls, value: list[str]) -> list[str]:
        return _check_audience(value)


class AnnouncementPatchIn(RequestModel):
    """Any subset of the fields of LIB-MSG-01."""

    title: Title = None  # type: ignore[assignment]
    body: Body = None  # type: ignore[assignment]
    branch_id: StrictInt | None = None
    audience: list[str] = None  # type: ignore[assignment]
    priority: Priority = None  # type: ignore[assignment]
    pinned: StrictBool = None  # type: ignore[assignment]
    publish_at: DateTimeValue = None  # type: ignore[assignment]
    expires_at: DateTimeValue | None = None

    @field_validator("audience")
    @classmethod
    def _audience(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _check_audience(value)

    @field_validator("title", "body", "audience", "priority", "pinned", "publish_at", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        return reject_null(value)


class ThreadCreateIn(RequestModel):
    branch_id: StrictInt
    subject: Subject
    category: Category = "general"
    loan_id: StrictInt | None = None
    fee_id: StrictInt | None = None
    body: MessageBody


class MessageIn(RequestModel):
    body: MessageBody
    internal: StrictBool = False


class AssignIn(RequestModel):
    user_id: StrictInt | None


class RateIn(RequestModel):
    rating: Annotated[StrictInt, Field(ge=1, le=5)]


# --- responses -------------------------------------------------------------------------------


def _dt(value: datetime.datetime | None) -> str | None:
    return None if value is None else format_datetime(value)


class AnnouncementOut(BaseModel):
    id: int
    title: str
    body: str
    branch_id: int | None
    audience: list[str]
    priority: str
    pinned: bool
    publish_at: str
    expires_at: str | None
    status: str
    published_at: str | None
    withdrawn_at: str | None
    live: bool
    scheduled: bool
    # Only for members (LIB-MSG-09): left out of the response when not set.
    read: bool | None = None


def announcement_out(a: Announcement, now: datetime.datetime) -> AnnouncementOut:
    return AnnouncementOut(
        id=a.id,
        title=a.title,
        body=a.body,
        branch_id=a.branch_id,
        audience=list(a.audience),
        priority=a.priority,
        pinned=a.pinned,
        publish_at=format_datetime(a.publish_at),
        expires_at=_dt(a.expires_at),
        status=a.status,
        published_at=_dt(a.published_at),
        withdrawn_at=_dt(a.withdrawn_at),
        live=a.is_live(now),
        scheduled=a.status == "published" and a.publish_at > now,
    )


class FeedPage(BaseModel):
    items: list[AnnouncementOut]
    page: int
    page_size: int
    total: int
    unread: int


class ReadOut(BaseModel):
    announcement_id: int
    read_at: str


class StatsOut(BaseModel):
    audience_size: int
    reads: int
    read_rate: str


class MessageOut(BaseModel):
    id: int
    author: str
    user_id: int | None
    body: str
    internal: bool
    created_at: str
    read_at: str | None


def message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        author=m.author,
        user_id=m.user_id,
        body=m.body,
        internal=m.internal,
        created_at=format_datetime(m.created_at),
        read_at=_dt(m.read_at),
    )


class ThreadMemberOut(BaseModel):
    id: int
    member_no: str
    full_name: str
    membership_type: str


class ThreadLoanOut(BaseModel):
    id: int
    status: str
    due_date: datetime.date


class ThreadFeeOut(BaseModel):
    id: int
    kind: str
    amount: str
    status: str


class ThreadOut(BaseModel):
    id: int
    member_id: int
    branch_id: int
    subject: str
    category: str
    loan_id: int | None
    fee_id: int | None
    status: str
    assigned_to: int | None
    due_at: str | None
    close_reason: str | None
    rating: int | None
    created_at: str
    closed_at: str | None
    first_reply_at: str | None
    last_message_at: str | None
    unread: int
    is_overdue: bool
    overdue_by_hours: int | None
    # Only for staff (LIB-MSG-21) and in a single thread: left out of the response when not set.
    member: ThreadMemberOut | None = None
    loan: ThreadLoanOut | None = None
    fee: ThreadFeeOut | None = None
    messages: list[MessageOut] | None = None


def thread_out(
    t: Thread, *, last_message_at: datetime.datetime | None, unread: int, now: datetime.datetime
) -> ThreadOut:
    overdue = t.status == "open" and t.due_at is not None and now > t.due_at
    hours = int((now - t.due_at).total_seconds() // 3600) if overdue and t.due_at is not None else None
    return ThreadOut(
        id=t.id,
        member_id=t.member_id,
        branch_id=t.branch_id,
        subject=t.subject,
        category=t.category,
        loan_id=t.loan_id,
        fee_id=t.fee_id,
        status=t.status,
        assigned_to=t.assigned_to,
        due_at=_dt(t.due_at),
        close_reason=t.close_reason,
        rating=t.rating,
        created_at=format_datetime(t.created_at),
        closed_at=_dt(t.closed_at),
        first_reply_at=_dt(t.first_reply_at),
        last_message_at=_dt(last_message_at),
        unread=unread,
        is_overdue=overdue,
        overdue_by_hours=hours,
    )


class ProcessOut(BaseModel):
    announcements_released: int
    threads_closed: int


class MessagesSummaryOut(BaseModel):
    unread_announcements: int
    open_threads: int
    unread_replies: int


class ByCategoryOut(BaseModel):
    general: int
    loan: int
    fee: int
    room: int
    other: int


class AnnouncementsReportOut(BaseModel):
    published: int
    important: int
    reads: int


class MessagingReportOut(BaseModel):
    threads: int
    by_category: ByCategoryOut
    answered: int
    average_first_reply_hours: str | None
    overdue_now: int
    closed: int
    average_rating: str | None
    announcements: AnnouncementsReportOut
