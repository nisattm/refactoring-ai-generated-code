"""Copy statuses and allowed transitions (section 8.2)."""

from __future__ import annotations

from typing import Literal

from lms.catalog.models import Copy
from lms.core.errors import Conflict

CopyStatus = Literal["available", "on_loan", "on_hold", "in_transfer", "damaged", "lost", "withdrawn"]

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "available": frozenset({"on_loan", "on_hold", "in_transfer", "withdrawn"}),
    # on_hold -> on_hold and in_transfer -> in_transfer: the release procedure and transfer arrival
    # may keep a copy held or start a new transfer.
    "on_hold": frozenset({"on_loan", "available", "in_transfer", "on_hold"}),
    "on_loan": frozenset({"available", "on_hold", "in_transfer", "damaged", "lost"}),
    "in_transfer": frozenset({"available", "on_hold", "in_transfer"}),
    "damaged": frozenset({"available", "on_hold", "in_transfer", "withdrawn"}),
    "lost": frozenset({"withdrawn"}),
    "withdrawn": frozenset(),
}

# Statuses that do not count towards a book's lendability or availability totals (LIB-CAT-12).
GONE_STATUSES = ("lost", "withdrawn")


def invalid_status(copy: Copy, action: str) -> Conflict:
    return Conflict(
        f"Copy {copy.id} has status {copy.status}: {action} is not allowed",
        code="INVALID_COPY_STATUS",
        details={"id": copy.id, "status": copy.status},
    )


def set_status(copy: Copy, new_status: str) -> None:
    """Move ``copy`` to ``new_status``; any transition not listed in 8.2 is ``409 INVALID_COPY_STATUS``."""
    if new_status not in ALLOWED_TRANSITIONS[copy.status]:
        raise invalid_status(copy, f"change to {new_status}")
    copy.status = new_status
