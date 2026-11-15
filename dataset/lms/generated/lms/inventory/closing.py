"""Closing and applying a count, reading lines (LIB-INV-14 to LIB-INV-19)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.catalog.models import Book, Copy
from lms.catalog.release import release_copy
from lms.core.errors import Forbidden
from lms.inventory import rules
from lms.inventory.counts import _emit, expected_ids, invalid_count_status, summary_of
from lms.inventory.missing import mark_missing, restore_copy
from lms.inventory.models import InventoryCount, InventoryLine, InventoryScan
from lms.inventory.schemas import LineOut, SummaryOut


def close_count(db: Session, now: datetime.datetime, actor: User, count: InventoryCount) -> SummaryOut:
    """LIB-INV-14, LIB-INV-15."""
    if count.status != "open":
        raise invalid_count_status(count, "closing")
    scanned = set(
        db.scalars(
            sa.select(InventoryScan.copy_id).where(InventoryScan.count_id == count.id, InventoryScan.copy_id.is_not(None))
        )
    )
    expected = expected_ids(db, count.id)
    copies = {c.id: c for c in db.scalars(sa.select(Copy).where(Copy.id.in_(expected)))} if expected else {}
    for copy_id in expected:
        copy = copies[copy_id]
        if copy_id in scanned:
            outcome = "found"
        elif copy.status in rules.SHELF_STATUSES and copy.current_branch_id == count.branch_id:
            outcome = "missing"
        else:
            outcome = "moved"
        db.add(InventoryLine(count_id=count.id, copy_id=copy_id, outcome=outcome))
    count.status = "closed"
    count.closed_at = now
    db.flush()
    summary = summary_of(db, count.id)
    assert summary is not None
    _emit(db, now, actor, "inventory_count_closed", count, **summary.model_dump())
    return summary


def line_list_stmt(count_id: int, outcome: str | None) -> sa.Select[tuple[InventoryLine, str, str, str | None]]:
    """LIB-INV-17."""
    stmt = (
        sa.select(InventoryLine, Copy.barcode, Book.title, Copy.shelf_location)
        .join(Copy, Copy.id == InventoryLine.copy_id)
        .join(Book, Book.id == Copy.book_id)
        .where(InventoryLine.count_id == count_id)
        .order_by(InventoryLine.copy_id)
    )
    if outcome is not None:
        stmt = stmt.where(InventoryLine.outcome == outcome)
    return stmt


def line_out(row: tuple[InventoryLine, str, str, str | None]) -> LineOut:
    line, barcode, title, shelf = row
    return LineOut(copy_id=line.copy_id, outcome=line.outcome, barcode=barcode, book_title=title, shelf_location=shelf)


def missing_line_count(db: Session, count_id: int) -> int:
    return (
        db.scalar(
            sa.select(sa.func.count())
            .select_from(InventoryLine)
            .where(InventoryLine.count_id == count_id, InventoryLine.outcome == "missing")
        )
        or 0
    )


def apply_count(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    count: InventoryCount,
) -> tuple[int, int, int]:
    """LIB-INV-18, LIB-INV-19: ``(missing_marked, found, relocated)``."""
    if missing_line_count(db, count.id) > rules.APPLY_ADMIN_LIMIT and actor.role != "admin":
        raise Forbidden("Only an admin applies a count with more than 10 missing copies")
    if count.status != "closed":
        raise invalid_count_status(count, "applying")

    marked = 0
    missing_lines = db.scalars(
        sa.select(InventoryLine.copy_id)
        .where(InventoryLine.count_id == count.id, InventoryLine.outcome == "missing")
        .order_by(InventoryLine.copy_id)
    ).all()
    for copy_id in missing_lines:  # (1)
        copy = db.get(Copy, copy_id)
        assert copy is not None
        if copy.status in rules.SHELF_STATUSES and copy.current_branch_id == count.branch_id:
            mark_missing(db, now, copy)
            marked += 1

    found = 0
    relocated = 0
    scans = db.scalars(
        sa.select(InventoryScan)
        .where(InventoryScan.count_id == count.id, InventoryScan.result.in_(("found_lost", "wrong_branch")))
        .order_by(InventoryScan.id)
    ).all()
    for scan in scans:
        if scan.result == "found_lost" and scan.copy_id is not None:  # (2)
            copy = db.get(Copy, scan.copy_id)
            assert copy is not None
            if copy.status in ("lost", "missing"):
                restore_copy(db, now, actor.id, holidays, copy, count.branch_id)
                scan.applied = True
                found += 1
    for scan in scans:
        if scan.result == "wrong_branch" and scan.copy_id is not None:  # (3)
            copy = db.get(Copy, scan.copy_id)
            assert copy is not None
            if copy.status == "available" and copy.current_branch_id != count.branch_id:
                copy.current_branch_id = count.branch_id
                db.flush()
                release_copy(db, copy, now, holidays, actor.id)
                scan.applied = True
                relocated += 1

    count.status = "applied"
    count.applied_at = now
    db.flush()
    _emit(db, now, actor, "inventory_count_applied", count, missing_marked=marked, found=found, relocated=relocated)
    return marked, found, relocated
