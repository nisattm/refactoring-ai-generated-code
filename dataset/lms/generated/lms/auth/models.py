"""User model (section 6.1). Sessions are added with the login step."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(254))
    # Normalized e-mail (LIB-COM-30): the uniqueness key.
    email_key: Mapped[str] = mapped_column(sa.String(254), unique=True)
    full_name: Mapped[str] = mapped_column(sa.String(200))
    role: Mapped[str] = mapped_column(sa.String(20))
    password_hash: Mapped[str] = mapped_column(sa.String(300))
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
    # Link to the member record (module 3); set only for role ``member``.
    member_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, default=None)
