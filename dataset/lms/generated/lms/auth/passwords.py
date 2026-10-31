"""Password policy (LIB-AUTH-02) and storage (LIB-AUTH-03): ``scrypt$<salt hex>$<hash hex>``."""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 16

PASSWORD_MIN = 8
PASSWORD_MAX = 128


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check. A malformed or unusable stored hash never matches."""
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_scrypt(password, salt), expected)


def password_problem(password: str) -> str | None:
    """Return the reason a password breaks the policy, or ``None`` if it is acceptable."""
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters long"
    if not any(c.isalpha() for c in password):
        return "password must contain at least one letter"
    if not any(c.isdigit() for c in password):
        return "password must contain at least one digit"
    return None
