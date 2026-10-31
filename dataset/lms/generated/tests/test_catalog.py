import pytest
import sqlalchemy as sa

from lms.catalog.models import Copy
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_branches import lib_h, mk_branch

API = "/api/v1"


def mk_author(client, hd, name="Ada Lovelace"):
    r = client.post(f"{API}/authors", headers=hd, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def mk_publisher(client, hd, name="Pub House"):
    r = client.post(f"{API}/publishers", headers=hd, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def book_body(a=1, p=1, **kw):
    return {
        "isbn": "978-0-306-40615-7",
        "title": "Analytical Engines",
        "subtitle": None,
        "author_ids": [a],
        "publisher_id": p,
        "publication_year": 2020,
        "language": "en",
        "classification": "005.133",
        **kw,
    }


@pytest.fixture
def cat(client, admin_h):
    mk_branch(client, admin_h, "MERKEZ")
    mk_branch(client, admin_h, "KAMPUS")
    mk_author(client, admin_h)
    mk_publisher(client, admin_h)
    r = client.post(f"{API}/books", headers=admin_h, json=book_body())
    assert r.status_code == 201, r.text
    return r.json()


def mk_copy(client, hd, book_id=1, barcode="BC-0001", branch=1, **kw):
    body = {"barcode": barcode, "home_branch_id": branch, "price": "50.00", "acquired_on": "2026-10-01", **kw}
    return client.post(f"{API}/books/{book_id}/copies", headers=hd, json=body)


def set_status(app, copy_id, status):
    with app.state.session_factory.begin() as s:
        s.get(Copy, copy_id).status = status


def test_isbn_normalization(client, admin_h, cat):
    r = client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="0-306-40615-2"))
    err(r, 409, "CONFLICT")  # same book as 978-0-306-40615-7
    r = client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="0 8044 2957 x"))
    assert r.status_code == 201 and r.json()["isbn"] == "9780804429573"
    for bad in ("0-306-40615-3", "9780306406158", "9770306406157", "12345", "abcdefghij", 123, "030640615Y"):
        err(client.post(f"{API}/books", headers=admin_h, json=book_body(isbn=bad)), 422, "VALIDATION_ERROR")


def test_book_create_and_out(client, admin_h, cat, app):
    assert cat["isbn"] == "9780306406157" and cat["authors"] == [{"id": 1, "name": "Ada Lovelace"}]
    assert cat["publisher"] == {"id": 1, "name": "Pub House"} and cat["availability"] == []
    assert cat["subtitle"] is None and cat["created_at"].endswith("+03:00")
    assert [a.entity_id for a in audit(app, "book_created")] == [1]


def test_book_validation(client, admin_h, cat):
    for kw in (
        {"title": " "}, {"subtitle": "x" * 201}, {"author_ids": []}, {"author_ids": [1, 1]},
        {"author_ids": list(range(1, 12))}, {"publication_year": 1449}, {"publication_year": 2027},
        {"language": "EN"}, {"language": "eng"}, {"classification": "05"}, {"classification": "005.1234567"},
        {"classification": "005."}, {"extra": 1},
    ):
        err(client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780804429573", **kw)), 422, "VALIDATION_ERROR")
    ok = client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780804429573", publication_year=2026, classification="005"))
    assert ok.status_code == 201


def test_book_references(client, admin_h, cat):
    e = err(client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780804429573", a=9)), 404, "NOT_FOUND")
    assert e["details"] == {"field": "author_ids", "id": 9}
    e = err(client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780804429573", p=9)), 404, "NOT_FOUND")
    assert e["details"] == {"field": "publisher_id", "id": 9}


def test_author_order_and_list(client, admin_h):
    for n in ("Zed", "İzmir Writer", "Ayşe", "ali"):
        mk_author(client, admin_h, n)
    names = [a["name"] for a in client.get(f"{API}/authors", headers=admin_h).json()["items"]]
    assert names == ["ali", "Ayşe", "İzmir Writer", "Zed"]
    r = client.get(f"{API}/authors?q=IZM", headers=admin_h).json()
    assert [a["name"] for a in r["items"]] == ["İzmir Writer"] and r["total"] == 1


def test_publisher_unique_and_patch(client, admin_h):
    mk_publisher(client, admin_h, "Iğdır Yayınları")
    err(client.post(f"{API}/publishers", headers=admin_h, json={"name": "IĞDIR yayınları"}), 409, "CONFLICT")
    mk_publisher(client, admin_h, "Other")
    assert client.patch(f"{API}/publishers/2", headers=admin_h, json={"name": "other"}).json()["name"] == "other"
    err(client.patch(f"{API}/publishers/2", headers=admin_h, json={"name": "iğdır Yayınları"}), 409, "CONFLICT")
    err(client.patch(f"{API}/publishers/9", headers=admin_h, json={"name": "x"}), 404, "NOT_FOUND")


def test_delete_in_use(client, admin_h, cat):
    err(client.delete(f"{API}/authors/1", headers=admin_h), 409, "IN_USE")
    err(client.delete(f"{API}/publishers/1", headers=admin_h), 409, "IN_USE")
    mk_copy(client, admin_h)
    err(client.delete(f"{API}/books/1", headers=admin_h), 409, "BOOK_HAS_COPIES")
    client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "worn out"})
    err(client.delete(f"{API}/books/1", headers=admin_h), 409, "BOOK_HAS_COPIES")


def test_delete_book_then_author_publisher(client, admin_h, cat, app):
    assert client.delete(f"{API}/books/1", headers=admin_h).status_code == 204
    assert [a.entity_id for a in audit(app, "book_deleted")] == [1]
    err(client.get(f"{API}/books/1", headers=admin_h), 404, "NOT_FOUND")
    assert client.delete(f"{API}/authors/1", headers=admin_h).status_code == 204
    assert client.delete(f"{API}/publishers/1", headers=admin_h).status_code == 204


def test_list_books_filters_and_order(client, admin_h, cat):
    mk_author(client, admin_h, "Second")
    mk_publisher(client, admin_h, "Second Pub")
    client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780804429573", title="analytical a", a=2, p=2, language="tr", classification="813"))
    client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780262033848", title="Zebra", classification="005"))

    def titles(qs=""):
        return [b["title"] for b in client.get(f"{API}/books{qs}", headers=admin_h).json()["items"]]

    assert titles() == ["analytical a", "Analytical Engines", "Zebra"]
    assert titles("?isbn=0-306-40615-2") == ["Analytical Engines"]
    assert titles("?author_id=2") == ["analytical a"]
    assert titles("?publisher_id=1") == ["Analytical Engines", "Zebra"]
    assert titles("?language=tr") == ["analytical a"]
    assert titles("?classification_prefix=005") == ["Analytical Engines", "Zebra"]
    assert titles("?classification_prefix=005.1") == ["Analytical Engines"]
    err(client.get(f"{API}/books?isbn=bad", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/books?page=0", headers=admin_h), 422, "VALIDATION_ERROR")


def test_patch_book(client, admin_h, cat, app):
    mk_author(client, admin_h, "Second")
    r = client.patch(f"{API}/books/1", headers=admin_h, json={"title": "New", "author_ids": [2, 1], "subtitle": "sub"})
    assert r.status_code == 200
    b = r.json()
    assert b["title"] == "New" and [a["id"] for a in b["authors"]] == [2, 1] and b["subtitle"] == "sub"
    entry = audit(app, "book_updated")[0].details
    assert entry["title"] == {"old": "Analytical Engines", "new": "New"} and entry["author_ids"] == {"old": [1], "new": [2, 1]}
    assert client.patch(f"{API}/books/1", headers=admin_h, json={"subtitle": None}).json()["subtitle"] is None
    err(client.patch(f"{API}/books/1", headers=admin_h, json={"title": None}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/books/1", headers=admin_h, json={"publication_year": 2999}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/books/9", headers=admin_h, json={"title": "x"}), 404, "NOT_FOUND")
    err(client.patch(f"{API}/books/9", headers=admin_h, json={"title": ""}), 422, "VALIDATION_ERROR")
    client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780804429573"))
    err(client.patch(f"{API}/books/2", headers=admin_h, json={"isbn": "0-306-40615-2"}), 409, "CONFLICT")
    assert client.patch(f"{API}/books/2", headers=admin_h, json={"isbn": "9780804429573"}).status_code == 200
    err(client.patch(f"{API}/books/2", headers=admin_h, json={"author_ids": [7]}), 404, "NOT_FOUND")


def test_permissions(client, admin_h, cat, app):
    lh = lib_h(client, admin_h)
    mem = client.post(
        f"{API}/members", headers=lh,
        json={"full_name": "M One", "email": "m@example.com", "membership_type": "student", "university_id": "S1234",
              "home_branch_id": 1, "password": "Passw0rd1"},
    )
    assert mem.status_code == 201
    mh = h(token_of(client, "m@example.com", "Passw0rd1"))
    mk_copy(client, lh)
    for path in ("/authors", "/authors/1", "/publishers", "/publishers/1", "/books", "/books/1", "/books/1/copies",
                 "/copies/1", "/copies/by-barcode/bc-0001"):
        assert client.get(API + path, headers=mh).status_code == 200, path
        err(client.get(API + path), 401, "UNAUTHENTICATED")
    for method, path, body in (
        ("post", "/authors", {"name": "x"}), ("patch", "/authors/1", {"name": "x"}), ("delete", "/authors/1", None),
        ("post", "/publishers", {"name": "x"}), ("delete", "/books/1", None), ("post", "/books", book_body()),
        ("patch", "/books/1", {}), ("post", "/books/1/copies", {}), ("patch", "/copies/1", {}),
        ("post", "/copies/1/withdraw", {"reason": "12345"}), ("post", "/copies/1/repair", None),
    ):
        err(client.request(method, API + path, headers=mh, json=body), 403, "FORBIDDEN")
    assert client.patch(f"{API}/authors/1", headers=lh, json={"name": "Lib Edit"}).status_code == 200


def test_add_copy(client, admin_h, cat, app):
    r = mk_copy(client, admin_h, barcode="ab-1234", shelf_location="A1")
    assert r.status_code == 201
    c = r.json()
    assert c == {
        "id": 1, "book_id": 1, "barcode": "AB-1234", "home_branch_id": 1, "current_branch_id": 1, "price": "50.00",
        "status": "available", "acquired_on": "2026-10-01", "shelf_location": "A1", "withdrawn_reason": None,
    }
    assert [a.entity_id for a in audit(app, "copy_added")] == [1]
    err(mk_copy(client, admin_h, barcode="AB-1234", branch=2), 409, "CONFLICT")
    mk_copy(client, admin_h, barcode="XY-9999", branch=2)
    b = client.get(f"{API}/books/1", headers=admin_h).json()
    assert b["availability"] == [{"branch_id": 1, "available": 1, "total": 1}, {"branch_id": 2, "available": 1, "total": 1}]
    set_status(app, 1, "on_loan")
    b = client.get(f"{API}/books/1", headers=admin_h).json()
    assert b["availability"][0] == {"branch_id": 1, "available": 0, "total": 1}
    set_status(app, 1, "lost")
    assert client.get(f"{API}/books/1", headers=admin_h).json()["availability"][0] == {"branch_id": 1, "available": 0, "total": 0}


def test_copy_validation_and_refs(client, admin_h, cat):
    for kw in (
        {"barcode": "ABC12"}, {"barcode": "A" * 21}, {"barcode": "AB_123"}, {"price": "0.00"}, {"price": "100000.01"},
        {"price": 5}, {"price": "1.234"}, {"price": "-1.00"}, {"acquired_on": "2026-11-03"}, {"acquired_on": "bad"},
        {"shelf_location": "x" * 51}, {"extra": 1},
    ):
        err(mk_copy(client, admin_h, **kw), 422, "VALIDATION_ERROR")
    assert mk_copy(client, admin_h, price="100000.00", acquired_on="2026-11-02").status_code == 201
    e = err(mk_copy(client, admin_h, barcode="BC-0002", branch=9), 404, "NOT_FOUND")
    assert e["details"] == {"field": "home_branch_id", "id": 9}
    err(mk_copy(client, admin_h, book_id=9), 404, "NOT_FOUND")
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(mk_copy(client, admin_h, barcode="BC-0003", branch=2), 409, "BRANCH_INACTIVE")


def test_list_copies_and_barcode(client, admin_h, cat, app):
    mk_copy(client, admin_h, barcode="BC-0001")
    mk_copy(client, admin_h, barcode="BC-0002", branch=2)
    mk_copy(client, admin_h, barcode="BC-0003")
    set_status(app, 3, "damaged")

    def ids(qs):
        return [c["id"] for c in client.get(f"{API}/books/1/copies{qs}", headers=admin_h).json()["items"]]

    assert ids("") == [1, 2, 3] and ids("?status=damaged") == [3] and ids("?branch_id=1") == [1, 3]
    err(client.get(f"{API}/books/1/copies?status=nope", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/books/9/copies", headers=admin_h), 404, "NOT_FOUND")
    assert client.get(f"{API}/copies/by-barcode/bc-0002", headers=admin_h).json()["id"] == 2
    err(client.get(f"{API}/copies/by-barcode/NOPE-00", headers=admin_h), 404, "NOT_FOUND")
    err(client.get(f"{API}/copies/0", headers=admin_h), 422, "VALIDATION_ERROR")


def test_update_copy(client, admin_h, cat, app):
    mk_copy(client, admin_h)
    r = client.patch(f"{API}/copies/1", headers=admin_h, json={"price": "75.50", "shelf_location": "B2"})
    assert r.status_code == 200 and r.json()["price"] == "75.50" and r.json()["shelf_location"] == "B2"
    assert audit(app, "copy_updated")[0].details["price"] == {"old": "50.00", "new": "75.50"}
    r = client.patch(f"{API}/copies/1", headers=admin_h, json={"home_branch_id": 2})
    assert r.json()["home_branch_id"] == 2 and r.json()["current_branch_id"] == 2
    assert client.patch(f"{API}/copies/1", headers=admin_h, json={"shelf_location": None}).json()["shelf_location"] is None
    err(client.patch(f"{API}/copies/1", headers=admin_h, json={"price": "0.00"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/copies/1", headers=admin_h, json={"barcode": "NEW-0001"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/copies/1", headers=admin_h, json={"home_branch_id": 9}), 404, "NOT_FOUND")
    set_status(app, 1, "on_loan")
    err(client.patch(f"{API}/copies/1", headers=admin_h, json={"home_branch_id": 1}), 409, "INVALID_COPY_STATUS")
    assert client.patch(f"{API}/copies/1", headers=admin_h, json={"price": "10.00"}).status_code == 200
    err(client.patch(f"{API}/copies/9", headers=admin_h, json={}), 404, "NOT_FOUND")


def test_withdraw(client, admin_h, cat, app):
    for i in range(1, 6):
        mk_copy(client, admin_h, barcode=f"BC-000{i}")
    err(client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "abcd"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "x" * 501}), 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": " torn pages "})
    assert r.status_code == 200 and r.json()["status"] == "withdrawn" and r.json()["withdrawn_reason"] == "torn pages"
    assert [a.entity_id for a in audit(app, "copy_withdrawn")] == [1]
    err(client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "again"}), 409, "INVALID_COPY_STATUS")
    for cid, status, ok in ((2, "damaged", True), (3, "lost", True), (4, "on_loan", False), (5, "on_hold", False)):
        set_status(app, cid, status)
        code = client.post(f"{API}/copies/{cid}/withdraw", headers=admin_h, json={"reason": "reason!"}).status_code
        assert code == (200 if ok else 409)


def test_repair(client, admin_h, cat, app):
    mk_copy(client, admin_h)
    err(client.post(f"{API}/copies/1/repair", headers=admin_h), 409, "INVALID_COPY_STATUS")
    set_status(app, 1, "damaged")
    r = client.post(f"{API}/copies/1/repair", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "available"
    assert [a.entity_id for a in audit(app, "copy_repaired")] == [1]
    err(client.post(f"{API}/copies/9/repair", headers=admin_h), 404, "NOT_FOUND")


def test_transition_table():
    from lms.catalog.models import Copy as C
    from lms.catalog.status import set_status as move
    from lms.core.errors import Conflict

    allowed = {
        ("available", "on_loan"), ("available", "on_hold"), ("available", "in_transfer"), ("available", "withdrawn"),
        ("on_hold", "on_loan"), ("on_hold", "available"), ("on_hold", "in_transfer"), ("on_hold", "on_hold"),
        ("on_loan", "available"), ("on_loan", "on_hold"), ("on_loan", "in_transfer"), ("on_loan", "damaged"),
        ("on_loan", "lost"), ("in_transfer", "available"), ("in_transfer", "on_hold"), ("in_transfer", "in_transfer"),
        ("damaged", "available"), ("damaged", "on_hold"), ("damaged", "in_transfer"), ("damaged", "withdrawn"),
        ("lost", "withdrawn"),
    }
    names = ["available", "on_loan", "on_hold", "in_transfer", "damaged", "lost", "withdrawn"]
    for a in names:
        for b in names:
            c = C(id=1, status=a)
            if (a, b) in allowed:
                move(c, b)
                assert c.status == b
            else:
                with pytest.raises(Conflict) as ei:
                    move(c, b)
                assert ei.value.code == "INVALID_COPY_STATUS"


def test_branch_in_use_by_copy(client, admin_h, cat):
    mk_copy(client, admin_h, branch=2)
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "gone away"})
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200


def test_rollback_on_error(client, admin_h, cat, app):
    err(client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="9780804429573", a=9)), 404, "NOT_FOUND")
    assert [a.entity_id for a in audit(app, "book_created")] == [1]
    with app.state.session_factory() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Copy)) == 0
