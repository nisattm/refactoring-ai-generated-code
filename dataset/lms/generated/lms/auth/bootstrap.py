"""Bootstrap administrator (LIB-AUTH-01)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.auth.passwords import hash_password
from lms.core.clock import local_now
from lms.core.settings import Settings
from lms.core.text import normalize


def ensure_bootstrap_admin(session: Session, settings: Settings) -> None:
    """Create the bootstrap admin if no user with role ``admin`` exists. Idempotent."""
    exists = session.scalar(sa.select(User.id).where(User.role == "admin").limit(1))
    if exists is not None:
        return
    email = settings.bootstrap_admin_email.strip().lower()
    session.add(
        User(
            email=email,
            email_key=normalize(email),
            full_name="Administrator",
            role="admin",
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_active=True,
            failed_login_count=0,
            created_at=local_now(settings.clock),
        )
    )
