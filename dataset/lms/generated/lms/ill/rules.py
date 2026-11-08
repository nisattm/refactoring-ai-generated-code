"""Constants and date rules of module 18 (sections 26.3 and 26.6)."""

from __future__ import annotations

import datetime
from collections.abc import Container

from lms.core.calendar import is_working_day

# 26.3: open incoming requests per membership type (0: not allowed).
OPEN_LIMITS: dict[str, int] = {"student": 2, "academic": 5, "staff": 2, "guest": 0}

COLLECT_DAYS = 7  # LIB-ILL-10
MIN_PERIOD_DAYS = 7  # LIB-ILL-11
OUTGOING_DAYS = 28  # LIB-ILL-25
MAX_TRIED_PARTNERS = 3  # LIB-ILL-07
LOCAL_BUFFER_WORKING_DAYS = 3  # LIB-ILL-12


def member_due_on(partner_due_on: datetime.date, holidays: Container[datetime.date]) -> datetime.date:
    """LIB-ILL-12: the 3rd working day before ``partner_due_on``, counting back from the day before it."""
    day = partner_due_on
    remaining = LOCAL_BUFFER_WORKING_DAYS
    while remaining > 0:
        day -= datetime.timedelta(days=1)
        if is_working_day(day, holidays):
            remaining -= 1
    return day
