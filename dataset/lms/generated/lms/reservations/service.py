"""Reservation rules that loans depend on (module 6, section 10).

The reservation data and endpoints are added with module 6. Until then no reservation can exist,
so these functions describe the situation without reservations; module 6 replaces their bodies.
"""

from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from lms.catalog.models import Copy
from lms.members.models import Member


def count_active(db: Session, member_id: int) -> int:
    """Active reservations (``waiting``, ``in_transit``, ``ready``) of a member."""
    return 0


def book_has_active_reservation(db: Session, book_id: int) -> bool:
    """LIB-LOAN-07: any member has an active reservation for the book."""
    return False


def hold_belongs_to_member(db: Session, now: datetime.datetime, copy: Copy, member: Member) -> bool:
    """LIB-LOAN-05 step 6 and LIB-RES-11: the ``on_hold`` copy is held by a ``ready`` reservation of
    the member that has not passed ``hold_until`` (a reservation past it is expired first)."""
    return False


def fulfil_for_loan(db: Session, now: datetime.datetime, member: Member, copy: Copy) -> None:
    """LIB-RES-10: the member's active reservation for the book of ``copy`` becomes ``fulfilled``."""
