import copy as _copy
import csv
import io
import sqlite3

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

import lms
from lms.audit.models import AuditEntry
from lms.auth.models import User
from lms.fines.models import Fee
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_branches import lib_h

API = "/api/v1"

DATASET = {
    "format_version": 1,
    "branches": [
        {"id": 1, "code": "MERKEZ", "name": "Central Library", "address": "", "is_active": True},
        {"id": 5, "code": "KAMPUS", "name": "Campus, \"North\"", "address": "Line 1\nLine 2", "is_active": False},
    ],
    "authors": [{"id": 1, "name": "Orhan Pamuk"}, {"id": 3, "name": "Ada Lovelace"}],
    "publishers": [{"id": 1, "name": "Example Publishing"}],
    "books": [
        {"id": 1, "isbn": "9780306406157", "title": "İstanbul Hatırası", "subtitle": None, "author_ids": [3, 1],
         "publisher_id": 1, "publication_year": 2020, "language": "tr", "classification": "813.54"},
        {"id": 2, "isbn": "0-13-110362-8", "title": "The C Programming Language", "subtitle": "2nd ed.",
         "author_ids": [1], "publisher_id": 1, "publication_year": 1988, "language": "en", "classification": "005"},
        {"id": 7, "isbn": "9780201633610", "title": "Design Patterns", "subtitle": None, "author_ids": [3],
         "publisher_id": 1, "publication_year": 1994, "language": "en", "classification": "005.12"},
    ],
    "copies": [
        {"id": 1, "book_id": 1, "barcode": "c000001", "home_branch_id": 1, "current_branch_id": 1,
         "price": "180.00", "status": "available", "acquired_on": "2025-09-01", "shelf_location": "A-12"},
        {"id": 2, "book_id": 1, "barcode": "C000002", "home_branch_id": 1, "current_branch_id": 1,
         "price": "180.50", "status": "on_loan", "acquired_on": "2025-09-01", "shelf_location": None},
        {"id": 3, "book_id": 2, "barcode": "C000003", "home_branch_id": 1, "current_branch_id": 1,
         "price": "60.00", "status": "damaged", "acquired_on": "2025-09-02", "shelf_location": None},
        {"id": 4, "book_id": 2, "barcode": "C000004", "home_branch_id": 1, "current_branch_id": None,
         "price": "60.00", "status": "lost", "acquired_on": "2025-09-02", "shelf_location": None},
        {"id": 5, "book_id": 7, "barcode": "C000005", "home_branch_id": 5, "current_branch_id": 5,
         "price": "75.00", "status": "withdrawn", "acquired_on": "2025-09-03", "shelf_location": None},
    ],
    "members": [
        {"id": 1, "full_name": "Ayşe Yılmaz", "email": "Ayse@Example.edu.tr", "phone": None,
         "membership_type": "student", "university_id": "20231234", "home_branch_id": 1, "status": "active",
         "membership_start": "2026-09-15", "valid_until": "2027-09-14"},
        {"id": 4, "full_name": "Guest Person", "email": "guest@example.com", "phone": "+90 532 123 45 67",
         "membership_type": "guest", "university_id": None, "home_branch_id": 1, "status": "passive",
         "membership_start": "2026-09-01", "valid_until": "2026-11-29"},
    ],
    "loans": [
        {"id": 1, "copy_id": 1, "member_id": 1, "branch_id": 1, "loan_date": "2026-10-01", "due_date": "2026-10-15",
         "renewal_count": 0, "status": "returned", "returned_on": "2026-10-20", "return_branch_id": 1},
        {"id": 2, "copy_id": 2, "member_id": 1, "branch_id": 1, "loan_date": "2026-10-25", "due_date": "2026-11-08",
         "renewal_count": 1, "status": "open", "returned_on": None, "return_branch_id": None},
        {"id": 3, "copy_id": 4, "member_id": 4, "branch_id": 1, "loan_date": "2026-09-10", "due_date": "2026-09-17",
         "renewal_count": 0, "status": "lost", "returned_on": None, "return_branch_id": None},
    ],
}


def data(**changes):
    d = _copy.deepcopy(DATASET)
    d.update(changes)
    return d


def imp(client, hd, body):
    return client.post(f"{API}/import", headers=hd, json=body)


def fields(r):
    e = err(r, 422, "VALIDATION_ERROR")
    return {f["field"]: f["problem"] for f in e["details"]["fields"]}


def normalized(doc):
    """The expected export of DATASET: ISBN-13, upper-case barcodes and codes, lower-case e-mails."""
    d = _copy.deepcopy(DATASET)
    d["books"][1]["isbn"] = "9780131103627"
    d["copies"][0]["barcode"] = "C000001"
    d["members"][0]["email"] = "ayse@example.edu.tr"
    return d


def test_import_and_export_roundtrip(client, admin_h, app):
    r = imp(client, admin_h, DATASET)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "imported": {"branches": 2, "authors": 2, "publishers": 1, "books": 3, "copies": 5, "members": 2, "loans": 3}
    }
    exported = client.get(f"{API}/export", headers=admin_h)
    assert exported.status_code == 200
    assert exported.json() == normalized(DATASET)
    # the ids of the file are kept and new records continue after the highest id
    assert client.get(f"{API}/branches/5", headers=admin_h).json()["code"] == "KAMPUS"
    assert client.get(f"{API}/books/7", headers=admin_h).json()["title"] == "Design Patterns"
    b = client.post(f"{API}/branches", headers=admin_h, json={"code": "NEW", "name": "New"}).json()
    assert b["id"] == 6
    # export -> import into an empty database -> export gives the same document
    other = TestClient(lms.create_app(lms.Settings(database_url="sqlite://", clock=app.state.settings.clock)))
    oh = h(other.post(f"{API}/auth/login", json={"email": "admin@library.local", "password": "ChangeMe123"}).json()["access_token"])
    doc = client.get(f"{API}/export", headers=admin_h).json()
    doc["branches"] = [x for x in doc["branches"] if x["id"] != 6]
    assert imp(other, oh, doc).status_code == 200
    assert other.get(f"{API}/export", headers=oh).json() == doc


def test_import_effects(client, admin_h, app, clock):
    imp(client, admin_h, DATASET)
    with app.state.session_factory() as s:
        users = s.scalars(sa.select(User).where(User.role == "member").order_by(User.id)).all()
        assert [(u.email, u.full_name, u.member_id, u.is_active) for u in users] == [
            ("ayse@example.edu.tr", "Ayşe Yılmaz", 1, True),
            ("guest@example.com", "Guest Person", 4, True),
        ]
        assert s.scalar(sa.select(sa.func.count()).select_from(Fee)) == 0
        assert s.scalar(sa.select(sa.func.count()).select_from(Notification)) == 0
        entries = [a for a in s.scalars(sa.select(AuditEntry)) if a.event == "data_imported"]
        assert len(entries) == 1 and entries[0].details["books"] == 3 and entries[0].actor_user_id == 1
        assert {a.event for a in s.scalars(sa.select(AuditEntry))} == {"login_succeeded", "data_imported"}
    r = client.get(f"{API}/loans/2", headers=admin_h).json()
    assert (r["loan_period_days"], r["max_renewals"], r["daily_fee"]) == (14, 1, "2.00")
    assert r["created_by"] == 1 and r["status"] == "open" and r["is_overdue"] is False
    r = client.get(f"{API}/loans/3", headers=admin_h).json()
    assert (r["loan_period_days"], r["max_renewals"], r["daily_fee"]) == (7, 0, "5.00")
    r = client.get(f"{API}/loans/1", headers=admin_h).json()
    assert r["late_days"] == 3 and r["condition_on_return"] == "good"
    m = client.get(f"{API}/members/4", headers=admin_h).json()
    assert m["member_no"] == "M000004" and m["status"] == "passive" and m["valid_until"] == "2026-11-29"
    # passive member with an open loan is allowed (LIB-IO-06)
    d = data()
    d["loans"][1]["member_id"] = 4
    other = TestClient(lms.create_app(lms.Settings(database_url="sqlite://", clock=clock)))
    oh = h(other.post(f"{API}/auth/login", json={"email": "admin@library.local", "password": "ChangeMe123"}).json()["access_token"])
    assert imp(other, oh, d).status_code == 200


def test_imported_members_cannot_log_in_until_reset(client, admin_h):
    imp(client, admin_h, DATASET)
    for _ in range(2):
        err(
            client.post(f"{API}/auth/login", json={"email": "ayse@example.edu.tr", "password": "Passw0rd1"}),
            401,
            "INVALID_CREDENTIALS",
        )
    uid = client.get(f"{API}/members/1", headers=admin_h).json()
    users = client.get(f"{API}/users?role=member", headers=admin_h)
    assert users.status_code == 200
    user = next(u for u in users.json()["items"] if u["member_id"] == 1)
    assert client.post(f"{API}/users/{user['id']}/reset-password", headers=admin_h, json={"new_password": "Newpass123"}).status_code == 204
    t = token_of(client, "ayse@example.edu.tr", "Newpass123")
    assert client.get(f"{API}/members/me", headers=h(t)).json()["id"] == uid["id"]


def test_import_permissions_and_not_empty(client, admin_h):
    lh = lib_h(client, admin_h)
    err(imp(client, lh, DATASET), 403, "FORBIDDEN")
    err(client.post(f"{API}/import", json=DATASET), 401, "UNAUTHENTICATED")
    err(client.get(f"{API}/export", headers=lh), 403, "FORBIDDEN")
    err(client.get(f"{API}/export"), 401, "UNAUTHENTICATED")
    err(client.get(f"{API}/export/books.csv", headers=lh), 403, "FORBIDDEN")
    assert imp(client, admin_h, DATASET).status_code == 200
    err(imp(client, admin_h, DATASET), 409, "DATABASE_NOT_EMPTY")


def test_not_empty_with_a_single_branch(client, admin_h):
    client.post(f"{API}/branches", headers=admin_h, json={"code": "AB", "name": "x"})
    err(imp(client, admin_h, DATASET), 409, "DATABASE_NOT_EMPTY")


def test_staff_users_do_not_block_import(client, admin_h):
    lib_h(client, admin_h)
    assert imp(client, admin_h, DATASET).status_code == 200


def test_empty_dataset(client, admin_h):
    empty = {"format_version": 1, **{k: [] for k in ("branches", "authors", "publishers", "books", "copies", "members", "loans")}}
    r = imp(client, admin_h, empty)
    assert r.json() == {"imported": {k: 0 for k in empty if k != "format_version"}}
    assert client.get(f"{API}/export", headers=admin_h).json() == empty


@pytest.mark.parametrize(
    "mutate, field",
    [
        (lambda d: d.update(format_version=2), "format_version"),
        (lambda d: d.update(format_version="1"), "format_version"),
        (lambda d: d.update(format_version=True), "format_version"),
        (lambda d: d.pop("format_version"), "format_version"),
        (lambda d: d.pop("loans"), "loans"),
        (lambda d: d.update(loans={}), "loans"),
        (lambda d: d.update(extra=[]), "extra"),
        (lambda d: d["branches"][0].update(code="A"), "branches[0].code"),
        (lambda d: d["branches"][1].update(code="merkez"), "branches[1].code"),
        (lambda d: d["branches"][0].update(color="red"), "branches[0].color"),
        (lambda d: d["branches"][0].update(is_active="yes"), "branches[0].is_active"),
        (lambda d: d["branches"][0].pop("name"), "branches[0].name"),
        (lambda d: d["branches"][0].update(id=0), "branches[0].id"),
        (lambda d: d["branches"][1].update(id=1), "branches[1].id"),
        (lambda d: d["authors"][0].update(name="  "), "authors[0].name"),
        (lambda d: d["publishers"].append({"id": 2, "name": "EXAMPLE publishing"}), "publishers[1].name"),
        (lambda d: d["books"][0].update(isbn="1234567890"), "books[0].isbn"),
        (lambda d: d["books"][1].update(isbn="9780306406157"), "books[1].isbn"),
        (lambda d: d["books"][1].update(isbn="0-306-40615-2"), "books[1].isbn"),
        (lambda d: d["books"][0].update(author_ids=[]), "books[0].author_ids"),
        (lambda d: d["books"][0].update(author_ids=[1, 1]), "books[0].author_ids"),
        (lambda d: d["books"][0].update(author_ids=[99]), "books[0].author_ids"),
        (lambda d: d["books"][0].update(publisher_id=99), "books[0].publisher_id"),
        (lambda d: d["books"][0].update(publication_year=2027), "books[0].publication_year"),
        (lambda d: d["books"][0].update(publication_year=1449), "books[0].publication_year"),
        (lambda d: d["books"][0].update(language="TR"), "books[0].language"),
        (lambda d: d["books"][0].update(classification="81"), "books[0].classification"),
        (lambda d: d["copies"][0].update(book_id=99), "copies[0].book_id"),
        (lambda d: d["copies"][0].update(home_branch_id=99), "copies[0].home_branch_id"),
        (lambda d: d["copies"][0].update(current_branch_id=99), "copies[0].current_branch_id"),
        (lambda d: d["copies"][0].update(barcode="bad code"), "copies[0].barcode"),
        (lambda d: d["copies"][1].update(barcode="c000001"), "copies[1].barcode"),
        (lambda d: d["copies"][0].update(price=180), "copies[0].price"),
        (lambda d: d["copies"][0].update(price="0.00"), "copies[0].price"),
        (lambda d: d["copies"][0].update(price="1.234"), "copies[0].price"),
        (lambda d: d["copies"][0].update(status="on_hold"), "copies[0].status"),
        (lambda d: d["copies"][0].update(status="in_transfer"), "copies[0].status"),
        (lambda d: d["copies"][0].update(current_branch_id=None), "copies[0].current_branch_id"),
        (lambda d: d["copies"][0].update(acquired_on="2026-11-03"), "copies[0].acquired_on"),
        (lambda d: d["copies"][0].update(acquired_on="2025-9-1"), "copies[0].acquired_on"),
        (lambda d: d["members"][0].update(email="nope"), "members[0].email"),
        (lambda d: d["members"][1].update(email="AYSE@example.edu.tr"), "members[1].email"),
        (lambda d: d["members"][0].update(phone="12"), "members[0].phone"),
        (lambda d: d["members"][0].update(university_id=None), "members[0].university_id"),
        (lambda d: d["members"][0].update(university_id="ab"), "members[0].university_id"),
        (lambda d: d["members"][1].update(university_id="12345678"), "members[1].university_id"),
        (lambda d: d["members"][1].update(phone=None), "members[1].phone"),
        (lambda d: d["members"][0].update(membership_type="vip"), "members[0].membership_type"),
        (lambda d: d["members"][0].update(status="deleted"), "members[0].status"),
        (lambda d: d["members"][0].update(home_branch_id=99), "members[0].home_branch_id"),
        (lambda d: d["members"][0].update(valid_until="2026-09-14"), "members[0].valid_until"),
        (lambda d: d["members"][1].update(university_id="20231234", membership_type="student"), "members[1].university_id"),
        (lambda d: d["loans"][0].update(returned_on=None), "loans[0].returned_on"),
        (lambda d: d["loans"][0].update(return_branch_id=None), "loans[0].return_branch_id"),
        (lambda d: d["loans"][0].update(returned_on="2026-09-30"), "loans[0].returned_on"),
        (lambda d: d["loans"][1].update(returned_on="2026-10-30"), "loans[1].returned_on"),
        (lambda d: d["loans"][2].update(returned_on="2026-10-30"), "loans[2].returned_on"),
        (lambda d: d["loans"][1].update(status="bogus"), "loans[1].status"),
        (lambda d: d["loans"][0].update(copy_id=99), "loans[0].copy_id"),
        (lambda d: d["loans"][0].update(member_id=99), "loans[0].member_id"),
        (lambda d: d["loans"][0].update(branch_id=99), "loans[0].branch_id"),
        (lambda d: d["loans"][0].update(return_branch_id=99), "loans[0].return_branch_id"),
        (lambda d: d["loans"][0].update(renewal_count=-1), "loans[0].renewal_count"),
        (lambda d: d["loans"][0].update(due_date="2026-09-30"), "loans[0].due_date"),
        (lambda d: d["loans"][1].update(copy_id=3), "loans[1].copy_id"),  # open loan, copy damaged
        (lambda d: d["copies"][1].update(status="available"), "loans[1].copy_id"),
        (lambda d: d["copies"][3].update(status="available", current_branch_id=1), "loans[2].copy_id"),
        (lambda d: d["copies"][3].update(current_branch_id=1), "loans[2].copy_id"),
        (lambda d: d["loans"].append({**d["loans"][1], "id": 9, "member_id": 4}), "loans[3].copy_id"),
    ],
)
def test_import_validation(client, admin_h, app, mutate, field):
    d = data()
    mutate(d)
    problems = fields(imp(client, admin_h, d))
    assert field in problems, problems
    # all or nothing
    with app.state.session_factory() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(AuditEntry).where(AuditEntry.event == "data_imported")) == 0
    assert client.get(f"{API}/branches", headers=admin_h).json()["total"] == 0
    assert client.get(f"{API}/books", headers=admin_h).json()["total"] == 0


def test_import_rejects_non_objects(client, admin_h):
    for body in ([], "text", 5, None):
        err(client.post(f"{API}/import", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    d = data(branches=["x", 5, {"id": 1, "code": "AB", "name": "ok"}])
    p = fields(imp(client, admin_h, d))
    assert "branches[0]" in p and "branches[1]" in p


def test_import_reports_at_most_100_problems(client, admin_h):
    d = data(authors=[{"id": i, "name": ""} for i in range(1, 301)])
    e = err(imp(client, admin_h, d), 422, "VALIDATION_ERROR")
    assert len(e["details"]["fields"]) == 100
    assert e["details"]["fields"][0]["field"] == "authors[0].name"


def test_import_duplicate_email_with_staff(client, admin_h):
    make_user(client, admin_h, "ayse@example.edu.tr", "librarian")
    assert "members[0].email" in fields(imp(client, admin_h, DATASET))


def test_import_isbn10_and_barcode_normalization(client, admin_h):
    imp(client, admin_h, DATASET)
    b = client.get(f"{API}/books/2", headers=admin_h).json()
    assert b["isbn"] == "9780131103627" and [a["name"] for a in client.get(f"{API}/books/1", headers=admin_h).json()["authors"]] == [
        "Ada Lovelace",
        "Orhan Pamuk",
    ]
    assert client.get(f"{API}/copies/by-barcode/c000001", headers=admin_h).json()["id"] == 1


# --- CSV ----------------------------------------------------------------------------------


def parse_csv(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert not r.content.startswith(b"\xef\xbb\xbf")
    assert r.text.endswith("\r\n") and "\n" not in r.text.replace("\r\n", "").replace("Line 1\nLine 2", "")
    return list(csv.reader(io.StringIO(r.text, newline="")))


def test_csv_exports(client, admin_h, app):
    imp(client, admin_h, DATASET)
    rows = parse_csv(client.get(f"{API}/export/branches.csv", headers=admin_h))
    assert rows[0] == ["id", "code", "name", "address", "is_active"]
    assert rows[1] == ["1", "MERKEZ", "Central Library", "", "true"]
    assert rows[2] == ["5", "KAMPUS", 'Campus, "North"', "Line 1\nLine 2", "false"]
    raw = client.get(f"{API}/export/branches.csv", headers=admin_h).content
    assert raw.startswith(b"id,code,name,address,is_active\r\n1,MERKEZ,Central Library,,true\r\n")
    assert b'5,KAMPUS,"Campus, ""North""","Line 1\nLine 2",false\r\n' in raw

    rows = parse_csv(client.get(f"{API}/export/books.csv", headers=admin_h))
    assert rows[0] == ["id", "isbn", "title", "subtitle", "authors", "publisher", "publication_year", "language", "classification"]
    assert rows[1] == ["1", "9780306406157", "İstanbul Hatırası", "", "Ada Lovelace; Orhan Pamuk", "Example Publishing", "2020", "tr", "813.54"]
    assert rows[2][3] == "2nd ed." and [r[0] for r in rows[1:]] == ["1", "2", "7"]

    rows = parse_csv(client.get(f"{API}/export/copies.csv", headers=admin_h))
    assert rows[0] == ["id", "book_id", "barcode", "home_branch_id", "current_branch_id", "price", "status", "acquired_on", "shelf_location"]
    assert rows[1] == ["1", "1", "C000001", "1", "1", "180.00", "available", "2025-09-01", "A-12"]
    assert rows[4] == ["4", "2", "C000004", "1", "", "60.00", "lost", "2025-09-02", ""]

    rows = parse_csv(client.get(f"{API}/export/members.csv", headers=admin_h))
    assert rows[0] == ["id", "member_no", "full_name", "email", "phone", "membership_type", "university_id", "home_branch_id", "status", "membership_start", "valid_until"]
    assert rows[1] == ["1", "M000001", "Ayşe Yılmaz", "ayse@example.edu.tr", "", "student", "20231234", "1", "active", "2026-09-15", "2027-09-14"]
    assert rows[2][4] == "+90 532 123 45 67" and rows[2][6] == ""

    rows = parse_csv(client.get(f"{API}/export/loans.csv", headers=admin_h))
    assert rows[0] == ["id", "copy_id", "member_id", "branch_id", "loan_date", "due_date", "renewal_count", "status", "returned_on", "return_branch_id", "late_days"]
    assert rows[1] == ["1", "1", "1", "1", "2026-10-01", "2026-10-15", "0", "returned", "2026-10-20", "1", "3"]
    assert rows[2][7:] == ["open", "", "", ""]
    err(client.get(f"{API}/export/users.csv", headers=admin_h), 404, "NOT_FOUND")
    err(client.get(f"{API}/export/authors.csv", headers=admin_h), 404, "NOT_FOUND")


def test_csv_empty_has_header_only(client, admin_h):
    assert client.get(f"{API}/export/loans.csv", headers=admin_h).content == (
        b"id,copy_id,member_id,branch_id,loan_date,due_date,renewal_count,status,returned_on,return_branch_id,late_days\r\n"
    )


def test_export_audit(client, admin_h, app):
    client.get(f"{API}/export", headers=admin_h)
    client.get(f"{API}/export/copies.csv", headers=admin_h)
    entries = audit(app, "data_exported")
    assert [(e.details["entity"], e.actor_user_id) for e in entries] == [("all", 1), ("copies", 1)]
    r = client.get(f"{API}/audit-log?event=data_exported", headers=admin_h).json()
    assert r["total"] == 2


def test_export_after_activity(client, admin_h):
    """Records created through the API export in the same format (amounts, ISBN-13, author order)."""
    from tests.test_catalog import book_body, mk_author, mk_copy, mk_publisher
    from tests.test_branches import mk_branch

    mk_branch(client, admin_h, "MERKEZ")
    mk_author(client, admin_h)
    mk_author(client, admin_h, "Second Author")
    mk_publisher(client, admin_h)
    client.post(f"{API}/books", headers=admin_h, json=book_body(author_ids=[2, 1], isbn="0-306-40615-2"))
    assert mk_copy(client, admin_h).status_code == 201
    doc = client.get(f"{API}/export", headers=admin_h).json()
    assert doc["books"][0]["isbn"] == "9780306406157" and doc["books"][0]["author_ids"] == [2, 1]
    assert doc["copies"][0]["price"] == "50.00" and doc["copies"][0]["acquired_on"] == "2026-10-01"
    assert set(doc) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert set(doc["branches"][0]) == {"id", "code", "name", "address", "is_active"}


# --- service interface ----------------------------------------------------------------------


def test_import_dataset_and_export_dataset_functions(tmp_path, clock):
    settings = lms.Settings(database_url=f"sqlite:///{tmp_path}/x.db", clock=clock)
    counts = lms.import_dataset(settings, DATASET)
    assert counts == {"branches": 2, "authors": 2, "publishers": 1, "books": 3, "copies": 5, "members": 2, "loans": 3}
    assert lms.export_dataset(settings) == normalized(DATASET)
    with pytest.raises(RuntimeError):
        lms.import_dataset(settings, DATASET)
    app = lms.create_app(settings)  # the schema and bootstrap admin already exist
    c = TestClient(app)
    hd = h(c.post(f"{API}/auth/login", json={"email": "admin@library.local", "password": "ChangeMe123"}).json()["access_token"])
    assert c.get(f"{API}/export", headers=hd).json() == normalized(DATASET)
    assert c.get(f"{API}/branches/5", headers=hd).json()["name"].startswith("Campus")


def test_import_dataset_validation_error(tmp_path, clock):
    settings = lms.Settings(database_url=f"sqlite:///{tmp_path}/y.db", clock=clock)
    bad = data()
    bad["members"][0]["email"] = "nope"
    with pytest.raises(ValueError, match=r"members\[0\]\.email"):
        lms.import_dataset(settings, bad)
    # nothing was imported
    assert lms.export_dataset(settings)["members"] == []
    assert lms.import_dataset(settings, DATASET)["members"] == 2


def test_in_memory_settings_share_state_with_app(clock):
    settings = lms.Settings(database_url="sqlite://", clock=clock)
    lms.import_dataset(settings, DATASET)
    app = lms.create_app(settings)
    c = TestClient(app)
    hd = h(c.post(f"{API}/auth/login", json={"email": "admin@library.local", "password": "ChangeMe123"}).json()["access_token"])
    assert c.get(f"{API}/members/4", headers=hd).status_code == 200
    # a different Settings object never shares the database
    other = lms.Settings(database_url="sqlite://", clock=clock)
    assert lms.export_dataset(other)["branches"] == []


def test_failed_import_keeps_nothing_in_file_db(tmp_path, clock):
    path = tmp_path / "z.db"
    settings = lms.Settings(database_url=f"sqlite:///{path}", clock=clock)
    bad = data()
    bad["loans"][0]["copy_id"] = 99
    with pytest.raises(ValueError):
        lms.import_dataset(settings, bad)
    con = sqlite3.connect(path)
    assert con.execute("select count(*) from branches").fetchone() == (0,)
    assert con.execute("select count(*) from audit_entries where event='data_imported'").fetchone() == (0,)


def test_e2e_import_export_search(client, admin_h):
    """LIB-E2E-11."""
    imp(client, admin_h, DATASET)
    r = client.get(f"{API}/search/books?q=istanbul", headers=admin_h).json()
    assert [i["book"]["title"] for i in r["items"]] == ["İstanbul Hatırası"]
    assert r["items"][0]["loan_count"] == 2
    err(client.post(f"{API}/auth/login", json={"email": "guest@example.com", "password": "Passw0rd1"}), 401, "INVALID_CREDENTIALS")


def test_openapi_lists_new_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/import", "/api/v1/export", "/api/v1/export/{entity}.csv", "/api/v1/suppliers",
        "/api/v1/suppliers/{supplier_id}", "/api/v1/purchase-orders", "/api/v1/purchase-orders/{order_id}",
        "/api/v1/purchase-orders/{order_id}/submit", "/api/v1/purchase-orders/{order_id}/cancel",
        "/api/v1/purchase-orders/{order_id}/receive",
    ):
        assert path in paths
