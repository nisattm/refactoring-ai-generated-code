"""Password policy and storage (LIB-AUTH-02, LIB-AUTH-03) and session tokens (LIB-AUTH-07)."""

import hashlib
import hmac
import re
import secrets

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

_LETTER_RE = re.compile(r"[^\W\d_]")
_DIGIT_RE = re.compile(r"[0-9]")

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


def check_password_policy(password: str) -> str:
    """LIB-AUTH-02: 8-128 characters, at least one letter and one digit. Raises ValueError."""
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValueError("must be 8 to 128 characters long")
    if not _LETTER_RE.search(password) or not _DIGIT_RE.search(password):
        raise ValueError("must contain at least one letter and one digit")
    return password


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )


def hash_password(password: str) -> str:
    """LIB-AUTH-03: 'scrypt$<salt hex>$<hash hex>' with a random 16-byte salt."""
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True when the password matches the stored hash. A malformed stored value never matches."""
    parts = stored.split("$")
    if len(parts) != 3 or parts[0] != "scrypt":
        return False
    try:
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
    except ValueError:
        return False
    return hmac.compare_digest(_scrypt(password, salt), expected)


def new_session_token() -> str:
    """LIB-AUTH-07: 32 random bytes, base64url without padding (43 characters)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """SHA-256 hex digest. Only this digest is stored (LIB-AUTH-07)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
