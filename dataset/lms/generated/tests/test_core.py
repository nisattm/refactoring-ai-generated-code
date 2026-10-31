import datetime
import hashlib

import pytest
import sqlalchemy as sa
from fastapi import APIRouter
from fastapi.testclient import TestClient
from hypothesis import given, strategies as st

import lms
from lms.core import calendar as cal
from lms.core.money import MoneyType, Money, quantize, format_amount
from lms.core.text import normalize
from lms.core.timeutil import format_datetime

TZ = datetime.timezone(datetime.timedelta(hours=3))
D = datetime.date


def err(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)
    return body["error"]


# --- interface -------------------------------------------------------------

def test_exports():
    assert set(lms.__all__) == {
        "create_app", "Settings", "Clock", "SystemClock", "FixedClock", "DEFAULT_HOLIDAYS", "import_dataset", "export_dataset",
    }
    assert len(lms.DEFAULT_HOLIDAYS) == 27


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "today": "2026-11-02"}


def test_health_follows_clock_and_local_date(client, clock):
    clock.set(datetime.datetime(2026, 11, 2, 22, 0, tzinfo=datetime.timezone.utc))  # 01:00 next day local
    assert client.get("/health").json()["today"] == "2026-11-03"
    clock.advance(days=1)
    assert client.get("/health").json()["today"] == "2026-11-04"


def test_clock_rules():
    with pytest.raises(ValueError):
        lms.FixedClock(datetime.datetime(2026, 1, 1))
    c = lms.FixedClock(datetime.datetime(2026, 1, 1, tzinfo=TZ))
    with pytest.raises(ValueError):
        c.set(datetime.datetime(2026, 1, 1))
    c.advance(days=1, hours=2, minutes=3)
    assert c.now() == datetime.datetime(2026, 1, 2, 2, 3, tzinfo=TZ)
    now = lms.SystemClock().now()
    assert now.utcoffset() == datetime.timedelta(hours=3)


@pytest.mark.parametrize("ttl", [0, 169, -1, True])
def test_ttl_validation(ttl):
    with pytest.raises(ValueError):
        lms.Settings(token_ttl_hours=ttl)


@pytest.mark.parametrize("ttl", [1, 12, 168])
def test_ttl_ok(ttl):
    assert lms.Settings(token_ttl_hours=ttl).token_ttl_hours == ttl


# --- bootstrap admin / database -----------------------------------------------

def test_bootstrap_admin_once(tmp_path, clock):
    url = f"sqlite:///{tmp_path}/t.db"
    s = lms.Settings(database_url=url, clock=clock, bootstrap_admin_email="Boss@Library.Local")
    app1 = lms.create_app(s)
    lms.create_app(s)
    from lms.auth.models import User
    with app1.state.session_factory() as session:
        users = session.scalars(sa.select(User)).all()
    assert len(users) == 1
    u = users[0]
    assert (u.id, u.email, u.role, u.full_name, u.is_active) == (1, "boss@library.local", "admin", "Administrator", True)
    scheme, salt, digest = u.password_hash.split("$")
    assert scheme == "scrypt" and len(bytes.fromhex(salt)) == 16
    assert hashlib.scrypt(b"ChangeMe123", salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=64).hex() == digest
    assert u.created_at == clock.now()


def test_apps_do_not_share_state(clock):
    a = lms.create_app(lms.Settings(database_url="sqlite://", clock=clock))
    b = lms.create_app(lms.Settings(database_url="sqlite://", clock=clock, bootstrap_admin_email="b@x.io"))
    from lms.auth.models import User
    with a.state.session_factory() as s:
        assert s.scalar(sa.select(User.email)) == "admin@library.local"
    with b.state.session_factory() as s:
        assert s.scalar(sa.select(User.email)) == "b@x.io"


def test_money_and_datetime_storage(app):
    from lms.core.db import Base
    t = sa.Table("tmp_money", sa.MetaData(), sa.Column("id", sa.Integer, primary_key=True), sa.Column("m", MoneyType))
    with app.state.engine.begin() as c:
        t.create(c)
        c.execute(t.insert().values(m=quantize("0.125")))
        c.execute(t.insert().values(m=sa.literal(None)))
        assert c.execute(sa.text("select typeof(m), m from tmp_money where id=1")).one() == ("integer", 13)
        assert c.execute(sa.select(t.c.m).where(t.c.id == 1)).scalar() == __import__("decimal").Decimal("0.13")


# --- money / text -------------------------------------------------------------

def test_money_rounding():
    assert format_amount(quantize("0.125")) == "0.13"
    assert format_amount(quantize("2.675")) == "2.68"
    assert format_amount(quantize("0")) == "0.00"
    assert format_amount(quantize("12.5")) == "12.50"


def test_money_model():
    from pydantic import BaseModel, ValidationError

    class M(BaseModel):
        a: Money

    assert M(a="12.5").a == __import__("decimal").Decimal("12.50")
    assert M(a="-3").a < 0
    assert M(a="1").model_dump(mode="json") == {"a": "1.00"}
    for bad in (12.5, 12, "1.234", "abc", "", "1e3", None):
        with pytest.raises(ValidationError):
            M(a=bad)


def test_normalize():
    assert normalize("ISTANBUL") == normalize("İstanbul") == normalize("istanbul") == "istanbul"
    assert normalize("Işık") == "işik" == normalize("IŞIK")
    assert normalize("Işık") != "isik"


def test_format_datetime():
    assert format_datetime(datetime.datetime(2026, 11, 2, 6, 30, tzinfo=datetime.timezone.utc)) == "2026-11-02T09:30:00+03:00"


# --- calendar logic ---------------------------------------------------------------

H = lms.DEFAULT_HOLIDAYS


def test_calendar_examples():
    assert cal.next_working_day(D(2026, 5, 27), H) == D(2026, 6, 1)
    assert cal.next_working_day(D(2026, 3, 24), H) == D(2026, 3, 24)
    assert cal.next_working_day(D(2027, 1, 1), H) == D(2027, 1, 4)
    assert cal.add_working_days(D(2026, 10, 28), 2, H) == D(2026, 11, 2)
    assert cal.add_working_days(D(2026, 5, 26), 2, H) == D(2026, 6, 2)
    assert cal.working_days_between(D(2026, 6, 1), D(2026, 6, 5), H) == 4
    assert cal.working_days_between(D(2026, 10, 23), D(2026, 10, 26), H) == 1
    assert cal.working_days_between(D(2026, 10, 27), D(2026, 10, 30), H) == 2


def test_arife_are_working_days():
    for d in (D(2026, 3, 19), D(2026, 5, 26), D(2026, 10, 28), D(2027, 3, 8), D(2027, 5, 15), D(2027, 10, 28)):
        if d.weekday() < 5:
            assert cal.is_working_day(d, H)


@given(st.dates(D(2020, 1, 1), D(2030, 12, 31)), st.integers(1, 60))
def test_add_between_roundtrip(d, n):
    r = cal.add_working_days(d, n, H)
    assert cal.is_working_day(r, H)
    assert cal.working_days_between(d, r, H) == n


# --- calendar endpoints -----------------------------------------------------------

def test_holidays_endpoint(client):
    r = client.get("/api/v1/calendar/holidays", params={"year": 2026})
    assert r.status_code == 200
    body = r.json()
    assert body["year"] == 2026 and len(body["holidays"]) == 14
    assert body["holidays"][0] == {"date": "2026-01-01", "name": "New Year's Day"}
    dates = [h["date"] for h in body["holidays"]]
    assert dates == sorted(dates)
    r27 = client.get("/api/v1/calendar/holidays?year=2027").json()["holidays"]
    assert r27[-4]["name"] == "Kurban Bayramı, day 4; Commemoration of Atatürk, Youth and Sports Day"
    assert client.get("/api/v1/calendar/holidays?year=2030").json() == {"year": 2030, "holidays": []}
    assert client.get("/api/v1/calendar/holidays?year=1900").status_code == 200
    assert client.get("/api/v1/calendar/holidays?year=2100").status_code == 200


@pytest.mark.parametrize("q", ["year=1899", "year=2101", "year=abc", "", "year="])
def test_holidays_invalid(client, q):
    e = err(client.get(f"/api/v1/calendar/holidays?{q}"), 422, "VALIDATION_ERROR")
    assert [f["field"] for f in e["details"]["fields"]] == ["year"]


def test_custom_holidays():
    s = lms.Settings(database_url="sqlite://", holidays=frozenset({D(2026, 11, 3)}))
    c = TestClient(lms.create_app(s))
    assert c.get("/api/v1/calendar/days/2026-11-03").json() == {"date": "2026-11-03", "working_day": False, "reason": "holiday"}
    assert c.get("/api/v1/calendar/days/2026-10-29").json()["working_day"] is True
    assert c.get("/api/v1/calendar/next-working-day?date=2026-11-03").json() == {"date": "2026-11-04"}


def test_days_endpoint(client):
    g = lambda d: client.get(f"/api/v1/calendar/days/{d}").json()
    assert g("2026-10-29") == {"date": "2026-10-29", "working_day": False, "reason": "holiday"}
    assert g("2026-10-31") == {"date": "2026-10-31", "working_day": False, "reason": "weekend"}
    assert g("2026-11-02") == {"date": "2026-11-02", "working_day": True, "reason": None}
    assert g("2026-03-21")["reason"] == "holiday"  # holiday and Saturday
    assert g("2026-05-26")["working_day"] is True
    assert g("1850-01-02")["working_day"] is True  # outside the list: weekends only


@pytest.mark.parametrize("d", ["2026-02-30", "abc", "2026-1-1", "20261029", "2026-10-29T00:00:00"])
def test_days_invalid(client, d):
    e = err(client.get(f"/api/v1/calendar/days/{d}"), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "date"


def test_next_working_day(client):
    assert client.get("/api/v1/calendar/next-working-day?date=2026-05-27").json() == {"date": "2026-06-01"}
    assert client.get("/api/v1/calendar/next-working-day?date=2027-01-01").json() == {"date": "2027-01-04"}
    e = err(client.get("/api/v1/calendar/next-working-day"), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "date"
    err(client.get("/api/v1/calendar/next-working-day?date=nope"), 422, "VALIDATION_ERROR")


def test_add_working_days(client):
    u = "/api/v1/calendar/add-working-days"
    assert client.get(f"{u}?date=2026-10-28&days=2").json() == {"date": "2026-11-02"}
    assert client.get(f"{u}?date=2026-05-26&days=2").json() == {"date": "2026-06-02"}
    assert client.get(f"{u}?date=2026-11-02&days=365").status_code == 200
    for q in ("date=2026-10-28&days=0", "date=2026-10-28&days=366", "date=2026-10-28&days=x", "date=2026-10-28", "days=2"):
        err(client.get(f"{u}?{q}"), 422, "VALIDATION_ERROR")
    e = err(client.get(f"{u}?date=bad&days=0"), 422, "VALIDATION_ERROR")
    assert sorted(f["field"] for f in e["details"]["fields"]) == ["date", "days"]
    err(client.get(f"{u}?date=9999-12-30&days=5"), 422, "VALIDATION_ERROR")


def test_working_days_between(client):
    u = "/api/v1/calendar/working-days-between"
    assert client.get(f"{u}?start=2026-06-01&end=2026-06-05").json() == {"working_days": 4}
    assert client.get(f"{u}?start=2026-10-23&end=2026-10-26").json() == {"working_days": 1}
    assert client.get(f"{u}?start=2026-10-27&end=2026-10-30").json() == {"working_days": 2}
    assert client.get(f"{u}?start=2026-06-05&end=2026-06-01").json() == {"working_days": 0}
    assert client.get(f"{u}?start=2026-06-05&end=2026-06-05").json() == {"working_days": 0}
    start = D(2026, 1, 1)
    assert client.get(f"{u}?start={start}&end={start + datetime.timedelta(days=3660)}").status_code == 200
    err(client.get(f"{u}?start={start}&end={start + datetime.timedelta(days=3661)}"), 422, "VALIDATION_ERROR")
    e = err(client.get(f"{u}?start=x"), 422, "VALIDATION_ERROR")
    assert sorted(f["field"] for f in e["details"]["fields"]) == ["end", "start"]


def test_calendar_public(client):
    # No Authorization header needed, and a bogus one is ignored.
    r = client.get("/api/v1/calendar/days/2026-11-02", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 200


# --- error handling -----------------------------------------------------------------

def test_unknown_path_and_method(client):
    err(client.get("/api/v1/nope"), 404, "NOT_FOUND")
    err(client.get("/nope"), 404, "NOT_FOUND")
    err(client.post("/api/v1/calendar/holidays"), 405, "METHOD_NOT_ALLOWED")
    err(client.post("/health"), 405, "METHOD_NOT_ALLOWED")
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_openapi(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in ("/health", "/api/v1/calendar/holidays", "/api/v1/calendar/days/{day}",
              "/api/v1/calendar/next-working-day", "/api/v1/calendar/add-working-days",
              "/api/v1/calendar/working-days-between"):
        assert p in paths


def test_internal_error_and_transaction_rollback(app, client):
    from lms.auth.models import User
    from lms.core.db import SessionDep
    from lms.core.errors import Conflict, ValidationFailed, reference_not_found

    router = APIRouter()

    @router.post("/boom")
    def boom(session: SessionDep):
        session.add(User(email="a@b.c", email_key="a@b.c", full_name="x", role="librarian", password_hash="x",
                         created_at=app.state.settings.clock.now()))
        session.flush()
        raise RuntimeError("secret internals")

    @router.post("/conflict")
    def conflict(session: SessionDep):
        session.add(User(email="c@b.c", email_key="c@b.c", full_name="x", role="librarian", password_hash="x",
                         created_at=app.state.settings.clock.now()))
        session.flush()
        raise Conflict("dup", details={"field": "email"})

    @router.post("/ok")
    def ok(session: SessionDep):
        session.add(User(email="d@b.c", email_key="d@b.c", full_name="x", role="librarian", password_hash="x",
                         created_at=app.state.settings.clock.now()))
        return {}

    @router.get("/ref")
    def ref():
        raise reference_not_found("member_id", 99)

    @router.get("/val")
    def val():
        raise ValidationFailed.single("x", "bad")

    app.include_router(router)
    e = err(client.post("/boom"), 500, "INTERNAL_ERROR")
    assert "secret" not in str(e) and "Traceback" not in str(e)
    e = err(client.post("/conflict"), 409, "CONFLICT")
    assert e["details"] == {"field": "email"}
    assert client.post("/ok").status_code == 200
    with app.state.session_factory() as s:
        assert sorted(s.scalars(sa.select(User.email)).all()) == ["admin@library.local", "d@b.c"]
    assert err(client.get("/ref"), 404, "NOT_FOUND")["details"] == {"field": "member_id", "id": 99}
    assert err(client.get("/val"), 422, "VALIDATION_ERROR")["details"]["fields"] == [{"field": "x", "problem": "bad"}]


def test_request_validation_fields_and_pagination(app, client):
    from pydantic import Field
    from lms.core.pagination import PageDep, paginate_sequence
    from lms.core.schemas import RequestModel

    class Body(RequestModel):
        name: str = Field(min_length=1)
        nested: dict[str, int] | None = None

    router = APIRouter()

    @router.post("/echo")
    def echo(body: Body):
        return {"name": body.name}

    @router.get("/items")
    def items(p: PageDep):
        return paginate_sequence(list(range(1, 58)), p)

    app.include_router(router)
    assert client.post("/echo", json={"name": "  Ada  "}).json() == {"name": "Ada"}
    e = err(client.post("/echo", json={"name": "  "}), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "name"
    e = err(client.post("/echo", json={"name": "x", "extra": 1}), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "extra"
    e = err(client.post("/echo", json={"name": "x", "nested": {"a": "z"}}), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "nested.a"

    body = client.get("/items").json()
    assert body == {"items": list(range(1, 21)), "page": 1, "page_size": 20, "total": 57}
    assert client.get("/items?page=3&page_size=20").json()["items"] == list(range(41, 58))
    assert client.get("/items?page=9").json() == {"items": [], "page": 9, "page_size": 20, "total": 57}
    for q in ("page=0", "page_size=0", "page_size=101", "page=x"):
        err(client.get(f"/items?{q}"), 422, "VALIDATION_ERROR")


def test_paginate_query(app):
    from lms.auth.models import User
    from lms.core.pagination import PageParams, paginate
    with app.state.session_factory() as s:
        page = paginate(s, sa.select(User).order_by(User.id), PageParams(page=1, page_size=5), lambda u: u.id)
    assert (page.items, page.total) == ([1], 1)
