"""Shared fixtures for the LMS tests (contract: README.md, "Fixture and helper contract").

The tests are written before the code exists; until then they fail at ``import lms``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Make ``support`` importable in every pytest import mode (the runner uses importlib mode).
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from support import api  # noqa: E402

LOCAL_TZ = timezone(timedelta(hours=3))  # LIB-COM-01

ADMIN_EMAIL = "admin@library.local"  # LIB-AUTH-01, Settings defaults (section 4.2)
ADMIN_PASSWORD = "ChangeMe123"
LIBRARIAN_EMAIL = "lib@library.local"
LIBRARIAN_PASSWORD = "Librarian123"


@pytest.fixture
def start() -> datetime:
    """2026-11-02 09:00 local time (a Monday and a working day)."""
    return datetime(2026, 11, 2, 9, 0, tzinfo=LOCAL_TZ)


@pytest.fixture
def clock(start):
    import lms

    return lms.FixedClock(start)


@pytest.fixture
def settings(clock):
    import lms

    return lms.Settings(database_url="sqlite://", clock=clock)


@pytest.fixture
def app(settings):
    import lms

    return lms.create_app(settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin(client) -> dict[str, str]:
    """Authorization header of the bootstrap administrator."""
    return api.login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def librarian(client, admin) -> dict[str, str]:
    """Authorization header of a librarian created by the admin (LIB-AUTH-17)."""
    api.post(
        client,
        "/api/v1/users",
        admin,
        {
            "email": LIBRARIAN_EMAIL,
            "full_name": "Test Librarian",
            "role": "librarian",
            "password": LIBRARIAN_PASSWORD,
        },
        expect=201,
    )
    return api.login(client, LIBRARIAN_EMAIL, LIBRARIAN_PASSWORD)


@pytest.fixture
def branch_a(client, admin) -> dict:
    return api.create_branch(client, admin, "A")


@pytest.fixture
def branch_b(client, admin) -> dict:
    return api.create_branch(client, admin, "B")
