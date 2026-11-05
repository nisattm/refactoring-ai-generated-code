"""Text, e-mail and normalization rules (LIB-COM-15 to LIB-COM-17, LIB-COM-30, LIB-SRCH-01)."""

_TURKISH_I_FOLDS = str.maketrans({"İ": "i", "I": "i", "ı": "i"})


def normalize(text: str) -> str:
    """LIB-SRCH-01: İ, I and ı become i, then casefold. No other character is folded."""
    return text.translate(_TURKISH_I_FOLDS).casefold()


def clean_text(value: str, *, min_length: int = 0, max_length: int = 1000) -> str:
    """LIB-COM-15/16: trim white space, then check the length in characters.

    A required text field uses min_length=1; names use max_length=200.
    Raises ValueError with a problem description; callers turn it into a 422.
    """
    trimmed = value.strip()
    if len(trimmed) < min_length:
        if min_length == 1:
            raise ValueError("must not be empty")
        raise ValueError(f"must be at least {min_length} characters")
    if len(trimmed) > max_length:
        raise ValueError(f"must be at most {max_length} characters")
    return trimmed


def clean_email(value: str) -> str:
    """LIB-COM-17: exactly one '@', a local part, and a domain containing a dot. Stored in lower case."""
    trimmed = value.strip()
    local, sep, domain = trimmed.partition("@")
    if not sep or "@" in domain or not local or "." not in domain:
        raise ValueError("must be an e-mail address")
    return trimmed.lower()
