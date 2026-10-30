"""Heldout tests: module 4 (Catalog). Generated from cases/catalog.md."""
from support.api import (
    add_copy, create_book, error_code, lend, member_headers, register_member, reserve, return_loan,
)


def author(client, lib, name="Orhan Pamuk"):
    r = client.post("/api/v1/authors", headers=lib, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def publisher(client, lib, name="Example Publishing"):
    r = client.post("/api/v1/publishers", headers=lib, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def book_payload(a, p, **kw):
    data = {"isbn": "978-0-306-40615-7", "title": "Kar", "subtitle": None, "author_ids": [a["id"]],
            "publisher_id": p["id"], "publication_year": 2002, "language": "tr", "classification": "813.54"}
    data.update(kw)
    return data


def post_book(client, lib, data):
    return client.post("/api/v1/books", headers=lib, json=data)


def copy_status(client, lib, cid):
    return client.get(f"/api/v1/copies/{cid}", headers=lib).json()["status"]


def test_t_cat_01_b(client, librarian, branch_a):
    """T-CAT-01-b (LIB-CAT-01): 409 CONFLICT; 403 FORBIDDEN"""
    publisher(client, librarian, "Yapı Kredi")
    r = client.post("/api/v1/publishers", headers=librarian, json={"name": "YAPI KREDİ"})
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert client.post("/api/v1/authors", headers=mh, json={"name": "X"}).status_code == 403


def test_t_cat_02_b(client, librarian):
    """T-CAT-02-b (LIB-CAT-02): 9780804429573; 9791090636071"""
    a, p = author(client, librarian), publisher(client, librarian)
    r1 = post_book(client, librarian, book_payload(a, p, isbn="0-8044-2957-x"))
    r2 = post_book(client, librarian, book_payload(a, p, isbn="979 10 90636 07 1", title="Other"))
    assert r1.json()["isbn"] == "9780804429573" and r2.json()["isbn"] == "9791090636071"


def test_t_cat_03_b(client, librarian):
    """T-CAT-03-b (LIB-CAT-03): Second 409 CONFLICT"""
    a, p = author(client, librarian), publisher(client, librarian)
    assert post_book(client, librarian, book_payload(a, p, isbn="0-306-40615-2")).status_code == 201
    r = post_book(client, librarian, book_payload(a, p, isbn="9780306406157"))
    assert r.status_code == 409 and error_code(r) == "CONFLICT"


def test_t_cat_04_a(client, librarian):
    """T-CAT-04-a (LIB-CAT-04): Ordered case-insensitively by title; filters return the matching book"""
    a, p = author(client, librarian), publisher(client, librarian)
    post_book(client, librarian, book_payload(a, p, title="zebra", isbn="9780140449136", classification="500"))
    post_book(client, librarian, book_payload(a, p, title="apple", isbn="0-306-40615-2", classification="813.54"))
    titles = [b["title"] for b in client.get("/api/v1/books", headers=librarian).json()["items"]]
    assert titles == ["apple", "zebra"]
    by_isbn = client.get("/api/v1/books", headers=librarian, params={"isbn": "0306406152"}).json()["items"]
    assert [b["title"] for b in by_isbn] == ["apple"]
    by_class = client.get("/api/v1/books", headers=librarian, params={"classification_prefix": "81"}).json()["items"]
    assert [b["title"] for b in by_class] == ["apple"]


def test_t_cat_06_b(client, librarian, branch_a):
    """T-CAT-06-b (LIB-CAT-06): 409 BOOK_HAS_COPIES; 409 IN_USE; 409 IN_USE"""
    a, p = author(client, librarian), publisher(client, librarian)
    b = post_book(client, librarian, book_payload(a, p)).json()
    add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    assert error_code(client.delete(f"/api/v1/books/{b['id']}", headers=librarian)) == "BOOK_HAS_COPIES"
    assert error_code(client.delete(f"/api/v1/authors/{a['id']}", headers=librarian)) == "IN_USE"
    assert error_code(client.delete(f"/api/v1/publishers/{p['id']}", headers=librarian)) == "IN_USE"


def test_t_cat_07_b(client, librarian, branch_a):
    """T-CAT-07-b (LIB-CAT-07): 422; 409 CONFLICT; 422; 422"""
    b = create_book(client, librarian)
    add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode="ABC-123")
    for bc in ("ABC12", "A" * 21):
        add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode=bc, expect=422)
    add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode="abc-123", expect=409)
    for price in ("0.00", "100000.01"):
        add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], price=price, expect=422)
    r = client.post(f"/api/v1/books/{b['id']}/copies", headers=librarian, json={"barcode": "TOMORROW1", "home_branch_id": branch_a["id"], "price": "10.00", "acquired_on": "2026-11-03"})
    assert r.status_code == 422


def test_t_cat_08_a(client, librarian, branch_a, branch_b):
    """T-CAT-08-a (LIB-CAT-08): Before lending: availability A 2/2, B 1/1; after lending: filters return B's copy and the lent copy"""
    b = create_book(client, librarian)
    a1 = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    add_copy(client, librarian, b["id"], home_branch_id=branch_b["id"])
    avail = client.get(f"/api/v1/books/{b['id']}", headers=librarian).json()["availability"]
    assert avail == [{"branch_id": branch_a["id"], "available": 2, "total": 2}, {"branch_id": branch_b["id"], "available": 1, "total": 1}]
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], a1["id"])
    lst = lambda **p: [c["id"] for c in client.get(f"/api/v1/books/{b['id']}/copies", headers=librarian, params=p).json()["items"]]
    assert len(lst(branch_id=branch_b["id"])) == 1
    assert lst(status="on_loan") == [a1["id"]]


def test_t_cat_09_b(client, librarian, branch_a, branch_b):
    """T-CAT-09-b (LIB-CAT-09): 409 INVALID_COPY_STATUS"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    r = client.patch(f"/api/v1/copies/{c['id']}", headers=librarian, json={"home_branch_id": branch_b["id"]})
    assert r.status_code == 409 and error_code(r) == "INVALID_COPY_STATUS"


def test_t_cat_10_b(client, librarian, branch_a):
    """T-CAT-10-b (LIB-CAT-10): 409 INVALID_COPY_STATUS; 422; 409 INVALID_COPY_STATUS"""
    b = create_book(client, librarian)
    lent = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    other = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], lent["id"])
    assert error_code(client.post(f"/api/v1/copies/{lent['id']}/withdraw", headers=librarian, json={"reason": "Lost it"})) == "INVALID_COPY_STATUS"
    assert client.post(f"/api/v1/copies/{other['id']}/withdraw", headers=librarian, json={"reason": "Old"}).status_code == 422
    client.post(f"/api/v1/copies/{other['id']}/withdraw", headers=librarian, json={"reason": "Too old"})
    assert error_code(client.post(f"/api/v1/copies/{other['id']}/withdraw", headers=librarian, json={"reason": "Too old"})) == "INVALID_COPY_STATUS"


def test_t_cat_11_b(client, librarian, branch_a):
    """T-CAT-11-b (LIB-CAT-11): 409 INVALID_COPY_STATUS"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    r = client.post(f"/api/v1/copies/{c['id']}/repair", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "INVALID_COPY_STATUS"


def test_t_cat_12_a(client, librarian, branch_a):
    """T-CAT-12-a (LIB-CAT-12): Reservation accepted (book is lendable)"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], price="120.00")
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
