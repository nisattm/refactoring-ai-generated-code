"""Response schemas of module 8 (section 14)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from lms.core.timeutil import format_datetime
from lms.notifications.models import Notification

NotificationType = Literal[
    "reservation_ready",
    "reservation_in_transit",
    "reservation_expired",
    "reservation_cancelled",
    "loan_created",
    "loan_renewed",
    "loan_returned",
    "loan_lost",
    "fee_created",
    "payment_received",
    "fee_waived",
    "membership_renewed",
    "member_deactivated",
    "due_reminder",
    "overdue_notice",
]


class NotificationOut(BaseModel):
    id: int
    member_id: int
    type: str
    message: str
    loan_id: int | None
    reservation_id: int | None
    fee_id: int | None
    created_at: str
    read_at: str | None


class UnreadCountOut(BaseModel):
    unread: int


class ReadAllOut(BaseModel):
    updated: int


class RemindersOut(BaseModel):
    due_reminders: int
    overdue_notices: int


def notification_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        member_id=n.member_id,
        type=n.type,
        message=n.message,
        loan_id=n.loan_id,
        reservation_id=n.reservation_id,
        fee_id=n.fee_id,
        created_at=format_datetime(n.created_at),
        read_at=format_datetime(n.read_at) if n.read_at is not None else None,
    )
