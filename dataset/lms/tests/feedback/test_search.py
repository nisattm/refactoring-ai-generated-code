"""Feedback tests: module 9 (Search). Generated from cases/search.md."""
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


def test_t_srch_01_a(client, librarian):
    """T-SRCH-01-a (LIB-SRCH-01): Found with each query"""
    a, p = author(client, librarian, "Ahmet Ümit"), publisher(client, librarian, "Everest")
    book(client, librarian, "İstanbul Hatırası", a, p)
    for q in ("ISTANBUL", "istanbul", "İstanbul"):
        assert titles(client, librarian, q=q) == ["İstanbul Hatırası"], q


def test_t_srch_02_a(client, librarian):
    """T-SRCH-02-a (LIB-SRCH-02): Both Pamuk books, not Kar Tanesi (every token must match)"""
    pamuk, kulin = author(client, librarian, "Orhan Pamuk"), author(client, librarian, "Ayşe Kulin")
    p = publisher(client, librarian, "İletişim")
    book(client, librarian, "Kar", pamuk, p)
    book(client, librarian, "Kara Kitap", pamuk, p)
    book(client, librarian, "Kar Tanesi", kulin, p)
    assert sorted(titles(client, librarian, q="kar pamuk")) == ["Kar", "Kara Kitap"]


def test_t_srch_03_a(client, librarian):
    """T-SRCH-03-a (LIB-SRCH-03): Each filter returns the matching books; combined filters are AND"""
    pamuk, kulin = author(client, librarian, "Orhan Pamuk"), author(client, librarian, "Ayşe Kulin")
    yk, ev = publisher(client, librarian, "Yapı Kredi"), publisher(client, librarian, "Everest")
    book(client, librarian, "Kar", pamuk, yk, publication_year=2002, language="tr", classification="813")
    book(client, librarian, "Snow", pamuk, ev, publication_year=2004, language="en", classification="813")
    book(client, librarian, "Nefes Nefese", kulin, ev, publication_year=2002, language="tr", classification="500")
    assert sorted(titles(client, librarian, author="pamuk")) == ["Kar", "Snow"]
    assert titles(client, librarian, publisher="YAPI") == ["Kar"]
    assert titles(client, librarian, language="en") == ["Snow"]
    assert sorted(titles(client, librarian, year_from=2000, year_to=2003)) == ["Kar", "Nefes Nefese"]
    assert titles(client, librarian, classification_prefix="5") == ["Nefes Nefese"]
    assert titles(client, librarian, author="pamuk", language="tr") == ["Kar"]


def test_t_srch_05_a(client, librarian):
    """T-SRCH-05-a (LIB-SRCH-05): Scores 3, 2, 1 and 3 (highest per token, not summed)"""
    karl, other = author(client, librarian, "Karl May"), author(client, librarian, "Zeynep")
    kar_pub, plain = publisher(client, librarian, "Karınca"), publisher(client, librarian, "Plain")
    book(client, librarian, "Kar", other, plain)
    book(client, librarian, "Winnetou", karl, plain)
    book(client, librarian, "Deniz", other, kar_pub)
    book(client, librarian, "Kar Masalı", karl, plain)
    scores = {i["book"]["title"]: i["score"] for i in search(client, librarian, q="kar")["items"]}
    assert scores == {"Kar": 3, "Winnetou": 2, "Deniz": 1, "Kar Masalı": 3}


def test_t_srch_06_a(client, librarian):
    """T-SRCH-06-a (LIB-SRCH-06): Score then title; title; years descending and ascending with title as tie-breaker"""
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    book(client, librarian, "beta kar", a, p, publication_year=2001)
    book(client, librarian, "Alfa Kar", a, p, publication_year=2005)
    book(client, librarian, "Gama", a, p, publication_year=2005)
    assert titles(client, librarian, q="kar") == ["Alfa Kar", "beta kar"]
    assert titles(client, librarian, sort="title") == ["Alfa Kar", "beta kar", "Gama"]
    assert titles(client, librarian, sort="year_desc") == ["Alfa Kar", "Gama", "beta kar"]
    assert titles(client, librarian, sort="year_asc") == ["beta kar", "Alfa Kar", "Gama"]


def test_t_srch_07_a(client, librarian, branch_a):
    """T-SRCH-07-a (LIB-SRCH-07): Paginated envelope (total 25, 10 items); each item has book (BookOut), score, loan_count; members may search"""
    from support.api import member_headers
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    for i in range(25):
        book(client, librarian, f"Book {i:02d}", a, p)
    body = search(client, librarian, page=2, page_size=10)
    assert body["total"] == 25 and len(body["items"]) == 10 and body["page"] == 2
    item = body["items"][0]
    assert set(item) == {"book", "score", "loan_count"} and {"isbn", "authors", "publisher", "availability"} <= set(item["book"])
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert client.get("/api/v1/search/books", headers=mh).status_code == 200
