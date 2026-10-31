"""Feedback tests: module 1 (Core), technical constraints, common rules and fixed interface. Generated from cases/core.md."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _LazyLMS:
    """Imports lms at first use, so the tests can be collected before the code exists."""

    def __getattr__(self, name):
        import lms as real
        return getattr(real, name)


lms = _LazyLMS()
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


def test_t_tech_05_a(tmp_path, clock):
    """T-TECH-05-a (LIB-TECH-05): The SQLite file exists and holds the data after restarting the app"""
    settings = file_settings(tmp_path, clock)
    c1 = TestClient(lms.create_app(settings))
    adm = login(c1, "admin@library.local", "ChangeMe123")
    create_branch(c1, adm, "AA")
    assert (tmp_path / "lms.db").exists()
    c2 = TestClient(lms.create_app(settings))
    adm2 = login(c2, "admin@library.local", "ChangeMe123")
    codes = [b["code"] for b in c2.get("/api/v1/branches", headers=adm2).json()["items"]]
    assert codes == ["AA"]


def test_t_tech_07_a(tmp_path, clock):
    """T-TECH-07-a (LIB-TECH-07): create_app creates the schema; bootstrap admin can log in"""
    client = TestClient(lms.create_app(file_settings(tmp_path, clock, name="new.db")))
    login(client, "admin@library.local", "ChangeMe123")


def test_t_tech_08_a(client, librarian, admin, branch_a):
    """T-TECH-08-a (LIB-TECH-08): 409 CONFLICT; no user account with the new e-mail exists"""
    register_member(client, librarian, home_branch_id=branch_a["id"], university_id="U1001")
    r = client.post("/api/v1/members", headers=librarian, json={
        "full_name": "Second", "email": "second@uni.edu.tr", "membership_type": "student",
        "university_id": "U1001", "home_branch_id": branch_a["id"], "password": "Member1234"})
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
    users = client.get("/api/v1/users", headers=admin, params={"q": "second@uni.edu.tr"}).json()
    assert users["total"] == 0


def test_t_tech_09_a(client, clock):
    """T-TECH-09-a (LIB-TECH-09): /health reports today 2027-03-08 (the clock, not the system time)"""
    clock.set(datetime(2027, 3, 8, 10, 0, tzinfo=TR))
    assert client.get("/health").json()["today"] == "2027-03-08"


def test_t_com_01_a(client, clock):
    """T-COM-01-a (LIB-COM-01): today 2026-11-03"""
    clock.set(datetime(2026, 11, 2, 22, 30, tzinfo=timezone.utc))
    assert client.get("/health").json()["today"] == "2026-11-03"


def test_t_com_03_a(client, librarian):
    """T-COM-03-a (LIB-COM-03): expires_at '2026-11-02T21:00:00+03:00'"""
    r = client.post("/api/v1/auth/login", json={"email": "lib@library.local", "password": "Librarian123"})
    expires = datetime.fromisoformat(r.json()["expires_at"])
    assert expires.utcoffset() == timedelta(hours=3)
    assert expires == datetime(2026, 11, 2, 21, 0, tzinfo=TR)


def test_t_com_05_a(client):
    """T-COM-05-a (LIB-COM-05): Not a working day (weekend); working day"""
    sat = client.get("/api/v1/calendar/days/2026-11-07").json()
    mon = client.get("/api/v1/calendar/days/2026-11-09").json()
    assert sat == {"date": "2026-11-07", "working_day": False, "reason": "weekend"}
    assert mon == {"date": "2026-11-09", "working_day": True, "reason": None}


def test_t_com_06_a(client):
    """T-COM-06-a (LIB-COM-06): The 14 dates of the 2026 table, in order"""
    got = [h["date"] for h in client.get("/api/v1/calendar/holidays", params={"year": 2026}).json()["holidays"]]
    assert got == ["2026-01-01", "2026-03-20", "2026-03-21", "2026-03-22", "2026-04-23", "2026-05-01",
                   "2026-05-19", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30", "2026-07-15",
                   "2026-08-30", "2026-10-29"]


def test_t_com_07_a(client):
    """T-COM-07-a (LIB-COM-07): Working day"""
    assert client.get("/api/v1/calendar/days/2028-05-01").json()["working_day"] is True


def test_t_com_08_a(client):
    """T-COM-08-a (LIB-COM-08): 2026-06-01"""
    assert client.get("/api/v1/calendar/next-working-day", params={"date": "2026-05-27"}).json() == {"date": "2026-06-01"}


def test_t_com_09_a(client):
    """T-COM-09-a (LIB-COM-09): 2026-11-02"""
    r = client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 2})
    assert r.json() == {"date": "2026-11-02"}


def test_t_com_10_a(client):
    """T-COM-10-a (LIB-COM-10): 4"""
    r = client.get("/api/v1/calendar/working-days-between", params={"start": "2026-06-01", "end": "2026-06-05"})
    assert r.json() == {"working_days": 4}


def test_t_com_10_c(client):
    """T-COM-10-c (LIB-COM-10): 0; 0"""
    q = lambda s, e: client.get("/api/v1/calendar/working-days-between", params={"start": s, "end": e}).json()["working_days"]
    assert q("2026-11-02", "2026-11-02") == 0
    assert q("2026-11-05", "2026-11-02") == 0


def test_t_com_11_a(client, librarian, branch_a):
    """T-COM-11-a (LIB-COM-11): '0.10' exactly (no float artefacts)"""
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="0.10")
    assert client.get(f"/api/v1/copies/{copy['id']}", headers=librarian).json()["price"] == "0.10"


def test_t_com_13_a(client, librarian, branch_a):
    """T-COM-13-a (LIB-COM-13): Response amount is the string '100.00'"""
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="100.00")
    assert copy["price"] == "100.00" and isinstance(copy["price"], str)


def test_t_com_13_c(client, librarian, branch_a):
    """T-COM-13-c (LIB-COM-13): 422 VALIDATION_ERROR"""
    book = create_book(client, librarian)
    add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="1.005", expect=422)


def test_t_com_15_a(client, admin):
    """T-COM-15-a (LIB-COM-15): Stored and returned as 'Central'"""
    assert create_branch(client, admin, "CC", name="  Central  ")["name"] == "Central"


def test_t_com_16_a(client, admin):
    """T-COM-16-a (LIB-COM-16): Accepted"""
    r = client.post("/api/v1/users", headers=admin, json=user_payload(full_name="a" * 200))
    assert r.status_code == 201


def test_t_com_17_a(client, admin):
    """T-COM-17-a (LIB-COM-17): Stored and returned as 'new.staff@library.local'"""
    r = client.post("/api/v1/users", headers=admin, json=user_payload(email="New.Staff@Library.Local"))
    assert r.json()["email"] == "new.staff@library.local"


def test_t_com_18_a(client, admin):
    """T-COM-18-a (LIB-COM-18): 422 VALIDATION_ERROR both"""
    assert client.get("/api/v1/users", headers=admin, params={"page_size": 101}).status_code == 422
    assert client.get("/api/v1/users", headers=admin, params={"page": 0}).status_code == 422


def test_t_com_19_a(client, admin, librarian):
    """T-COM-19-a (LIB-COM-19): 10 items, total 27 (admin + librarian + 25)"""
    for i in range(25):
        client.post("/api/v1/users", headers=admin, json=user_payload(email=f"s{i}@library.local"))
    body = client.get("/api/v1/users", headers=admin, params={"page": 2, "page_size": 10}).json()
    assert set(body) >= {"items", "page", "page_size", "total"}
    assert len(body["items"]) == 10 and body["total"] == 27 and body["page"] == 2


def test_t_com_21_a(client, admin):
    """T-COM-21-a (LIB-COM-21): 404 NOT_FOUND in the error format"""
    r = client.get("/users", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"


def test_t_com_23_a(client, admin):
    """T-COM-23-a (LIB-COM-23): 422 VALIDATION_ERROR"""
    r = client.post("/api/v1/users", headers=admin, json=user_payload(nickname="x"))
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_t_com_25_a(client, admin):
    """T-COM-25-a (LIB-COM-25): Body {'error': {'code', 'message', 'details'}} with details an object"""
    err = client.get("/api/v1/users/9999", headers=admin).json()["error"]
    assert err["code"] == "NOT_FOUND" and isinstance(err["message"], str) and isinstance(err["details"], dict)


def test_t_com_28_a(client):
    """T-COM-28-a (LIB-COM-28): 401 (authentication first)"""
    r = client.post("/api/v1/users", json={"email": "bad"})
    assert r.status_code == 401


def test_t_com_28_c(client, admin):
    """T-COM-28-c (LIB-COM-28): 422 (validation before existence); then 404"""
    assert client.patch("/api/v1/users/9999", headers=admin, json={"role": "boss"}).status_code == 422
    r = client.patch("/api/v1/users/9999", headers=admin, json={"full_name": "N"})
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"


def test_t_com_29_a(client, librarian):
    """T-COM-29-a (LIB-COM-29): 404 NOT_FOUND, details {'field': 'home_branch_id', 'id': 999}"""
    r = client.post("/api/v1/members", headers=librarian, json={
        "full_name": "M", "email": "m@uni.edu.tr", "membership_type": "student",
        "university_id": "U2001", "home_branch_id": 999, "password": "Member1234"})
    assert r.status_code == 404
    assert r.json()["error"]["details"] == {"field": "home_branch_id", "id": 999}


def test_t_com_30_a(client, admin):
    """T-COM-30-a (LIB-COM-30): Second returns 409 CONFLICT"""
    assert client.post("/api/v1/users", headers=admin, json=user_payload(email="isik@library.local")).status_code == 201
    r = client.post("/api/v1/users", headers=admin, json=user_payload(email="ISIK@library.local"))
    assert r.status_code == 409 and error_code(r) == "CONFLICT"


def test_t_if_01_a(settings):
    """T-IF-01-a (LIB-IF-01): A FastAPI application"""
    assert isinstance(lms.create_app(settings), FastAPI)


def test_t_if_03_a(tmp_path, clock):
    """T-IF-03-a (LIB-IF-03): The other app has no branch"""
    c1 = TestClient(lms.create_app(file_settings(tmp_path, clock, name="one.db")))
    c2 = TestClient(lms.create_app(file_settings(tmp_path, clock, name="two.db")))
    create_branch(c1, login(c1, "admin@library.local", "ChangeMe123"), "AA")
    adm2 = login(c2, "admin@library.local", "ChangeMe123")
    assert c2.get("/api/v1/branches", headers=adm2).json()["total"] == 0


def test_t_if_05_a(client, admin):
    """T-IF-05-a (LIB-IF-05): The branch is visible"""
    create_branch(client, admin, "MM")
    assert client.get("/api/v1/branches", headers=admin).json()["total"] == 1


def test_t_if_06_a(clock):
    """T-IF-06-a (LIB-IF-06): ValueError both"""
    for bad in (0, 169):
        with pytest.raises(ValueError):
            lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=bad)


def test_t_if_07_a():
    """T-IF-07-a (LIB-IF-07): Aware datetime with offset +03:00"""
    assert lms.SystemClock().now().utcoffset() == timedelta(hours=3)


def test_t_if_09_a(client, clock):
    """T-IF-09-a (LIB-IF-09): today changes from 2026-11-02 to 2026-11-03 without restart"""
    assert client.get("/health").json()["today"] == "2026-11-02"
    clock.advance(days=1)
    assert client.get("/health").json()["today"] == "2026-11-03"


def test_t_if_11_a(settings):
    """T-IF-11-a (LIB-IF-11): Counts {'branches': 1, ...: 0}"""
    data = {"format_version": 1, "branches": [{"id": 1, "code": "MERKEZ", "name": "Central", "address": "", "is_active": True}],
            "authors": [], "publishers": [], "books": [], "copies": [], "members": [], "loans": []}
    counts = lms.import_dataset(settings, data)
    assert counts == {"branches": 1, "authors": 0, "publishers": 0, "books": 0, "copies": 0, "members": 0, "loans": 0}


def test_t_core_01_a(client):
    """T-CORE-01-a (LIB-CORE-01): year 2026; first entry {'date': '2026-01-01', 'name': 'New Year's Day'}; no auth needed"""
    body = client.get("/api/v1/calendar/holidays", params={"year": 2026}).json()
    assert body["year"] == 2026 and body["holidays"][0] == {"date": "2026-01-01", "name": "New Year's Day"}


def test_t_core_01_c(client):
    """T-CORE-01-c (LIB-CORE-01): 13 dates; 2027-05-19 appears once"""
    dates = [h["date"] for h in client.get("/api/v1/calendar/holidays", params={"year": 2027}).json()["holidays"]]
    assert len(dates) == 13 and dates.count("2027-05-19") == 1 and dates == sorted(dates)


def test_t_core_02_a(client):
    """T-CORE-02-a (LIB-CORE-02): {'date': '2026-10-29', 'working_day': false, 'reason': 'holiday'}"""
    assert client.get("/api/v1/calendar/days/2026-10-29").json() == {"date": "2026-10-29", "working_day": False, "reason": "holiday"}


def test_t_core_03_a(client):
    """T-CORE-03-a (LIB-CORE-03): {'date': '2026-06-01'}"""
    r = client.get("/api/v1/calendar/next-working-day", params={"date": "2026-05-27"})
    assert r.status_code == 200 and r.json() == {"date": "2026-06-01"}


def test_t_core_04_a(client):
    """T-CORE-04-a (LIB-CORE-04): {'date': '2026-11-02'}"""
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 2}).json() == {"date": "2026-11-02"}


def test_t_core_05_a(client):
    """T-CORE-05-a (LIB-CORE-05): {'working_days': 4}"""
    assert client.get("/api/v1/calendar/working-days-between", params={"start": "2026-06-01", "end": "2026-06-05"}).json() == {"working_days": 4}


def test_t_core_07_a(client, clock, librarian, branch_a):
    """T-CORE-07-a (LIB-CORE-07): Loan due_date equals next-working-day of 2027-01-01 (2027-01-04)"""
    clock.set(datetime(2026, 12, 2, 10, 0, tzinfo=TR))
    member = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="academic")
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, member["id"], copy["id"])
    expected = client.get("/api/v1/calendar/next-working-day", params={"date": "2027-01-01"}).json()["date"]
    assert loan["due_date"] == expected == "2027-01-04"


def test_t_core_09_a(client, librarian):
    """T-CORE-09-a (LIB-CORE-09): 404 in the error format of LIB-COM-25"""
    r = client.get("/api/v1/books/9999", headers=librarian)
    assert r.status_code == 404 and set(r.json()["error"]) >= {"code", "message", "details"}
