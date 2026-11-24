"""Constants of module 26 (sections 34.2 and 34.5 to 34.7)."""

from __future__ import annotations

from decimal import Decimal

POINTS_ON_TIME = 10
POINTS_LATE = 5
POINTS_MANUAL = 10
POINTS_EVENT = 15
POINTS_FEATURED = 5
POINTS_WEEKLY_BONUS = 10
BONUS_WEEKS = 3

MANUAL_ENTRY_LIMIT = 3
PROGRAM_LIMIT = 3
DEBT_BLOCK = Decimal("50.00")
REMINDER_DAYS = 3

MIN_DAYS = 13
MAX_DAYS = 120
MAX_FEATURED = 30
MAX_REWARD = Decimal("50.00")

REWARD_REASON = "Reading program reward"
