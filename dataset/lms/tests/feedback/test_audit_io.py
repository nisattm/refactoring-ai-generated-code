"""Feedback tests: module 13 (Audit log, import and export). Generated from cases/audit_io.md."""
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


def test_t_aud_01_a(client, admin):
    """T-AUD-01-a (LIB-AUD-01): Entry user_created with actor_user_id = admin and entity_type user; entry login_failed with actor_user_id null"""
    me = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    uid = client.post("/api/v1/users", headers=admin, json={"email": "s@library.local", "full_name": "S", "role": "librarian", "password": "Passw0rd1"}).json()["id"]
    created = audit(client, admin, event="user_created")
    assert [(e["actor_user_id"], e["entity_type"], e["entity_id"]) for e in created] == [(me, "user", uid)]
    client.post("/api/v1/auth/login", json={"email": "ghost@library.local", "password": "Wrong0000"})
    failed = audit(client, admin, event="login_failed")
    assert len(failed) == 1 and failed[0]["actor_user_id"] is None


def test_t_aud_02_a(client, admin):
    """T-AUD-02-a (LIB-AUD-02): user_updated details {'full_name': {'old': 'Old', 'new': 'New'}}"""
    uid = client.post("/api/v1/users", headers=admin, json={"email": "o@library.local", "full_name": "Old", "role": "librarian", "password": "Passw0rd1"}).json()["id"]
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"full_name": "New"})
    entry = audit(client, admin, event="user_updated", entity_id=uid)[0]
    assert entry["details"]["full_name"] == {"old": "Old", "new": "New"}


def test_t_aud_03_a(client, admin, librarian, branch_a):
    """T-AUD-03-a (LIB-AUD-03): Ordered by id descending; filters match; librarian gets 403"""
    register_member(client, librarian, home_branch_id=branch_a["id"])
    entries = audit(client, admin)
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)
    assert {e["event"] for e in audit(client, admin, entity_type="member")} >= {"member_registered"}
    assert audit(client, admin, **{"from": "2026-11-03", "to": "2026-11-30"}) == []
    assert len(audit(client, admin, **{"from": "2026-11-02", "to": "2026-11-02"})) == len(entries)
    assert client.get("/api/v1/audit-log", headers=librarian).status_code == 403


def test_t_io_01_a(client, admin):
    """T-IO-01-a (LIB-IO-01): 200 with counts branches 2, authors 1, publishers 1, books 1, copies 2, members 2, loans 1"""
    r = do_import(client, admin, dataset())
    assert r.json() == {"imported": {"branches": 2, "authors": 1, "publishers": 1, "books": 1, "copies": 2, "members": 2, "loans": 1}}


def test_t_io_03_a(client, admin):
    """T-IO-03-a (LIB-IO-03): 422 with field members[1].email; nothing imported (no branches)"""
    data = dataset()
    data["members"][1]["email"] = "bad"
    r = do_import(client, admin, data, expect=422)
    assert "members[1].email" in {f["field"] for f in r.json()["error"]["details"]["fields"]}
    assert client.get("/api/v1/branches", headers=admin).json()["total"] == 0


def test_t_io_04_a(client, admin):
    """T-IO-04-a (LIB-IO-04): GET /api/v1/books/7 works; ISBN stored as 9780306406157"""
    data = dataset()
    data["books"][0]["isbn"] = "0-306-40615-2"
    do_import(client, admin, data)
    b = client.get("/api/v1/books/7", headers=admin).json()
    assert b["id"] == 7 and b["isbn"] == "9780306406157"


def test_t_io_05_a(client, admin):
    """T-IO-05-a (LIB-IO-05): 401 INVALID_CREDENTIALS; then 200"""
    do_import(client, admin, dataset())
    r = client.post("/api/v1/auth/login", json={"email": "ayse@example.edu.tr", "password": "Member1234"})
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"
    users = client.get("/api/v1/users", headers=admin, params={"q": "ayse@example.edu.tr"}).json()["items"]
    client.post(f"/api/v1/users/{users[0]['id']}/reset-password", headers=admin, json={"new_password": "Member1234"})
    assert client.post("/api/v1/auth/login", json={"email": "ayse@example.edu.tr", "password": "Member1234"}).status_code == 200


def test_t_io_06_a(client, admin):
    """T-IO-06-a (LIB-IO-06): 422 each"""
    data = dataset()
    data["copies"][0]["status"] = "available"
    do_import(client, admin, data, expect=422)
    data = dataset()
    data["loans"][0]["status"] = "lost"
    data["copies"][0]["status"] = "lost"
    do_import(client, admin, data, expect=422)


def test_t_io_07_a(client, admin, tmp_path, clock):
    """T-IO-07-a (LIB-IO-07): Both exports are equal to each other and to the imported data"""
    data = dataset()
    do_import(client, admin, data)
    first = client.get("/api/v1/export", headers=admin).json()
    assert first == data
    other = TestClient(lms.create_app(lms.Settings(database_url=f"sqlite:///{tmp_path / 'c.db'}", clock=clock)))
    adm = login(other, "admin@library.local", "ChangeMe123")
    do_import(other, adm, _copy.deepcopy(first))
    assert other.get("/api/v1/export", headers=adm).json() == first


def test_t_io_08_a(client, admin, librarian):
    """T-IO-08-a (LIB-IO-08): CSV with header id,code,name,address,is_active and 2 rows ordered by id; 404 NOT_FOUND; 403"""
    do_import(client, admin, dataset())
    r = client.get("/api/v1/export/branches.csv", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0] == ["id", "code", "name", "address", "is_active"] and [row[0] for row in rows[1:]] == ["1", "2"]
    r = client.get("/api/v1/export/users.csv", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
    assert client.get("/api/v1/export/branches.csv", headers=librarian).status_code == 403


def test_t_io_09_a(client, admin):
    """T-IO-09-a (LIB-IO-09): Two data_exported entries with entity all and books"""
    client.get("/api/v1/export", headers=admin)
    client.get("/api/v1/export/books.csv", headers=admin)
    entries = audit(client, admin, event="data_exported")
    assert len(entries) == 2
    values = {v for e in entries for v in e["details"].values() if isinstance(v, str)}
    assert {"all", "books"} <= values


def test_t_io_10_a(client, admin):
    """T-IO-10-a (LIB-IO-10): 422 each"""
    data = dataset(); data["format_version"] = 2
    do_import(client, admin, data, expect=422)
    data = dataset(); del data["loans"]
    do_import(client, admin, data, expect=422)
    data = dataset(); data["branches"][0]["notes"] = "x"
    do_import(client, admin, data, expect=422)


def test_t_io_11_a(client, admin):
    """T-IO-11-a (LIB-IO-11): 422 each"""
    for status in ("on_hold", "in_transfer"):
        data = dataset()
        data["copies"][1]["status"] = status
        do_import(client, admin, data, expect=422)


def test_t_io_13_a(client, admin):
    """T-IO-13-a (LIB-IO-13): No BOM; lines end with \r\n; the name is quoted"""
    do_import(client, admin, dataset())
    raw = client.get("/api/v1/export/branches.csv", headers=admin).content
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.count(b"\r\n") == 3 and b"\n" not in raw.replace(b"\r\n", b"")
    assert b'"Campus, North"' in raw
