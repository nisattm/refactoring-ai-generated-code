"""Users and sessions (section 6.1)."""

import datetime

import sqlalchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base, TZDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored in lower case (LIB-COM-17).
    email: Mapped[str] = mapped_column(sqlalchemy.String(254))
    # Comparison key of the e-mail (LIB-COM-30); unique, never returned by the API.
    email_key: Mapped[str] = mapped_column(sqlalchemy.String(254), unique=True)
    full_name: Mapped[str] = mapped_column(sqlalchemy.String(200))
    role: Mapped[str] = mapped_column(sqlalchemy.String(16))
    password_hash: Mapped[str] = mapped_column(sqlalchemy.String(256))
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, nullable=True)
    # Links a member user to its member record (module 3). The members table does not exist yet.
    member_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, nullable=True)


class AuthSession(Base):
    """A login session. Named AuthSession to keep it apart from SQLAlchemy's Session."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(sqlalchemy.String(64), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    expires_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(TZDateTime, nullable=True)
