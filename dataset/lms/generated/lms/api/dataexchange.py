"""Import and export endpoints (sections 19.2 and 19.3)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Request, Response
from pydantic import BaseModel

from lms.api.responses import csv_response
from lms.audit import exporter
from lms.audit.importer import import_data
from lms.auth.deps import AdminOnly
from lms.core.context import app_settings, request_now
from lms.core.db import SessionDep
from lms.core.errors import NotFound

router = APIRouter(tags=["import-export"])


class ImportedOut(BaseModel):
    imported: dict[str, int]


@router.post("/import", response_model=ImportedOut)
def import_dataset(
    request: Request, db: SessionDep, admin: AdminOnly, data: Annotated[Any, Body()]
) -> ImportedOut:
    return ImportedOut(
        imported=import_data(db, request_now(request), admin.user.id, app_settings(request).holidays, data)
    )


@router.get("/export")
def export_all(request: Request, db: SessionDep, admin: AdminOnly) -> dict[str, Any]:
    now = request_now(request)
    document = exporter.build_document(db)
    exporter.record_export(db, now, admin.user.id, "all")
    return document


@router.get("/export/{entity}.csv")
def export_csv(
    entity: Annotated[str, Path()], request: Request, db: SessionDep, admin: AdminOnly
) -> Response:
    if entity not in exporter.CSV_ENTITIES:
        raise NotFound(f"Unknown entity {entity}", details={"resource": "entity", "entity": entity})
    now = request_now(request)
    text = exporter.build_csv(db, entity)
    exporter.record_export(db, now, admin.user.id, entity)
    return csv_response(text)
