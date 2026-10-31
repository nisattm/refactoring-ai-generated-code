import datetime

import pytest
from fastapi.testclient import TestClient

import lms

TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def clock():
    return lms.FixedClock(datetime.datetime(2026, 11, 2, 9, 30, tzinfo=TZ))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock)


@pytest.fixture
def app(settings):
    return lms.create_app(settings)


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)
