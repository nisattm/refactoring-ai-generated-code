"""LMS Module 12: Purchasing: held-out set.

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


def test_t_pur_01_b(client, librarian):
    """T-PUR-01-b

    LIB-PUR-01, LIB-COM-30. Supplier "Istanbul Yayin" exists; create "İSTANBUL YAYIN"
    Expected: 409 CONFLICT (names compared with LIB-COM-30 normalization)
    """
    supplier(client, librarian, "Istanbul Yayin")
    r = supplier(client, librarian, "İSTANBUL YAYIN", expect=409)
    assert api.error_code(r) == "CONFLICT"


def test_t_pur_01_d(client, librarian):
    """T-PUR-01-d

    LIB-PUR-01. PATCH a supplier's name, email, phone and is_active
    Expected: 200 with the new values; GET returns the same
    """
    s = supplier(client, librarian, "Old Name")
    changed = api.patch(client, f"/api/v1/suppliers/{s['id']}", librarian,
                        {"name": "New Name", "email": "new@example.com", "phone": "+905321112233", "is_active": False})
    assert (changed["name"], changed["email"], changed["phone"], changed["is_active"]) == (
        "New Name", "new@example.com", "+905321112233", False)
    assert api.get(client, f"/api/v1/suppliers/{s['id']}", librarian)["name"] == "New Name"


def test_t_pur_01_f(client, librarian):
    """T-PUR-01-f

    LIB-PUR-01, 18.1, LIB-COM-17. Supplier with e-mail "no-at-sign.example.com"
    Expected: 422 VALIDATION_ERROR; without e-mail and phone (both null) 201
    """
    r = supplier(client, librarian, "Bad Mail", email="no-at-sign.example.com", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    s = supplier(client, librarian, "No Contact")
    assert s["email"] is None and s["phone"] is None


def test_t_pur_02_b(client, librarian, branch_a):
    """T-PUR-02-b

    LIB-PUR-02. Order with an inactive supplier
    Expected: 409 SUPPLIER_INACTIVE
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    api.patch(client, f"/api/v1/suppliers/{p['id']}", librarian, {"is_active": False})
    r = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"])], expect=409)
    assert api.error_code(r) == "SUPPLIER_INACTIVE"


def test_t_pur_02_d(client, librarian, branch_a):
    """T-PUR-02-d

    LIB-PUR-02. Draft order with 0 lines
    Expected: 201, total "0.00", lines empty
    """
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[])
    assert (po["status"], po["total"], po["lines"]) == ("draft", "0.00", [])


def test_t_pur_02_f(client, librarian, branch_a):
    """T-PUR-02-f

    LIB-PUR-02, 18.1. Line quantity 0 and 101; unit_price "0.00" and "100000.01"
    Expected: Each 422 VALIDATION_ERROR
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    for bad in (line(book["id"], 0), line(book["id"], 101), line(book["id"], 1, "0.00"), line(book["id"], 1, "100000.01")):
        r = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[bad], expect=422)
        assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_pur_02_h(client, admin, librarian):
    """T-PUR-02-h

    LIB-PUR-02, LIB-BR-04. Order for an inactive branch
    Expected: 409 BRANCH_INACTIVE
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    inactive = api.create_branch(client, admin, "C")
    api.deactivate_branch(client, admin, inactive["id"])
    r = order(client, librarian, supplier_id=p["id"], branch_id=inactive["id"], lines=[line(book["id"])], expect=409)
    assert api.error_code(r) == "BRANCH_INACTIVE"


def test_t_pur_02_j(client, librarian, branch_a):
    """T-PUR-02-j

    LIB-PUR-02, 18.2. A member creates an order
    Expected: 403 FORBIDDEN
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    mh = api.member_headers(client, api.register_member(client, librarian, home_branch_id=branch_a["id"]))
    r = order(client, mh, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"])], expect=403)
    assert api.error_code(r) == "FORBIDDEN"


def test_t_pur_03_b(client, librarian, branch_a, branch_b):
    """T-PUR-03-b

    LIB-PUR-03. PATCH a draft's supplier_id and branch_id only
    Expected: 200; new supplier and branch; lines unchanged
    """
    book = api.create_book(client, librarian)
    p1, p2 = supplier(client, librarian), supplier(client, librarian)
    po = order(client, librarian, supplier_id=p1["id"], branch_id=branch_a["id"], lines=[line(book["id"], 2)])
    changed = api.patch(client, f"/api/v1/purchase-orders/{po['id']}", librarian,
                        {"supplier_id": p2["id"], "branch_id": branch_b["id"]})
    assert (changed["supplier_id"], changed["branch_id"]) == (p2["id"], branch_b["id"])
    assert [(x["book_id"], x["quantity"]) for x in changed["lines"]] == [(book["id"], 2)]


def test_t_pur_03_d(client, librarian, branch_a, branch_b):
    """T-PUR-03-d

    LIB-PUR-03. PATCH a cancelled order
    Expected: 409 INVALID_ORDER_STATUS
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    action(client, librarian, po["id"], "cancel")
    r = api.patch(client, f"/api/v1/purchase-orders/{po['id']}", librarian, {"branch_id": branch_b["id"]}, expect=409)
    assert api.error_code(r) == "INVALID_ORDER_STATUS"


def test_t_pur_04_b(client, librarian, branch_a):
    """T-PUR-04-b

    LIB-PUR-04. Submit a draft without lines
    Expected: 409 ORDER_EMPTY; status stays draft
    """
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[])
    assert failed(client, librarian, po["id"], "submit") == "ORDER_EMPTY"
    assert get_order(client, librarian, po["id"])["status"] == "draft"


def test_t_pur_05_b(client, librarian, branch_a):
    """T-PUR-05-b

    LIB-PUR-05. Cancel an ordered order with nothing received
    Expected: status cancelled
    """
    po, _ = ordered(client, librarian, branch_a["id"])
    action(client, librarian, po["id"], "cancel")
    assert get_order(client, librarian, po["id"])["status"] == "cancelled"


def test_t_pur_05_d(client, librarian, branch_a):
    """T-PUR-05-d

    LIB-PUR-05. Cancel an order that is already cancelled
    Expected: 409 INVALID_ORDER_STATUS
    """
    po, _ = ordered(client, librarian, branch_a["id"])
    action(client, librarian, po["id"], "cancel")
    assert failed(client, librarian, po["id"], "cancel") == "INVALID_ORDER_STATUS"


def test_t_pur_06_b(client, librarian, branch_a):
    """T-PUR-06-b

    LIB-PUR-06. Receive on a draft
    Expected: 409 INVALID_ORDER_STATUS; no copy created
    """
    book = api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    assert failed(client, librarian, po["id"], "receive", receive_body(po["lines"][0]["id"], "PUR-0001")) == "INVALID_ORDER_STATUS"
    assert copies_of(client, librarian, book["id"]) == []


def test_t_pur_06_d(client, librarian, branch_a):
    """T-PUR-06-d

    LIB-PUR-06, LIB-COM-29. Receive with the line_id of another order
    Expected: 404 NOT_FOUND; no copy created
    """
    po1, book1 = ordered(client, librarian, branch_a["id"])
    po2, _ = ordered(client, librarian, branch_a["id"])
    body = receive_body(po2["lines"][0]["id"], "PUR-0001")
    assert failed(client, librarian, po1["id"], "receive", body, status=404) == "NOT_FOUND"
    assert copies_of(client, librarian, book1["id"]) == []


def test_t_pur_06_f(client, librarian, branch_a):
    """T-PUR-06-f

    LIB-PUR-06. Receive on a cancelled order
    Expected: 409 INVALID_ORDER_STATUS
    """
    po, _ = ordered(client, librarian, branch_a["id"])
    action(client, librarian, po["id"], "cancel")
    assert failed(client, librarian, po["id"], "receive", receive_body(po["lines"][0]["id"], "PUR-0001")) == "INVALID_ORDER_STATUS"


def test_t_pur_07_b(client, librarian, branch_a):
    """T-PUR-07-b

    LIB-PUR-07. Two lines (quantity 1 each); one request receives 1 on the first and 2 on the second
    Expected: 409 RECEIVE_EXCEEDS_ORDERED; nothing created on either line
    """
    b1, b2 = api.create_book(client, librarian), api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(b1["id"]), line(b2["id"])])
    action(client, librarian, po["id"], "submit")
    l1, l2 = (x["id"] for x in get_order(client, librarian, po["id"])["lines"])
    body = {"lines": [{"line_id": l1, "barcodes": ["PUR-0001"]}, {"line_id": l2, "barcodes": ["PUR-0002", "PUR-0003"]}]}
    assert failed(client, librarian, po["id"], "receive", body) == "RECEIVE_EXCEEDS_ORDERED"
    assert copies_of(client, librarian, b1["id"]) == [] and copies_of(client, librarian, b2["id"]) == []


def test_t_pur_07_d(client, librarian, branch_a):
    """T-PUR-07-d

    LIB-PUR-07. The same barcode twice in one request
    Expected: 409 CONFLICT; no copy created
    """
    po, book = ordered(client, librarian, branch_a["id"])
    body = receive_body(po["lines"][0]["id"], "PUR-0001", "PUR-0001")
    assert failed(client, librarian, po["id"], "receive", body) == "CONFLICT"
    assert copies_of(client, librarian, book["id"]) == []


def test_t_pur_08_b(client, librarian, branch_a):
    """T-PUR-08-b

    LIB-PUR-08. Two lines (1 and 2): first line complete, second 1 of 2; then the last copy
    Expected: partially_received, then received
    """
    b1, b2 = api.create_book(client, librarian), api.create_book(client, librarian)
    p = supplier(client, librarian)
    po = order(client, librarian, supplier_id=p["id"], branch_id=branch_a["id"], lines=[line(b1["id"], 1), line(b2["id"], 2)])
    action(client, librarian, po["id"], "submit")
    l1, l2 = (x["id"] for x in get_order(client, librarian, po["id"])["lines"])
    body = {"lines": [{"line_id": l1, "barcodes": ["PUR-0001"]}, {"line_id": l2, "barcodes": ["PUR-0002"]}]}
    action(client, librarian, po["id"], "receive", body)
    assert get_order(client, librarian, po["id"])["status"] == "partially_received"
    action(client, librarian, po["id"], "receive", receive_body(l2, "PUR-0003"))
    assert get_order(client, librarian, po["id"])["status"] == "received"


def test_t_pur_09_b(client, librarian, branch_a, branch_b):
    """T-PUR-09-b

    LIB-PUR-09. Filters status=draft, supplier_id=p1, branch_id=B
    Expected: draft → o3, o1; p1 → o3, o1; B → o3
    """
    # o1: draft (supplier p1, branch A); o2: ordered (p2, A); o3: draft (p1, B)
    book = api.create_book(client, librarian)
    p1, p2 = supplier(client, librarian), supplier(client, librarian)
    o1 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o2 = order(client, librarian, supplier_id=p2["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o3 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_b["id"], lines=[line(book["id"])])
    action(client, librarian, o2["id"], "submit")

    assert order_ids(client, librarian, {"status": "draft"}) == [o3["id"], o1["id"]]
    assert order_ids(client, librarian, {"supplier_id": p1["id"]}) == [o3["id"], o1["id"]]
    assert order_ids(client, librarian, {"branch_id": branch_b["id"]}) == [o3["id"]]


def test_t_pur_09_d(client, librarian, branch_a, branch_b):
    """T-PUR-09-d

    LIB-PUR-09, 18.2. A member lists orders and reads one order
    Expected: Both 403 FORBIDDEN
    """
    # o1: draft (supplier p1, branch A); o2: ordered (p2, A); o3: draft (p1, B)
    book = api.create_book(client, librarian)
    p1, p2 = supplier(client, librarian), supplier(client, librarian)
    o1 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o2 = order(client, librarian, supplier_id=p2["id"], branch_id=branch_a["id"], lines=[line(book["id"])])
    o3 = order(client, librarian, supplier_id=p1["id"], branch_id=branch_b["id"], lines=[line(book["id"])])
    action(client, librarian, o2["id"], "submit")

    mh = api.member_headers(client, api.register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert api.error_code(api.get(client, "/api/v1/purchase-orders", mh, expect=403)) == "FORBIDDEN"
    assert api.error_code(api.get(client, f"/api/v1/purchase-orders/{o1['id']}", mh, expect=403)) == "FORBIDDEN"
    assert order_ids(client, librarian) == [o3["id"], o2["id"], o1["id"]]
