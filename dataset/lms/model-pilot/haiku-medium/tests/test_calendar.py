import pytest


def test_holidays_of_2026_ordered_with_names(client):
    body = client.get("/api/v1/calendar/holidays", params={"year": 2026}).json()
    assert body["year"] == 2026
    dates = [h["date"] for h in body["holidays"]]
    assert dates == sorted(dates)
    assert body["holidays"][0] == {"date": "2026-01-01", "name": "New Year's Day"}
    assert len(body["holidays"]) == 14


def test_holidays_of_year_without_entries_is_empty(client):
    response = client.get("/api/v1/calendar/holidays", params={"year": 1950})
    assert response.status_code == 200
    assert response.json() == {"year": 1950, "holidays": []}


@pytest.mark.parametrize("year", ["1899", "2101", "abc"])
def test_holidays_year_out_of_range_is_422(client, year):
    response = client.get("/api/v1/calendar/holidays", params={"year": year})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["fields"][0]["field"] == "year"


@pytest.mark.parametrize(
    "day, working, reason",
    [
        ("2026-10-29", False, "holiday"),  # Thursday holiday
        ("2026-10-31", False, "weekend"),  # Saturday
        ("2026-08-30", False, "holiday"),  # Sunday that is also a holiday
        ("2026-10-28", True, None),  # half-day eve is a working day
        ("2026-03-24", True, None),
    ],
)
def test_check_day(client, day, working, reason):
    body = client.get(f"/api/v1/calendar/days/{day}").json()
    assert body == {"date": day, "working_day": working, "reason": reason}


def test_check_day_rejects_malformed_date(client):
    response = client.get("/api/v1/calendar/days/2026-02-30")
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"][0]["field"] == "date"


@pytest.mark.parametrize(
    "start, expected",
    [("2026-05-27", "2026-06-01"), ("2026-03-24", "2026-03-24"), ("2027-01-01", "2027-01-04")],
)
def test_next_working_day(client, start, expected):
    response = client.get("/api/v1/calendar/next-working-day", params={"date": start})
    assert response.status_code == 200
    assert response.json() == {"date": expected}


@pytest.mark.parametrize(
    "start, days, expected",
    [("2026-10-28", 2, "2026-11-02"), ("2026-05-26", 2, "2026-06-02")],
)
def test_add_working_days(client, start, days, expected):
    response = client.get(
        "/api/v1/calendar/add-working-days", params={"date": start, "days": days}
    )
    assert response.status_code == 200
    assert response.json() == {"date": expected}


@pytest.mark.parametrize("days", [0, 366])
def test_add_working_days_bounds(client, days):
    response = client.get(
        "/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": days}
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("2026-06-01", "2026-06-05", 4),
        ("2026-10-23", "2026-10-26", 1),
        ("2026-10-27", "2026-10-30", 2),
        ("2026-06-05", "2026-06-01", 0),
        ("2026-06-05", "2026-06-05", 0),
    ],
)
def test_working_days_between(client, start, end, expected):
    response = client.get(
        "/api/v1/calendar/working-days-between", params={"start": start, "end": end}
    )
    assert response.status_code == 200
    assert response.json() == {"working_days": expected}


def test_working_days_between_span_limit(client):
    ok = client.get(
        "/api/v1/calendar/working-days-between",
        params={"start": "2000-01-01", "end": "2010-01-01"},
    )
    assert ok.status_code == 200
    too_long = client.get(
        "/api/v1/calendar/working-days-between",
        params={"start": "2000-01-01", "end": "2010-12-31"},
    )
    assert too_long.status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/calendar/next-working-day",
        "/api/v1/calendar/add-working-days?date=2026-10-28",
        "/api/v1/calendar/working-days-between?start=2026-06-01",
        "/api/v1/calendar/next-working-day?date=2026-13-01",
        "/api/v1/calendar/next-working-day?date=20261028",
    ],
)
def test_missing_or_bad_date_parameters_are_422(client, url):
    response = client.get(url)
    error = response.json()["error"]
    assert response.status_code == 422
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["fields"]


def test_calendar_needs_no_authentication(client):
    assert client.get("/api/v1/calendar/days/2026-11-05").status_code == 200
