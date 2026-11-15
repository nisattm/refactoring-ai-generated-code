"""Inventory report (LIB-INV-32)."""

from __future__ import annotations

import datetime
from collections import defaultdict

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.models import AuditEntry
from lms.branches.models import Branch
from lms.catalog.models import Copy
from lms.core.clock import LOCAL_TZ
from lms.inventory import rules
from lms.inventory.models import InventoryCount, InventoryLine, InventoryScan
from lms.inventory.schemas import InventoryReportRowOut


def inventory_report(db: Session, year: int) -> list[InventoryReportRowOut]:
    """One row per branch with a count applied in ``year``, ordered by branch code."""
    first = datetime.datetime(year, 1, 1, tzinfo=LOCAL_TZ)
    after = datetime.datetime(year + 1, 1, 1, tzinfo=LOCAL_TZ)
    counts = db.scalars(
        sa.select(InventoryCount)
        .where(InventoryCount.status == "applied", InventoryCount.applied_at >= first, InventoryCount.applied_at < after)
        .order_by(InventoryCount.id)
    ).all()
    if not counts:
        return []
    by_branch: dict[int, list[InventoryCount]] = defaultdict(list)
    for count in counts:
        by_branch[count.branch_id].append(count)
    codes = dict(db.execute(sa.select(Branch.id, Branch.code).where(Branch.id.in_(by_branch))).all())

    outcomes: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for count_id, outcome, n in db.execute(
        sa.select(InventoryLine.count_id, InventoryLine.outcome, sa.func.count())
        .where(InventoryLine.count_id.in_([c.id for c in counts]))
        .group_by(InventoryLine.count_id, InventoryLine.outcome)
    ):
        outcomes[count_id][outcome] = n

    found_events: dict[int, int] = defaultdict(int)  # copy_found events of the year, by branch
    for (details,) in db.execute(
        sa.select(AuditEntry.details).where(AuditEntry.event == "copy_found", AuditEntry.at >= first, AuditEntry.at < after)
    ):
        branch_id = details.get("branch_id") if isinstance(details, dict) else None
        if branch_id in by_branch:
            found_events[branch_id] += 1

    rows: list[InventoryReportRowOut] = []
    for branch_id in sorted(by_branch, key=lambda b: (codes[b], b)):
        branch_counts = by_branch[branch_id]
        ids = [c.id for c in branch_counts]
        found = sum(outcomes[i]["found"] for i in ids)
        missing = sum(outcomes[i]["missing"] for i in ids)
        moved = sum(outcomes[i]["moved"] for i in ids)
        missing_now = (
            db.scalar(
                sa.select(sa.func.count()).select_from(Copy).where(Copy.current_branch_id == branch_id, Copy.status == "missing")
            )
            or 0
        )
        applied_scans = (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(InventoryScan)
                .where(InventoryScan.count_id.in_(ids), InventoryScan.result == "found_lost", InventoryScan.applied.is_(True))
            )
            or 0
        )
        last = max(c.applied_at for c in branch_counts if c.applied_at is not None)
        rows.append(
            InventoryReportRowOut(
                branch_id=branch_id,
                counts_applied=len(branch_counts),
                last_applied_on=last.date().isoformat(),
                expected=found + missing + moved,
                found=found,
                missing=missing,
                accuracy=rules.accuracy(found, missing),
                missing_now=missing_now,
                found_again=found_events[branch_id] + applied_scans,
            )
        )
    return rows
