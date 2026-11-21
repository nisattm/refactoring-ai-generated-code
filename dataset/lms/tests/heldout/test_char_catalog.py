"""Characterization tests (held-out): module 4 (Catalog). Cases: cases/char_catalog.md (issue #115)."""
from support.api import add_copy, create_book


def named(client, lib, kind, name):
    r = client.post(f"/api/v1/{kind}", headers=lib, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_t_char_cat_02_a(client, librarian):
    """T-CHAR-CAT-02-a (LIB-CAT-01): GET unknown publisher -> 404 NOT_FOUND"""
    r = client.get("/api/v1/publishers/999999", headers=librarian)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"resource": "publisher", "id": 999999}


def test_t_char_cat_04_a(client, librarian):
    """T-CHAR-CAT-04-a (LIB-CAT-01): PATCH publisher with {} -> 200, name unchanged"""
    p = named(client, librarian, "publishers", "Delta Press")
    r = client.patch(f"/api/v1/publishers/{p['id']}", headers=librarian, json={})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": p["id"], "name": "Delta Press"}


def test_t_char_cat_06_a(client, librarian):
    """T-CHAR-CAT-06-a (LIB-CAT-01): DELETE unused author and publisher -> 204; then GET -> 404"""
    a = named(client, librarian, "authors", "Unused Author")
    p = named(client, librarian, "publishers", "Unused Press")
    for kind, obj in (("authors", a), ("publishers", p)):
        r = client.delete(f"/api/v1/{kind}/{obj['id']}", headers=librarian)
        assert r.status_code == 204, r.text
        r = client.get(f"/api/v1/{kind}/{obj['id']}", headers=librarian)
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "NOT_FOUND"


def test_t_char_cat_08_a(client, librarian):
    """T-CHAR-CAT-08-a (LIB-CAT-05): PATCH book publisher_id 999999 -> 404 NOT_FOUND"""
    b = create_book(client, librarian)
    r = client.patch(f"/api/v1/books/{b['id']}", headers=librarian, json={"publisher_id": 999999})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"field": "publisher_id", "id": 999999}


def test_t_char_cat_10_a(client, librarian):
    """T-CHAR-CAT-10-a (LIB-CAT-05): PATCH author_ids [B, A] -> 200 in that order; same again -> 200 unchanged"""
    a = named(client, librarian, "authors", "First Author")
    b = named(client, librarian, "authors", "Second Author")
    book = create_book(client, librarian, author_ids=[a["id"], b["id"]])
    for _ in range(2):
        r = client.patch(f"/api/v1/books/{book['id']}", headers=librarian, json={"author_ids": [b["id"], a["id"]]})
        assert r.status_code == 200, r.text
        assert [x["id"] for x in r.json()["authors"]] == [b["id"], a["id"]]


def test_t_char_cat_12_a(client, librarian, branch_a):
    """T-CHAR-CAT-12-a (LIB-CAT-09): barcode lookup in lower case -> 200; unknown barcode -> 404 NOT_FOUND"""
    book = create_book(client, librarian)
    c = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    r = client.get(f"/api/v1/copies/by-barcode/{c['barcode'].lower()}", headers=librarian)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == c["id"]
    r = client.get("/api/v1/copies/by-barcode/NOPE-0", headers=librarian)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"resource": "copy", "barcode": "NOPE-0"}
