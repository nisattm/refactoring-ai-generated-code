"""Base class for request bodies (LIB-COM-15, LIB-COM-23)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """Rejects unknown fields (422) and trims text (LIB-COM-15)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def reject_null(value: object) -> object:
    """Body of the ``mode="before"`` validators of patch fields that may be left out but not be ``null``."""
    if value is None:
        raise ValueError("this field cannot be null")
    return value
