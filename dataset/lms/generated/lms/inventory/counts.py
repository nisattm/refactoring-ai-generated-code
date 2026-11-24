"""Starting, reading and cancelling counts, scanning (LIB-INV-01 to LIB-INV-13, LIB-INV-29)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Copy
from lms.core.errors import Conflict, ValidationFailed
from lms.core.lookup import get_or_404
from lms.core.timeutil import format_datetime
from lms.inventory import rules
from lms.inventory.models import ExpectedCopy, InventoryCount, InventoryLine, InventoryScan
from lms.inventory.schemas import (
    CountDetailOut,
    CountOut,
    ProblemsOut,
    ProgressOut,
    ScanOut,
    SummaryOut,
)
from lms.staff.schedule import load_schedule


def get_count_or_404(db: Session, count_id: int) -> InventoryCount:
    return get_or_404(db, InventoryCount, count_id, label="Inventory count", resource="inventory_count")


def get_scan_or_404(db: Session, scan_id: int) -> InventoryScan:
    return get_or_404(db, InventoryScan, scan_id, label="Inventory scan", resource="inventory_scan")


def invalid_count_status(count: InventoryCount, action: str) -> Conflict:
    return Conflict(
        f"Inventory count {count.id} has status {count.status}: {action} is not allowed",
        code="INVALID_COUNT_STATUS",
        details={"id": count.id, "status": count.status},
    )


def _datetime(value: datetime.datetime | None) -> str | None:
    return format_datetime(value) if value is not None else None


def expected_ids(db: Session, count_id: int) -> list[int]:
    return list(db.scalars(sa.select(ExpectedCopy.copy_id).where(ExpectedCopy.count_id == count_id).order_by(ExpectedCopy.copy_id)))


def count_out(db: Session, count: InventoryCount) -> CountOut:
    expected = expected_ids(db, count.id)
    return CountOut(**_base(count, expected))


def _base(count: InventoryCount, expected: list[int]) -> dict[str, Any]:
    return {
        "id": count.id,
        "branch_id": count.branch_id,
        "name": count.name,
        "shelf_prefix": count.shelf_prefix,
        "status": count.status,
        "cancel_reason": count.cancel_reason,
        "started_at": format_datetime(count.started_at),
        "closed_at": _datetime(count.closed_at),
        "applied_at": _datetime(count.applied_at),
        "expected": expected,
        "expected_count": len(expected),
    }


def summary_of(db: Session, count_id: int) -> SummaryOut | None:
    """LIB-INV-15 from the stored lines; ``None`` while the count has none."""
    rows = dict(
        db.execute(
            sa.select(InventoryLine.outcome, sa.func.count())
            .where(InventoryLine.count_id == count_id)
            .group_by(InventoryLine.outcome)
        ).all()
    )
    if not rows:
        return None
    found, missing, moved = rows.get("found", 0), rows.get("missing", 0), rows.get("moved", 0)
    return SummaryOut(
        expected=found + missing + moved,
        found=found,
        missing=missing,
        moved=moved,
        accuracy=rules.accuracy(found, missing),
    )


def progress_of(db: Session, count: InventoryCount, expected: int) -> ProgressOut:
    """LIB-INV-05."""
    scanned_expected = (
        db.scalar(
            sa.select(sa.func.count(sa.distinct(InventoryScan.copy_id)))
            .join(
                ExpectedCopy,
                sa.and_(ExpectedCopy.count_id == InventoryScan.count_id, ExpectedCopy.copy_id == InventoryScan.copy_id),
            )
            .where(InventoryScan.count_id == count.id)
        )
        or 0
    )
    counts = dict(
        db.execute(
            sa.select(InventoryScan.result, sa.func.count())
            .where(InventoryScan.count_id == count.id)
            .group_by(InventoryScan.result)
        ).all()
    )
    problems = ProblemsOut(**{name: counts.get(name, 0) for name in rules.PROBLEM_RESULTS})
    return ProgressOut(
        expected=expected, scanned_expected=scanned_expected, remaining=expected - scanned_expected, problems=problems
    )


def count_detail_out(db: Session, count: InventoryCount) -> CountDetailOut:
    expected = expected_ids(db, count.id)
    return CountDetailOut(
        **_base(count, expected), progress=progress_of(db, count, len(expected)), summary=summary_of(db, count.id)
    )


def scan_out(scan: InventoryScan) -> ScanOut:
    return ScanOut(
        id=scan.id,
        count_id=scan.count_id,
        barcode=scan.barcode,
        copy_id=scan.copy_id,
        result=scan.result,
        scanned_at=format_datetime(scan.scanned_at),
        scanned_by=scan.scanned_by,
    )


def _emit(
    db: Session,
    now: datetime.datetime,
    actor: User,
    event: str,
    count: InventoryCount,
    **extra: Any,
) -> None:
    record(
        db,
        at=now,
        event=event,
        actor_user_id=actor.id,
        entity_type="inventory_count",
        entity_id=count.id,
        details={"branch_id": count.branch_id, "name": count.name, "shelf_prefix": count.shelf_prefix, **extra},
    )


# --- starting ----------------------------------------------------------------------------------


def snapshot_of(db: Session, branch_id: int, prefix: str | None) -> list[int]:
    """LIB-INV-02: the copies in the scope of a count that have a shelf status, ascending."""
    rows = db.execute(
        sa.select(Copy.id, Copy.shelf_location)
        .where(Copy.current_branch_id == branch_id, Copy.status.in_(rules.SHELF_STATUSES))
        .order_by(Copy.id)
    )
    return [copy_id for copy_id, shelf in rows if rules.in_prefix(shelf, prefix)]


def start_count(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    branch_id: int,
    name: str,
    shelf_prefix: str | None,
) -> InventoryCount:
    """LIB-INV-01 to LIB-INV-03, LIB-INV-29."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise ValidationFailed.single("branch_id", f"branch {branch_id} does not exist")
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": "branch_id", "id": branch.id}
        )
    day = now.date()
    reason = load_schedule(db, branch.id).closed_reason(day, holidays)
    if reason is not None:
        raise Conflict(
            "The branch is not open today",
            code="BRANCH_NOT_OPEN",
            details={"reason": reason.split(":")[0], "date": day.isoformat()},
        )
    open_counts = db.scalars(
        sa.select(InventoryCount).where(InventoryCount.branch_id == branch.id, InventoryCount.status == "open").order_by(InventoryCount.id)
    )
    for other in open_counts:
        if rules.prefixes_overlap(other.shelf_prefix, shelf_prefix):
            raise Conflict(
                f"The open count {other.id} of the branch overlaps",
                code="COUNT_SCOPE_OVERLAP",
                details={"count_id": other.id},
            )
    expected = snapshot_of(db, branch.id, shelf_prefix)
    if not expected:
        raise Conflict("The count has no copies to count", code="COUNT_EMPTY", details={"branch_id": branch.id})

    count = InventoryCount(branch_id=branch.id, name=name, shelf_prefix=shelf_prefix, status="open", started_at=now)
    db.add(count)
    db.flush()
    db.add_all(ExpectedCopy(count_id=count.id, copy_id=copy_id) for copy_id in expected)
    db.flush()
    _emit(db, now, actor, "inventory_count_started", count, expected_count=len(expected))
    return count


def list_stmt(*, branch_id: int | None = None, status: str | None = None) -> sa.Select[tuple[InventoryCount]]:
    """LIB-INV-05."""
    stmt = sa.select(InventoryCount).order_by(InventoryCount.id.desc())
    if branch_id is not None:
        stmt = stmt.where(InventoryCount.branch_id == branch_id)
    if status is not None:
        stmt = stmt.where(InventoryCount.status == status)
    return stmt


def cancel_count(db: Session, now: datetime.datetime, actor: User, count: InventoryCount) -> InventoryCount:
    """LIB-INV-06."""
    if count.status not in ("open", "closed"):
        raise invalid_count_status(count, "cancellation")
    count.status = "cancelled"
    count.cancel_reason = "staff_request"
    _emit(db, now, actor, "inventory_count_cancelled", count, cancel_reason="staff_request")
    return count


# --- scanning ------------------------------------------------------------------------------------


def scan_result(copy: Copy | None, count: InventoryCount, expected: set[int], scanned: set[int]) -> str:
    """LIB-INV-08: the first rule that applies."""
    if copy is None:
        return "unknown"
    if copy.id in scanned:
        return "duplicate"
    if copy.id in expected:
        return "expected"
    if copy.status in ("lost", "missing"):
        return "found_lost"
    if copy.status == "withdrawn":
        return "withdrawn"
    if copy.current_branch_id is None or copy.current_branch_id != count.branch_id:
        return "wrong_branch"
    if copy.status not in rules.SHELF_STATUSES:
        return "unexpected_status"
    return "out_of_scope"


def add_scans(
    db: Session, now: datetime.datetime, actor: User, count: InventoryCount, barcodes: list[str]
) -> list[InventoryScan]:
    """LIB-INV-07."""
    if count.status != "open":
        raise invalid_count_status(count, "scanning")
    expected = set(expected_ids(db, count.id))
    scanned = set(db.scalars(sa.select(InventoryScan.copy_id).where(InventoryScan.count_id == count.id, InventoryScan.copy_id.is_not(None))))
    scans: list[InventoryScan] = []
    for raw in barcodes:
        barcode = raw.upper()
        copy = db.scalar(sa.select(Copy).where(Copy.barcode == barcode))
        result = scan_result(copy, count, expected, scanned)
        scan = InventoryScan(
            count_id=count.id,
            barcode=barcode,
            copy_id=copy.id if copy is not None else None,
            result=result,
            scanned_at=now,
            scanned_by=actor.id,
        )
        db.add(scan)
        db.flush()
        if copy is not None:
            scanned.add(copy.id)
        scans.append(scan)
    _emit(
        db,
        now,
        actor,
        "inventory_scans_added",
        count,
        scan_ids=[s.id for s in scans],
        barcodes=[s.barcode for s in scans],
        results=[s.result for s in scans],
    )
    return scans


def scan_list_stmt(count_id: int, result: str | None) -> sa.Select[tuple[InventoryScan]]:
    """LIB-INV-11."""
    stmt = sa.select(InventoryScan).where(InventoryScan.count_id == count_id).order_by(InventoryScan.id)
    if result is not None:
        stmt = stmt.where(InventoryScan.result == result)
    return stmt


def remove_scan(db: Session, now: datetime.datetime, actor: User, scan: InventoryScan) -> None:
    """LIB-INV-12: later ``duplicate`` scans keep their result; the copy counts as scanned while a scan is left."""
    count = db.get(InventoryCount, scan.count_id)
    assert count is not None
    if count.status != "open":
        raise invalid_count_status(count, "removing a scan")
    details = {"count_id": count.id, "barcode": scan.barcode, "copy_id": scan.copy_id, "result": scan.result}
    scan_id = scan.id
    db.delete(scan)
    db.flush()
    record(
        db,
        at=now,
        event="inventory_scan_removed",
        actor_user_id=actor.id,
        entity_type="inventory_scan",
        entity_id=scan_id,
        details=details,
    )
