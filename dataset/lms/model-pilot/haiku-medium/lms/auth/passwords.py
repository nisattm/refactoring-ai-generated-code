"""Password policy and scrypt storage (LIB-AUTH-02, LIB-AUTH-03)."""

import hashlib
import hmac
import secrets

_N, _R, _P, _DKLEN = 16384, 8, 1, 64


def check_password_policy(value: str) -> str:
    """8-128 characters with at least one letter and one digit (LIB-AUTH-02). Passwords are not trimmed."""
    if not 8 <= len(value) <= 128:
        raise ValueError("must be 8 to 128 characters long")
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise ValueError("must contain at least one letter and one digit")
    return value


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    return hmac.compare_digest(_derive(password, salt), expected)


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
