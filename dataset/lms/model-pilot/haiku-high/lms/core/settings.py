"""Application settings (section 4.2)."""

import dataclasses
import datetime

from lms.core.clock import Clock, SystemClock
from lms.core.workdays import DEFAULT_HOLIDAYS


@dataclasses.dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./lms.db"
    clock: Clock = SystemClock()
    holidays: frozenset[datetime.date] = DEFAULT_HOLIDAYS
    bootstrap_admin_email: str = "admin@library.local"
    bootstrap_admin_password: str = "ChangeMe123"
    token_ttl_hours: int = 12

    def __post_init__(self) -> None:
        # LIB-IF-06
        if not 1 <= self.token_ttl_hours <= 168:
            raise ValueError("token_ttl_hours must be between 1 and 168")
