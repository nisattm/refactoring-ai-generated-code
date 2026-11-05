"""Application settings (LIB-IF-04 to LIB-IF-06) and the default holiday list (LIB-COM-06)."""

import dataclasses
import datetime

from lms.core.clock import Clock, SystemClock

D = datetime.date

# Default official holidays for 2026-2027 (section 3.2). Half-day eves are working days.
HOLIDAY_NAMES: dict[datetime.date, str] = {
    D(2026, 1, 1): "New Year's Day",
    D(2026, 3, 20): "Ramazan Bayramı, day 1",
    D(2026, 3, 21): "Ramazan Bayramı, day 2",
    D(2026, 3, 22): "Ramazan Bayramı, day 3",
    D(2026, 4, 23): "National Sovereignty and Children's Day",
    D(2026, 5, 1): "Labour and Solidarity Day",
    D(2026, 5, 19): "Commemoration of Atatürk, Youth and Sports Day",
    D(2026, 5, 27): "Kurban Bayramı, day 1",
    D(2026, 5, 28): "Kurban Bayramı, day 2",
    D(2026, 5, 29): "Kurban Bayramı, day 3",
    D(2026, 5, 30): "Kurban Bayramı, day 4",
    D(2026, 7, 15): "Democracy and National Unity Day",
    D(2026, 8, 30): "Victory Day",
    D(2026, 10, 29): "Republic Day",
    D(2027, 1, 1): "New Year's Day",
    D(2027, 3, 9): "Ramazan Bayramı, day 1",
    D(2027, 3, 10): "Ramazan Bayramı, day 2",
    D(2027, 3, 11): "Ramazan Bayramı, day 3",
    D(2027, 4, 23): "National Sovereignty and Children's Day",
    D(2027, 5, 1): "Labour and Solidarity Day",
    D(2027, 5, 16): "Kurban Bayramı, day 1",
    D(2027, 5, 17): "Kurban Bayramı, day 2",
    D(2027, 5, 18): "Kurban Bayramı, day 3",
    D(2027, 5, 19): "Kurban Bayramı, day 4; Commemoration of Atatürk, Youth and Sports Day",
    D(2027, 7, 15): "Democracy and National Unity Day",
    D(2027, 8, 30): "Victory Day",
    D(2027, 10, 29): "Republic Day",
}

DEFAULT_HOLIDAYS: frozenset[datetime.date] = frozenset(HOLIDAY_NAMES)

# Name used for a holiday in Settings.holidays that is not in the default table.
UNNAMED_HOLIDAY = "Official holiday"


@dataclasses.dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./lms.db"
    clock: Clock = SystemClock()
    holidays: frozenset[datetime.date] = DEFAULT_HOLIDAYS
    bootstrap_admin_email: str = "admin@library.local"
    bootstrap_admin_password: str = "ChangeMe123"
    token_ttl_hours: int = 12

    def __post_init__(self) -> None:
        if not 1 <= self.token_ttl_hours <= 168:
            raise ValueError("token_ttl_hours must be between 1 and 168")
