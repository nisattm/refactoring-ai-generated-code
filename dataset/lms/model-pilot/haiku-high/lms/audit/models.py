"""Audit entries (section 19.1). Entries are written here and never changed or deleted (LIB-AUD-04)."""

import datetime
import typing

import sqlalchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base, TZDateTime


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event: Mapped[str] = mapped_column(sqlalchemy.String(64))
    entity_type: Mapped[str] = mapped_column(sqlalchemy.String(64))
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, typing.Any]] = mapped_column(sqlalchemy.JSON)
