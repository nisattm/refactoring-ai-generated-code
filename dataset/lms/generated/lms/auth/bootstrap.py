"""Bootstrap administrator (LIB-AUTH-01)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.auth.passwords import hash_password
from lms.auth.service import build_user
from lms.core.clock import local_now
from lms.core.settings import Settings


def ensure_bootstrap_admin(session: Session, settings: Settings) -> None:
    """Create the bootstrap admin if no user with role ``admin`` exists. Idempotent."""
    exists = session.scalar(sa.select(User.id).where(User.role == "admin").limit(1))
    if exists is not None:
        return
    session.add(
        build_user(
            email=settings.bootstrap_admin_email.strip().lower(),
            full_name="Administrator",
            role="admin",
            password_hash=hash_password(settings.bootstrap_admin_password),
            now=local_now(settings.clock),
        )
    )
