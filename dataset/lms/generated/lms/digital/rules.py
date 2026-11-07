"""Constants of module 17 (sections 25.1 and 25.2)."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

SESSION_LENGTH = datetime.timedelta(minutes=60)
HOLD_KEEP = datetime.timedelta(hours=48)
RENEW_WINDOW = datetime.timedelta(hours=72)
DUE_SOON_WINDOW = datetime.timedelta(hours=24)
DAILY_SESSIONS = 6
DEFAULT_LOAN_DAYS = 14
DEBT_BLOCK = Decimal("50.00")


@dataclasses.dataclass(frozen=True)
class DigitalRules:
    """One row of the table in 25.2."""

    loans: int
    holds: int
    sessions: int


DIGITAL_RULES: dict[str, DigitalRules] = {
    "student": DigitalRules(5, 5, 1),
    "academic": DigitalRules(10, 10, 2),
    "staff": DigitalRules(5, 5, 1),
    "guest": DigitalRules(0, 0, 0),
}
