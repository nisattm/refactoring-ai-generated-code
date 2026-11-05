"""HTTP behavior of module 1 and the application (sections 4, 5 and the common error rules)."""

import asyncio
import datetime
import inspect

import pytest
from fastapi import Depends, Query
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session

from helpers import Probe, local_datetime
from lms import Settings, create_app
from lms.api.deps import get_session
from lms.core.errors import ApiError
from lms.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate

CALENDAR_PATHS = [
    "/api/v1/calendar/holidays",
    "/api/v1/calendar/days/{date}",
    "/api/v1/calendar/next-working-day",
    "/api/v1/calendar/add-working-days",
    "/api/v1/calendar/working-days-between",
]


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)
    return body["error"]


# LIB-IF-10
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "today": "2026-11-05"}


# LIB-IF-09
def test_clock_changes_are_seen_by_next_request(app, clock, client):
    clock.advance(days=1)
    assert client.get("/health").json()["today"] == "2026-11-06"
    clock.set(local_datetime(2027, 1, 1, 0, 0))
    assert client.get("/health").json()["today"] == "2027-01-01"


# LIB-CORE-01
def test_holidays_of_a_year_in_date_order(client):
    response = client.get("/api/v1/calendar/holidays", params={"year": 2026})
    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2026
    assert body["holidays"][0] == {"date": "2026-01-01", "name": "New Year's Day"}
    dates = [h["date"] for h in body["holidays"]]
    assert dates == sorted(dates)
    assert len(dates) == 14


def test_year_without_entries_gives_empty_list(client):
    body = client.get("/api/v1/calendar/holidays", params={"year": 2030}).json()
    assert body == {"year": 2030, "holidays": []}


def test_double_holiday_name_for_2027_05_19(client):
    holidays = client.get("/api/v1/calendar/holidays", params={"year": 2027}).json()["holidays"]
    entry = next(h for h in holidays if h["date"] == "2027-05-19")
    assert entry["name"] == "Kurban Bayramı, day 4; Commemoration of Atatürk, Youth and Sports Day"


@pytest.mark.parametrize("year", [1899, 2101, "abc", ""])
def test_year_out_of_range_or_invalid(client, year):
    response = client.get("/api/v1/calendar/holidays", params={"year": year})
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert {f["field"] for f in error["details"]["fields"]} == {"year"}


def test_missing_year_names_the_parameter(client):
    error = assert_error(client.get("/api/v1/calendar/holidays"), 422, "VALIDATION_ERROR")
    assert error["details"]["fields"][0]["field"] == "year"
    assert error["details"]["fields"][0]["problem"]


# LIB-CORE-02
def test_day_status_holiday_and_weekend(client):
    assert client.get("/api/v1/calendar/days/2026-10-29").json() == {
        "date": "2026-10-29",
        "working_day": False,
        "reason": "holiday",
    }
    # Sunday and Victory Day: reason is holiday
    assert client.get("/api/v1/calendar/days/2026-08-30").json()["reason"] == "holiday"
    assert client.get("/api/v1/calendar/days/2026-11-07").json() == {
        "date": "2026-11-07",
        "working_day": False,
        "reason": "weekend",
    }
    assert client.get("/api/v1/calendar/days/2026-11-02").json() == {
        "date": "2026-11-02",
        "working_day": True,
        "reason": None,
    }


def test_half_day_eve_is_working_day_over_api(client):
    body = client.get("/api/v1/calendar/days/2026-10-28").json()
    assert body["working_day"] is True


def test_invalid_path_date_is_validation_error(client):
    error = assert_error(client.get("/api/v1/calendar/days/2026-02-30"), 422, "VALIDATION_ERROR")
    assert error["details"]["fields"][0]["field"] == "date"


# LIB-CORE-03, LIB-CORE-04
def test_next_working_day(client):
    response = client.get("/api/v1/calendar/next-working-day", params={"date": "2026-05-27"})
    assert response.status_code == 200
    assert response.json() == {"date": "2026-06-01"}


def test_add_working_days(client):
    response = client.get(
        "/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 2}
    )
    assert response.json() == {"date": "2026-11-02"}


@pytest.mark.parametrize("days", [0, 366, -1])
def test_add_working_days_out_of_range(client, days):
    response = client.get(
        "/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": days}
    )
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert error["details"]["fields"][0]["field"] == "days"


def test_add_working_days_accepts_365(client):
    response = client.get(
        "/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 365}
    )
    assert response.status_code == 200


# LIB-CORE-05
def test_working_days_between(client):
    response = client.get(
        "/api/v1/calendar/working-days-between",
        params={"start": "2026-06-01", "end": "2026-06-05"},
    )
    assert response.json() == {"working_days": 4}


def test_working_days_between_end_before_start_is_zero(client):
    response = client.get(
        "/api/v1/calendar/working-days-between",
        params={"start": "2026-06-05", "end": "2026-06-01"},
    )
    assert response.json() == {"working_days": 0}


def test_working_days_between_span_limit(client):
    start = datetime.date(2000, 1, 1)
    at_limit = start + datetime.timedelta(days=3660)
    over_limit = start + datetime.timedelta(days=3661)
    ok = client.get(
        "/api/v1/calendar/working-days-between",
        params={"start": start.isoformat(), "end": at_limit.isoformat()},
    )
    assert ok.status_code == 200
    too_long = client.get(
        "/api/v1/calendar/working-days-between",
        params={"start": start.isoformat(), "end": over_limit.isoformat()},
    )
    error = assert_error(too_long, 422, "VALIDATION_ERROR")
    assert error["details"]["fields"][0]["field"] == "end"


# LIB-CORE-06
@pytest.mark.parametrize(
    ("path", "params", "field"),
    [
        ("/api/v1/calendar/next-working-day", {}, "date"),
        ("/api/v1/calendar/next-working-day", {"date": "27.05.2026"}, "date"),
        ("/api/v1/calendar/add-working-days", {"date": "2026-05-27"}, "days"),
        ("/api/v1/calendar/add-working-days", {"days": 2}, "date"),
        ("/api/v1/calendar/working-days-between", {"start": "2026-06-01"}, "end"),
        ("/api/v1/calendar/working-days-between", {"start": "x", "end": "2026-06-01"}, "start"),
    ],
)
def test_missing_or_unparseable_dates_name_the_parameter(client, path, params, field):
    error = assert_error(client.get(path, params=params), 422, "VALIDATION_ERROR")
    assert field in {f["field"] for f in error["details"]["fields"]}


def test_calendar_is_public(client):
    # No Authorization header is needed; the response is 200, not 401.
    assert client.get("/api/v1/calendar/days/2026-11-02").status_code == 200


# LIB-API-02 and LIB-COM-25
def test_unknown_path_uses_error_format(client):
    assert_error(client.get("/api/v1/nothing-here"), 404, "NOT_FOUND")


def test_unsupported_method_uses_error_format(client):
    assert_error(client.post("/api/v1/calendar/days/2026-11-02"), 405, "METHOD_NOT_ALLOWED")


# LIB-CORE-09, LIB-COM-27
def test_unexpected_error_hides_details(app, client):
    def boom():
        raise RuntimeError("secret database password")

    app.add_api_route("/boom", boom)
    response = client.get("/boom")
    error = assert_error(response, 500, "INTERNAL_ERROR")
    assert error["details"] == {}
    assert "secret" not in response.text


# LIB-API-04, LIB-TECH-06
def test_openapi_lists_every_core_endpoint(client):
    schema = client.get("/openapi.json").json()
    for path in CALENDAR_PATHS:
        assert path in schema["paths"], path
    assert "/health" in schema["paths"]


def test_endpoints_are_synchronous(app):
    for route in app.routes:
        if isinstance(route, APIRoute):
            assert not inspect.iscoroutinefunction(route.endpoint), route.path


# LIB-TECH-08
def test_failed_request_leaves_no_changes(app, client):
    def write_then_fail(session: Session = Depends(get_session)):
        session.add(Probe(name="written"))
        session.flush()
        raise ApiError(409, "BUSINESS_RULE_VIOLATION", "Nope.")

    def write_and_succeed(session: Session = Depends(get_session)):
        session.add(Probe(name="kept"))
        return {"ok": True}

    app.add_api_route("/probe/fail", write_then_fail, methods=["POST"])
    app.add_api_route("/probe/ok", write_and_succeed, methods=["POST"])

    assert_error(client.post("/probe/fail"), 409, "BUSINESS_RULE_VIOLATION")
    assert client.post("/probe/ok").status_code == 200

    with app.state.session_factory() as session:
        names = session.scalars(select(Probe.name)).all()
    assert names == ["kept"]


# LIB-IF-05
def test_in_memory_database_is_shared_by_requests(app, client):
    def add(session: Session = Depends(get_session)):
        session.add(Probe(name="shared"))
        return {}

    def read(session: Session = Depends(get_session)):
        return {"names": list(session.scalars(select(Probe.name)).all())}

    app.add_api_route("/probe/add", add, methods=["POST"])
    app.add_api_route("/probe/read", read, methods=["GET"])
    client.post("/probe/add")
    assert client.get("/probe/read").json() == {"names": ["shared"]}


# LIB-IF-02, LIB-IF-03
def test_creating_apps_twice_on_one_file_database_is_fine(tmp_path):
    url = f"sqlite:///{tmp_path / 'lms.db'}"
    create_app(Settings(database_url=url))
    create_app(Settings(database_url=url))


def test_applications_with_different_databases_share_no_state(tmp_path):
    first = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'a.db'}"))
    second = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'b.db'}"))

    with first.state.session_factory() as session:
        session.add(Probe(name="only in a"))
        session.commit()
    with second.state.session_factory() as session:
        assert session.scalars(select(Probe)).all() == []


# LIB-COM-18 to LIB-COM-20
def test_pagination_helper(app):
    with app.state.session_factory() as session:
        session.add_all([Probe(name=f"p{i}") for i in range(1, 58)])
        session.commit()

        statement = select(Probe).order_by(Probe.id)
        items, total = paginate(session, statement, page=1, page_size=20)
        assert total == 57
        assert [p.name for p in items][:2] == ["p1", "p2"]
        assert len(items) == 20

        items, total = paginate(session, statement, page=3, page_size=20)
        assert [p.name for p in items] == [f"p{i}" for i in range(41, 58)]

        items, total = paginate(session, statement, page=4, page_size=20)
        assert items == [] and total == 57


def test_page_parameters_are_validated(app):
    # Pagination parameters are validated by the endpoint that declares them, so
    # the shared bounds are checked through a probe route that uses them.
    def listing(
        page: int = Query(1, ge=1),
        page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    ):
        return {"page": page, "page_size": page_size}

    app.add_api_route("/probe/list", listing)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/probe/list").json() == {"page": 1, "page_size": 20}
    assert_error(client.get("/probe/list", params={"page": 0}), 422, "VALIDATION_ERROR")
    assert_error(client.get("/probe/list", params={"page_size": 101}), 422, "VALIDATION_ERROR")
    assert client.get("/probe/list", params={"page_size": 100}).status_code == 200
