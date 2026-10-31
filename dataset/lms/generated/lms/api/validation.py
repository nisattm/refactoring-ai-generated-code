"""Manual request-body validation helpers (LIB-COM-15 to LIB-COM-17, LIB-AUTH-02)."""
from typing import Any

from ..core.errors import ValidationFailed


def check_keys(body: dict, allowed: set[str], required: set[str], fields: list) -> None:
    for k in body:
        if k not in allowed:
            fields.append({"field": str(k), "problem": "unknown field"})
    for k in sorted(required):
        if k not in body:
            fields.append({"field": k, "problem": "is required"})


def text(body: dict, name: str, fields: list, lo: int = 1, hi: int = 200) -> str | None:
    v = body.get(name)
    if not isinstance(v, str):
        fields.append({"field": name, "problem": "must be a string"})
        return None
    v = v.strip()
    if not lo <= len(v) <= hi:
        fields.append({"field": name, "problem": f"length must be between {lo} and {hi}"})
        return None
    return v


def email(body: dict, name: str, fields: list) -> str | None:
    v = body.get(name)
    if not isinstance(v, str):
        fields.append({"field": name, "problem": "must be a string"})
        return None
    v = v.strip()
    local, sep, domain = v.partition("@")
    if len(v) > 254 or not sep or "@" in domain or not local or "." not in domain:
        fields.append({"field": name, "problem": "must be a valid e-mail address"})
        return None
    return v


def password(body: dict, name: str, fields: list) -> str | None:
    v = body.get(name)
    if not isinstance(v, str):
        fields.append({"field": name, "problem": "must be a string"})
        return None
    if not 8 <= len(v) <= 128 or not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        fields.append(
            {"field": name, "problem": "must be 8-128 characters with at least one letter and one digit"}
        )
        return None
    return v


def string_raw(body: dict, name: str, fields: list) -> str | None:
    v = body.get(name)
    if not isinstance(v, str):
        fields.append({"field": name, "problem": "must be a string"})
        return None
    return v


def fail(fields: list) -> None:
    if fields:
        raise ValidationFailed(fields)


def present(body: dict, name: str) -> Any:
    return body.get(name)
