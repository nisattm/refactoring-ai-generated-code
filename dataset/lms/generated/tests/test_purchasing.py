import sqlalchemy as sa

from lms.catalog.models import Copy
from tests.test_auth import admin_h, audit, err  # noqa: F401
from tests.test_loans import API, at, lend, lib, mk_book, mk_member, new_copy  # noqa: F401


def mk_supplier(client, hd, name="Acme Books", **kw):
    r = client.post(f"{API}/suppliers", headers=hd, json={"name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def mk_order(client, hd, lines=None, supplier=1, branch=1):
    lines = [{"book_id": 1, "quantity": 3, "unit_price": "95.50"}] if lines is None else lines
    r = client.post(
        f"{API}/purchase-orders", headers=hd, json={"supplier_id": supplier, "branch_id": branch, "lines": lines}
    )
    assert r.status_code == 201, r.text
    return r.json()


def receive(client, hd, order_id, *lines):
    return client.post(
        f"{API}/purchase-orders/{order_id}/receive",
        headers=hd,
        json={"lines": [{"line_id": line, "barcodes": codes} for line, codes in lines]},
    )


def test_supplier_crud(client, lib, app):
    s = mk_supplier(client, lib, " Acme Books ", email="Sales@Acme.COM", phone="+90 532 123 45 67")
    assert s == {"id": 1, "name": "Acme Books", "email": "sales@acme.com", "phone": "+90 532 123 45 67", "is_active": True}
    assert mk_supplier(client, lib, "Plain")["email"] is None
    err(client.post(f"{API}/suppliers", headers=lib, json={"name": "ACME BOOKS"}), 409, "CONFLICT")
    err(client.post(f"{API}/suppliers", headers=lib, json={"name": "x", "email": "nope"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/suppliers", headers=lib, json={"name": "x", "phone": "12"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/suppliers", headers=lib, json={"name": " "}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/suppliers", headers=lib, json={"name": "x", "bogus": 1}), 422, "VALIDATION_ERROR")
    r = client.patch(f"{API}/suppliers/2", headers=lib, json={"name": "Zeta", "email": None, "is_active": False})
    assert r.status_code == 200 and r.json()["name"] == "Zeta" and r.json()["is_active"] is False
    err(client.patch(f"{API}/suppliers/2", headers=lib, json={"name": "acme books"}), 409, "CONFLICT")
    assert client.patch(f"{API}/suppliers/2", headers=lib, json={"name": "Zeta"}).status_code == 200
    err(client.get(f"{API}/suppliers/9", headers=lib), 404, "NOT_FOUND")
    assert client.get(f"{API}/suppliers/1", headers=lib).json()["name"] == "Acme Books"
    assert [a.entity_id for a in audit(app, "supplier_created")] == [1, 2]
    updated = audit(app, "supplier_updated")
    assert len(updated) == 1 and updated[0].details["name"] == {"old": "Plain", "new": "Zeta"}


def test_supplier_list_and_permissions(client, lib, admin_h):
    for n in ("Zeta", "alpha", "İstanbul Kitap", "Beta"):
        mk_supplier(client, lib, n)
    client.patch(f"{API}/suppliers/4", headers=lib, json={"is_active": False})
    r = client.get(f"{API}/suppliers", headers=lib).json()
    assert [s["name"] for s in r["items"]] == ["alpha", "Beta", "İstanbul Kitap", "Zeta"] and r["total"] == 4
    assert [s["name"] for s in client.get(f"{API}/suppliers?q=ISTANBUL", headers=lib).json()["items"]] == ["İstanbul Kitap"]
    assert [s["name"] for s in client.get(f"{API}/suppliers?is_active=false", headers=lib).json()["items"]] == ["Beta"]
    r = client.get(f"{API}/suppliers?page=2&page_size=3", headers=admin_h).json()
    assert [s["name"] for s in r["items"]] == ["Zeta"] and r["page"] == 2
    err(client.get(f"{API}/suppliers"), 401, "UNAUTHENTICATED")
    err(client.post(f"{API}/suppliers", json={"name": "x"}), 401, "UNAUTHENTICATED")


def test_create_order(client, lib, app):
    mk_book(client, lib, 0)
    mk_book(client, lib, 1)
    mk_supplier(client, lib)
    o = mk_order(
        client,
        lib,
        [{"book_id": 1, "quantity": 3, "unit_price": "95.50"}, {"book_id": 2, "quantity": 1, "unit_price": "0.01"}],
    )
    assert o["status"] == "draft" and o["total"] == "286.51" and o["ordered_on"] is None
    assert o["supplier_id"] == 1 and o["branch_id"] == 1 and o["created_by"] == 2
    assert o["created_at"].endswith("+03:00")
    assert [(ln["id"], ln["book_id"], ln["quantity"], ln["unit_price"], ln["received_quantity"]) for ln in o["lines"]] == [
        (1, 1, 3, "95.50", 0),
        (2, 2, 1, "0.01", 0),
    ]
    assert mk_order(client, lib, [])["total"] == "0.00"
    assert [a.entity_id for a in audit(app, "purchase_order_created")] == [1, 2]
    assert client.get(f"{API}/purchase-orders/1", headers=lib).json() == o


def test_create_order_validation_and_checks(client, lib):
    mk_book(client, lib, 0)
    mk_supplier(client, lib)
    base = {"supplier_id": 1, "branch_id": 1}
    line = {"book_id": 1, "quantity": 1, "unit_price": "1.00"}
    for body in (
        {**base, "lines": [line, line]},
        {**base, "lines": [{**line, "quantity": 0}]},
        {**base, "lines": [{**line, "quantity": 101}]},
        {**base, "lines": [{**line, "unit_price": "0.00"}]},
        {**base, "lines": [{**line, "unit_price": "100000.01"}]},
        {**base, "lines": [{**line, "unit_price": 5}]},
        {**base, "lines": [{**line, "unit_price": "1.234"}]},
        {**base, "lines": [{**line, "extra": 1}]},
        {**base, "lines": [{"book_id": b, "quantity": 1, "unit_price": "1.00"} for b in range(1, 52)]},
        {"supplier_id": 1},
        {**base, "status": "ordered"},
    ):
        err(client.post(f"{API}/purchase-orders", headers=lib, json=body), 422, "VALIDATION_ERROR")
    e = err(client.post(f"{API}/purchase-orders", headers=lib, json={**base, "supplier_id": 9}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "supplier_id", "id": 9}
    e = err(client.post(f"{API}/purchase-orders", headers=lib, json={**base, "branch_id": 9}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "branch_id", "id": 9}
    err(client.post(f"{API}/purchase-orders", headers=lib, json={**base, "lines": [{**line, "book_id": 9}]}), 404, "NOT_FOUND")
    client.patch(f"{API}/suppliers/1", headers=lib, json={"is_active": False})
    err(client.post(f"{API}/purchase-orders", headers=lib, json=base), 409, "SUPPLIER_INACTIVE")


def test_inactive_branch_comes_first(client, lib, admin_h):
    mk_supplier(client, lib)
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    client.patch(f"{API}/suppliers/1", headers=lib, json={"is_active": False})
    err(client.post(f"{API}/purchase-orders", headers=lib, json={"supplier_id": 1, "branch_id": 2}), 409, "BRANCH_INACTIVE")


def test_edit_draft(client, lib, app):
    mk_book(client, lib, 0)
    mk_book(client, lib, 1)
    mk_supplier(client, lib)
    mk_supplier(client, lib, "Other")
    mk_order(client, lib)
    r = client.patch(
        f"{API}/purchase-orders/1",
        headers=lib,
        json={"supplier_id": 2, "branch_id": 2, "lines": [{"book_id": 2, "quantity": 2, "unit_price": "10.00"}]},
    )
    assert r.status_code == 200, r.text
    o = r.json()
    assert (o["supplier_id"], o["branch_id"], o["total"]) == (2, 2, "20.00")
    assert [(ln["book_id"], ln["quantity"]) for ln in o["lines"]] == [(2, 2)]
    d = audit(app, "purchase_order_updated")[0].details
    assert d["supplier_id"] == {"old": 1, "new": 2} and d["branch_id"] == {"old": 1, "new": 2} and "lines" in d
    # lines can be emptied, and an empty patch changes nothing
    assert client.patch(f"{API}/purchase-orders/1", headers=lib, json={"lines": []}).json()["lines"] == []
    assert client.patch(f"{API}/purchase-orders/1", headers=lib, json={}).status_code == 200
    err(client.patch(f"{API}/purchase-orders/1", headers=lib, json={"lines": None}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/purchase-orders/1", headers=lib, json={"status": "ordered"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/purchase-orders/9", headers=lib, json={}), 404, "NOT_FOUND")
    err(client.patch(f"{API}/purchase-orders/1", headers=lib, json={"supplier_id": 9}), 404, "NOT_FOUND")
    client.patch(f"{API}/suppliers/2", headers=lib, json={"is_active": False})
    err(client.patch(f"{API}/purchase-orders/1", headers=lib, json={"supplier_id": 2}), 409, "SUPPLIER_INACTIVE")
    # not a draft any more
    client.patch(f"{API}/purchase-orders/1", headers=lib, json={"lines": [{"book_id": 1, "quantity": 1, "unit_price": "1.00"}]})
    assert client.post(f"{API}/purchase-orders/1/submit", headers=lib).status_code == 200
    err(client.patch(f"{API}/purchase-orders/1", headers=lib, json={"branch_id": 1}), 409, "INVALID_ORDER_STATUS")


def test_submit_and_cancel(client, lib, clock, app):
    mk_book(client, lib, 0)
    mk_supplier(client, lib)
    mk_order(client, lib, [])
    err(client.post(f"{API}/purchase-orders/1/submit", headers=lib), 409, "ORDER_EMPTY")
    mk_order(client, lib)
    r = client.post(f"{API}/purchase-orders/2/submit", headers=lib)
    assert r.status_code == 200 and r.json()["status"] == "ordered" and r.json()["ordered_on"] == "2026-11-02"
    err(client.post(f"{API}/purchase-orders/2/submit", headers=lib), 409, "INVALID_ORDER_STATUS")
    assert [a.entity_id for a in audit(app, "purchase_order_submitted")] == [2]
    # cancel: ordered with nothing received, draft
    assert client.post(f"{API}/purchase-orders/2/cancel", headers=lib).json()["status"] == "cancelled"
    err(client.post(f"{API}/purchase-orders/2/cancel", headers=lib), 409, "INVALID_ORDER_STATUS")
    err(client.post(f"{API}/purchase-orders/2/submit", headers=lib), 409, "INVALID_ORDER_STATUS")
    assert client.post(f"{API}/purchase-orders/1/cancel", headers=lib).json()["status"] == "cancelled"
    assert [a.entity_id for a in audit(app, "purchase_order_cancelled")] == [2, 1]
    err(client.post(f"{API}/purchase-orders/9/cancel", headers=lib), 404, "NOT_FOUND")


def test_cancel_after_receiving_is_rejected(client, lib):
    mk_book(client, lib, 0)
    mk_supplier(client, lib)
    mk_order(client, lib)
    client.post(f"{API}/purchase-orders/1/submit", headers=lib)
    assert receive(client, lib, 1, (1, ["BC-0001"])).status_code == 200
    err(client.post(f"{API}/purchase-orders/1/cancel", headers=lib), 409, "INVALID_ORDER_STATUS")


def test_purchasing_to_shelf(client, lib, app):
    """LIB-E2E-09."""
    mk_book(client, lib, 0)
    mk_supplier(client, lib)
    o = mk_order(client, lib)
    assert o["total"] == "286.50"
    err(receive(client, lib, 1, (1, ["BC-0001"])), 409, "INVALID_ORDER_STATUS")  # still a draft
    client.post(f"{API}/purchase-orders/1/submit", headers=lib)
    r = receive(client, lib, 1, (1, ["bc-0001", "BC-0002"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "partially_received" and r.json()["lines"][0]["received_quantity"] == 2
    copies = client.get(f"{API}/books/1/copies", headers=lib).json()["items"]
    assert [(c["barcode"], c["status"], c["price"], c["home_branch_id"], c["current_branch_id"], c["acquired_on"]) for c in copies] == [
        ("BC-0001", "available", "95.50", 1, 1, "2026-11-02"),
        ("BC-0002", "available", "95.50", 1, 1, "2026-11-02"),
    ]
    e = err(receive(client, lib, 1, (1, ["BC-0003", "BC-0004"])), 409, "RECEIVE_EXCEEDS_ORDERED")
    assert e["details"]["line_id"] == 1
    assert client.get(f"{API}/books/1/copies", headers=lib).json()["total"] == 2
    assert client.get(f"{API}/purchase-orders/1", headers=lib).json()["lines"][0]["received_quantity"] == 2
    r = receive(client, lib, 1, (1, ["BC-0003"]))
    assert r.json()["status"] == "received" and r.json()["lines"][0]["received_quantity"] == 3
    err(receive(client, lib, 1, (1, ["BC-0004"])), 409, "INVALID_ORDER_STATUS")
    assert len(audit(app, "purchase_order_received")) == 2
    assert len(audit(app, "copy_added")) == 3


def test_receive_validation_and_conflicts(client, lib):
    mk_book(client, lib, 0)
    mk_book(client, lib, 1)
    mk_supplier(client, lib)
    mk_order(client, lib, [{"book_id": 1, "quantity": 5, "unit_price": "1.00"}, {"book_id": 2, "quantity": 5, "unit_price": "2.00"}])
    client.post(f"{API}/purchase-orders/1/submit", headers=lib)
    url = f"{API}/purchase-orders/1/receive"
    for body in (
        {"lines": []},
        {"lines": [{"line_id": 1, "barcodes": []}]},
        {"lines": [{"line_id": 1, "barcodes": ["BC-0001"]}, {"line_id": 1, "barcodes": ["BC-0002"]}]},
        {"lines": [{"line_id": 1, "barcodes": ["bad code"]}]},
        {"lines": [{"line_id": 1, "barcodes": ["AB"]}]},
        {"lines": [{"line_id": 1}]},
        {},
        {"lines": [{"line_id": 1, "barcodes": ["BC-0001"], "extra": 1}]},
    ):
        err(client.post(url, headers=lib, json=body), 422, "VALIDATION_ERROR")
    e = err(receive(client, lib, 1, (7, ["BC-0001"])), 404, "NOT_FOUND")
    assert e["details"]["id"] == 7
    err(receive(client, lib, 9, (1, ["BC-0001"])), 404, "NOT_FOUND")
    # duplicate inside the request, also across lines
    err(receive(client, lib, 1, (1, ["BC-0001", "BC-0001"])), 409, "CONFLICT")
    err(receive(client, lib, 1, (1, ["BC-0001"]), (2, ["bc-0001"])), 409, "CONFLICT")
    assert client.get(f"{API}/books/1/copies", headers=lib).json()["total"] == 0
    # existing barcode rejects the whole request, nothing is created
    assert receive(client, lib, 1, (1, ["BC-0001"])).status_code == 200
    err(receive(client, lib, 1, (1, ["BC-0002"]), (2, ["BC-0001"])), 409, "CONFLICT")
    assert client.get(f"{API}/books/1/copies", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/books/2/copies", headers=lib).json()["total"] == 0
    # exceeding on a second line rejects the first line too
    err(receive(client, lib, 1, (1, ["BC-0003"]), (2, [f"BD-000{i}" for i in range(6)])), 409, "RECEIVE_EXCEEDS_ORDERED")
    assert client.get(f"{API}/books/1/copies", headers=lib).json()["total"] == 1


def test_receive_goes_through_release_procedure(client, lib):
    """A received copy is released: a waiting reservation takes it at once."""
    book = mk_book(client, lib, 0)
    m1 = mk_member(client, lib, 1)
    mk_member(client, lib, 2)
    mk_supplier(client, lib)
    c = new_copy(client, lib, book, "BC-0001")
    assert lend(client, lib, m1, c).status_code == 201
    r = client.post(f"{API}/reservations", headers=lib, json={"book_id": book, "pickup_branch_id": 2, "member_id": 2})
    assert r.status_code == 201
    mk_order(client, lib, [{"book_id": book, "quantity": 1, "unit_price": "10.00"}])
    client.post(f"{API}/purchase-orders/1/submit", headers=lib)
    assert receive(client, lib, 1, (1, ["BC-0002"])).status_code == 200
    res = client.get(f"{API}/reservations/{r.json()['id']}", headers=lib).json()
    assert res["status"] == "in_transit" and res["copy_id"] == 2
    with client.app.state.session_factory() as s:
        assert s.get(Copy, 2).status == "in_transfer"


def test_receive_to_inactive_branch(client, lib, admin_h):
    mk_book(client, lib, 0)
    mk_supplier(client, lib)
    mk_order(client, lib, branch=2)
    client.post(f"{API}/purchase-orders/1/submit", headers=lib)
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(receive(client, lib, 1, (1, ["BC-0001"])), 409, "BRANCH_INACTIVE")


def test_order_list_and_permissions(client, lib, admin_h):
    mk_book(client, lib, 0)
    mk_supplier(client, lib)
    mk_supplier(client, lib, "Other")
    mk_order(client, lib, supplier=1, branch=1)
    mk_order(client, lib, supplier=2, branch=2)
    mk_order(client, lib, supplier=1, branch=2)
    client.post(f"{API}/purchase-orders/2/submit", headers=lib)
    r = client.get(f"{API}/purchase-orders", headers=lib).json()
    assert [o["id"] for o in r["items"]] == [3, 2, 1] and r["total"] == 3
    ids = lambda q: [o["id"] for o in client.get(f"{API}/purchase-orders?{q}", headers=admin_h).json()["items"]]  # noqa: E731
    assert ids("status=ordered") == [2] and ids("supplier_id=1") == [3, 1] and ids("branch_id=2") == [3, 2]
    assert ids("page=2&page_size=2") == [1]
    err(client.get(f"{API}/purchase-orders?status=bogus", headers=lib), 422, "VALIDATION_ERROR")
    # permissions: members have no access
    from tests.test_loans import member_h

    mk_member(client, lib, 1)
    mh = member_h(client, 1)
    for method, path in (
        ("get", "/suppliers"), ("post", "/suppliers"), ("get", "/suppliers/1"), ("patch", "/suppliers/1"),
        ("get", "/purchase-orders"), ("post", "/purchase-orders"), ("get", "/purchase-orders/1"),
        ("patch", "/purchase-orders/1"), ("post", "/purchase-orders/1/submit"), ("post", "/purchase-orders/1/cancel"),
        ("post", "/purchase-orders/1/receive"),
    ):
        err(getattr(client, method)(API + path, headers=mh), 403, "FORBIDDEN")
        err(getattr(client, method)(API + path), 401, "UNAUTHENTICATED")
    err(client.get(f"{API}/purchase-orders/0", headers=lib), 422, "VALIDATION_ERROR")


def test_failed_receive_rolls_back(client, lib, app):
    mk_book(client, lib, 0)
    mk_supplier(client, lib)
    mk_order(client, lib)
    client.post(f"{API}/purchase-orders/1/submit", headers=lib)
    err(receive(client, lib, 1, (1, ["BC-0001", "BC-0002", "BC-0003", "BC-0004"])), 409, "RECEIVE_EXCEEDS_ORDERED")
    with app.state.session_factory() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Copy)) == 0
    assert audit(app, "purchase_order_received") == []
