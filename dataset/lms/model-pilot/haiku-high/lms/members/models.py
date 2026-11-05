"""Members (section 7.2)."""

import datetime

import sqlalchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base, TZDateTime


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    # "M" + id padded to six digits (LIB-MEM-01). Set once the id is known, see the member service.
    member_no: Mapped[str] = mapped_column(sqlalchemy.String(16), unique=True)
    full_name: Mapped[str] = mapped_column(sqlalchemy.String(200))
    # Stored in lower case (LIB-COM-17); the same address as the member's user account.
    email: Mapped[str] = mapped_column(sqlalchemy.String(254))
    phone: Mapped[str | None] = mapped_column(sqlalchemy.String(64), nullable=True)
    membership_type: Mapped[str] = mapped_column(sqlalchemy.String(16))
    university_id: Mapped[str | None] = mapped_column(sqlalchemy.String(20), nullable=True)
    # Comparison key of university_id (LIB-COM-30); unique among members.
    university_id_key: Mapped[str | None] = mapped_column(
        sqlalchemy.String(20), unique=True, nullable=True
    )
    home_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(sqlalchemy.String(16), default="active")
    membership_start: Mapped[datetime.date] = mapped_column(sqlalchemy.Date)
    valid_until: Mapped[datetime.date] = mapped_column(sqlalchemy.Date)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
