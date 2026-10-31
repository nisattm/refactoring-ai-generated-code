"""Audit entry model (section 19.1). The query endpoint is added with module 13."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.timeutil import TZDateTime


class AuditEntry(Base):
    __tablename__ = "audit_entries"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    actor_user_id: Mapped[int | None] = mapped_column(default=None)
    event: Mapped[str] = mapped_column(sa.String(60))
    entity_type: Mapped[str] = mapped_column(sa.String(60))
    entity_id: Mapped[int | None] = mapped_column(default=None)
    details: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)
