MODULE = "core"
TITLE = "module 1 (Core), technical constraints, common rules and fixed interface"

HEADER = '''
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
'''

S = None  # static case: no pytest code


def static(cid, req, inp, exp):
    return dict(id=cid, req=req, type="Static", input=inp, expected=exp, code=S)


CASES = [
    # ---------------- 2. Technical constraints ----------------
    static("T-TECH-01-a", "LIB-TECH-01", "Docker image", "Python 3.14 (check-tools output)"),
    static("T-TECH-02-a", "LIB-TECH-02", "Imports of the generated code", "Only FastAPI, Uvicorn, Pydantic, SQLAlchemy and the standard library (S22 check)"),
    static("T-TECH-03-a", "LIB-TECH-03", "Test imports", "Only pytest, httpx, Hypothesis besides the standard library"),
    static("T-TECH-04-a", "LIB-TECH-04", "`requirements.txt` of the generated code", "Exactly the seven pinned versions"),
    dict(id="T-TECH-05-a", req="LIB-TECH-05", type="Normal", input="`database_url` pointing to a file in a temporary folder; create a branch", expected="The SQLite file exists and holds the data after restarting the app", code='''
def TEST(tmp_path, clock):
    settings = file_settings(tmp_path, clock)
    c1 = TestClient(lms.create_app(settings))
    adm = login(c1, "admin@library.local", "ChangeMe123")
    create_branch(c1, adm, "AA")
    assert (tmp_path / "lms.db").exists()
    c2 = TestClient(lms.create_app(settings))
    adm2 = login(c2, "admin@library.local", "ChangeMe123")
    codes = [b["code"] for b in c2.get("/api/v1/branches", headers=adm2).json()["items"]]
    assert codes == ["AA"]
'''),
    static("T-TECH-06-a", "LIB-TECH-06", "Source code", "Synchronous SQLAlchemy `Session`; no `async def` endpoints"),
    dict(id="T-TECH-07-a", req="LIB-TECH-07", type="Normal", input="New empty database file", expected="`create_app` creates the schema; bootstrap admin can log in", code='''
def TEST(tmp_path, clock):
    client = TestClient(lms.create_app(file_settings(tmp_path, clock, name="new.db")))
    login(client, "admin@library.local", "ChangeMe123")
'''),
    dict(id="T-TECH-08-a", req="LIB-TECH-08", type="Error", input="Register a member whose `university_id` is already used (member and user are created in one transaction)", expected="`409 CONFLICT`; no user account with the new e-mail exists", code='''
def TEST(client, librarian, admin, branch_a):
    register_member(client, librarian, home_branch_id=branch_a["id"], university_id="U1001")
    r = client.post("/api/v1/members", headers=librarian, json={
        "full_name": "Second", "email": "second@uni.edu.tr", "membership_type": "student",
        "university_id": "U1001", "home_branch_id": branch_a["id"], "password": "Member1234"})
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
    users = client.get("/api/v1/users", headers=admin, params={"q": "second@uni.edu.tr"}).json()
    assert users["total"] == 0
'''),
    dict(id="T-TECH-08-b", req="LIB-TECH-08", type="Boundary", input="Five failed logins for the librarian (each returns 401)", expected="The failures are kept: the account is locked (exception to rollback)", code='''
def TEST(client, librarian):
    for _ in range(5):
        login(client, "lib@library.local", "Wrong0000", expect=401)
    r = client.post("/api/v1/auth/login", json={"email": "lib@library.local", "password": "Librarian123"})
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
'''),
    dict(id="T-TECH-09-a", req="LIB-TECH-09", type="Normal", input="`FixedClock` set to 2027-03-08T10:00+03:00", expected="`/health` reports `today` 2027-03-08 (the clock, not the system time)", code='''
def TEST(client, clock):
    clock.set(datetime(2027, 3, 8, 10, 0, tzinfo=TR))
    assert client.get("/health").json()["today"] == "2027-03-08"
'''),
    static("T-TECH-10-a", "LIB-TECH-10", "Source code", "Randomness only for tokens and salts; every list query has an ORDER BY"),
    static("T-TECH-11-a", "LIB-TECH-11", "Package layout", "One package per module as in section 2.2"),
    static("T-TECH-12-a", "LIB-TECH-12", "`uvicorn \"lms:create_app\" --factory` in the container", "Server starts; `GET /health` returns 200"),

    # ---------------- 3. Common rules ----------------
    dict(id="T-COM-01-a", req="LIB-COM-01", type="Boundary", input="Clock 2026-11-02T22:30:00+00:00 (01:30 local on 3 Nov)", expected="`today` 2026-11-03", code='''
def TEST(client, clock):
    clock.set(datetime(2026, 11, 2, 22, 30, tzinfo=timezone.utc))
    assert client.get("/health").json()["today"] == "2026-11-03"
'''),
    dict(id="T-COM-02-a", req="LIB-COM-02", type="Boundary", input="Clock 2026-11-02T23:59+03:00, then advance 1 minute", expected="`today` 2026-11-02, then 2026-11-03", code='''
def TEST(client, clock):
    clock.set(datetime(2026, 11, 2, 23, 59, tzinfo=TR))
    assert client.get("/health").json()["today"] == "2026-11-02"
    clock.advance(minutes=1)
    assert client.get("/health").json()["today"] == "2026-11-03"
'''),
    dict(id="T-COM-03-a", req="LIB-COM-03", type="Normal", input="Login at 2026-11-02T09:00+03:00", expected="`expires_at` `\"2026-11-02T21:00:00+03:00\"`", code='''
def TEST(client, librarian):
    r = client.post("/api/v1/auth/login", json={"email": "lib@library.local", "password": "Librarian123"})
    expires = datetime.fromisoformat(r.json()["expires_at"])
    assert expires.utcoffset() == timedelta(hours=3)
    assert expires == datetime(2026, 11, 2, 21, 0, tzinfo=TR)
'''),
    dict(id="T-COM-04-a", req="LIB-COM-04", type="Error", input="`GET /api/v1/calendar/days/2026-02-30`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client):
    r = client.get("/api/v1/calendar/days/2026-02-30")
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
'''),
    dict(id="T-COM-05-a", req="LIB-COM-05", type="Normal", input="2026-11-07 (Saturday), 2026-11-09 (Monday)", expected="Not a working day (`weekend`); working day", code='''
def TEST(client):
    sat = client.get("/api/v1/calendar/days/2026-11-07").json()
    mon = client.get("/api/v1/calendar/days/2026-11-09").json()
    assert sat == {"date": "2026-11-07", "working_day": False, "reason": "weekend"}
    assert mon == {"date": "2026-11-09", "working_day": True, "reason": None}
'''),
    dict(id="T-COM-06-a", req="LIB-COM-06", type="Normal", input="`GET /api/v1/calendar/holidays?year=2026`", expected="The 14 dates of the 2026 table, in order", code='''
def TEST(client):
    got = [h["date"] for h in client.get("/api/v1/calendar/holidays", params={"year": 2026}).json()["holidays"]]
    assert got == ["2026-01-01", "2026-03-20", "2026-03-21", "2026-03-22", "2026-04-23", "2026-05-01",
                   "2026-05-19", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30", "2026-07-15",
                   "2026-08-30", "2026-10-29"]
'''),
    dict(id="T-COM-06-b", req="LIB-COM-06", type="Boundary", input="Arife days 2026-10-28 (Wed) and 2027-03-08 (Mon)", expected="Both are working days", code='''
def TEST(client):
    for d in ("2026-10-28", "2027-03-08"):
        assert client.get(f"/api/v1/calendar/days/{d}").json()["working_day"] is True
'''),
    dict(id="T-COM-07-a", req="LIB-COM-07", type="Boundary", input="2028-05-01 (Monday, year not in the list)", expected="Working day", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/days/2028-05-01").json()["working_day"] is True
'''),
    dict(id="T-COM-08-a", req="LIB-COM-08", type="Normal", input="2026-05-27", expected="2026-06-01", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/next-working-day", params={"date": "2026-05-27"}).json() == {"date": "2026-06-01"}
'''),
    dict(id="T-COM-08-b", req="LIB-COM-08", type="Boundary", input="2026-03-24 (working day); 2027-01-01", expected="2026-03-24; 2027-01-04", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/next-working-day", params={"date": "2026-03-24"}).json() == {"date": "2026-03-24"}
    assert client.get("/api/v1/calendar/next-working-day", params={"date": "2027-01-01"}).json() == {"date": "2027-01-04"}
'''),
    dict(id="T-COM-09-a", req="LIB-COM-09", type="Normal", input="2026-10-28 + 2 working days", expected="2026-11-02", code='''
def TEST(client):
    r = client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 2})
    assert r.json() == {"date": "2026-11-02"}
'''),
    dict(id="T-COM-09-b", req="LIB-COM-09", type="Boundary", input="2026-05-26 + 2; 2026-11-06 (Fri) + 1", expected="2026-06-02; 2026-11-09", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-05-26", "days": 2}).json() == {"date": "2026-06-02"}
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-11-06", "days": 1}).json() == {"date": "2026-11-09"}
'''),
    dict(id="T-COM-10-a", req="LIB-COM-10", type="Normal", input="2026-06-01 → 2026-06-05", expected="4", code='''
def TEST(client):
    r = client.get("/api/v1/calendar/working-days-between", params={"start": "2026-06-01", "end": "2026-06-05"})
    assert r.json() == {"working_days": 4}
'''),
    dict(id="T-COM-10-b", req="LIB-COM-10", type="Boundary", input="2026-10-23 → 2026-10-26; 2026-10-27 → 2026-10-30", expected="1; 2", code='''
def TEST(client):
    q = lambda s, e: client.get("/api/v1/calendar/working-days-between", params={"start": s, "end": e}).json()["working_days"]
    assert q("2026-10-23", "2026-10-26") == 1
    assert q("2026-10-27", "2026-10-30") == 2
'''),
    dict(id="T-COM-10-c", req="LIB-COM-10", type="Boundary", input="end = start; end < start", expected="0; 0", code='''
def TEST(client):
    q = lambda s, e: client.get("/api/v1/calendar/working-days-between", params={"start": s, "end": e}).json()["working_days"]
    assert q("2026-11-02", "2026-11-02") == 0
    assert q("2026-11-05", "2026-11-02") == 0
'''),
    dict(id="T-COM-11-a", req="LIB-COM-11", type="Normal", input="Copy with price `\"0.10\"`, read back", expected="`\"0.10\"` exactly (no float artefacts)", code='''
def TEST(client, librarian, branch_a):
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="0.10")
    assert client.get(f"/api/v1/copies/{copy['id']}", headers=librarian).json()["price"] == "0.10"
'''),
    static("T-COM-12-a", "LIB-COM-12", "Fee calculations (module 7 tests)", "ROUND_HALF_UP to two places; inputs have at most two decimals, so rounding is observed through fee tests"),
    dict(id="T-COM-13-a", req="LIB-COM-13", type="Normal", input="Copy with price `\"100.00\"`", expected="Response amount is the string `\"100.00\"`", code='''
def TEST(client, librarian, branch_a):
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="100.00")
    assert copy["price"] == "100.00" and isinstance(copy["price"], str)
'''),
    dict(id="T-COM-13-b", req="LIB-COM-13", type="Error", input="Price as JSON number 100", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, librarian, branch_a):
    book = create_book(client, librarian)
    r = client.post(f"/api/v1/books/{book['id']}/copies", headers=librarian, json={
        "barcode": "NUM-0001", "home_branch_id": branch_a["id"], "price": 100, "acquired_on": "2026-11-01"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
'''),
    dict(id="T-COM-13-c", req="LIB-COM-13", type="Error", input="Price `\"1.005\"` (three decimals)", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, librarian, branch_a):
    book = create_book(client, librarian)
    add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="1.005", expect=422)
'''),
    dict(id="T-COM-14-a", req="LIB-COM-14", type="Normal", input="Create two branches in a new database", expected="ids 1 and 2", code='''
def TEST(client, admin):
    assert create_branch(client, admin, "XX")["id"] == 1
    assert create_branch(client, admin, "YY")["id"] == 2
'''),
    dict(id="T-COM-15-a", req="LIB-COM-15", type="Normal", input="Branch name `\"  Central  \"`", expected="Stored and returned as `\"Central\"`", code='''
def TEST(client, admin):
    assert create_branch(client, admin, "CC", name="  Central  ")["name"] == "Central"
'''),
    dict(id="T-COM-15-b", req="LIB-COM-15", type="Error", input="Branch name of spaces only", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, admin):
    create_branch(client, admin, "DD", name="   ", expect=422)
'''),
    dict(id="T-COM-16-a", req="LIB-COM-16", type="Boundary", input="User `full_name` of 200 characters", expected="Accepted", code='''
def TEST(client, admin):
    r = client.post("/api/v1/users", headers=admin, json=user_payload(full_name="a" * 200))
    assert r.status_code == 201
'''),
    dict(id="T-COM-16-b", req="LIB-COM-16", type="Boundary", input="User `full_name` of 201 characters", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, admin):
    r = client.post("/api/v1/users", headers=admin, json=user_payload(full_name="a" * 201))
    assert r.status_code == 422
'''),
    dict(id="T-COM-17-a", req="LIB-COM-17", type="Normal", input="User e-mail `\"New.Staff@Library.Local\"`", expected="Stored and returned as `\"new.staff@library.local\"`", code='''
def TEST(client, admin):
    r = client.post("/api/v1/users", headers=admin, json=user_payload(email="New.Staff@Library.Local"))
    assert r.json()["email"] == "new.staff@library.local"
'''),
    dict(id="T-COM-17-b", req="LIB-COM-17", type="Error", input="E-mails `\"a@b\"`, `\"@x.com\"`, `\"a@@x.com\"`", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, admin):
    for bad in ("a@b", "@x.com", "a@@x.com"):
        r = client.post("/api/v1/users", headers=admin, json=user_payload(email=bad))
        assert r.status_code == 422, bad
'''),
    dict(id="T-COM-18-a", req="LIB-COM-18", type="Boundary", input="`GET /api/v1/users?page_size=101`; `page=0`", expected="`422 VALIDATION_ERROR` both", code='''
def TEST(client, admin):
    assert client.get("/api/v1/users", headers=admin, params={"page_size": 101}).status_code == 422
    assert client.get("/api/v1/users", headers=admin, params={"page": 0}).status_code == 422
'''),
    dict(id="T-COM-18-b", req="LIB-COM-18", type="Normal", input="`GET /api/v1/users` without parameters; `page_size=100`", expected="`page` 1, `page_size` 20; 100 accepted", code='''
def TEST(client, admin):
    body = client.get("/api/v1/users", headers=admin).json()
    assert body["page"] == 1 and body["page_size"] == 20
    assert client.get("/api/v1/users", headers=admin, params={"page_size": 100}).status_code == 200
'''),
    dict(id="T-COM-19-a", req="LIB-COM-19", type="Normal", input="25 extra users; page 2 with page size 10", expected="10 items, `total` 27 (admin + librarian + 25)", code='''
def TEST(client, admin, librarian):
    for i in range(25):
        client.post("/api/v1/users", headers=admin, json=user_payload(email=f"s{i}@library.local"))
    body = client.get("/api/v1/users", headers=admin, params={"page": 2, "page_size": 10}).json()
    assert set(body) >= {"items", "page", "page_size", "total"}
    assert len(body["items"]) == 10 and body["total"] == 27 and body["page"] == 2
'''),
    dict(id="T-COM-19-b", req="LIB-COM-19", type="Boundary", input="Page beyond the last page", expected="200 with `items` []", code='''
def TEST(client, admin):
    r = client.get("/api/v1/users", headers=admin, params={"page": 50})
    assert r.status_code == 200 and r.json()["items"] == []
'''),
    dict(id="T-COM-20-a", req="LIB-COM-20", type="Normal", input="Users created in the order admin, librarian, x, y", expected="List ordered by `id` ascending", code='''
def TEST(client, admin, librarian):
    for e in ("y@library.local", "x@library.local"):
        client.post("/api/v1/users", headers=admin, json=user_payload(email=e))
    ids = [u["id"] for u in client.get("/api/v1/users", headers=admin).json()["items"]]
    assert ids == sorted(ids)
'''),
    dict(id="T-COM-21-a", req="LIB-COM-21", type="Error", input="`GET /users` without `/api/v1`", expected="`404 NOT_FOUND` in the error format", code='''
def TEST(client, admin):
    r = client.get("/users", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
'''),
    dict(id="T-COM-22-a", req="LIB-COM-22", type="Normal", input="Create user, update user, logout", expected="201 with body; 200 with body; 204 without body", code='''
def TEST(client, admin):
    r = client.post("/api/v1/users", headers=admin, json=user_payload())
    assert r.status_code == 201 and r.json()["email"] == "x1@library.local"
    r2 = client.patch(f"/api/v1/users/{r.json()['id']}", headers=admin, json={"full_name": "Renamed"})
    assert r2.status_code == 200 and r2.json()["full_name"] == "Renamed"
    r3 = client.post("/api/v1/auth/logout", headers=admin)
    assert r3.status_code == 204 and r3.content == b""
'''),
    dict(id="T-COM-23-a", req="LIB-COM-23", type="Error", input="`POST /api/v1/users` with an extra field `nickname`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, admin):
    r = client.post("/api/v1/users", headers=admin, json=user_payload(nickname="x"))
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
'''),
    dict(id="T-COM-24-a", req="LIB-COM-24", type="Error", input="Header `Authorization: Token abc` (not Bearer)", expected="`401 UNAUTHENTICATED`", code='''
def TEST(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Token abc"})
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"
'''),
    dict(id="T-COM-25-a", req="LIB-COM-25", type="Normal", input="`GET /api/v1/users/9999` as admin", expected="Body `{\"error\": {\"code\", \"message\", \"details\"}}` with `details` an object", code='''
def TEST(client, admin):
    err = client.get("/api/v1/users/9999", headers=admin).json()["error"]
    assert err["code"] == "NOT_FOUND" and isinstance(err["message"], str) and isinstance(err["details"], dict)
'''),
    dict(id="T-COM-26-a", req="LIB-COM-26", type="Normal", input="`POST /api/v1/users` with invalid `email` and missing `full_name`", expected="`details.fields` names both fields", code='''
def TEST(client, admin):
    data = user_payload(email="bad")
    del data["full_name"]
    fields = client.post("/api/v1/users", headers=admin, json=data).json()["error"]["details"]["fields"]
    names = {f["field"] for f in fields}
    assert {"email", "full_name"} <= names
    assert all(isinstance(f["problem"], str) for f in fields)
'''),
    static("T-COM-27-a", "LIB-COM-27", "Forced internal error (fault injection in the pilot)", "`500 INTERNAL_ERROR`, no stack trace in the body"),
    dict(id="T-COM-28-a", req="LIB-COM-28", type="Error", input="No token and an invalid body to `POST /api/v1/users`", expected="401 (authentication first)", code='''
def TEST(client):
    r = client.post("/api/v1/users", json={"email": "bad"})
    assert r.status_code == 401
'''),
    dict(id="T-COM-28-b", req="LIB-COM-28", type="Error", input="Librarian sends an invalid body to `POST /api/v1/users` (admin only)", expected="`403 FORBIDDEN` (role before validation)", code='''
def TEST(client, librarian):
    r = client.post("/api/v1/users", headers=librarian, json={"email": "bad"})
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"
'''),
    dict(id="T-COM-28-c", req="LIB-COM-28", type="Error", input="Admin: `PATCH /api/v1/users/9999` with invalid `role`; then with a valid body", expected="422 (validation before existence); then 404", code='''
def TEST(client, admin):
    assert client.patch("/api/v1/users/9999", headers=admin, json={"role": "boss"}).status_code == 422
    r = client.patch("/api/v1/users/9999", headers=admin, json={"full_name": "N"})
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
'''),
    dict(id="T-COM-29-a", req="LIB-COM-29", type="Error", input="Register a member with `home_branch_id` 999", expected="`404 NOT_FOUND`, `details` `{\"field\": \"home_branch_id\", \"id\": 999}`", code='''
def TEST(client, librarian):
    r = client.post("/api/v1/members", headers=librarian, json={
        "full_name": "M", "email": "m@uni.edu.tr", "membership_type": "student",
        "university_id": "U2001", "home_branch_id": 999, "password": "Member1234"})
    assert r.status_code == 404
    assert r.json()["error"]["details"] == {"field": "home_branch_id", "id": 999}
'''),
    dict(id="T-COM-30-a", req="LIB-COM-30", type="Boundary", input="Users `isik@library.local` and `ISIK@library.local`", expected="Second returns `409 CONFLICT`", code='''
def TEST(client, admin):
    assert client.post("/api/v1/users", headers=admin, json=user_payload(email="isik@library.local")).status_code == 201
    r = client.post("/api/v1/users", headers=admin, json=user_payload(email="ISIK@library.local"))
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
'''),
    dict(id="T-COM-30-b", req="LIB-COM-30", type="Normal", input="User named `\"Işık Yılmaz\"`; filter `q=IŞIK` (LIB-SRCH-01: `ş` is not folded)", expected="The user is found", code='''
def TEST(client, admin):
    client.post("/api/v1/users", headers=admin, json=user_payload(full_name="Işık Yılmaz"))
    items = client.get("/api/v1/users", headers=admin, params={"q": "IŞIK"}).json()["items"]
    assert [u["full_name"] for u in items] == ["Işık Yılmaz"]
'''),

    # ---------------- 4. Fixed service interface ----------------
    dict(id="T-IF-01-a", req="LIB-IF-01", type="Normal", input="`lms.create_app(settings)`", expected="A FastAPI application", code='''
def TEST(settings):
    assert isinstance(lms.create_app(settings), FastAPI)
'''),
    dict(id="T-IF-02-a", req="LIB-IF-02", type="Boundary", input="`create_app` twice on the same database file", expected="No error; exactly one admin", code='''
def TEST(tmp_path, clock):
    settings = file_settings(tmp_path, clock)
    lms.create_app(settings)
    client = TestClient(lms.create_app(settings))
    adm = login(client, "admin@library.local", "ChangeMe123")
    assert client.get("/api/v1/users", headers=adm, params={"role": "admin"}).json()["total"] == 1
'''),
    dict(id="T-IF-03-a", req="LIB-IF-03", type="Normal", input="Two apps with different database files; branch created in one", expected="The other app has no branch", code='''
def TEST(tmp_path, clock):
    c1 = TestClient(lms.create_app(file_settings(tmp_path, clock, name="one.db")))
    c2 = TestClient(lms.create_app(file_settings(tmp_path, clock, name="two.db")))
    create_branch(c1, login(c1, "admin@library.local", "ChangeMe123"), "AA")
    adm2 = login(c2, "admin@library.local", "ChangeMe123")
    assert c2.get("/api/v1/branches", headers=adm2).json()["total"] == 0
'''),
    dict(id="T-IF-04-a", req="LIB-IF-04", type="Normal", input="`lms.DEFAULT_HOLIDAYS`", expected="27 dates; contains 2026-10-29, not 2026-10-28", code='''
def TEST():
    assert len(lms.DEFAULT_HOLIDAYS) == 27
    assert date(2026, 10, 29) in lms.DEFAULT_HOLIDAYS and date(2026, 10, 28) not in lms.DEFAULT_HOLIDAYS
'''),
    dict(id="T-IF-05-a", req="LIB-IF-05", type="Normal", input="In-memory database: create a branch, read it in a later request", expected="The branch is visible", code='''
def TEST(client, admin):
    create_branch(client, admin, "MM")
    assert client.get("/api/v1/branches", headers=admin).json()["total"] == 1
'''),
    dict(id="T-IF-06-a", req="LIB-IF-06", type="Boundary", input="`token_ttl_hours` 0 and 169", expected="`ValueError` both", code='''
def TEST(clock):
    for bad in (0, 169):
        with pytest.raises(ValueError):
            lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=bad)
'''),
    dict(id="T-IF-06-b", req="LIB-IF-06", type="Boundary", input="`token_ttl_hours` 1 and 168", expected="Accepted", code='''
def TEST(clock):
    for ok in (1, 168):
        lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=ok)
'''),
    dict(id="T-IF-07-a", req="LIB-IF-07", type="Normal", input="`lms.SystemClock().now()`", expected="Aware datetime with offset +03:00", code='''
def TEST():
    assert lms.SystemClock().now().utcoffset() == timedelta(hours=3)
'''),
    dict(id="T-IF-08-a", req="LIB-IF-08", type="Error", input="`FixedClock(naive)`; `set(naive)`", expected="`ValueError` both", code='''
def TEST(clock):
    with pytest.raises(ValueError):
        lms.FixedClock(datetime(2026, 11, 2, 9, 0))
    with pytest.raises(ValueError):
        clock.set(datetime(2026, 11, 2, 9, 0))
'''),
    dict(id="T-IF-09-a", req="LIB-IF-09", type="Normal", input="`clock.advance(days=1)` between two requests", expected="`today` changes from 2026-11-02 to 2026-11-03 without restart", code='''
def TEST(client, clock):
    assert client.get("/health").json()["today"] == "2026-11-02"
    clock.advance(days=1)
    assert client.get("/health").json()["today"] == "2026-11-03"
'''),
    dict(id="T-IF-10-a", req="LIB-IF-10", type="Normal", input="`GET /health` without token", expected="200 `{\"status\": \"ok\", \"today\": \"2026-11-02\"}`", code='''
def TEST(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "today": "2026-11-02"}
'''),
    dict(id="T-IF-11-a", req="LIB-IF-11", type="Normal", input="`import_dataset` with one branch and empty lists into an empty database", expected="Counts `{\"branches\": 1, ...: 0}`", code='''
def TEST(settings):
    data = {"format_version": 1, "branches": [{"id": 1, "code": "MERKEZ", "name": "Central", "address": "", "is_active": True}],
            "authors": [], "publishers": [], "books": [], "copies": [], "members": [], "loans": []}
    counts = lms.import_dataset(settings, data)
    assert counts == {"branches": 1, "authors": 0, "publishers": 0, "books": 0, "copies": 0, "members": 0, "loans": 0}
'''),
    dict(id="T-IF-11-b", req="LIB-IF-11", type="Error", input="Second import into the same database; invalid `format_version`", expected="`RuntimeError`; `ValueError`", code='''
def TEST(tmp_path, clock):
    settings = file_settings(tmp_path, clock)
    data = {"format_version": 1, "branches": [{"id": 1, "code": "MERKEZ", "name": "Central", "address": "", "is_active": True}],
            "authors": [], "publishers": [], "books": [], "copies": [], "members": [], "loans": []}
    with pytest.raises(ValueError):
        lms.import_dataset(file_settings(tmp_path, clock, name="other.db"), dict(data, format_version=2))
    lms.import_dataset(settings, data)
    with pytest.raises(RuntimeError):
        lms.import_dataset(settings, data)
'''),
    dict(id="T-IF-12-a", req="LIB-IF-12", type="Normal", input="After creating a branch: `export_dataset(settings)` and `GET /api/v1/export`", expected="Equal documents", code='''
def TEST(client, admin, settings):
    create_branch(client, admin, "AA")
    assert lms.export_dataset(settings) == client.get("/api/v1/export", headers=admin).json()
'''),

    # ---------------- 5. Module 1: Core ----------------
    dict(id="T-CORE-01-a", req="LIB-CORE-01", type="Normal", input="`holidays?year=2026`", expected="`year` 2026; first entry `{\"date\": \"2026-01-01\", \"name\": \"New Year's Day\"}`; no auth needed", code='''
def TEST(client):
    body = client.get("/api/v1/calendar/holidays", params={"year": 2026}).json()
    assert body["year"] == 2026 and body["holidays"][0] == {"date": "2026-01-01", "name": "New Year's Day"}
'''),
    dict(id="T-CORE-01-b", req="LIB-CORE-01", type="Boundary", input="`year` 2030; `year` 1899 and 2101", expected="Empty list; `422` for both", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/holidays", params={"year": 2030}).json()["holidays"] == []
    for y in (1899, 2101):
        assert client.get("/api/v1/calendar/holidays", params={"year": y}).status_code == 422
'''),
    dict(id="T-CORE-01-c", req="LIB-CORE-01", type="Normal", input="`year` 2027", expected="13 dates; 2027-05-19 appears once", code='''
def TEST(client):
    dates = [h["date"] for h in client.get("/api/v1/calendar/holidays", params={"year": 2027}).json()["holidays"]]
    assert len(dates) == 13 and dates.count("2027-05-19") == 1 and dates == sorted(dates)
'''),
    dict(id="T-CORE-02-a", req="LIB-CORE-02", type="Normal", input="2026-10-29", expected="`{\"date\": \"2026-10-29\", \"working_day\": false, \"reason\": \"holiday\"}`", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/days/2026-10-29").json() == {"date": "2026-10-29", "working_day": False, "reason": "holiday"}
'''),
    dict(id="T-CORE-02-b", req="LIB-CORE-02", type="Boundary", input="2026-03-21 (Saturday and holiday)", expected="`reason` `\"holiday\"`", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/days/2026-03-21").json()["reason"] == "holiday"
'''),
    dict(id="T-CORE-03-a", req="LIB-CORE-03", type="Normal", input="`next-working-day?date=2026-05-27` without token", expected="`{\"date\": \"2026-06-01\"}`", code='''
def TEST(client):
    r = client.get("/api/v1/calendar/next-working-day", params={"date": "2026-05-27"})
    assert r.status_code == 200 and r.json() == {"date": "2026-06-01"}
'''),
    dict(id="T-CORE-04-a", req="LIB-CORE-04", type="Normal", input="`add-working-days?date=2026-10-28&days=2`", expected="`{\"date\": \"2026-11-02\"}`", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 2}).json() == {"date": "2026-11-02"}
'''),
    dict(id="T-CORE-04-b", req="LIB-CORE-04", type="Boundary", input="`days` 0 and 366; `days` 365", expected="`422` for 0 and 366; 200 for 365", code='''
def TEST(client):
    for d in (0, 366):
        assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": d}).status_code == 422
    assert client.get("/api/v1/calendar/add-working-days", params={"date": "2026-10-28", "days": 365}).status_code == 200
'''),
    dict(id="T-CORE-05-a", req="LIB-CORE-05", type="Normal", input="`working-days-between?start=2026-06-01&end=2026-06-05`", expected="`{\"working_days\": 4}`", code='''
def TEST(client):
    assert client.get("/api/v1/calendar/working-days-between", params={"start": "2026-06-01", "end": "2026-06-05"}).json() == {"working_days": 4}
'''),
    dict(id="T-CORE-05-b", req="LIB-CORE-05", type="Boundary", input="`end` − `start` = 3660 days; 3661 days", expected="200; `422`", code='''
def TEST(client):
    start = date(2026, 1, 1)
    ok = (start + timedelta(days=3660)).isoformat()
    bad = (start + timedelta(days=3661)).isoformat()
    assert client.get("/api/v1/calendar/working-days-between", params={"start": "2026-01-01", "end": ok}).status_code == 200
    assert client.get("/api/v1/calendar/working-days-between", params={"start": "2026-01-01", "end": bad}).status_code == 422
'''),
    dict(id="T-CORE-06-a", req="LIB-CORE-06", type="Error", input="`working-days-between` without `end`", expected="`422`, `details.fields` contains `end`", code='''
def TEST(client):
    r = client.get("/api/v1/calendar/working-days-between", params={"start": "2026-06-01"})
    assert r.status_code == 422
    assert "end" in {f["field"] for f in r.json()["error"]["details"]["fields"]}
'''),
    dict(id="T-CORE-07-a", req="LIB-CORE-07", type="Normal", input="Academic lends a copy on 2026-12-02", expected="Loan `due_date` equals `next-working-day` of 2027-01-01 (2027-01-04)", code='''
def TEST(client, clock, librarian, branch_a):
    clock.set(datetime(2026, 12, 2, 10, 0, tzinfo=TR))
    member = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="academic")
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, member["id"], copy["id"])
    expected = client.get("/api/v1/calendar/next-working-day", params={"date": "2027-01-01"}).json()["date"]
    assert loan["due_date"] == expected == "2027-01-04"
'''),
    static("T-CORE-08-a", "LIB-CORE-08", "Fee calculations (module 7 tests)", "Rounding applied to final results only"),
    dict(id="T-CORE-09-a", req="LIB-CORE-09", type="Normal", input="`GET /api/v1/books/9999` as librarian", expected="`404` in the error format of LIB-COM-25", code='''
def TEST(client, librarian):
    r = client.get("/api/v1/books/9999", headers=librarian)
    assert r.status_code == 404 and set(r.json()["error"]) >= {"code", "message", "details"}
'''),
    dict(id="T-CORE-10-a", req="LIB-CORE-10", type="Boundary", input="`GET /api/v1/members?page_size=101`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, librarian):
    assert client.get("/api/v1/members", headers=librarian, params={"page_size": 101}).status_code == 422
'''),
]
