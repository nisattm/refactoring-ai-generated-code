"""Base class for request bodies (LIB-COM-15, LIB-COM-23)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """Rejects unknown fields (422) and trims text (LIB-COM-15)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    def provided_fields(self) -> dict[str, Any]:
        """The fields the client sent (for PATCH bodies, where every field is optional)."""
        return {name: getattr(self, name) for name in self.model_fields_set}
