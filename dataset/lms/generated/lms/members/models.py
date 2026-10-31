"""Member model (section 7.2)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class Member(Base):
    __tablename__ = "members"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(sa.String(200))
    email: Mapped[str] = mapped_column(sa.String(254))
    phone: Mapped[str | None] = mapped_column(sa.String(40), default=None)
    membership_type: Mapped[str] = mapped_column(sa.String(20))
    university_id: Mapped[str | None] = mapped_column(sa.String(20), default=None)
    # Normalized university_id (LIB-COM-30): the uniqueness key; NULL for guests.
    university_id_key: Mapped[str | None] = mapped_column(sa.String(20), unique=True, default=None)
    home_branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    status: Mapped[str] = mapped_column(sa.String(10), default="active")
    membership_start: Mapped[datetime.date] = mapped_column(sa.Date)
    valid_until: Mapped[datetime.date] = mapped_column(sa.Date)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)

    @property
    def member_no(self) -> str:
        """``"M"`` followed by the id padded to 6 digits."""
        return f"M{self.id:06d}"

    def is_valid_on(self, day: datetime.date) -> bool:
        """LIB-MEM-04."""
        return self.status == "active" and day <= self.valid_until
