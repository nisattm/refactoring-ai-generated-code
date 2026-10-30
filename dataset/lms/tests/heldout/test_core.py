"""Heldout tests: module 1 (Core), technical constraints, common rules and fixed interface. Generated from cases/core.md."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import lms
from support.api import (
    D, add_copy, create_book, create_branch, error_code, lend, login, register_member,
)

TR = timezone(timedelta(hours=3))


def file_settings(tmp_path, clock, name="lms.db", **kw):
    return lms.Settings(database_url=f"sqlite:///{tmp_path / name}", clock=clock, **kw)


def user_payload(**kw):
    data = {"email": "x1@library.local", "full_name": "Staff One", "role": "librarian", "password": "Passw0rd1"}
    data.update(kw)
    return data


def test_t_tech_08_b(client, librarian):
    """T-TECH-08-b (LIB-TECH-08): The failures are kept: the account is locked (exception to rollback)"""
    for _ in range(5):
        login(client, "lib@library.local", "Wrong0000", expect=401)
    r = client.post("/api/v1/auth/login", json={"email": "lib@library.local", "password": "Librarian123"})
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"


def test_t_com_02_a(client, clock):
    """T-COM-02-a (LIB-COM-02): today 2026-11-02, then 2026-11-03"""
    clock.set(datetime(2026, 11, 2, 23, 59, tzinfo=TR))
    assert client.get("/health").json()["today"] == "2026-11-02"
    clock.advance(minutes=1)
    assert client.get("/health").json()["today"] == "2026-11-03"


def test_t_com_04_a(client):
    """T-COM-04-a (LIB-COM-04): 422 VALIDATION_ERROR"""
    r = client.get("/api/v1/calendar/days/2026-02-30")
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_t_com_06_b(client):
    """T-COM-06-b (LIB-COM-06): Both are working days"""
    for d in ("2026-10-28", "2027-03-08"):
        assert client.get(f"/api/v1/calendar/days/{d}").json()["working_day"] is True


def test_t_com_08_b(client):
    """T-COM-08-b (LIB-COM-08): 2026-03-24; 2027-01-04"""
    assert client.get("/api/v1/calendar/next-working-day", params={"date": "2026-03-24"}).json() == {"date": "2026-03-24"}
    assert client.get("/api/v1/calendar/next-working-day", params={"date": "2027-01-01"}).json() == {"date": "2027-01-04"}


def test_t_com_09_b(client):
    """T-COM-09-b (LIB-COM-09): 2026-06-02; 2026-11-09"""
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-05-26", "days": 2}).json() == {"date": "2026-06-02"}
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-11-06", "days": 1}).json() == {"date": "2026-11-09"}


def test_t_com_10_b(client):
    """T-COM-10-b (LIB-COM-10): 1; 2"""
    q = lambda s, e: client.get("/api/v1/calendar/working-days-between", params={"start": s, "end": e}).json()["working_days"]
    assert q("2026-10-23", "2026-10-26") == 1
    assert q("2026-10-27", "2026-10-30") == 2


def test_t_com_13_b(client, librarian, branch_a):
    """T-COM-13-b (LIB-COM-13): 422 VALIDATION_ERROR"""
    book = create_book(client, librarian)
    r = client.post(f"/api/v1/books/{book['id']}/copies", headers=librarian, json={
        "barcode": "NUM-0001", "home_branch_id": branch_a["id"], "price": 100, "acquired_on": "2026-11-01"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_t_com_14_a(client, admin):
    """T-COM-14-a (LIB-COM-14): ids 1 and 2"""
    assert create_branch(client, admin, "X")["id"] == 1
    assert create_branch(client, admin, "Y")["id"] == 2


def test_t_com_15_b(client, admin):
    """T-COM-15-b (LIB-COM-15): 422 VALIDATION_ERROR"""
    create_branch(client, admin, "D", name="   ", expect=422)


def test_t_com_16_b(client, admin):
    """T-COM-16-b (LIB-COM-16): 422 VALIDATION_ERROR"""
    r = client.post("/api/v1/users", headers=admin, json=user_payload(full_name="a" * 201))
    assert r.status_code == 422


def test_t_com_17_b(client, admin):
    """T-COM-17-b (LIB-COM-17): 422 VALIDATION_ERROR each"""
    for bad in ("a@b", "@x.com", "a@@x.com"):
        r = client.post("/api/v1/users", headers=admin, json=user_payload(email=bad))
        assert r.status_code == 422, bad


def test_t_com_18_b(client, admin):
    """T-COM-18-b (LIB-COM-18): page 1, page_size 20; 100 accepted"""
    body = client.get("/api/v1/users", headers=admin).json()
    assert body["page"] == 1 and body["page_size"] == 20
    assert client.get("/api/v1/users", headers=admin, params={"page_size": 100}).status_code == 200


def test_t_com_19_b(client, admin):
    """T-COM-19-b (LIB-COM-19): 200 with items []"""
    r = client.get("/api/v1/users", headers=admin, params={"page": 50})
    assert r.status_code == 200 and r.json()["items"] == []


def test_t_com_20_a(client, admin, librarian):
    """T-COM-20-a (LIB-COM-20): List ordered by id ascending"""
    for e in ("y@library.local", "x@library.local"):
        client.post("/api/v1/users", headers=admin, json=user_payload(email=e))
    ids = [u["id"] for u in client.get("/api/v1/users", headers=admin).json()["items"]]
    assert ids == sorted(ids)


def test_t_com_22_a(client, admin):
    """T-COM-22-a (LIB-COM-22): 201 with body; 200 with body; 204 without body"""
    r = client.post("/api/v1/users", headers=admin, json=user_payload())
    assert r.status_code == 201 and r.json()["email"] == "x1@library.local"
    r2 = client.patch(f"/api/v1/users/{r.json()['id']}", headers=admin, json={"full_name": "Renamed"})
    assert r2.status_code == 200 and r2.json()["full_name"] == "Renamed"
    r3 = client.post("/api/v1/auth/logout", headers=admin)
    assert r3.status_code == 204 and r3.content == b""


def test_t_com_24_a(client):
    """T-COM-24-a (LIB-COM-24): 401 UNAUTHENTICATED"""
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Token abc"})
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"


def test_t_com_26_a(client, admin):
    """T-COM-26-a (LIB-COM-26): details.fields names both fields"""
    data = user_payload(email="bad")
    del data["full_name"]
    fields = client.post("/api/v1/users", headers=admin, json=data).json()["error"]["details"]["fields"]
    names = {f["field"] for f in fields}
    assert {"email", "full_name"} <= names
    assert all(isinstance(f["problem"], str) for f in fields)


def test_t_com_28_b(client, librarian):
    """T-COM-28-b (LIB-COM-28): 403 FORBIDDEN (role before validation)"""
    r = client.post("/api/v1/users", headers=librarian, json={"email": "bad"})
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"


def test_t_com_30_b(client, admin):
    """T-COM-30-b (LIB-COM-30): The user is found"""
    client.post("/api/v1/users", headers=admin, json=user_payload(full_name="Işık Yılmaz"))
    items = client.get("/api/v1/users", headers=admin, params={"q": "ISIK"}).json()["items"]
    assert [u["full_name"] for u in items] == ["Işık Yılmaz"]


def test_t_if_02_a(tmp_path, clock):
    """T-IF-02-a (LIB-IF-02): No error; exactly one admin"""
    settings = file_settings(tmp_path, clock)
    lms.create_app(settings)
    client = TestClient(lms.create_app(settings))
    adm = login(client, "admin@library.local", "ChangeMe123")
    assert client.get("/api/v1/users", headers=adm, params={"role": "admin"}).json()["total"] == 1


def test_t_if_04_a():
    """T-IF-04-a (LIB-IF-04): 27 dates; contains 2026-10-29, not 2026-10-28"""
    assert len(lms.DEFAULT_HOLIDAYS) == 27
    assert date(2026, 10, 29) in lms.DEFAULT_HOLIDAYS and date(2026, 10, 28) not in lms.DEFAULT_HOLIDAYS


def test_t_if_06_b(clock):
    """T-IF-06-b (LIB-IF-06): Accepted"""
    for ok in (1, 168):
        lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=ok)


def test_t_if_08_a(clock):
    """T-IF-08-a (LIB-IF-08): ValueError both"""
    with pytest.raises(ValueError):
        lms.FixedClock(datetime(2026, 11, 2, 9, 0))
    with pytest.raises(ValueError):
        clock.set(datetime(2026, 11, 2, 9, 0))


def test_t_if_10_a(client):
    """T-IF-10-a (LIB-IF-10): 200 {'status': 'ok', 'today': '2026-11-02'}"""
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "today": "2026-11-02"}


def test_t_if_11_b(tmp_path, clock):
    """T-IF-11-b (LIB-IF-11): RuntimeError; ValueError"""
    settings = file_settings(tmp_path, clock)
    data = {"format_version": 1, "branches": [{"id": 1, "code": "MERKEZ", "name": "Central", "address": "", "is_active": True}],
            "authors": [], "publishers": [], "books": [], "copies": [], "members": [], "loans": []}
    with pytest.raises(ValueError):
        lms.import_dataset(file_settings(tmp_path, clock, name="other.db"), dict(data, format_version=2))
    lms.import_dataset(settings, data)
    with pytest.raises(RuntimeError):
        lms.import_dataset(settings, data)


def test_t_if_12_a(client, admin, settings):
    """T-IF-12-a (LIB-IF-12): Equal documents"""
    create_branch(client, admin, "A")
    assert lms.export_dataset(settings) == client.get("/api/v1/export", headers=admin).json()


def test_t_core_01_b(client):
    """T-CORE-01-b (LIB-CORE-01): Empty list; 422 for both"""
    assert client.get("/api/v1/calendar/holidays", params={"year": 2030}).json()["holidays"] == []
    for y in (1899, 2101):
        assert client.get("/api/v1/calendar/holidays", params={"year": y}).status_code == 422


def test_t_core_02_b(client):
    """T-CORE-02-b (LIB-CORE-02): reason 'holiday'"""
    assert client.get("/api/v1/calendar/days/2026-03-21").json()["reason"] == "holiday"


def test_t_core_04_b(client):
    """T-CORE-04-b (LIB-CORE-04): 422 for 0 and 366; 200 for 365"""
    for d in (0, 366):
        assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": d}).status_code == 422
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 365}).status_code == 200


def test_t_core_05_b(client):
    """T-CORE-05-b (LIB-CORE-05): 200; 422"""
    start = date(2026, 1, 1)
    ok = (start + timedelta(days=3660)).isoformat()
    bad = (start + timedelta(days=3661)).isoformat()
    assert client.get("/api/v1/calendar/working-days-between", params={"start": "2026-01-01", "end": ok}).status_code == 200
    assert client.get("/api/v1/calendar/working-days-between", params={"start": "2026-01-01", "end": bad}).status_code == 422


def test_t_core_06_a(client):
    """T-CORE-06-a (LIB-CORE-06): 422, details.fields contains end"""
    r = client.get("/api/v1/calendar/working-days-between", params={"start": "2026-06-01"})
    assert r.status_code == 422
    assert "end" in {f["field"] for f in r.json()["error"]["details"]["fields"]}


def test_t_core_10_a(client, librarian):
    """T-CORE-10-a (LIB-CORE-10): 422 VALIDATION_ERROR"""
    assert client.get("/api/v1/members", headers=librarian, params={"page_size": 101}).status_code == 422
