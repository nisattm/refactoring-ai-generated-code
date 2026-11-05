"""Branches (section 17.1)."""

import datetime

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base, TZDateTime


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored in upper case; unique (LIB-BR-01).
    code: Mapped[str] = mapped_column(sqlalchemy.String(10), unique=True)
    name: Mapped[str] = mapped_column(sqlalchemy.String(200))
    address: Mapped[str] = mapped_column(sqlalchemy.String(300))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
