"""Constants and pure rules of module 23 (sections 31.5 and 31.6)."""

from __future__ import annotations

import datetime
from decimal import Decimal

APPROVAL_LIMIT = Decimal("500.00")  # LIB-PRE-13: above this only an admin approves
URGENT_MARGIN = Decimal("0.10")  # LIB-PRE-12: share of the budget an urgent job may exceed
OVERRUN_FACTOR = Decimal("1.2")  # LIB-PRE-22
REQUEST_EXPIRY_DAYS = 60  # LIB-PRE-25
WORN_LOANS = 30  # LIB-PRE-26

TURNAROUND_DAYS = {"repair": 7, "rebinding": 21, "conservation": 42}
SUPPLIER_EXTRA_DAYS = 7


def turnaround_days(kind: str, provider: str, priority: str) -> int:
    """LIB-PRE-17."""
    days = TURNAROUND_DAYS[kind] + (SUPPLIER_EXTRA_DAYS if provider == "supplier" else 0)
    if priority == "urgent":
        days = (days + 1) // 2
    return days


def due_back_for(sent_on: datetime.date, kind: str, provider: str, priority: str) -> datetime.date:
    return sent_on + datetime.timedelta(days=turnaround_days(kind, provider, priority))
