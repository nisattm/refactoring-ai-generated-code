"""Users and sessions (section 6.1)."""

import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lms.core.database import Base, LocalDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    # normalize_text(email); enforces case-insensitive uniqueness (LIB-COM-30, LIB-AUTH-05).
    email_key: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16))  # member | librarian | admin
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime.datetime | None] = mapped_column(LocalDateTime, nullable=True)
    member_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # module 3 links the member
    created_at: Mapped[datetime.datetime] = mapped_column(LocalDateTime)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(LocalDateTime, nullable=True)


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(LocalDateTime)
    expires_at: Mapped[datetime.datetime] = mapped_column(LocalDateTime)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(LocalDateTime, nullable=True)

    user: Mapped[User] = relationship()
