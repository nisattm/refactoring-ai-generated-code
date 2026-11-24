"""Constants and counting rules of module 29 (sections 37.1, 37.2, 37.5 and 37.7)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from lms.core.limits import MAX_REPORT_DAYS  # noqa: F401  (re-exported)

FREE_PAGES = {"student": 100, "academic": 300, "staff": 300, "guest": 0}
PRICE_BW = Decimal("0.50")
PRICE_COLOR = Decimal("2.00")
PACK_PAGES = 50
PACK_PRICE = Decimal("20.00")
PACK_LIMIT = 4
QUEUE_LIMIT = 3
DAILY_PAGE_LIMIT = 200
MAX_PAPER = 5000
LOW_PAPER = 100
FAIL_WINDOW = datetime.timedelta(hours=24)
QUEUE_EXPIRY = datetime.timedelta(hours=24)
DEBT_BLOCK = Decimal("50.00")
FAILED_WAIVE_REASON = "Failed print"


def sheets_of(pages: int, copies: int, duplex: bool) -> int:
    """LIB-PRT-09: ``pages × copies``; with duplex ``ceil(pages / 2) × copies``."""
    return ((pages + 1) // 2 if duplex else pages) * copies


def free_pages_of(membership_type: str) -> int:
    return FREE_PAGES[membership_type]
