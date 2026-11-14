"""Constants of module 20 (sections 28.2 and 28.6 to 28.7)."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

REGISTRATION_CLOSES_BEFORE = datetime.timedelta(hours=1)
PROMOTION_CLOSES_BEFORE = datetime.timedelta(hours=1)
TIMELY_CANCELLATION = datetime.timedelta(hours=24)
CHECK_IN_EARLY = datetime.timedelta(minutes=30)
REMINDER_WINDOW = datetime.timedelta(hours=24)
MIN_DURATION_MINUTES = 60
MAX_DURATION_MINUTES = 240
MIN_LEAD_TO_PUBLISH = datetime.timedelta(hours=24)

DEBT_BLOCK = Decimal("50.00")
MAX_FEE = Decimal("200.00")
BAN_NO_SHOWS = 3
BAN_WINDOW_DAYS = 90
BAN_DAYS = 30

WAIVE_TIMELY = "Registration cancelled in time"
WAIVE_EVENT_CANCELLED = "Event cancelled"


@dataclasses.dataclass(frozen=True)
class EventRules:
    """One row of the table in 28.2."""

    limit: int
    audiences: tuple[str, ...]


EVENT_RULES: dict[str, EventRules] = {
    "student": EventRules(5, ("all", "students")),
    "academic": EventRules(10, ("all", "academics")),
    "staff": EventRules(10, ("all",)),
    "guest": EventRules(2, ("all",)),
}
