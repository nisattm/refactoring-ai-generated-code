"""Characterization tests (feedback): module 4 (Catalog). Cases: cases/char_catalog.md (issue #115)."""
from support.api import add_copy, create_book


def named(client, lib, kind, name):
    r = client.post(f"/api/v1/{kind}", headers=lib, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_t_char_cat_01_a(client, librarian):
    """T-CHAR-CAT-01-a (LIB-CAT-01): GET unknown author -> 404 NOT_FOUND"""
    r = client.get("/api/v1/authors/999999", headers=librarian)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"resource": "author", "id": 999999}


def test_t_char_cat_03_a(client, librarian):
    """T-CHAR-CAT-03-a (LIB-CAT-01): PATCH author with {} -> 200, name unchanged"""
    a = named(client, librarian, "authors", "Orhan Pamuk")
    r = client.patch(f"/api/v1/authors/{a['id']}", headers=librarian, json={})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": a["id"], "name": "Orhan Pamuk"}


def test_t_char_cat_05_a(client, librarian):
    """T-CHAR-CAT-05-a (LIB-CAT-01): rename publisher -> 200; rename another to that name -> 409 CONFLICT"""
    p1 = named(client, librarian, "publishers", "Alpha Press")
    p2 = named(client, librarian, "publishers", "Beta Press")
    r = client.patch(f"/api/v1/publishers/{p1['id']}", headers=librarian, json={"name": "Gamma Press"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Gamma Press"
    r = client.patch(f"/api/v1/publishers/{p2['id']}", headers=librarian, json={"name": "Gamma Press"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "CONFLICT"
    assert r.json()["error"]["details"] == {"field": "name"}


def test_t_char_cat_07_a(client, librarian):
    """T-CHAR-CAT-07-a (LIB-CAT-05): PATCH book author_ids [999999] -> 404 NOT_FOUND"""
    b = create_book(client, librarian)
    r = client.patch(f"/api/v1/books/{b['id']}", headers=librarian, json={"author_ids": [999999]})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"field": "author_ids", "id": 999999}


def test_t_char_cat_09_a(client, librarian):
    """T-CHAR-CAT-09-a (LIB-CAT-05): PATCH book with its own isbn -> 200, isbn unchanged"""
    b = create_book(client, librarian)
    r = client.patch(f"/api/v1/books/{b['id']}", headers=librarian, json={"isbn": b["isbn"]})
    assert r.status_code == 200, r.text
    assert r.json()["isbn"] == b["isbn"]


def test_t_char_cat_11_a(client, librarian):
    """T-CHAR-CAT-11-a (LIB-CAT-09): GET unknown copy -> 404 NOT_FOUND"""
    r = client.get("/api/v1/copies/999999", headers=librarian)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"resource": "copy", "id": 999999}


def test_t_char_cat_13_a(client, librarian, branch_a):
    """T-CHAR-CAT-13-a (LIB-CAT-09): PATCH copy with its own price -> 200, price unchanged"""
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    r = client.patch(f"/api/v1/copies/{c['id']}", headers=librarian, json={"price": "100.00"})
    assert r.status_code == 200, r.text
    assert r.json()["price"] == "100.00"
