"""Constants and pure rules of module 22 (sections 30.4 to 30.7)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Literal

OFFER_LIMIT = 3
EXPECTED_DAYS = 14
KEEP_DAYS = 180
TOO_OLD_YEARS = 30
DUPLICATE_COPIES = 3
MAX_ITEMS = 30
MAX_TOTAL_QUANTITY = 100

Level = Literal["none", "bronze", "silver", "gold"]
LEVEL_RANK = {"none": 0, "bronze": 1, "silver": 2, "gold": 3}

BRONZE = Decimal("500.00")
SILVER = Decimal("2000.00")
GOLD = Decimal("10000.00")


def level_of(value: Decimal) -> Level:
    """LIB-DON-31."""
    if value >= GOLD:
        return "gold"
    if value >= SILVER:
        return "silver"
    if value >= BRONZE:
        return "bronze"
    return "none"


def keep_until(acquired_on: datetime.date) -> datetime.date:
    """LIB-DON-25."""
    return acquired_on + datetime.timedelta(days=KEEP_DAYS)
