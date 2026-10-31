import pytest

from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_branches import lib_h, member_body, mk_branch  # noqa: F401
from tests.test_loans import (  # noqa: F401
    API,
    at,
    copy_of,
    lend,
    lib,
    member_h,
    mk_book,
    mk_member,
    new_copy,
    ret,
)


def lose(client, lib, member, barcode, price):
    """Lend a new copy of the first book to the member and report it lost."""
    books = client.get(f"{API}/books", headers=lib).json()["items"]
    book = books[0]["id"] if books else mk_book(client, lib, 0)
    c = new_copy(client, lib, book, barcode, price=price)
    lid = lend(client, lib, member, c).json()["id"]
    r = client.post(f"{API}/loans/{lid}/report-lost", headers=lib)
    assert r.status_code == 200, r.text
    return c, lid


def pay(client, hd, member, amount, method="cash"):
    return client.post(f"{API}/members/{member}/payments", headers=hd, json={"amount": amount, "method": method})


def fees_of(client, hd, member, **params):
    r = client.get(f"{API}/members/{member}/fees", headers=hd, params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_fee_representation(client, lib):
    s = mk_member(client, lib)
    _, lid = lose(client, lib, s, "BC-0001", "180.00")
    fee = fees_of(client, lib, s)[0]
    assert fee == {
        "id": 1, "member_id": s, "loan_id": lid, "kind": "lost_book", "amount": "180.00", "paid_amount": "0.00",
        "status": "open", "created_on": "2026-11-02", "waived_by": None, "waived_at": None, "waive_reason": None,
        "outstanding": "180.00",
    }


def test_lost_book_payment_e2e(client, lib, clock, app):
    """LIB-E2E-04"""
    s = mk_member(client, lib)
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="180.00")
    lid = lend(client, lib, s, c).json()["id"]
    at(clock, 2026, 11, 18)
    client.post(f"{API}/loans/{lid}/report-lost", headers=lib)
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json()["total_debt"] == "209.00"
    e = err(pay(client, lib, s, "209.01"), 409, "PAYMENT_EXCEEDS_BALANCE")
    assert e["details"]["outstanding_fees"] == "209.00"
    r = pay(client, lib, s, "209.00", "card")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["id"] == 1 and p["member_id"] == s and p["amount"] == "209.00" and p["method"] == "card"
    assert p["received_by"] == 2 and p["paid_at"] == "2026-11-18T09:00:00+03:00"
    assert p["allocations"] == [
        {"fee_id": 1, "amount": "4.00"}, {"fee_id": 2, "amount": "180.00"}, {"fee_id": 3, "amount": "25.00"}
    ]
    assert [f["status"] for f in fees_of(client, lib, s)] == ["paid"] * 3
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json() == {
        "outstanding_fees": "0.00", "accrued_late_fees": "0.00", "total_debt": "0.00", "blocked": False
    }
    assert client.post(f"{API}/copies/{c}/withdraw", headers=lib, json={"reason": "lost for good"}).json()["status"] == "withdrawn"
    assert len(audit(app, "payment_received")) == 1


def test_payment_allocation_order_and_partial(client, lib, clock):
    s = mk_member(client, lib)
    _, _ = lose(client, lib, s, "BC-0001", "6.00")  # lost_book 6.00 + processing 25.00 (created 2026-11-02)
    at(clock, 2026, 11, 3)
    lose(client, lib, s, "BC-0002", "20.00")  # later fees
    ids = [(f["id"], f["kind"], f["amount"]) for f in fees_of(client, lib, s)]
    assert ids == [(1, "lost_book", "6.00"), (2, "lost_processing", "25.00"), (3, "lost_book", "20.00"), (4, "lost_processing", "25.00")]
    p = pay(client, lib, s, "10.00").json()
    assert p["allocations"] == [{"fee_id": 1, "amount": "6.00"}, {"fee_id": 2, "amount": "4.00"}]
    fees = fees_of(client, lib, s)
    assert [(f["status"], f["paid_amount"], f["outstanding"]) for f in fees] == [
        ("paid", "6.00", "0.00"), ("open", "4.00", "21.00"), ("open", "0.00", "20.00"), ("open", "0.00", "25.00")
    ]
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json()["outstanding_fees"] == "66.00"
    p2 = pay(client, lib, s, "22.00").json()
    assert p2["allocations"] == [{"fee_id": 2, "amount": "21.00"}, {"fee_id": 3, "amount": "1.00"}]


def test_payment_validation(client, lib):
    s = mk_member(client, lib)
    lose(client, lib, s, "BC-0001", "10.00")
    url = f"{API}/members/{s}/payments"
    for body in (
        {"amount": "0.00", "method": "cash"}, {"amount": "-1.00", "method": "cash"}, {"amount": 5, "method": "cash"},
        {"amount": "1.001", "method": "cash"}, {"amount": "1.00", "method": "bitcoin"}, {"amount": "1.00"},
        {"method": "cash"}, {"amount": "1.00", "method": "cash", "x": 1},
    ):
        err(client.post(url, headers=lib, json=body), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/members/99/payments", headers=lib, json={"amount": "1.00", "method": "cash"}), 404, "NOT_FOUND")
    err(client.post(url, headers=member_h(client), json={"amount": "1.00", "method": "cash"}), 403, "FORBIDDEN")
    err(client.post(url, json={"amount": "1.00", "method": "cash"}), 401, "UNAUTHENTICATED")
    assert pay(client, lib, s, "35.00").status_code == 201
    # nothing is left to pay
    err(pay(client, lib, s, "0.01"), 409, "PAYMENT_EXCEEDS_BALANCE")


def test_accrued_late_fees_cannot_be_paid(client, lib, clock):
    s = mk_member(client, lib)
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    lend(client, lib, s, c)
    at(clock, 2026, 11, 20)
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json() == {
        "outstanding_fees": "0.00", "accrued_late_fees": "8.00", "total_debt": "8.00", "blocked": False
    }
    e = err(pay(client, lib, s, "1.00"), 409, "PAYMENT_EXCEEDS_BALANCE")
    assert e["details"]["outstanding_fees"] == "0.00"


def test_balance_adds_accrued_and_outstanding(client, lib, clock):
    g = mk_member(client, lib, 1, "guest")
    s = mk_member(client, lib, 2)
    lose(client, lib, g, "BC-0001", "10.00")  # 35.00 outstanding
    book = mk_book(client, lib, 1)
    c = new_copy(client, lib, book, "BC-0002")
    lend(client, lib, g, c)  # guest due 2026-11-09
    at(clock, 2026, 11, 10)  # 1 working day late -> 5.00
    assert client.get(f"{API}/members/{g}/balance", headers=lib).json() == {
        "outstanding_fees": "35.00", "accrued_late_fees": "5.00", "total_debt": "40.00", "blocked": False
    }
    at(clock, 2026, 11, 11)  # 2 days -> 10.00 -> 45.00
    assert client.get(f"{API}/members/{g}/balance", headers=lib).json()["blocked"] is False
    at(clock, 2026, 11, 12)  # 3 days -> 15.00 -> 50.00 blocked
    assert client.get(f"{API}/members/{g}/balance", headers=lib).json()["blocked"] is True
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json()["total_debt"] == "0.00"


def test_balance_and_fee_ownership(client, lib):
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lose(client, lib, s1, "BC-0001", "10.00")
    for path in ("balance", "fees", "payments"):
        assert client.get(f"{API}/members/{s1}/{path}", headers=member_h(client, 1)).status_code == 200
        err(client.get(f"{API}/members/{s1}/{path}", headers=member_h(client, 2)), 403, "FORBIDDEN")
        err(client.get(f"{API}/members/99/{path}", headers=lib), 404, "NOT_FOUND")
        err(client.get(f"{API}/members/{s1}/{path}"), 401, "UNAUTHENTICATED")
        assert client.get(f"{API}/members/{s2}/{path}", headers=lib).status_code == 200
    err(client.get(f"{API}/fees", headers=member_h(client, 1)), 403, "FORBIDDEN")
    err(client.get(f"{API}/fees"), 401, "UNAUTHENTICATED")


def test_fee_lists_and_filters(client, lib, clock):
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    book = mk_book(client, lib, 0)
    c1, c2 = new_copy(client, lib, book, "BC-0001"), new_copy(client, lib, book, "BC-0002", price="9.00")
    l1 = lend(client, lib, s1, c1).json()["id"]
    l2 = lend(client, lib, s2, c2).json()["id"]
    at(clock, 2026, 11, 17)
    ret(client, lib, l1)  # late 1 day: 2.00
    client.post(f"{API}/loans/{l2}/report-lost", headers=lib)  # late 2.00, lost 9.00, processing 25.00
    allf = client.get(f"{API}/fees", headers=lib).json()
    assert allf["total"] == 4 and [f["id"] for f in allf["items"]] == [1, 2, 3, 4]
    assert [f["id"] for f in client.get(f"{API}/fees", headers=lib, params={"member_id": s2}).json()["items"]] == [2, 3, 4]
    assert [f["id"] for f in client.get(f"{API}/fees", headers=lib, params={"kind": "lost_book"}).json()["items"]] == [3]
    assert [f["id"] for f in client.get(f"{API}/fees", headers=lib, params={"loan_id": l1}).json()["items"]] == [1]
    pay(client, lib, s1, "2.00")
    assert [f["id"] for f in client.get(f"{API}/fees", headers=lib, params={"status": "paid"}).json()["items"]] == [1]
    assert [f["id"] for f in fees_of(client, lib, s2, status="open", kind="late_fee")] == [2]
    assert fees_of(client, lib, s1, loan_id=l2) == []
    err(client.get(f"{API}/fees", headers=lib, params={"kind": "other"}), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/fees", headers=lib, params={"status": "other"}), 422, "VALIDATION_ERROR")
    page = client.get(f"{API}/fees", headers=lib, params={"page_size": 3, "page": 2}).json()
    assert page["total"] == 4 and [f["id"] for f in page["items"]] == [4]


def test_payments_list(client, lib, clock):
    s = mk_member(client, lib)
    lose(client, lib, s, "BC-0001", "50.00")
    pay(client, lib, s, "10.00")
    at(clock, 2026, 11, 3)
    pay(client, lib, s, "5.00", "card")
    items = client.get(f"{API}/members/{s}/payments", headers=lib).json()
    assert items["total"] == 2
    assert [(p["id"], p["amount"], p["method"]) for p in items["items"]] == [(1, "10.00", "cash"), (2, "5.00", "card")]
    assert items["items"][1]["allocations"][0] == {"fee_id": 1, "amount": "5.00"}
    own = client.get(f"{API}/members/{s}/payments", headers=member_h(client)).json()
    assert own["total"] == 2


def test_waive(client, lib, admin_h, app):
    """LIB-E2E-08"""
    s = mk_member(client, lib)
    lose(client, lib, s, "BC-0001", "50.00")
    err(client.post(f"{API}/fees/2/waive", headers=lib, json={"reason": "goodwill"}), 403, "FORBIDDEN")
    err(client.post(f"{API}/fees/2/waive", headers=member_h(client), json={"reason": "goodwill"}), 403, "FORBIDDEN")
    err(client.post(f"{API}/fees/2/waive", json={"reason": "goodwill"}), 401, "UNAUTHENTICATED")
    err(client.post(f"{API}/fees/2/waive", headers=admin_h, json={"reason": "abc"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/fees/2/waive", headers=admin_h, json={}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/fees/99/waive", headers=admin_h, json={"reason": "goodwill"}), 404, "NOT_FOUND")
    pay(client, lib, s, "10.00")  # fee 1 (lost_book 50.00): paid 10.00
    r = client.post(f"{API}/fees/1/waive", headers=admin_h, json={"reason": " goodwill "})
    assert r.status_code == 200, r.text
    fee = r.json()
    assert fee["status"] == "waived" and fee["waive_reason"] == "goodwill" and fee["waived_by"] == 1
    assert fee["waived_at"] == "2026-11-02T09:30:00+03:00"
    assert fee["paid_amount"] == "10.00" and fee["outstanding"] == "0.00" and fee["amount"] == "50.00"
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json()["outstanding_fees"] == "25.00"
    err(client.post(f"{API}/fees/1/waive", headers=admin_h, json={"reason": "goodwill"}), 409, "FEE_NOT_OPEN")
    # waived fees receive no further payments
    assert pay(client, lib, s, "25.00").json()["allocations"] == [{"fee_id": 2, "amount": "25.00"}]
    err(client.post(f"{API}/fees/2/waive", headers=admin_h, json={"reason": "goodwill"}), 409, "FEE_NOT_OPEN")
    assert [a.entity_id for a in audit(app, "fee_waived")] == [1]


def test_waive_unblocks_lending(client, lib, admin_h):
    s = mk_member(client, lib)
    lose(client, lib, s, "BC-0001", "40.00")  # 65.00
    book = mk_book(client, lib, 1)
    c = new_copy(client, lib, book, "BC-0002")
    err(lend(client, lib, s, c), 409, "MEMBER_BLOCKED_BY_DEBT")
    client.post(f"{API}/fees/1/waive", headers=admin_h, json={"reason": "goodwill"})
    assert lend(client, lib, s, c).status_code == 201


def test_academic_daily_fee(client, lib, clock):
    a = mk_member(client, lib, 1, "academic")
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    lid = lend(client, lib, a, c).json()["id"]  # due 2026-12-02
    at(clock, 2026, 12, 7)
    loan = ret(client, lib, lid).json()
    assert loan["late_days"] == 3 and loan["accrued_late_fee"] == "3.00"
