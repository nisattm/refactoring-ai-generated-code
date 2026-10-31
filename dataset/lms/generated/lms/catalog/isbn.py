"""ISBN normalization (LIB-CAT-02)."""

from __future__ import annotations


def _isbn13_check_digit(first12: str) -> str:
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def normalize_isbn(raw: str) -> str:
    """Return the ISBN-13 form of ``raw``; raises ``ValueError`` if it is not a valid ISBN-10 or ISBN-13."""
    text = raw.replace("-", "").replace(" ", "")
    if len(text) == 10 and text[:9].isascii() and text[:9].isdigit() and (
        (text[9].isascii() and text[9].isdigit()) or text[9] in "Xx"
    ):
        values = [int(c) for c in text[:9]] + [10 if text[9] in "Xx" else int(text[9])]
        if sum(v * w for v, w in zip(values, range(10, 0, -1))) % 11 != 0:
            raise ValueError("invalid ISBN-10 check character")
        return "978" + text[:9] + _isbn13_check_digit("978" + text[:9])
    if len(text) == 13 and text.isascii() and text.isdigit() and text[:3] in ("978", "979"):
        if _isbn13_check_digit(text[:12]) != text[12]:
            raise ValueError("invalid ISBN-13 check digit")
        return text
    raise ValueError("isbn must be a valid ISBN-10 or ISBN-13")
