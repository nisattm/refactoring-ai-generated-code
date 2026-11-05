import dataclasses
import datetime
import decimal

import pytest
from fastapi.testclient import TestClient

from lms import DEFAULT_HOLIDAYS, FixedClock, Settings, SystemClock, create_app
from lms.core.money import format_amount, round_money
from lms.core.working_days import add_working_days, working_days_between
from lms.core.clock import LOCAL_TZ as LOCAL


def test_health_today_follows_clock_and_local_zone(clock):
    client = TestClient(create_app(Settings(database_url="sqlite://", clock=clock)))
    assert client.get("/health").json() == {"status": "ok", "today": "2026-11-05"}
    # 23:30 UTC on 4 Nov is already 5 Nov in UTC+03:00.
    clock.set(datetime.datetime(2026, 11, 4, 23, 30, tzinfo=datetime.timezone.utc))
    assert client.get("/health").json()["today"] == "2026-11-05"


def test_clock_change_is_visible_without_restart(client, clock):
    clock.advance(days=30)
    assert client.get("/health").json()["today"] == "2026-12-05"


def test_fixed_clock_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        FixedClock(datetime.datetime(2026, 1, 1))
    clock = FixedClock(datetime.datetime(2026, 1, 1, tzinfo=LOCAL))
    with pytest.raises(ValueError):
        clock.set(datetime.datetime(2026, 1, 1))


def test_system_clock_is_utc_plus_three():
    assert SystemClock().now().utcoffset() == datetime.timedelta(hours=3)


@pytest.mark.parametrize("ttl", [0, 169])
def test_token_ttl_out_of_range_raises(ttl):
    with pytest.raises(ValueError):
        Settings(token_ttl_hours=ttl)


def test_settings_defaults():
    settings = Settings()
    assert settings.database_url == "sqlite:///./lms.db"
    assert settings.holidays == DEFAULT_HOLIDAYS
    assert settings.bootstrap_admin_email == "admin@library.local"
    assert settings.token_ttl_hours == 12
    assert dataclasses.is_dataclass(settings)
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.token_ttl_hours = 1


def test_default_holidays_count():
    assert len(DEFAULT_HOLIDAYS) == 27  # 14 in 2026, 13 in 2027


def test_working_day_rules_on_custom_holidays():
    settings = Settings(holidays=frozenset({datetime.date(2026, 11, 9)}))
    assert working_days_between(datetime.date(2026, 11, 6), datetime.date(2026, 11, 11), settings) == 2
    assert add_working_days(datetime.date(2026, 11, 6), 1, settings) == datetime.date(2026, 11, 10)


def test_working_days_outside_holiday_years_use_weekends_only():
    settings = Settings()
    assert add_working_days(datetime.date(2030, 1, 1), 1, settings) == datetime.date(2030, 1, 2)


def test_money_rounds_half_up_to_two_places():
    assert round_money(decimal.Decimal("0.125")) == decimal.Decimal("0.13")
    assert format_amount(decimal.Decimal("12.5")) == "12.50"
    assert format_amount(decimal.Decimal("0")) == "0.00"


def test_create_app_twice_on_same_file_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'lms.db'}"
    create_app(Settings(database_url=url))
    app = create_app(Settings(database_url=url))
    assert TestClient(app).get("/health").status_code == 200


def test_applications_do_not_share_state(clock):
    first = TestClient(create_app(Settings(database_url="sqlite://", clock=clock)))
    second = TestClient(create_app(Settings(database_url="sqlite://", clock=FixedClock(
        datetime.datetime(2000, 1, 1, tzinfo=LOCAL)))))
    assert first.get("/health").json()["today"] == "2026-11-05"
    assert second.get("/health").json()["today"] == "2000-01-01"


def test_unknown_path_and_wrong_method_use_error_format(client):
    missing = client.get("/api/v1/nothing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    wrong = client.post("/health")
    assert wrong.status_code == 405
    assert wrong.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_openapi_lists_core_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in [
        "/health",
        "/api/v1/calendar/holidays",
        "/api/v1/calendar/days/{date}",
        "/api/v1/calendar/next-working-day",
        "/api/v1/calendar/add-working-days",
        "/api/v1/calendar/working-days-between",
    ]:
        assert path in paths


def test_unexpected_error_returns_generic_500(clock, monkeypatch):
    app = create_app(Settings(database_url="sqlite://", clock=clock))
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr("lms.api.app.today", lambda _clock: 1 / 0)
    response = client.get("/health")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "details": {}}
    }
