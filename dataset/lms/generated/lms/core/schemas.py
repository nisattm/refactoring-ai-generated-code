"""Base class for request bodies (LIB-COM-15, LIB-COM-23)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """Rejects unknown fields (422) and trims text (LIB-COM-15)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
