"""Audit entries (section 19.1). Only the writing side is here; the log endpoints belong to module 13."""

import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.database import Base, LocalDateTime


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime.datetime] = mapped_column(LocalDateTime, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
