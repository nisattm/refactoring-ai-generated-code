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
def client(app, clock, settings):
    """Test client that renews the sessions of ``api.session`` once the clock has passed their
    expiry (LIB-AUTH-12). Tests move the clock by days; without renewal every later request of
    the fixture users would return ``401 TOKEN_EXPIRED``. Sessions from ``api.login`` are never
    renewed, so expiry is still tested."""
    from fastapi.testclient import TestClient

    ttl = timedelta(hours=getattr(settings, "token_ttl_hours", 12))

    class SessionClient(TestClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._sessions: dict[str, list] = {}  # Authorization value -> [headers, email, password, expires]

        def track_session(self, headers: dict, email: str, password: str) -> None:
            self._sessions[headers["Authorization"]] = [headers, email, password, clock.now() + ttl]

        def _renew(self, entry: list) -> str | None:
            headers, email, password, _ = entry
            r = super().request("POST", f"{api.BASE}/auth/login", json={"email": email, "password": password})
            if r.status_code != 200:
                return None  # e.g. locked or deactivated: keep the old token
            new = f"Bearer {r.json()['access_token']}"
            del self._sessions[headers["Authorization"]]
            headers["Authorization"] = new  # the dict the test holds
            entry[3] = clock.now() + ttl
            self._sessions[new] = entry
            return new

        def request(self, method, url, *args, **kwargs):
            headers = kwargs.get("headers")
            if headers:
                entry = self._sessions.get(dict(headers).get("Authorization"))
                if entry is not None and clock.now() >= entry[3]:
                    new = self._renew(entry)
                    if new is not None:
                        kwargs["headers"] = {**dict(headers), "Authorization": new}
            return super().request(method, url, *args, **kwargs)

    with SessionClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin(client) -> dict[str, str]:
    """Authorization header of the bootstrap administrator (renewed after expiry)."""
    return api.session(client, ADMIN_EMAIL, ADMIN_PASSWORD)


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
    return api.session(client, LIBRARIAN_EMAIL, LIBRARIAN_PASSWORD)


@pytest.fixture
def branch_a(client, admin) -> dict:
    return api.create_branch(client, admin, "AA")


@pytest.fixture
def branch_b(client, admin) -> dict:
    return api.create_branch(client, admin, "BB")
