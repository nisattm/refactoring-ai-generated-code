"""Members (section 7.2)."""

import datetime

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.database import Base, LocalDateTime


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_no: Mapped[str] = mapped_column(String(16), unique=True)  # "M" + id padded to 6 digits
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254))  # also the e-mail of the member's user account
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    membership_type: Mapped[str] = mapped_column(String(16))  # student | academic | staff | guest
    university_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # normalize_text(university_id); enforces case-insensitive uniqueness (LIB-COM-30, LIB-MEM-05).
    university_id_key: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    home_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | passive
    membership_start: Mapped[datetime.date] = mapped_column(Date)
    valid_until: Mapped[datetime.date] = mapped_column(Date)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(LocalDateTime)
