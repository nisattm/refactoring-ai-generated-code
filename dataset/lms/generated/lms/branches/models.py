"""Branch model (section 17.1). The transfer model is added with the transfer requirements."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(10), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    address: Mapped[str] = mapped_column(sa.String(300), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
