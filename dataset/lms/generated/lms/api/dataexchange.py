"""Import and export endpoints (sections 19.2 and 19.3)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Response
from pydantic import BaseModel

from lms.audit import exporter
from lms.audit.importer import import_data
from lms.auth.deps import AdminOnly
from lms.core.context import HolidaysDep, NowDep
from lms.core.db import SessionDep
from lms.core.errors import NotFound
from lms.core.responses import csv_response

router = APIRouter(tags=["import-export"])


class ImportedOut(BaseModel):
    imported: dict[str, int]


@router.post("/import", response_model=ImportedOut)
def import_dataset(
    now: NowDep, holidays: HolidaysDep, db: SessionDep, admin: AdminOnly, data: Annotated[Any, Body()]
) -> ImportedOut:
    return ImportedOut(imported=import_data(db, now, admin.user.id, holidays, data))


@router.get("/export")
def export_all(now: NowDep, db: SessionDep, admin: AdminOnly) -> dict[str, Any]:
    document = exporter.build_document(db)
    exporter.record_export(db, now, admin.user.id, "all")
    return document


@router.get("/export/{entity}.csv")
def export_csv(entity: Annotated[str, Path()], now: NowDep, db: SessionDep, admin: AdminOnly) -> Response:
    if entity not in exporter.CSV_ENTITIES:
        raise NotFound(f"Unknown entity {entity}", details={"resource": "entity", "entity": entity})
    text = exporter.build_csv(db, entity)
    exporter.record_export(db, now, admin.user.id, entity)
    return csv_response(text)
