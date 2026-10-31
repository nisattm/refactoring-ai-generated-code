"""Import and export endpoints (sections 19.2 and 19.3)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Request, Response
from pydantic import BaseModel

from lms.audit import exporter
from lms.audit.importer import import_data
from lms.auth.deps import AdminOnly
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import NotFound

router = APIRouter(tags=["import-export"])

CSV_TYPE = "text/csv; charset=utf-8"


class ImportedOut(BaseModel):
    imported: dict[str, int]


@router.post("/import", response_model=ImportedOut)
def import_dataset(
    request: Request, db: SessionDep, admin: AdminOnly, data: Annotated[Any, Body()]
) -> ImportedOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    return ImportedOut(imported=import_data(db, now, admin.user.id, settings.holidays, data))


@router.get("/export")
def export_all(request: Request, db: SessionDep, admin: AdminOnly) -> dict[str, Any]:
    now = local_now(request.app.state.settings.clock)
    document = exporter.build_document(db)
    exporter.record_export(db, now, admin.user.id, "all")
    return document


@router.get("/export/{entity}.csv")
def export_csv(
    entity: Annotated[str, Path()], request: Request, db: SessionDep, admin: AdminOnly
) -> Response:
    if entity not in exporter.CSV_ENTITIES:
        raise NotFound(f"Unknown entity {entity}", details={"resource": "entity", "entity": entity})
    now = local_now(request.app.state.settings.clock)
    text = exporter.build_csv(db, entity)
    exporter.record_export(db, now, admin.user.id, entity)
    return Response(content=text.encode("utf-8"), media_type=CSV_TYPE)
