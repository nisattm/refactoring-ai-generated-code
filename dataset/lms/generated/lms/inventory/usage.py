"""Light-weight lookups of module 24 used by other modules (branches, catalog).

Imports only models, so that the other modules can use it without import cycles."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.errors import Conflict
from lms.inventory.models import ExpectedCopy, InventoryCount


def open_count_id_of_copy(db: Session, copy_id: int) -> int | None:
    """LIB-INV-13: the open count that has the copy in its snapshot."""
    stmt = (
        sa.select(InventoryCount.id)
        .join(ExpectedCopy, ExpectedCopy.count_id == InventoryCount.id)
        .where(ExpectedCopy.copy_id == copy_id, InventoryCount.status == "open")
        .order_by(InventoryCount.id)
        .limit(1)
    )
    return db.scalar(stmt)


def require_not_in_count(db: Session, copy_id: int) -> None:
    """LIB-INV-13: relocation and withdrawal of a copy in a count are refused."""
    count_id = open_count_id_of_copy(db, copy_id)
    if count_id is not None:
        raise Conflict(
            f"Copy {copy_id} is in the open inventory count {count_id}",
            code="COPY_IN_COUNT",
            details={"count_id": count_id},
        )
