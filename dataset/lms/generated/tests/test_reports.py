import csv
import io

from tests.test_auth import admin_h, err, h, token_of  # noqa: F401
from tests.test_loans import API, at, copy_of, lend, lib, member_h, mk_book, mk_member, new_copy, ret  # noqa: F401
from tests.test_reservations import reserve  # noqa: F401


def rep(client, hd, name, **params):
    return client.get(f"{API}/reports/{name}", headers=hd, params=params)


def test_permissions(client, lib, admin_h):
    mk_member(client, lib)
    paths = {
        "most-borrowed": {"from": "2026-11-01", "to": "2026-11-30"},
        "overdue": {},
        "monthly-summary": {"year": 2026, "month": 11},
        "inventory": {},
    }
    for name, params in paths.items():
        assert err(client.get(f"{API}/reports/{name}", params=params), 401, "UNAUTHENTICATED")
        assert err(rep(client, member_h(client, 1), name, **params), 403, "FORBIDDEN")
        assert rep(client, lib, name, **params).status_code == 200
        assert rep(client, admin_h, name, **params).status_code == 200


def test_most_borrowed(client, lib):
    b0, b1, b2 = (mk_book(client, lib, i) for i in range(3))
    c0, c1, c2 = (new_copy(client, lib, b, f"BC-000{i}") for i, b in enumerate((b0, b1, b2)))
    m = mk_member(client, lib)
    m2 = mk_member(client, lib, 2)
    for member, copy in ((m, c0), (m2, c1), (m, c1), (m2, c0), (m, c2)):
        loan = lend(client, lib, member, copy).json()
        assert ret(client, lib, loan["id"], branch=2 if copy == c2 else 1).status_code == 200
    r = rep(client, lib, "most-borrowed", **{"from": "2026-11-02", "to": "2026-11-02"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert list(body) == ["from", "to", "branch_id", "items"]
    assert body["from"] == "2026-11-02" and body["to"] == "2026-11-02" and body["branch_id"] is None
    assert body["items"] == [
        {"rank": 1, "book_id": b0, "title": "Book 0", "isbn": "9780306406157", "loan_count": 2},
        {"rank": 2, "book_id": b1, "title": "Book 1", "isbn": "9780131103627", "loan_count": 2},
        {"rank": 3, "book_id": b2, "title": "Book 2", "isbn": "9780201633610", "loan_count": 1},
    ]
    assert [i["rank"] for i in rep(client, lib, "most-borrowed", **{"from": "2026-11-02", "to": "2026-11-02", "limit": 2}).json()["items"]] == [1, 2]
    assert rep(client, lib, "most-borrowed", **{"from": "2026-11-03", "to": "2026-11-10"}).json()["items"] == []
    r = rep(client, lib, "most-borrowed", **{"from": "2026-11-02", "to": "2026-11-02", "branch_id": 2})
    assert r.json()["branch_id"] == 2 and r.json()["items"] == []  # loans were made at branch 1


def test_most_borrowed_validation(client, lib):
    ok = {"from": "2026-01-01", "to": "2027-01-01"}  # 365 days apart: 366 days including both ends
    assert rep(client, lib, "most-borrowed", **ok).status_code == 200
    assert err(rep(client, lib, "most-borrowed", **{"from": "2026-01-01", "to": "2027-01-02"}), 422, "VALIDATION_ERROR")
    assert err(rep(client, lib, "most-borrowed", **{"from": "2026-02-01", "to": "2026-01-01"}), 422, "VALIDATION_ERROR")
    e = err(rep(client, lib, "most-borrowed"), 422, "VALIDATION_ERROR")
    assert {f["field"] for f in e["details"]["fields"]} == {"from", "to"}
    assert err(rep(client, lib, "most-borrowed", **{"from": "x", "to": "2026-01-01"}), 422, "VALIDATION_ERROR")
    for bad in (0, 101):
        assert err(rep(client, lib, "most-borrowed", limit=bad, **ok), 422, "VALIDATION_ERROR")
    assert err(rep(client, lib, "most-borrowed", format="xml", **ok), 422, "VALIDATION_ERROR")


def test_most_borrowed_csv(client, lib):
    b = mk_book(client, lib, 0)
    c = new_copy(client, lib, b, "BC-0001")
    m = mk_member(client, lib)
    assert lend(client, lib, m, c).status_code == 201
    r = rep(client, lib, "most-borrowed", format="csv", **{"from": "2026-11-02", "to": "2026-11-02"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.content.decode("utf-8") == "rank,book_id,title,isbn,loan_count\r\n1,1,Book 0,9780306406157,1\r\n"


def make_overdue(client, lib, clock):
    b0, b1 = mk_book(client, lib, 0), mk_book(client, lib, 1)
    c0 = new_copy(client, lib, b0, "BC-0001")
    c1 = new_copy(client, lib, b1, "BC-0002", branch=2)
    m = mk_member(client, lib)
    m2 = mk_member(client, lib, 2, "guest")
    assert lend(client, lib, m, c0).status_code == 201  # student: due 2026-11-16
    assert lend(client, lib, m2, c1).status_code == 201  # guest: due 2026-11-09
    return m, m2


def test_overdue_report(client, lib, clock):
    make_overdue(client, lib, clock)
    assert rep(client, lib, "overdue").json() == {
        "items": [], "page": 1, "page_size": 20, "total": 0, "total_accrued": "0.00"
    }
    at(clock, 2026, 11, 10)  # guest loan: 1 working day late = 5.00
    body = rep(client, lib, "overdue").json()
    assert body["total"] == 1 and body["total_accrued"] == "5.00"
    assert body["items"] == [{
        "loan_id": 2, "member_id": 2, "member_no": "M000002", "member_name": "Ayşe Yılmaz",
        "book_id": 2, "title": "Book 1", "copy_barcode": "BC-0002", "due_date": "2026-11-09",
        "late_days": 1, "accrued_late_fee": "5.00",
    }]
    at(clock, 2026, 11, 18)  # guest: 7 days late = 35.00; student: 2 days late = 4.00
    body = rep(client, lib, "overdue").json()
    assert [i["loan_id"] for i in body["items"]] == [2, 1]  # by due date
    assert [i["accrued_late_fee"] for i in body["items"]] == ["35.00", "4.00"]
    assert body["total_accrued"] == "39.00"
    body = rep(client, lib, "overdue", page_size=1, page=2).json()
    assert (body["total"], body["total_accrued"], [i["loan_id"] for i in body["items"]]) == (2, "39.00", [1])
    assert [i["loan_id"] for i in rep(client, lib, "overdue", branch_id=1).json()["items"]] == [1]
    assert rep(client, lib, "overdue", branch_id=1).json()["total_accrued"] == "4.00"
    r = rep(client, lib, "overdue", format="csv", page_size=1)
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    rows = list(csv.reader(io.StringIO(r.text, newline="")))
    assert rows[0] == ["loan_id", "member_id", "member_no", "member_name", "book_id", "title", "copy_barcode",
                       "due_date", "late_days", "accrued_late_fee"]
    assert [row[0] for row in rows[1:]] == ["2", "1"] and rows[1][9] == "35.00"
    assert r.text.endswith("\r\n")
    # returned loans leave the report
    assert ret(client, lib, 2).status_code == 200
    assert [i["loan_id"] for i in rep(client, lib, "overdue").json()["items"]] == [1]


def test_overdue_not_late_on_weekend(client, lib, clock):
    make_overdue(client, lib, clock)
    at(clock, 2026, 11, 14)  # Saturday; student due 2026-11-16, guest due Monday 2026-11-09 -> 4 late days
    body = rep(client, lib, "overdue").json()
    assert [(i["loan_id"], i["late_days"]) for i in body["items"]] == [(2, 4)]


def test_monthly_summary(client, lib, admin_h, clock):
    b = mk_book(client, lib, 0)
    c = new_copy(client, lib, b, "BC-0001", price="80.00")
    m = mk_member(client, lib)
    m2 = mk_member(client, lib, 2)
    loan = lend(client, lib, m, c).json()  # 2026-11-02
    assert reserve(client, member_h(client, 2), b, branch=1).status_code == 201
    at(clock, 2026, 11, 20)
    assert client.post(f"{API}/loans/{loan['id']}/report-lost", headers=lib).status_code == 200
    # fees: late 8.00 (4 days), lost 80.00, processing 25.00 = 113.00 (loan branch 1)
    r = client.post(f"{API}/members/{m}/payments", headers=lib, json={"amount": "10.00", "method": "cash"})
    assert r.status_code == 201
    admin_h.update(h(token_of(client, "admin@library.local", "ChangeMe123")))  # the clock moved on
    assert client.post(f"{API}/fees/3/waive", headers=admin_h, json={"reason": "goodwill waive"}).status_code == 200
    body = rep(client, lib, "monthly-summary", year=2026, month=11).json()
    assert body == {
        "year": 2026, "month": 11, "branch_id": None,
        "new_members": 2, "loans_created": 1, "loans_returned": 0, "loans_lost": 1,
        "reservations_created": 1, "reservations_fulfilled": 0, "reservations_expired": 0,
        "fees_created": "113.00", "payments_received": "10.00", "fees_waived": "25.00",
    }
    one = rep(client, lib, "monthly-summary", year=2026, month=11, branch_id=1).json()
    assert {k: v for k, v in one.items() if k != "branch_id"} == {k: v for k, v in body.items() if k != "branch_id"}
    two = rep(client, lib, "monthly-summary", year=2026, month=11, branch_id=2).json()
    assert two["new_members"] == 0 and two["loans_created"] == 0 and two["loans_lost"] == 0
    assert (two["fees_created"], two["payments_received"], two["fees_waived"]) == ("0.00", "0.00", "0.00")
    assert two["reservations_created"] == 0
    other = rep(client, lib, "monthly-summary", year=2026, month=10).json()
    assert other["loans_created"] == 0 and other["fees_created"] == "0.00" and other["new_members"] == 0
    assert m2


def test_monthly_summary_returns_and_reservations(client, lib, clock):
    b = mk_book(client, lib, 0)
    c = new_copy(client, lib, b, "BC-0001")
    m = mk_member(client, lib)
    loan = lend(client, lib, m, c).json()
    assert ret(client, lib, loan["id"], branch=2).status_code == 200
    body = rep(client, lib, "monthly-summary", year=2026, month=11).json()
    assert body["loans_returned"] == 1
    assert rep(client, lib, "monthly-summary", year=2026, month=11, branch_id=2).json()["loans_returned"] == 1
    assert rep(client, lib, "monthly-summary", year=2026, month=11, branch_id=1).json()["loans_returned"] == 0
    assert rep(client, lib, "monthly-summary", year=2026, month=11, branch_id=1).json()["loans_created"] == 1


def test_monthly_summary_validation(client, lib):
    for params in ({"year": 2026}, {"month": 11}, {"year": 2026, "month": 0}, {"year": 2026, "month": 13},
                   {"year": 1899, "month": 1}, {"year": 2101, "month": 1}, {"year": 2026, "month": 12},
                   {"year": 2027, "month": 1}):
        assert err(rep(client, lib, "monthly-summary", **params), 422, "VALIDATION_ERROR"), params
    assert rep(client, lib, "monthly-summary", year=2026, month=11).status_code == 200  # current month
    assert rep(client, lib, "monthly-summary", year=1900, month=1).status_code == 200


def test_inventory(client, lib):
    assert rep(client, lib, "inventory").json() == {"items": []}
    b = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, b, "BC-0001")
    new_copy(client, lib, b, "BC-0002")
    c3 = new_copy(client, lib, b, "BC-0003", branch=2)
    c4 = new_copy(client, lib, b, "BC-0004", branch=2)
    m = mk_member(client, lib)
    m2 = mk_member(client, lib, 2)
    lend(client, lib, m, c1)
    lend(client, lib, m2, c3)
    client.post(f"{API}/loans/2/report-lost", headers=lib)  # c3 lost -> branch null
    client.post(f"{API}/transfers", headers=lib, json={"copy_id": c4, "to_branch_id": 1})  # in transfer -> null
    body = rep(client, lib, "inventory").json()
    assert body == {"items": [
        {"branch_id": 1, "status": "available", "copies": 1},
        {"branch_id": 1, "status": "on_loan", "copies": 1},
        {"branch_id": None, "status": "in_transfer", "copies": 1},
        {"branch_id": None, "status": "lost", "copies": 1},
    ]}
    assert rep(client, lib, "inventory", branch_id=1).json()["items"] == body["items"][:2]
    assert rep(client, lib, "inventory", branch_id=2).json() == {"items": []}
    assert copy_of(client, lib, c3)["status"] == "lost"
