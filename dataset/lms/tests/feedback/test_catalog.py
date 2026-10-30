"""Feedback tests: module 4 (Catalog). Generated from cases/catalog.md."""
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


def test_t_cat_01_a(client, librarian):
    """T-CAT-01-a (LIB-CAT-01): 201 each; ordered by name (case-insensitive); q finds Zeynep; PATCH returns new name"""
    for n in ("Zeynep", "ahmet", "Mehmet"):
        author(client, librarian, n)
    names = [a["name"] for a in client.get("/api/v1/authors", headers=librarian).json()["items"]]
    assert names == ["ahmet", "Mehmet", "Zeynep"]
    found = client.get("/api/v1/authors", headers=librarian, params={"q": "ZEY"}).json()["items"]
    assert [a["name"] for a in found] == ["Zeynep"]
    r = client.patch(f"/api/v1/authors/{found[0]['id']}", headers=librarian, json={"name": "Zeynep K."})
    assert r.status_code == 200 and r.json()["name"] == "Zeynep K."


def test_t_cat_02_a(client, librarian):
    """T-CAT-02-a (LIB-CAT-02): Stored as 9780306406157"""
    a, p = author(client, librarian), publisher(client, librarian)
    r = post_book(client, librarian, book_payload(a, p, isbn="0-306-40615-2"))
    assert r.status_code == 201 and r.json()["isbn"] == "9780306406157"


def test_t_cat_02_c(client, librarian):
    """T-CAT-02-c (LIB-CAT-02): 422 VALIDATION_ERROR each"""
    a, p = author(client, librarian), publisher(client, librarian)
    for bad in ("9780306406158", "0306406153", "9770000000003", "978030640615"):
        r = post_book(client, librarian, book_payload(a, p, isbn=bad))
        assert r.status_code == 422, bad


def test_t_cat_03_a(client, librarian):
    """T-CAT-03-a (LIB-CAT-03): 201 BookOut with authors in the given order, publisher object, availability []"""
    a1, a2, p = author(client, librarian, "Aaa"), author(client, librarian, "Bbb"), publisher(client, librarian)
    r = post_book(client, librarian, book_payload(a1, p, author_ids=[a2["id"], a1["id"]]))
    assert r.status_code == 201
    b = r.json()
    assert [x["name"] for x in b["authors"]] == ["Bbb", "Aaa"]
    assert b["publisher"] == {"id": p["id"], "name": p["name"]} and b["availability"] == []


def test_t_cat_03_c(client, librarian):
    """T-CAT-03-c (LIB-CAT-03): 422 each; year 1450 and 2026 accepted"""
    a, p = author(client, librarian), publisher(client, librarian)
    many = [author(client, librarian, f"A{i}")["id"] for i in range(11)]
    for kw in ({"publication_year": 1449}, {"publication_year": 2027}, {"language": "TR"}, {"classification": "5.1"},
               {"author_ids": many}, {"author_ids": [a["id"], a["id"]]}):
        assert post_book(client, librarian, book_payload(a, p, **kw)).status_code == 422, kw
    assert post_book(client, librarian, book_payload(a, p, publication_year=1450)).status_code == 201
    assert post_book(client, librarian, book_payload(a, p, isbn="9780140449136", publication_year=2026)).status_code == 201


def test_t_cat_05_a(client, librarian):
    """T-CAT-05-a (LIB-CAT-05): 200 with new title; 422"""
    a, p = author(client, librarian), publisher(client, librarian)
    b = post_book(client, librarian, book_payload(a, p)).json()
    r = client.patch(f"/api/v1/books/{b['id']}", headers=librarian, json={"title": "Masumiyet Müzesi"})
    assert r.status_code == 200 and r.json()["title"] == "Masumiyet Müzesi"
    assert client.patch(f"/api/v1/books/{b['id']}", headers=librarian, json={"isbn": "123"}).status_code == 422


def test_t_cat_06_a(client, librarian):
    """T-CAT-06-a (LIB-CAT-06): 204; then 404"""
    a, p = author(client, librarian), publisher(client, librarian)
    b = post_book(client, librarian, book_payload(a, p)).json()
    assert client.delete(f"/api/v1/books/{b['id']}", headers=librarian).status_code == 204
    assert client.get(f"/api/v1/books/{b['id']}", headers=librarian).status_code == 404


def test_t_cat_07_a(client, librarian, branch_a):
    """T-CAT-07-a (LIB-CAT-07): 201; barcode ABC-123, status available, current_branch_id = home"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode="abc-123")
    assert c["barcode"] == "ABC-123" and c["status"] == "available" and c["current_branch_id"] == branch_a["id"]


def test_t_cat_07_c(client, librarian, branch_a):
    """T-CAT-07-c (LIB-CAT-07): New copy on_hold; reservation ready"""
    b = create_book(client, librarian)
    c1 = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c1["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    c2 = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    assert copy_status(client, librarian, c2["id"]) == "on_hold"
    assert client.get(f"/api/v1/reservations/{res['id']}", headers=librarian).json()["status"] == "ready"


def test_t_cat_09_a(client, librarian, branch_a, branch_b):
    """T-CAT-09-a (LIB-CAT-09): 200; home and current branch both change"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    r = client.patch(f"/api/v1/copies/{c['id']}", headers=librarian, json={"price": "55.50", "shelf_location": "B-7"})
    assert r.status_code == 200 and r.json()["price"] == "55.50" and r.json()["shelf_location"] == "B-7"
    r = client.patch(f"/api/v1/copies/{c['id']}", headers=librarian, json={"home_branch_id": branch_b["id"]})
    assert r.json()["home_branch_id"] == branch_b["id"] and r.json()["current_branch_id"] == branch_b["id"]


def test_t_cat_10_a(client, librarian, branch_a):
    """T-CAT-10-a (LIB-CAT-10): 200; withdrawn, withdrawn_reason stored"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    r = client.post(f"/api/v1/copies/{c['id']}/withdraw", headers=librarian, json={"reason": "Water damage"})
    assert r.status_code == 200 and r.json()["status"] == "withdrawn" and r.json()["withdrawn_reason"] == "Water damage"


def test_t_cat_11_a(client, librarian, branch_a):
    """T-CAT-11-a (LIB-CAT-11): damaged, then available"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], price="120.00")
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="40.00")
    assert copy_status(client, librarian, c["id"]) == "damaged"
    assert client.post(f"/api/v1/copies/{c['id']}/repair", headers=librarian).status_code == 200
    assert copy_status(client, librarian, c["id"]) == "available"
