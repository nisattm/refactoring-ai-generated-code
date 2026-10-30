MODULE = "catalog"
TITLE = "module 4 (Catalog)"

HEADER = '''
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
'''


CASES = [
    dict(id="T-CAT-01-a", req="LIB-CAT-01", type="Normal", input="Authors `Zeynep`, `ahmet`, `Mehmet`; list; `q=ZEY`; PATCH name", expected="201 each; ordered by name (case-insensitive); `q` finds Zeynep; PATCH returns new name", code='''
def TEST(client, librarian):
    for n in ("Zeynep", "ahmet", "Mehmet"):
        author(client, librarian, n)
    names = [a["name"] for a in client.get("/api/v1/authors", headers=librarian).json()["items"]]
    assert names == ["ahmet", "Mehmet", "Zeynep"]
    found = client.get("/api/v1/authors", headers=librarian, params={"q": "ZEY"}).json()["items"]
    assert [a["name"] for a in found] == ["Zeynep"]
    r = client.patch(f"/api/v1/authors/{found[0]['id']}", headers=librarian, json={"name": "Zeynep K."})
    assert r.status_code == 200 and r.json()["name"] == "Zeynep K."
'''),
    dict(id="T-CAT-01-b", req="LIB-CAT-01", type="Error", input="Publisher `Yapı Kredi` twice (second as `YAPI KREDİ`); member creates an author", expected="`409 CONFLICT`; `403 FORBIDDEN`", code='''
def TEST(client, librarian, branch_a):
    publisher(client, librarian, "Yapı Kredi")
    r = client.post("/api/v1/publishers", headers=librarian, json={"name": "YAPI KREDİ"})
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert client.post("/api/v1/authors", headers=mh, json={"name": "X"}).status_code == 403
'''),
    dict(id="T-CAT-02-a", req="LIB-CAT-02", type="Normal", input="ISBN-10 `0-306-40615-2`", expected="Stored as `9780306406157`", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    r = post_book(client, librarian, book_payload(a, p, isbn="0-306-40615-2"))
    assert r.status_code == 201 and r.json()["isbn"] == "9780306406157"
'''),
    dict(id="T-CAT-02-b", req="LIB-CAT-02", type="Boundary", input="ISBN-10 with check `x` (`0-8044-2957-x`); ISBN-13 with 979 prefix and spaces (`979 10 90636 07 1`)", expected="`9780804429573`; `9791090636071`", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    r1 = post_book(client, librarian, book_payload(a, p, isbn="0-8044-2957-x"))
    r2 = post_book(client, librarian, book_payload(a, p, isbn="979 10 90636 07 1", title="Other"))
    assert r1.json()["isbn"] == "9780804429573" and r2.json()["isbn"] == "9791090636071"
'''),
    dict(id="T-CAT-02-c", req="LIB-CAT-02", type="Error", input="Wrong check digits (`9780306406158`, `0306406153`), prefix 977 with a valid checksum (`9770000000003`), 12 digits", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    for bad in ("9780306406158", "0306406153", "9770000000003", "978030640615"):
        r = post_book(client, librarian, book_payload(a, p, isbn=bad))
        assert r.status_code == 422, bad
'''),
    dict(id="T-CAT-03-a", req="LIB-CAT-03", type="Normal", input="Create a book with two authors in order [B, A]", expected="201 `BookOut` with `authors` in the given order, `publisher` object, `availability` []", code='''
def TEST(client, librarian):
    a1, a2, p = author(client, librarian, "Aaa"), author(client, librarian, "Bbb"), publisher(client, librarian)
    r = post_book(client, librarian, book_payload(a1, p, author_ids=[a2["id"], a1["id"]]))
    assert r.status_code == 201
    b = r.json()
    assert [x["name"] for x in b["authors"]] == ["Bbb", "Aaa"]
    assert b["publisher"] == {"id": p["id"], "name": p["name"]} and b["availability"] == []
'''),
    dict(id="T-CAT-03-b", req="LIB-CAT-03", type="Error", input="Same ISBN once as ISBN-10 and once as ISBN-13", expected="Second `409 CONFLICT`", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    assert post_book(client, librarian, book_payload(a, p, isbn="0-306-40615-2")).status_code == 201
    r = post_book(client, librarian, book_payload(a, p, isbn="9780306406157"))
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
'''),
    dict(id="T-CAT-03-c", req="LIB-CAT-03", type="Boundary", input="`publication_year` 1449 and 2027 (clock in 2026); `language` `TR`; `classification` `5.1`; 11 authors; duplicate author id", expected="`422` each; year 1450 and 2026 accepted", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    many = [author(client, librarian, f"A{i}")["id"] for i in range(11)]
    for kw in ({"publication_year": 1449}, {"publication_year": 2027}, {"language": "TR"}, {"classification": "5.1"},
               {"author_ids": many}, {"author_ids": [a["id"], a["id"]]}):
        assert post_book(client, librarian, book_payload(a, p, **kw)).status_code == 422, kw
    assert post_book(client, librarian, book_payload(a, p, publication_year=1450)).status_code == 201
    assert post_book(client, librarian, book_payload(a, p, isbn="9780140449136", publication_year=2026)).status_code == 201
'''),
    dict(id="T-CAT-04-a", req="LIB-CAT-04", type="Normal", input="Books `zebra`, `apple`; filters `isbn` as ISBN-10, `classification_prefix=81`", expected="Ordered case-insensitively by title; filters return the matching book", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    post_book(client, librarian, book_payload(a, p, title="zebra", isbn="9780140449136", classification="500"))
    post_book(client, librarian, book_payload(a, p, title="apple", isbn="0-306-40615-2", classification="813.54"))
    titles = [b["title"] for b in client.get("/api/v1/books", headers=librarian).json()["items"]]
    assert titles == ["apple", "zebra"]
    by_isbn = client.get("/api/v1/books", headers=librarian, params={"isbn": "0306406152"}).json()["items"]
    assert [b["title"] for b in by_isbn] == ["apple"]
    by_class = client.get("/api/v1/books", headers=librarian, params={"classification_prefix": "81"}).json()["items"]
    assert [b["title"] for b in by_class] == ["apple"]
'''),
    dict(id="T-CAT-05-a", req="LIB-CAT-05", type="Normal", input="PATCH `title`; PATCH invalid `isbn`", expected="200 with new title; `422`", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    b = post_book(client, librarian, book_payload(a, p)).json()
    r = client.patch(f"/api/v1/books/{b['id']}", headers=librarian, json={"title": "Masumiyet Müzesi"})
    assert r.status_code == 200 and r.json()["title"] == "Masumiyet Müzesi"
    assert client.patch(f"/api/v1/books/{b['id']}", headers=librarian, json={"isbn": "123"}).status_code == 422
'''),
    dict(id="T-CAT-06-a", req="LIB-CAT-06", type="Normal", input="Delete a book without copies", expected="204; then 404", code='''
def TEST(client, librarian):
    a, p = author(client, librarian), publisher(client, librarian)
    b = post_book(client, librarian, book_payload(a, p)).json()
    assert client.delete(f"/api/v1/books/{b['id']}", headers=librarian).status_code == 204
    assert client.get(f"/api/v1/books/{b['id']}", headers=librarian).status_code == 404
'''),
    dict(id="T-CAT-06-b", req="LIB-CAT-06", type="Error", input="Delete a book with a copy; delete its author; delete its publisher", expected="`409 BOOK_HAS_COPIES`; `409 IN_USE`; `409 IN_USE`", code='''
def TEST(client, librarian, branch_a):
    a, p = author(client, librarian), publisher(client, librarian)
    b = post_book(client, librarian, book_payload(a, p)).json()
    add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    assert error_code(client.delete(f"/api/v1/books/{b['id']}", headers=librarian)) == "BOOK_HAS_COPIES"
    assert error_code(client.delete(f"/api/v1/authors/{a['id']}", headers=librarian)) == "IN_USE"
    assert error_code(client.delete(f"/api/v1/publishers/{p['id']}", headers=librarian)) == "IN_USE"
'''),
    dict(id="T-CAT-07-a", req="LIB-CAT-07", type="Normal", input="Add copy with barcode `abc-123`", expected="201; barcode `ABC-123`, `status` `available`, `current_branch_id` = home", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode="abc-123")
    assert c["barcode"] == "ABC-123" and c["status"] == "available" and c["current_branch_id"] == branch_a["id"]
'''),
    dict(id="T-CAT-07-b", req="LIB-CAT-07", type="Boundary", input="Barcodes `ABC12` (5) and 21 chars; `ABC-123` again; price `0.00` and `100000.01`; `acquired_on` tomorrow", expected="`422`; `409 CONFLICT`; `422`; `422`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode="ABC-123")
    for bc in ("ABC12", "A" * 21):
        add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode=bc, expect=422)
    add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], barcode="abc-123", expect=409)
    for price in ("0.00", "100000.01"):
        add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], price=price, expect=422)
    r = client.post(f"/api/v1/books/{b['id']}/copies", headers=librarian, json={"barcode": "TOMORROW1", "home_branch_id": branch_a["id"], "price": "10.00", "acquired_on": "2026-11-03"})
    assert r.status_code == 422
'''),
    dict(id="T-CAT-07-c", req="LIB-CAT-07", type="Normal", input="Waiting reservation (pickup A) for a lent-out book; a new copy is added at A", expected="New copy `on_hold`; reservation `ready`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    c1 = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c1["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    c2 = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    assert copy_status(client, librarian, c2["id"]) == "on_hold"
    assert client.get(f"/api/v1/reservations/{res['id']}", headers=librarian).json()["status"] == "ready"
'''),
    dict(id="T-CAT-08-a", req="LIB-CAT-08", type="Normal", input="Copies at A and B, one lent; filters `branch_id`, `status=on_loan`; `availability` in `BookOut`", expected="Before lending: availability A 2/2, B 1/1; after lending: filters return B's copy and the lent copy", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-CAT-09-a", req="LIB-CAT-09", type="Normal", input="PATCH `price`, `shelf_location`; PATCH `home_branch_id` of an available copy at home", expected="200; home and current branch both change", code='''
def TEST(client, librarian, branch_a, branch_b):
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    r = client.patch(f"/api/v1/copies/{c['id']}", headers=librarian, json={"price": "55.50", "shelf_location": "B-7"})
    assert r.status_code == 200 and r.json()["price"] == "55.50" and r.json()["shelf_location"] == "B-7"
    r = client.patch(f"/api/v1/copies/{c['id']}", headers=librarian, json={"home_branch_id": branch_b["id"]})
    assert r.json()["home_branch_id"] == branch_b["id"] and r.json()["current_branch_id"] == branch_b["id"]
'''),
    dict(id="T-CAT-09-b", req="LIB-CAT-09", type="Error", input="PATCH `home_branch_id` of a lent copy", expected="`409 INVALID_COPY_STATUS`", code='''
def TEST(client, librarian, branch_a, branch_b):
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    r = client.patch(f"/api/v1/copies/{c['id']}", headers=librarian, json={"home_branch_id": branch_b["id"]})
    assert r.status_code == 409 and error_code(r) == "INVALID_COPY_STATUS"
'''),
    dict(id="T-CAT-10-a", req="LIB-CAT-10", type="Normal", input="Withdraw an available copy with reason `Water damage`", expected="200; `withdrawn`, `withdrawn_reason` stored", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    r = client.post(f"/api/v1/copies/{c['id']}/withdraw", headers=librarian, json={"reason": "Water damage"})
    assert r.status_code == 200 and r.json()["status"] == "withdrawn" and r.json()["withdrawn_reason"] == "Water damage"
'''),
    dict(id="T-CAT-10-b", req="LIB-CAT-10", type="Error", input="Withdraw a lent copy; reason of 4 characters; withdraw twice", expected="`409 INVALID_COPY_STATUS`; `422`; `409 INVALID_COPY_STATUS`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    lent = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    other = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], lent["id"])
    assert error_code(client.post(f"/api/v1/copies/{lent['id']}/withdraw", headers=librarian, json={"reason": "Lost it"})) == "INVALID_COPY_STATUS"
    assert client.post(f"/api/v1/copies/{other['id']}/withdraw", headers=librarian, json={"reason": "Old"}).status_code == 422
    client.post(f"/api/v1/copies/{other['id']}/withdraw", headers=librarian, json={"reason": "Too old"})
    assert error_code(client.post(f"/api/v1/copies/{other['id']}/withdraw", headers=librarian, json={"reason": "Too old"})) == "INVALID_COPY_STATUS"
'''),
    dict(id="T-CAT-11-a", req="LIB-CAT-11", type="Normal", input="Copy returned damaged at A, then repaired", expected="`damaged`, then `available`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], price="120.00")
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="40.00")
    assert copy_status(client, librarian, c["id"]) == "damaged"
    assert client.post(f"/api/v1/copies/{c['id']}/repair", headers=librarian).status_code == 200
    assert copy_status(client, librarian, c["id"]) == "available"
'''),
    dict(id="T-CAT-11-b", req="LIB-CAT-11", type="Error", input="Repair an available copy", expected="`409 INVALID_COPY_STATUS`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    r = client.post(f"/api/v1/copies/{c['id']}/repair", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "INVALID_COPY_STATUS"
'''),
    dict(id="T-CAT-12-a", req="LIB-CAT-12", type="Boundary", input="Book whose only copy is damaged (not lost/withdrawn); member reserves it", expected="Reservation accepted (book is lendable)", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    c = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"], price="120.00")
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
'''),
]
