"""Import and export endpoints (sections 19.2 and 19.3)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Request, Response
from pydantic import BaseModel

from lms.api.common import csv_response, now_of, settings_of
from lms.audit import exporter
from lms.audit.importer import import_data
from lms.auth.deps import AdminOnly
from lms.core.db import SessionDep
from lms.core.errors import NotFound

router = APIRouter(tags=["import-export"])


class ImportedOut(BaseModel):
    imported: dict[str, int]


@router.post("/import", response_model=ImportedOut)
def import_dataset(
    request: Request, db: SessionDep, admin: AdminOnly, data: Annotated[Any, Body()]
) -> ImportedOut:
    settings = settings_of(request)
    return ImportedOut(imported=import_data(db, now_of(request), admin.user.id, settings.holidays, data))


@router.get("/export")
def export_all(request: Request, db: SessionDep, admin: AdminOnly) -> dict[str, Any]:
    now = now_of(request)
    document = exporter.build_document(db)
    exporter.record_export(db, now, admin.user.id, "all")
    return document


@router.get("/export/{entity}.csv")
def export_csv(
    entity: Annotated[str, Path()], request: Request, db: SessionDep, admin: AdminOnly
) -> Response:
    if entity not in exporter.CSV_ENTITIES:
        raise NotFound(f"Unknown entity {entity}", details={"resource": "entity", "entity": entity})
    now = now_of(request)
    text = exporter.build_csv(db, entity)
    exporter.record_export(db, now, admin.user.id, entity)
    return csv_response(text)
