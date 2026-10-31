"""Application settings (LIB-IF-04 to LIB-IF-06)."""

from __future__ import annotations

import dataclasses
import datetime

from lms.core.clock import Clock, SystemClock
from lms.core.holidays import DEFAULT_HOLIDAYS


@dataclasses.dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./lms.db"
    clock: Clock = SystemClock()
    holidays: frozenset[datetime.date] = DEFAULT_HOLIDAYS
    bootstrap_admin_email: str = "admin@library.local"
    bootstrap_admin_password: str = "ChangeMe123"
    token_ttl_hours: int = 12

    def __post_init__(self) -> None:
        ttl = self.token_ttl_hours
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not 1 <= ttl <= 168:
            raise ValueError("token_ttl_hours must be an integer between 1 and 168")
