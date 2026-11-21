"""Lookup of an addressed resource by id (LIB-COM-28 step 4)."""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy.orm import Session

from lms.core.errors import NotFound

M = TypeVar("M")


def get_or_404(db: Session, model: type[M], entity_id: int, label: str, resource: str) -> M:
    """The ``model`` row with this id, or ``404 NOT_FOUND`` naming it ``label`` in the message and ``resource`` in the details."""
    entity = db.get(model, entity_id)
    if entity is None:
        raise NotFound(f"{label} {entity_id} does not exist", details={"resource": resource, "id": entity_id})
    return entity
