"""Shared "load by id or fail with 404" helpers (LIB-COM-28, LIB-COM-29)."""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy.orm import Session

from lms.core.errors import NotFound, reference_not_found

T = TypeVar("T")


def get_or_404(db: Session, model: type[T], entity_id: int, *, label: str, resource: str) -> T:
    """Return the ``model`` row with ``entity_id`` or raise ``404 NOT_FOUND`` for an addressed resource.

    The message is ``"<label> <id> does not exist"``; ``details`` is ``{"resource": resource, "id": id}``.
    """
    entity = db.get(model, entity_id)
    if entity is None:
        raise NotFound(f"{label} {entity_id} does not exist", details={"resource": resource, "id": entity_id})
    return entity


def get_reference_or_404(db: Session, model: type[T], field: str, entity_id: int) -> T:
    """Return the ``model`` row referenced by request field ``field`` or raise ``404 NOT_FOUND`` (LIB-COM-29)."""
    entity = db.get(model, entity_id)
    if entity is None:
        raise reference_not_found(field, entity_id)
    return entity
