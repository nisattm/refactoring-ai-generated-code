import pytest
from fastapi.testclient import TestClient

import helpers  # registers the Probe table before create_app
from helpers import local_datetime
from lms import FixedClock, Settings, create_app


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(local_datetime(2026, 11, 5, 9, 30))


@pytest.fixture
def app(clock):
    return create_app(Settings(database_url="sqlite://", clock=clock))


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)
