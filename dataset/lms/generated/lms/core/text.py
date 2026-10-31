"""Text rules (LIB-COM-15, LIB-COM-17, LIB-COM-30 / LIB-SRCH-01)."""

from __future__ import annotations

_TURKISH_I = str.maketrans({"İ": "i", "I": "i", "ı": "i"})


def normalize(text: str) -> str:
    """Case-insensitive comparison key: ``İ``, ``I``, ``ı`` become ``i``, then ``casefold()``."""
    return text.translate(_TURKISH_I).casefold()


def is_valid_email(email: str) -> bool:
    """LIB-COM-17: exactly one ``@``, something before it, a domain with a dot after it."""
    if email.count("@") != 1:
        return False
    local, domain = email.split("@")
    return bool(local) and "." in domain
