MODULE = "audit_io"
TITLE = "module 13 (Audit log, import and export)"

HEADER = '''
import copy as _copy
import csv
import io

from fastapi.testclient import TestClient


class _LazyLMS:
    """Imports lms at first use, so the tests can be collected before the code exists."""

    def __getattr__(self, name):
        import lms as real
        return getattr(real, name)


lms = _LazyLMS()
from support.api import create_branch, error_code, login, register_member


def audit(client, admin, **params):
    r = client.get("/api/v1/audit-log", headers=admin, params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def dataset():
    """Small valid dataset in the format of requirements section 22.1."""
    return {
        "format_version": 1,
        "branches": [{"id": 1, "code": "MERKEZ", "name": "Central", "address": "", "is_active": True},
                     {"id": 2, "code": "KAMPUS", "name": "Campus, North", "address": "Çankaya", "is_active": True}],
        "authors": [{"id": 1, "name": "Sabahattin Ali"}],
        "publishers": [{"id": 1, "name": "Example Publishing"}],
        "books": [{"id": 7, "isbn": "9780306406157", "title": "Kürk Mantolu Madonna", "subtitle": None, "author_ids": [1],
                   "publisher_id": 1, "publication_year": 1943, "language": "tr", "classification": "813.54"}],
        "copies": [{"id": 1, "book_id": 7, "barcode": "C000001", "home_branch_id": 1, "current_branch_id": 1, "price": "150.00",
                    "status": "on_loan", "acquired_on": "2025-09-01", "shelf_location": None},
                   {"id": 2, "book_id": 7, "barcode": "C000002", "home_branch_id": 2, "current_branch_id": 2, "price": "150.00",
                    "status": "available", "acquired_on": "2025-09-01", "shelf_location": "A-1"}],
        "members": [{"id": 1, "full_name": "Ayşe Yılmaz", "email": "ayse@example.edu.tr", "phone": None, "membership_type": "student",
                     "university_id": "20231234", "home_branch_id": 1, "status": "active", "membership_start": "2026-09-15",
                     "valid_until": "2027-09-14"},
                    {"id": 2, "full_name": "John Smith", "email": "john@example.com", "phone": "+905320000000", "membership_type": "guest",
                     "university_id": None, "home_branch_id": 2, "status": "active", "membership_start": "2026-10-01",
                     "valid_until": "2026-12-29"}],
        "loans": [{"id": 1, "copy_id": 1, "member_id": 2, "branch_id": 1, "loan_date": "2026-10-26", "due_date": "2026-11-02",
                   "renewal_count": 0, "status": "open", "returned_on": None, "return_branch_id": None}],
    }


def do_import(client, admin, data, expect=200):
    r = client.post("/api/v1/import", headers=admin, json=data)
    assert r.status_code == expect, r.text
    return r
'''


CASES = [
    dict(id="T-AUD-01-a", req="LIB-AUD-01", type="Normal", input="Admin creates a user; a failed login with an unknown e-mail", expected="Entry `user_created` with `actor_user_id` = admin and `entity_type` `user`; entry `login_failed` with `actor_user_id` null", code='''
def TEST(client, admin):
    me = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    uid = client.post("/api/v1/users", headers=admin, json={"email": "s@library.local", "full_name": "S", "role": "librarian", "password": "Passw0rd1"}).json()["id"]
    created = audit(client, admin, event="user_created")
    assert [(e["actor_user_id"], e["entity_type"], e["entity_id"]) for e in created] == [(me, "user", uid)]
    client.post("/api/v1/auth/login", json={"email": "ghost@library.local", "password": "Wrong0000"})
    failed = audit(client, admin, event="login_failed")
    assert len(failed) == 1 and failed[0]["actor_user_id"] is None
'''),
    dict(id="T-AUD-01-b", req="LIB-AUD-01", type="Error", input="Registration that fails with `409 CONFLICT` (duplicate `university_id`)", expected="Only one `member_registered` entry (the rolled-back request leaves none)", code='''
def TEST(client, admin, librarian, branch_a):
    register_member(client, librarian, home_branch_id=branch_a["id"], university_id="U9001")
    r = client.post("/api/v1/members", headers=librarian, json={"full_name": "Dup", "email": "dup@uni.edu.tr", "membership_type": "student",
                                                                  "university_id": "U9001", "home_branch_id": branch_a["id"], "password": "Member1234"})
    assert r.status_code == 409
    assert len(audit(client, admin, event="member_registered")) == 1
'''),
    dict(id="T-AUD-02-a", req="LIB-AUD-02", type="Normal", input="PATCH a user's `full_name` from `Old` to `New`", expected="`user_updated` details `{\"full_name\": {\"old\": \"Old\", \"new\": \"New\"}}`", code='''
def TEST(client, admin):
    uid = client.post("/api/v1/users", headers=admin, json={"email": "o@library.local", "full_name": "Old", "role": "librarian", "password": "Passw0rd1"}).json()["id"]
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"full_name": "New"})
    entry = audit(client, admin, event="user_updated", entity_id=uid)[0]
    assert entry["details"]["full_name"] == {"old": "Old", "new": "New"}
'''),
    dict(id="T-AUD-02-b", req="LIB-AUD-02", type="Error", input="User created with password `Passw0rd1`, password changed to `NewPassw0rd`, logins", expected="No audit `details` contains a password, a hash or a token", code='''
def TEST(client, admin):
    client.post("/api/v1/users", headers=admin, json={"email": "p@library.local", "full_name": "P", "role": "librarian", "password": "Passw0rd1"})
    h = login(client, "p@library.local", "Passw0rd1")
    client.post("/api/v1/auth/change-password", headers=h, json={"current_password": "Passw0rd1", "new_password": "NewPassw0rd"})
    token = h["Authorization"].split()[1]
    dump = str(audit(client, admin, page_size=100)).lower()
    for secret in ("passw0rd1", "newpassw0rd", "scrypt$", token.lower()):
        assert secret not in dump, secret
'''),
    dict(id="T-AUD-03-a", req="LIB-AUD-03", type="Normal", input="Several events; filters `event`, `entity_type`, `from`/`to`; order", expected="Ordered by `id` descending; filters match; librarian gets `403`", code='''
def TEST(client, admin, librarian, branch_a):
    register_member(client, librarian, home_branch_id=branch_a["id"])
    entries = audit(client, admin)
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)
    assert {e["event"] for e in audit(client, admin, entity_type="member")} >= {"member_registered"}
    assert audit(client, admin, **{"from": "2026-11-03", "to": "2026-11-30"}) == []
    assert len(audit(client, admin, **{"from": "2026-11-02", "to": "2026-11-02"})) == len(entries)
    assert client.get("/api/v1/audit-log", headers=librarian).status_code == 403
'''),
    dict(id="T-AUD-04-a", req="LIB-AUD-04", type="Error", input="`DELETE`, `PATCH`, `PUT` on `/api/v1/audit-log/{id}` and `DELETE /api/v1/audit-log` as admin", expected="404 or 405 each; the entry still exists", code='''
def TEST(client, admin):
    entry = audit(client, admin)[0]
    for method in ("DELETE", "PATCH", "PUT"):
        assert client.request(method, f"/api/v1/audit-log/{entry['id']}", headers=admin, json={}).status_code in {404, 405}
    assert client.delete("/api/v1/audit-log", headers=admin).status_code in {404, 405}
    assert entry["id"] in [e["id"] for e in audit(client, admin, page_size=100)]
'''),
    dict(id="T-IO-01-a", req="LIB-IO-01", type="Normal", input="Import the small dataset into an empty database", expected="200 with counts branches 2, authors 1, publishers 1, books 1, copies 2, members 2, loans 1", code='''
def TEST(client, admin):
    r = do_import(client, admin, dataset())
    assert r.json() == {"imported": {"branches": 2, "authors": 1, "publishers": 1, "books": 1, "copies": 2, "members": 2, "loans": 1}}
'''),
    dict(id="T-IO-02-a", req="LIB-IO-02", type="Boundary", input="Database with one branch; database with only an extra staff user", expected="`409 DATABASE_NOT_EMPTY`; import succeeds", code='''
def TEST(client, admin, settings, tmp_path, clock):
    create_branch(client, admin, "XX")
    r = do_import(client, admin, dataset(), expect=409)
    assert error_code(r) == "DATABASE_NOT_EMPTY"
    other = TestClient(lms.create_app(lms.Settings(database_url=f"sqlite:///{tmp_path / 'b.db'}", clock=clock)))
    adm = login(other, "admin@library.local", "ChangeMe123")
    other.post("/api/v1/users", headers=adm, json={"email": "s@library.local", "full_name": "S", "role": "librarian", "password": "Passw0rd1"})
    do_import(other, adm, dataset())
'''),
    dict(id="T-IO-03-a", req="LIB-IO-03", type="Error", input="Dataset whose second member has e-mail `bad`", expected="`422` with field `members[1].email`; nothing imported (no branches)", code='''
def TEST(client, admin):
    data = dataset()
    data["members"][1]["email"] = "bad"
    r = do_import(client, admin, data, expect=422)
    assert "members[1].email" in {f["field"] for f in r.json()["error"]["details"]["fields"]}
    assert client.get("/api/v1/branches", headers=admin).json()["total"] == 0
'''),
    dict(id="T-IO-04-a", req="LIB-IO-04", type="Normal", input="Book with id 7 and ISBN-10 `0-306-40615-2`", expected="`GET /api/v1/books/7` works; ISBN stored as `9780306406157`", code='''
def TEST(client, admin):
    data = dataset()
    data["books"][0]["isbn"] = "0-306-40615-2"
    do_import(client, admin, data)
    b = client.get("/api/v1/books/7", headers=admin).json()
    assert b["id"] == 7 and b["isbn"] == "9780306406157"
'''),
    dict(id="T-IO-04-b", req="LIB-IO-04", type="Error", input="Copy referring to book id 99; two members with the same e-mail", expected="`422` each", code='''
def TEST(client, admin):
    data = dataset()
    data["copies"][1]["book_id"] = 99
    do_import(client, admin, data, expect=422)
    data = dataset()
    data["members"][1]["email"] = data["members"][0]["email"]
    do_import(client, admin, data, expect=422)
'''),
    dict(id="T-IO-05-a", req="LIB-IO-05", type="Normal", input="Imported member logs in; admin resets the password; member logs in again", expected="`401 INVALID_CREDENTIALS`; then 200", code='''
def TEST(client, admin):
    do_import(client, admin, dataset())
    r = client.post("/api/v1/auth/login", json={"email": "ayse@example.edu.tr", "password": "Member1234"})
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"
    users = client.get("/api/v1/users", headers=admin, params={"q": "ayse@example.edu.tr"}).json()["items"]
    client.post(f"/api/v1/users/{users[0]['id']}/reset-password", headers=admin, json={"new_password": "Member1234"})
    assert client.post("/api/v1/auth/login", json={"email": "ayse@example.edu.tr", "password": "Member1234"}).status_code == 200
'''),
    dict(id="T-IO-06-a", req="LIB-IO-06", type="Error", input="Open loan whose copy is `available`; lost loan whose copy is `lost` but has a branch", expected="`422` each", code='''
def TEST(client, admin):
    data = dataset()
    data["copies"][0]["status"] = "available"
    do_import(client, admin, data, expect=422)
    data = dataset()
    data["loans"][0]["status"] = "lost"
    data["copies"][0]["status"] = "lost"
    do_import(client, admin, data, expect=422)
'''),
    dict(id="T-IO-06-b", req="LIB-IO-06", type="Normal", input="Lost loan with copy `lost` and `current_branch_id` null; returned loan", expected="Import succeeds; no fees and no notifications; one `data_imported` audit entry", code='''
def TEST(client, admin):
    data = dataset()
    data["loans"][0]["status"] = "lost"
    data["copies"][0].update(status="lost", current_branch_id=None)
    data["loans"].append({"id": 2, "copy_id": 2, "member_id": 1, "branch_id": 2, "loan_date": "2026-09-20", "due_date": "2026-10-05",
                          "renewal_count": 0, "status": "returned", "returned_on": "2026-10-10", "return_branch_id": 2})
    do_import(client, admin, data)
    assert client.get("/api/v1/fees", headers=admin).json()["total"] == 0
    assert client.get("/api/v1/notifications", headers=admin).json()["total"] == 0
    assert len(audit(client, admin, event="data_imported")) == 1
'''),
    dict(id="T-IO-07-a", req="LIB-IO-07", type="Normal", input="Import, export, import the export into a second empty database, export again", expected="Both exports are equal to each other and to the imported data", code='''
def TEST(client, admin, tmp_path, clock):
    data = dataset()
    do_import(client, admin, data)
    first = client.get("/api/v1/export", headers=admin).json()
    assert first == data
    other = TestClient(lms.create_app(lms.Settings(database_url=f"sqlite:///{tmp_path / 'c.db'}", clock=clock)))
    adm = login(other, "admin@library.local", "ChangeMe123")
    do_import(other, adm, _copy.deepcopy(first))
    assert other.get("/api/v1/export", headers=adm).json() == first
'''),
    dict(id="T-IO-08-a", req="LIB-IO-08", type="Normal", input="`GET /api/v1/export/branches.csv`; `/export/users.csv`; librarian", expected="CSV with header `id,code,name,address,is_active` and 2 rows ordered by id; `404 NOT_FOUND`; `403`", code='''
def TEST(client, admin, librarian):
    do_import(client, admin, dataset())
    r = client.get("/api/v1/export/branches.csv", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0] == ["id", "code", "name", "address", "is_active"] and [row[0] for row in rows[1:]] == ["1", "2"]
    r = client.get("/api/v1/export/users.csv", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
    assert client.get("/api/v1/export/branches.csv", headers=librarian).status_code == 403
'''),
    dict(id="T-IO-08-b", req="LIB-IO-08", type="Normal", input="`books.csv`, `copies.csv`, `members.csv`, `loans.csv` headers", expected="Columns exactly as in requirements 22.2", code='''
def TEST(client, admin):
    do_import(client, admin, dataset())
    expected = {
        "books": ["id", "isbn", "title", "subtitle", "authors", "publisher", "publication_year", "language", "classification"],
        "copies": ["id", "book_id", "barcode", "home_branch_id", "current_branch_id", "price", "status", "acquired_on", "shelf_location"],
        "members": ["id", "member_no", "full_name", "email", "phone", "membership_type", "university_id", "home_branch_id", "status", "membership_start", "valid_until"],
        "loans": ["id", "copy_id", "member_id", "branch_id", "loan_date", "due_date", "renewal_count", "status", "returned_on", "return_branch_id", "late_days"],
    }
    for entity, header in expected.items():
        text = client.get(f"/api/v1/export/{entity}.csv", headers=admin).content.decode("utf-8")
        assert next(csv.reader(io.StringIO(text))) == header, entity
'''),
    dict(id="T-IO-09-a", req="LIB-IO-09", type="Normal", input="`GET /api/v1/export` and `GET /api/v1/export/books.csv`", expected="Two `data_exported` entries with entity `all` and `books`", code='''
def TEST(client, admin):
    client.get("/api/v1/export", headers=admin)
    client.get("/api/v1/export/books.csv", headers=admin)
    entries = audit(client, admin, event="data_exported")
    assert len(entries) == 2
    values = {v for e in entries for v in e["details"].values() if isinstance(v, str)}
    assert {"all", "books"} <= values
'''),
    dict(id="T-IO-10-a", req="LIB-IO-10", type="Error", input="`format_version` 2; `loans` list missing; unknown field `notes` in a branch", expected="`422` each", code='''
def TEST(client, admin):
    data = dataset(); data["format_version"] = 2
    do_import(client, admin, data, expect=422)
    data = dataset(); del data["loans"]
    do_import(client, admin, data, expect=422)
    data = dataset(); data["branches"][0]["notes"] = "x"
    do_import(client, admin, data, expect=422)
'''),
    dict(id="T-IO-10-b", req="LIB-IO-10", type="Boundary", input="All seven lists empty", expected="Import succeeds with all counts 0", code='''
def TEST(client, admin):
    data = {"format_version": 1, "branches": [], "authors": [], "publishers": [], "books": [], "copies": [], "members": [], "loans": []}
    assert set(do_import(client, admin, data).json()["imported"].values()) == {0}
'''),
    dict(id="T-IO-11-a", req="LIB-IO-11", type="Error", input="Copy with status `on_hold`; copy with status `in_transfer`", expected="`422` each", code='''
def TEST(client, admin):
    for status in ("on_hold", "in_transfer"):
        data = dataset()
        data["copies"][1]["status"] = status
        do_import(client, admin, data, expect=422)
'''),
    dict(id="T-IO-11-b", req="LIB-IO-11", type="Normal", input="Imported open loan of a guest", expected="`LoanOut` has `loan_period_days` 7, `max_renewals` 0, `daily_fee` `\"5.00\"`", code='''
def TEST(client, admin):
    do_import(client, admin, dataset())
    loan = client.get("/api/v1/loans/1", headers=admin).json()
    assert (loan["loan_period_days"], loan["max_renewals"], loan["daily_fee"]) == (7, 0, "5.00")
'''),
    dict(id="T-IO-12-a", req="LIB-IO-12", type="Normal", input="Import with the members listed in reverse id order; export", expected="Exactly the keys of 22.1; lists ordered by id; amounts as strings; no users", code='''
def TEST(client, admin):
    data = dataset()
    data["members"].reverse()
    do_import(client, admin, data)
    out = client.get("/api/v1/export", headers=admin).json()
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [m["id"] for m in out["members"]] == [1, 2]
    assert all(isinstance(c["price"], str) for c in out["copies"])
'''),
    dict(id="T-IO-13-a", req="LIB-IO-13", type="Normal", input="`branches.csv` with a name containing a comma (`Campus, North`)", expected="No BOM; lines end with `\\r\\n`; the name is quoted", code='''
def TEST(client, admin):
    do_import(client, admin, dataset())
    raw = client.get("/api/v1/export/branches.csv", headers=admin).content
    assert not raw.startswith(b"\\xef\\xbb\\xbf")
    assert raw.count(b"\\r\\n") == 3 and b"\\n" not in raw.replace(b"\\r\\n", b"")
    assert b'"Campus, North"' in raw
'''),
    dict(id="T-IO-14-a", req="LIB-IO-14", type="Normal", input="`copies.csv` and `members.csv`, `branches.csv`", expected="Null `shelf_location` empty; booleans `true`; amounts `150.00`; dates `YYYY-MM-DD`", code='''
def TEST(client, admin):
    do_import(client, admin, dataset())
    rows = lambda e: list(csv.DictReader(io.StringIO(client.get(f"/api/v1/export/{e}.csv", headers=admin).content.decode("utf-8"))))
    copies = rows("copies")
    assert copies[0]["shelf_location"] == "" and copies[0]["price"] == "150.00" and copies[0]["acquired_on"] == "2025-09-01"
    assert rows("branches")[0]["is_active"] == "true"
    assert rows("members")[0]["university_id"] == "20231234" and rows("members")[1]["university_id"] == ""
'''),
]
