"""Text rules: trimming, names, e-mail addresses and case-insensitive comparison (LIB-COM-15 to LIB-COM-17, LIB-COM-30, LIB-SRCH-01)."""


def normalize_text(value: str) -> str:
    """Comparison form of a text (LIB-SRCH-01): İ, I and ı become i, then casefold."""
    value = value.replace("İ", "i").replace("I", "i").replace("ı", "i")
    return value.casefold()


def clean_name(value: str) -> str:
    """Trim a person or organization name and check its length (LIB-COM-15, LIB-COM-16)."""
    value = value.strip()
    if not 1 <= len(value) <= 200:
        raise ValueError("must be 1 to 200 characters after trimming")
    return value


def clean_email(value: str) -> str:
    """Trim and lower-case an e-mail address; check its form (LIB-COM-17)."""
    value = value.strip().lower()
    local, at, domain = value.partition("@")
    if not local or not at or "@" in domain or "." not in domain or len(value) > 254:
        raise ValueError("must be an e-mail address with one @ and a dotted domain, at most 254 characters")
    return value
