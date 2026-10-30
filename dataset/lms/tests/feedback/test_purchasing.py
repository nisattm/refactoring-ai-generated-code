"""LMS Module 12: Purchasing: feedback set.

Case table: ../cases/purchasing.md. Requirements: ../../requirements.md.
Written before the code exists; fails at ``import lms`` until then.
"""

import itertools

from support import api

_names = itertools.count(1)


def supplier(client, headers, name=None, expect=201, **fields):
    body = {"name": name or f"Supplier {next(_names)}", "email": None, "phone": None}
    body.update(fields)
    return api.post(client, "/api/v1/suppliers", headers, body, expect=expect)


def line(book_id, quantity=1, unit_price="10.00"):
    return {"book_id": book_id, "quantity": quantity, "unit_price": unit_price}


def order(client, headers, *, supplier_id, branch_id, lines, expect=201):
    body = {"supplier_id": supplier_id, "branch_id": branch_id, "lines": lines}
    return api.post(client, "/api/v1/purchase-orders", headers, body, expect=expect)


def get_order(client, headers, order_id):
    return api.get(client, f"/api/v1/purchase-orders/{order_id}", headers)


def action(client, headers, order_id, name, body=None):
    """POST submit / cancel / receive. The success status of these actions is not fixed by
    the requirements, so only a 2xx status is checked here."""
    r = client.post(f"/api/v1/purchase-orders/{order_id}/{name}", json=body, headers=headers)
    assert 200 <= r.status_code < 300, r.text
    return r


def failed(client, headers, order_id, name, body=None, status=409):
    r = client.post(f"/api/v1/purchase-orders/{order_id}/{name}", json=body, headers=headers)
    assert r.status_code == status, r.text
    return api.error_code(r)


def receive_body(line_id, *barcodes):
    return {"lines": [{"line_id": line_id, "barcodes": list(barcodes)}]}


def copies_of(client, headers, book_id):
    return api.get(client, f"/api/v1/books/{book_id}/copies", headers)["items"]


def order_ids(client, headers, params=None):
    return [x["id"] for x in api.get(client, "/api/v1/purchase-orders", headers, params=params)["items"]]


def ordered(client, headers, branch_id, quantity=3, unit_price="95.50"):
    """Submitted order: one line of a new book. Returns (order, book)."""
    book = api.create_book(client, headers)
    sup = supplier(client, headers)
    po = order(client, headers, supplier_id=sup["id"], branch_id=branch_id,
               lines=[line(book["id"], quantity, unit_price)])
    action(client, headers, po["id"], "submit")
    return get_order(client, headers, po["id"]), book


def test_t_pur_01_a(client, librarian):
    """T-PUR-01-a

    LIB-PUR-01. Librarian creates supplier "Ankara Kitap" with e-mail and phone
    Expected: 201 with the fields and is_active true
    """
    s = supplier(client, librarian, "Ankara Kitap", email="orders@ankarakitap.com.tr", phone="+903121234567")
    assert (s["name"], s["email"], s["phone"], s["is_active"]) == (
        "Ankara Kitap", "orders@ankarakitap.com.tr", "+903121234567", True)


def test_t_pur_01_c(client, librarian):
    """T-PUR-01-c

    LIB-PUR-01. Suppliers "Beta", "alpha", "Gamma" (Gamma inactive); list, q=AL, is_active=false
    Expected: Ordered by name: alpha, Beta, Gamma; q=AL → alpha; is_active=false → Gamma
    """
    supplier(client, librarian, "Beta")
    supplier(client, librarian, "alpha")
    gamma = supplier(client, librarian, "Gamma")
    api.patch(client, f"/api/v1/suppliers/{gamma['id']}", librarian, {"is_active": False})
    def names(params=None):
        return [x["name"] for x in api.get(client, "/api/v1/suppliers", librarian, params=params)["items"]]
    assert names() == ["alpha", "Beta", "Gamma"]
    assert names({"q": "AL"}) == ["alpha"]
    assert names({"is_active": "false"}) == ["Gamma"]


def test_t_pur_01_e(client, librarian, branch_a):
    """T-PUR-01-e

    LIB-PUR-01, 18.2. A member creates a supplier and lists suppliers
    Expected: Both 403 FORBIDDEN
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    mh = api.member_headers(client, member)
    assert api.error_code(supplier(client, mh, expect=403)) == "FORBIDDEN"
    assert api.error_code(api.get(client, "/api/v1/suppliers", mh, expect=403)) == "FORBIDDEN"


def test_t_pur_02_a(client, librarian, branch_a):
    """T-PUR-02-a

    LIB-PUR-02. Draft order: supplier P, branch A, book K × 3 at 95.50 (LIB-E2E-09)
    Expected: 201, status draft, total "286.50", one line with received_quantity 0
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"], 3, "95.50")])
    assert po["status"] == "draft"
    assert po["total"] == "286.50"
    assert len(po["lines"]) == 1
    assert (po["lines"][0]["book_id"], po["lines"][0]["quantity"], po["lines"][0]["unit_price"],
            po["lines"][0]["received_quantity"]) == (book["id"], 3, "95.50", 0)


def test_t_pur_02_c(client, librarian, branch_a):
    """T-PUR-02-c

    LIB-PUR-02. The same book twice in lines
    Expected: 422 VALIDATION_ERROR
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    r = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"],
              lines=[line(book["id"]), line(book["id"], 2)], expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_pur_02_e(client, librarian, branch_a):
    """T-PUR-02-e

    LIB-PUR-02. Orders with 50 lines and with 51 lines (different books)
    Expected: 50: 201; 51: 422 VALIDATION_ERROR
    """
    author = api.post(client, "/api/v1/authors", librarian, {"name": "Shared Author"}, expect=201)
    publisher = api.post(client, "/api/v1/publishers", librarian, {"name": "Shared Publisher"}, expect=201)
    books = [api.create_book(client, librarian, author_ids=[author["id"]], publisher_id=publisher["id"]) for _ in range(51)]
    p = supplier(client, librarian)
    order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(b["id"]) for b in books[:50]])
    r = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(b["id"]) for b in books], expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_pur_02_g(client, librarian, branch_a):
    """T-PUR-02-g

    LIB-PUR-02, 18.1. Line with quantity 100 and unit_price "100000.00" (upper limits)
    Expected: 201, total "10000000.00"
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"], 100, "100000.00")])
    assert po["total"] == "10000000.00"


def test_t_pur_02_i(client, librarian, branch_a):
    """T-PUR-02-i

    LIB-PUR-02, LIB-COM-29. Line with unknown book_id 999999
    Expected: 404 NOT_FOUND
    """
    p = supplier(client, librarian)
    r = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(999999)], expect=404)
    assert api.error_code(r) == "NOT_FOUND"


def test_t_pur_03_a(client, librarian, branch_a):
    """T-PUR-03-a

    LIB-PUR-03. Draft with 2 lines (2 × 10.00, 1 × 5.00); PATCH lines with one line 4 × 7.50
    Expected: 200; one line; total "30.00"
    """
    b1, b2, b3 = (api.create_book(client, librarian) for _ in range(3))
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"],
               lines=[line(b1["id"], 2, "10.00"), line(b2["id"], 1, "5.00")])
    assert po["total"] == "25.00"
    changed = api.patch(client, f"/api/v1/purchase-orders/{po['id']}", librarian, {"lines": [line(b3["id"], 4, "7.50")]})
    assert [x["book_id"] for x in changed["lines"]] == [b3["id"]]
    assert changed["total"] == "30.00"


def test_t_pur_03_c(client, librarian, branch_a):
    """T-PUR-03-c

    LIB-PUR-03. PATCH an ordered order
    Expected: 409 INVALID_ORDER_STATUS
    """
    po, book = ordered(client, librarian, branch_a["id"])
    r = api.patch(client, f"/api/v1/purchase-orders/{po['id']}", librarian, {"lines": [line(book["id"], 1)]}, expect=409)
    assert api.error_code(r) == "INVALID_ORDER_STATUS"


def test_t_pur_04_a(client, clock, librarian, branch_a):
    """T-PUR-04-a

    LIB-PUR-04. Draft submitted on 2026-11-05
    Expected: status ordered, ordered_on 2026-11-05
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    assert po.get("ordered_on") is None
    api.set_today(clock, "2026-11-05")
    action(client, librarian, po["id"], "submit")
    got = get_order(client, librarian, po["id"])
    assert (got["status"], got["ordered_on"]) == ("ordered", "2026-11-05")


def test_t_pur_04_c(client, librarian, branch_a):
    """T-PUR-04-c

    LIB-PUR-04. Submit an order twice
    Expected: Second submit 409 INVALID_ORDER_STATUS
    """
    po, _ = ordered(client, librarian, branch_a["id"])
    assert failed(client, librarian, po["id"], "submit") == "INVALID_ORDER_STATUS"


def test_t_pur_05_a(client, librarian, branch_a):
    """T-PUR-05-a

    LIB-PUR-05. Cancel a draft
    Expected: status cancelled
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    action(client, librarian, po["id"], "cancel")
    assert get_order(client, librarian, po["id"])["status"] == "cancelled"


def test_t_pur_05_c(client, librarian, branch_a):
    """T-PUR-05-c

    LIB-PUR-05. Cancel a partially_received order (1 of 3 received)
    Expected: 409 INVALID_ORDER_STATUS; status unchanged
    """
    po, _ = ordered(client, librarian, branch_a["id"])
    action(client, librarian, po["id"], "receive", receive_body(po["lines"][0]["id"], "PUR-0001"))
    assert failed(client, librarian, po["id"], "cancel") == "INVALID_ORDER_STATUS"
    assert get_order(client, librarian, po["id"])["status"] == "partially_received"


def test_t_pur_05_e(client, librarian, branch_a):
    """T-PUR-05-e

    LIB-PUR-05. Cancel a fully received order
    Expected: 409 INVALID_ORDER_STATUS
    """
    po, _ = ordered(client, librarian, branch_a["id"], quantity=1)
    action(client, librarian, po["id"], "receive", receive_body(po["lines"][0]["id"], "PUR-0001"))
    assert failed(client, librarian, po["id"], "cancel") == "INVALID_ORDER_STATUS"


def test_t_pur_06_a(client, clock, librarian, branch_a):
    """T-PUR-06-a

    LIB-PUR-06. Ordered K × 3 at 95.50 for branch A; receive barcodes PUR-0001, PUR-0002 on 2026-11-05
    Expected: Two copies: home and current branch A, price "95.50", acquired_on 2026-11-05, status available; line received_quantity 2
    """
    po, book = ordered(client, librarian, branch_a["id"])
    api.set_today(clock, "2026-11-05")
    action(client, librarian, po["id"], "receive", receive_body(po["lines"][0]["id"], "PUR-0001", "PUR-0002"))
    copies = copies_of(client, librarian, book["id"])
    assert sorted(c["barcode"] for c in copies) == ["PUR-0001", "PUR-0002"]
    for c in copies:
        assert (c["home_branch_id"], c["current_branch_id"], c["price"], c["acquired_on"], c["status"]) == (
            branch_a["id"], branch_a["id"], "95.50", "2026-11-05", "available")
    assert get_order(client, librarian, po["id"])["lines"][0]["received_quantity"] == 2


def test_t_pur_06_c(client, librarian, branch_a):
    """T-PUR-06-c

    LIB-PUR-06. Receive with an empty lines list; with an empty barcodes list; with the same line_id twice
    Expected: Each 422 VALIDATION_ERROR
    """
    po, _ = ordered(client, librarian, branch_a["id"])
    line_id = po["lines"][0]["id"]
    twice = {"lines": [{"line_id": line_id, "barcodes": ["PUR-0001"]}, {"line_id": line_id, "barcodes": ["PUR-0002"]}]}
    for body in ({"lines": []}, receive_body(line_id), twice):
        assert failed(client, librarian, po["id"], "receive", body, status=422) == "VALIDATION_ERROR"


def test_t_pur_06_e(client, librarian, branch_a):
    """T-PUR-06-e

    LIB-PUR-06, LIB-RES-08. Book K's only copy is on loan; S2 waits (pickup A); the order for K (branch A) receives one copy
    Expected: The new copy is released: S2's reservation ready, the copy on_hold
    """
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    res = api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(first["book"]["id"], 1)])
    action(client, librarian, po["id"], "submit")
    po = get_order(client, librarian, po["id"])
    action(client, librarian, po["id"], "receive", receive_body(po["lines"][0]["id"], "PUR-0001"))
    new = [c for c in copies_of(client, librarian, first["book"]["id"]) if c["barcode"] == "PUR-0001"][0]
    assert new["status"] == "on_hold"
    assert api.get_reservation(client, librarian, res["id"])["status"] == "ready"


def test_t_pur_07_a(client, librarian, branch_a):
    """T-PUR-07-a

    LIB-PUR-07. Line of 3 with 2 received; receive 2 more (LIB-E2E-09)
    Expected: 409 RECEIVE_EXCEEDS_ORDERED; still 2 copies, received_quantity 2
    """
    po, book = ordered(client, librarian, branch_a["id"])
    line_id = po["lines"][0]["id"]
    action(client, librarian, po["id"], "receive", receive_body(line_id, "PUR-0001", "PUR-0002"))
    assert failed(client, librarian, po["id"], "receive", receive_body(line_id, "PUR-0003", "PUR-0004")) == "RECEIVE_EXCEEDS_ORDERED"
    assert len(copies_of(client, librarian, book["id"])) == 2
    assert get_order(client, librarian, po["id"])["lines"][0]["received_quantity"] == 2


def test_t_pur_07_c(client, librarian, branch_a):
    """T-PUR-07-c

    LIB-PUR-07. Receive a barcode that already exists in the catalog, together with a new one
    Expected: 409 CONFLICT; neither copy created
    """
    po, book = ordered(client, librarian, branch_a["id"])
    other = api.create_book(client, librarian)
    api.add_copy(client, librarian, other["id"], home_branch_id=branch_a["id"], barcode="TAKEN-001")
    body = receive_body(po["lines"][0]["id"], "PUR-0001", "TAKEN-001")
    assert failed(client, librarian, po["id"], "receive", body) == "CONFLICT"
    assert copies_of(client, librarian, book["id"]) == []


def test_t_pur_08_a(client, librarian, branch_a):
    """T-PUR-08-a

    LIB-PUR-08. Line of 3: receive 2, then 1 (LIB-E2E-09)
    Expected: partially_received after 2, received after 3
    """
    po, _ = ordered(client, librarian, branch_a["id"])
    line_id = po["lines"][0]["id"]
    action(client, librarian, po["id"], "receive", receive_body(line_id, "PUR-0001", "PUR-0002"))
    assert get_order(client, librarian, po["id"])["status"] == "partially_received"
    action(client, librarian, po["id"], "receive", receive_body(line_id, "PUR-0003"))
    assert get_order(client, librarian, po["id"])["status"] == "received"


def test_t_pur_09_a(client, librarian, branch_a, branch_b):
    """T-PUR-09-a

    LIB-PUR-09. Three orders, no filter
    Expected: Ordered by id descending: o3, o2, o1
    """
    # o1: draft (supplier p1, branch A); o2: ordered (p2, A); o3: draft (p1, B)
    book = api.create_book(client, librarian)
    p1, p2 = supplier(client, librarian), supplier(client, librarian)
    o1 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o2 = order(client, librarian, supplier_id=p2["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o3 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_b["id"], lines=[line(book["id"])])
    action(client, librarian, o2["id"], "submit")

    assert order_ids(client, librarian) == [o3["id"], o2["id"], o1["id"]]


def test_t_pur_09_c(client, librarian, branch_a, branch_b):
    """T-PUR-09-c

    LIB-PUR-09, LIB-COM-18. page_size=2, page 2
    Expected: One item (o1), total 3
    """
    # o1: draft (supplier p1, branch A); o2: ordered (p2, A); o3: draft (p1, B)
    book = api.create_book(client, librarian)
    p1, p2 = supplier(client, librarian), supplier(client, librarian)
    o1 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o2 = order(client, librarian, supplier_id=p2["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o3 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_b["id"], lines=[line(book["id"])])
    action(client, librarian, o2["id"], "submit")

    page = api.get(client, "/api/v1/purchase-orders", librarian, params={"page_size": 2, "page": 2})
    assert [x["id"] for x in page["items"]] == [o1["id"]]
    assert page["total"] == 3
    assert [x["id"] for x in api.get(client, "/api/v1/purchase-orders", librarian, params={"page_size": 2})["items"]] == [o3["id"], o2["id"]]
