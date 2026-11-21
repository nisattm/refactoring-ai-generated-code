"""Text rules (LIB-COM-15, LIB-COM-17, LIB-COM-30 / LIB-SRCH-01)."""

from __future__ import annotations

_TURKISH_I = str.maketrans({"İ": "i", "I": "i", "ı": "i"})


def normalize(text: str) -> str:
    """Case-insensitive comparison key: ``İ``, ``I``, ``ı`` become ``i``, then ``casefold()``."""
    return text.translate(_TURKISH_I).casefold()


def normalize_or_none(text: str | None) -> str | None:
    return normalize(text) if text is not None else None


def search_needle(q: str | None) -> str:
    """The normalized, trimmed ``q`` filter of a list endpoint; empty if there is none (LIB-COM-30)."""
    return normalize(q.strip()) if q is not None else ""


def is_valid_email(email: str) -> bool:
    """LIB-COM-17: exactly one ``@``, something before it, a domain with a dot after it."""
    if email.count("@") != 1:
        return False
    local, domain = email.split("@")
    return bool(local) and "." in domain


def check_email(value: str) -> str:
    """Validator of an e-mail field: returns it in lower case; raises ``ValueError`` if it is invalid."""
    value = value.lower()
    if len(value) > 254:
        raise ValueError("e-mail must be at most 254 characters")
    if not is_valid_email(value):
        raise ValueError("invalid e-mail address")
    return value
