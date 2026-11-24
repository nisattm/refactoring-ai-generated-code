"""Shipments to a bindery (LIB-PRE-19, LIB-PRE-20)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.errors import Conflict
from lms.core.lookup import get_or_404, get_reference_or_404
from lms.core.timeutil import format_datetime
from lms.preservation import jobs
from lms.preservation.models import RepairJob, Shipment
from lms.preservation.schemas import ShipmentOut
from lms.purchasing.models import Supplier


def get_shipment_or_404(db: Session, shipment_id: int) -> Shipment:
    return get_or_404(db, Shipment, shipment_id, label="Shipment", resource="repair_shipment")


def shipment_out(db: Session, shipment: Shipment) -> ShipmentOut:
    rows = db.execute(
        sa.select(RepairJob.id, RepairJob.status).where(RepairJob.shipment_id == shipment.id).order_by(RepairJob.id)
    ).all()
    return ShipmentOut(
        id=shipment.id,
        code=shipment.code,
        supplier_id=shipment.supplier_id,
        branch_id=shipment.branch_id,
        job_ids=[job_id for job_id, _ in rows],
        open_jobs=sum(1 for _, status in rows if status == "sent"),
        sent_at=format_datetime(shipment.sent_at),
    )


def create_shipment(
    db: Session, now: datetime.datetime, actor: User, *, supplier_id: int, job_ids: list[int]
) -> Shipment:
    """LIB-PRE-19: all jobs are sent or none."""
    supplier = get_reference_or_404(db, Supplier, "supplier_id", supplier_id)
    found: list[RepairJob] = [get_reference_or_404(db, RepairJob, "job_ids", job_id) for job_id in job_ids]
    if not supplier.is_active:
        raise Conflict(
            f"Supplier {supplier.id} is inactive",
            code="SUPPLIER_INACTIVE",
            details={"field": "supplier_id", "id": supplier.id},
        )
    branch_id = found[0].branch_id
    for job in found:
        if (
            job.status != "approved"
            or job.provider != "supplier"
            or job.supplier_id != supplier_id
            or job.branch_id != branch_id
        ):
            raise Conflict(
                f"Repair job {job.id} cannot be sent in this shipment",
                code="SHIPMENT_MISMATCH",
                details={"job_id": job.id},
            )
    branch = db.get(Branch, branch_id)
    assert branch is not None
    count = db.scalar(sa.select(sa.func.count()).select_from(Shipment).where(Shipment.branch_id == branch_id)) or 0
    shipment = Shipment(
        code=f"SH-{branch.code}-{count + 1}", supplier_id=supplier_id, branch_id=branch_id, sent_at=now
    )
    db.add(shipment)
    db.flush()
    for job in found:
        jobs.start_repair(db, now, job, shipment.id)
    db.flush()
    record(
        db,
        at=now,
        event="repair_shipment_sent",
        actor_user_id=actor.id,
        entity_type="repair_shipment",
        entity_id=shipment.id,
        details={
            "code": shipment.code,
            "supplier_id": supplier_id,
            "branch_id": branch_id,
            "job_ids": sorted(job_ids),
        },
    )
    return shipment


def shipment_list_stmt(supplier_id: int | None, branch_id: int | None) -> sa.Select[tuple[Shipment]]:
    """LIB-PRE-20."""
    stmt = sa.select(Shipment).order_by(Shipment.id.desc())
    if supplier_id is not None:
        stmt = stmt.where(Shipment.supplier_id == supplier_id)
    if branch_id is not None:
        stmt = stmt.where(Shipment.branch_id == branch_id)
    return stmt
