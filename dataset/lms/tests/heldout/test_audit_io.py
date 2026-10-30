"""Heldout tests: module 13 (Audit log, import and export). Generated from cases/audit_io.md."""
import copy as _copy
import csv
import io

from fastapi.testclient import TestClient

import lms
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


def test_t_aud_01_b(client, admin, librarian, branch_a):
    """T-AUD-01-b (LIB-AUD-01): Only one member_registered entry (the rolled-back request leaves none)"""
    register_member(client, librarian, home_branch_id=branch_a["id"], university_id="U9001")
    r = client.post("/api/v1/members", headers=librarian, json={"full_name": "Dup", "email": "dup@uni.edu.tr", "membership_type": "student",
                                                                  "university_id": "U9001", "home_branch_id": branch_a["id"], "password": "Member1234"})
    assert r.status_code == 409
    assert len(audit(client, admin, event="member_registered")) == 1


def test_t_aud_02_b(client, admin):
    """T-AUD-02-b (LIB-AUD-02): No audit details contains a password, a hash or a token"""
    client.post("/api/v1/users", headers=admin, json={"email": "p@library.local", "full_name": "P", "role": "librarian", "password": "Passw0rd1"})
    h = login(client, "p@library.local", "Passw0rd1")
    client.post("/api/v1/auth/change-password", headers=h, json={"current_password": "Passw0rd1", "new_password": "NewPassw0rd"})
    token = h["Authorization"].split()[1]
    dump = str(audit(client, admin, page_size=100)).lower()
    for secret in ("passw0rd1", "newpassw0rd", "scrypt$", token.lower()):
        assert secret not in dump, secret


def test_t_aud_04_a(client, admin):
    """T-AUD-04-a (LIB-AUD-04): 404 or 405 each; the entry still exists"""
    entry = audit(client, admin)[0]
    for method in ("DELETE", "PATCH", "PUT"):
        assert client.request(method, f"/api/v1/audit-log/{entry['id']}", headers=admin, json={}).status_code in {404, 405}
    assert client.delete("/api/v1/audit-log", headers=admin).status_code in {404, 405}
    assert entry["id"] in [e["id"] for e in audit(client, admin, page_size=100)]


def test_t_io_02_a(client, admin, settings, tmp_path, clock):
    """T-IO-02-a (LIB-IO-02): 409 DATABASE_NOT_EMPTY; import succeeds"""
    create_branch(client, admin, "X")
    r = do_import(client, admin, dataset(), expect=409)
    assert error_code(r) == "DATABASE_NOT_EMPTY"
    other = TestClient(lms.create_app(lms.Settings(database_url=f"sqlite:///{tmp_path / 'b.db'}", clock=clock)))
    adm = login(other, "admin@library.local", "ChangeMe123")
    other.post("/api/v1/users", headers=adm, json={"email": "s@library.local", "full_name": "S", "role": "librarian", "password": "Passw0rd1"})
    do_import(other, adm, dataset())


def test_t_io_04_b(client, admin):
    """T-IO-04-b (LIB-IO-04): 422 each"""
    data = dataset()
    data["copies"][1]["book_id"] = 99
    do_import(client, admin, data, expect=422)
    data = dataset()
    data["members"][1]["email"] = data["members"][0]["email"]
    do_import(client, admin, data, expect=422)


def test_t_io_06_b(client, admin):
    """T-IO-06-b (LIB-IO-06): Import succeeds; no fees and no notifications; one data_imported audit entry"""
    data = dataset()
    data["loans"][0]["status"] = "lost"
    data["copies"][0].update(status="lost", current_branch_id=None)
    data["loans"].append({"id": 2, "copy_id": 2, "member_id": 1, "branch_id": 2, "loan_date": "2026-09-20", "due_date": "2026-10-05",
                          "renewal_count": 0, "status": "returned", "returned_on": "2026-10-10", "return_branch_id": 2})
    do_import(client, admin, data)
    assert client.get("/api/v1/fees", headers=admin).json()["total"] == 0
    assert client.get("/api/v1/notifications", headers=admin).json()["total"] == 0
    assert len(audit(client, admin, event="data_imported")) == 1


def test_t_io_08_b(client, admin):
    """T-IO-08-b (LIB-IO-08): Columns exactly as in requirements 22.2"""
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


def test_t_io_10_b(client, admin):
    """T-IO-10-b (LIB-IO-10): Import succeeds with all counts 0"""
    data = {"format_version": 1, "branches": [], "authors": [], "publishers": [], "books": [], "copies": [], "members": [], "loans": []}
    assert set(do_import(client, admin, data).json()["imported"].values()) == {0}


def test_t_io_11_b(client, admin):
    """T-IO-11-b (LIB-IO-11): LoanOut has loan_period_days 7, max_renewals 0, daily_fee '5.00'"""
    do_import(client, admin, dataset())
    loan = client.get("/api/v1/loans/1", headers=admin).json()
    assert (loan["loan_period_days"], loan["max_renewals"], loan["daily_fee"]) == (7, 0, "5.00")


def test_t_io_12_a(client, admin):
    """T-IO-12-a (LIB-IO-12): Exactly the keys of 22.1; lists ordered by id; amounts as strings; no users"""
    data = dataset()
    data["members"].reverse()
    do_import(client, admin, data)
    out = client.get("/api/v1/export", headers=admin).json()
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [m["id"] for m in out["members"]] == [1, 2]
    assert all(isinstance(c["price"], str) for c in out["copies"])


def test_t_io_14_a(client, admin):
    """T-IO-14-a (LIB-IO-14): Null shelf_location empty; booleans true; amounts 150.00; dates YYYY-MM-DD"""
    do_import(client, admin, dataset())
    rows = lambda e: list(csv.DictReader(io.StringIO(client.get(f"/api/v1/export/{e}.csv", headers=admin).content.decode("utf-8"))))
    copies = rows("copies")
    assert copies[0]["shelf_location"] == "" and copies[0]["price"] == "150.00" and copies[0]["acquired_on"] == "2025-09-01"
    assert rows("branches")[0]["is_active"] == "true"
    assert rows("members")[0]["university_id"] == "20231234" and rows("members")[1]["university_id"] == ""
