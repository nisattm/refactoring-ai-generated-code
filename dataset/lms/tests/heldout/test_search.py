"""Heldout tests: module 9 (Search). Generated from cases/search.md."""
from support.api import add_copy, create_book, lend, register_member


def author(client, lib, name):
    return client.post("/api/v1/authors", headers=lib, json={"name": name}).json()


def publisher(client, lib, name):
    return client.post("/api/v1/publishers", headers=lib, json={"name": name}).json()


def book(client, lib, title, a, p, **kw):
    return create_book(client, lib, title=title, author_ids=[a["id"]], publisher_id=p["id"], **kw)


def search(client, headers, **params):
    r = client.get("/api/v1/search/books", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def titles(client, headers, **params):
    return [i["book"]["title"] for i in search(client, headers, **params)["items"]]


def test_t_srch_01_b(client, librarian):
    """T-SRCH-01-b (LIB-SRCH-01): Found, found, not found (ş is not folded)"""
    a, p = author(client, librarian, "Yazar"), publisher(client, librarian, "Yayınevi")
    book(client, librarian, "Işık Avcısı", a, p)
    assert titles(client, librarian, q="işik") == ["Işık Avcısı"]
    assert titles(client, librarian, q="IŞIK") == ["Işık Avcısı"]
    assert titles(client, librarian, q="isik") == []


def test_t_srch_02_b(client, librarian):
    """T-SRCH-02-b (LIB-SRCH-02): All 2 books; all 2 books; only that book"""
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    book(client, librarian, "First", a, p, isbn="9780306406157")
    book(client, librarian, "Second", a, p, isbn="9780140449136")
    assert search(client, librarian)["total"] == 2
    assert search(client, librarian, q="   ")["total"] == 2
    assert titles(client, librarian, q="9780140449136") == ["Second"]


def test_t_srch_03_b(client, librarian):
    """T-SRCH-03-b (LIB-SRCH-03): 422 VALIDATION_ERROR"""
    r = client.get("/api/v1/search/books", headers=librarian, params={"year_from": 2010, "year_to": 2000})
    assert r.status_code == 422


def test_t_srch_04_a(client, librarian, branch_a, branch_b):
    """T-SRCH-04-a (LIB-SRCH-04): Y; none; Y"""
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    x = book(client, librarian, "Xbook", a, p)
    y = book(client, librarian, "Ybook", a, p)
    cx = add_copy(client, librarian, x["id"], home_branch_id=branch_a["id"])
    add_copy(client, librarian, y["id"], home_branch_id=branch_b["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], cx["id"])
    assert titles(client, librarian, available_only="true") == ["Ybook"]
    assert titles(client, librarian, available_only="true", branch_id=branch_a["id"]) == []
    assert titles(client, librarian, branch_id=branch_b["id"]) == ["Ybook"]


def test_t_srch_05_b(client, librarian):
    """T-SRCH-05-b (LIB-SRCH-05): 10 + 3 = 13; score 0"""
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    book(client, librarian, "Deniz Feneri", a, p, isbn="9780306406157")
    assert search(client, librarian, q="9780306406157 deniz")["items"][0]["score"] == 13
    assert search(client, librarian)["items"][0]["score"] == 0


def test_t_srch_06_b(client, librarian, branch_a):
    """T-SRCH-06-b (LIB-SRCH-06): B, A, C; loan_count 2, 1, 0"""
    from support.api import return_loan
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    ba, bb, bc = (book(client, librarian, t, a, p) for t in ("Abook", "Bbook", "Cbook"))
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    ca = add_copy(client, librarian, ba["id"], home_branch_id=branch_a["id"])
    cb = add_copy(client, librarian, bb["id"], home_branch_id=branch_a["id"])
    l1 = lend(client, librarian, m["id"], cb["id"])
    return_loan(client, librarian, l1["id"], branch_id=branch_a["id"])
    lend(client, librarian, m["id"], cb["id"])
    lend(client, librarian, m["id"], ca["id"])
    items = search(client, librarian, sort="popularity")["items"]
    assert [(i["book"]["title"], i["loan_count"]) for i in items] == [("Bbook", 2), ("Abook", 1), ("Cbook", 0)]
