"""Module 2: Identity and access (section 6)."""
import datetime
import hashlib
import hmac
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core.errors import ApiError
from ..core.text import normalize
from .models import User, UserSession

ROLES = ("member", "librarian", "admin")

_N, _R, _P, _DKLEN = 16384, 8, 1, 64
_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False  # e.g. imported members without a usable password
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    return hmac.compare_digest(h, expected)


def email_key(email: str) -> str:
    return normalize(email)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_bootstrap_admin(session: Session, settings) -> None:  # noqa: ANN001
    """LIB-AUTH-01."""
    exists = session.scalars(select(User.id).where(User.role == "admin").limit(1)).first()
    if exists is not None:
        return
    email = settings.bootstrap_admin_email.strip()
    if session.scalars(select(User.id).where(User.email_key == email_key(email))).first() is not None:
        return
    session.add(
        User(
            email=email.lower(),
            email_key=email_key(email),
            full_name="Administrator",
            role="admin",
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_active=True,
            created_at=settings.clock.now(),
        )
    )
    session.commit()


def revoke_sessions(session: Session, user_id: int, now: datetime.datetime, except_id: int | None = None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    session.execute(stmt.values(revoked_at=now))


def authenticate(session: Session, header: str | None, now: datetime.datetime) -> tuple[User, UserSession]:
    """LIB-AUTH-12."""
    unauth = ApiError(401, "UNAUTHENTICATED", "Authentication required")
    if not header:
        raise unauth
    parts = header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise unauth
    sess = session.scalars(select(UserSession).where(UserSession.token_hash == token_digest(parts[1]))).first()
    if sess is None or sess.revoked_at is not None:
        raise unauth
    if now >= sess.expires_at:
        raise ApiError(401, "TOKEN_EXPIRED", "Token has expired")
    user = session.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise unauth
    return user, sess
