"""Import and export without HTTP (LIB-IF-11, LIB-IF-12)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import sessionmaker

from lms.audit import exporter
from lms.audit.importer import import_data
from lms.auth.bootstrap import ensure_bootstrap_admin
from lms.core.clock import local_now
from lms.core.db import create_schema, get_engine
from lms.core.errors import Conflict, ValidationFailed
from lms.core.settings import Settings


def _session_factory(settings: Settings) -> sessionmaker:
    engine = get_engine(settings)
    create_schema(engine)
    return sessionmaker(engine, expire_on_commit=False)


def import_dataset(settings: Settings, data: dict) -> dict[str, int]:
    """``POST /api/v1/import`` without authentication. Raises ``ValueError`` if the data is invalid and
    ``RuntimeError`` if the database is not empty. Returns the counts per list."""
    factory = _session_factory(settings)
    now = local_now(settings.clock)
    try:
        with factory.begin() as session:
            ensure_bootstrap_admin(session, settings)
            return import_data(session, now, None, settings.holidays, data)
    except ValidationFailed as exc:
        problems = "; ".join(f"{p['field']}: {p['problem']}" for p in exc.details["fields"])
        raise ValueError(f"invalid dataset: {problems}") from None
    except Conflict as exc:
        if exc.code == "DATABASE_NOT_EMPTY":
            raise RuntimeError(exc.message) from None
        raise


def export_dataset(settings: Settings) -> dict[str, Any]:
    """The document of ``GET /api/v1/export`` (section 22.1)."""
    factory = _session_factory(settings)
    now = local_now(settings.clock)
    with factory.begin() as session:
        document = exporter.build_document(session)
        exporter.record_export(session, now, None, "all")
    return document
