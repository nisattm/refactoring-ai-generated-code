import datetime

import pytest
from fastapi.testclient import TestClient

from lms import FixedClock, Settings, create_app

LOCAL = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime.datetime(2026, 11, 5, 9, 30, tzinfo=LOCAL))


@pytest.fixture
def client(clock: FixedClock) -> TestClient:
    app = create_app(Settings(database_url="sqlite://", clock=clock))
    return TestClient(app)
