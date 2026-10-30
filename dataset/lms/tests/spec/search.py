MODULE = "search"
TITLE = "module 9 (Search)"

HEADER = '''
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
'''


CASES = [
    dict(id="T-SRCH-01-a", req="LIB-SRCH-01", type="Normal", input="Book `İstanbul Hatırası`; `q` = `ISTANBUL`, `istanbul`, `İstanbul`", expected="Found with each query", code='''
def TEST(client, librarian):
    a, p = author(client, librarian, "Ahmet Ümit"), publisher(client, librarian, "Everest")
    book(client, librarian, "İstanbul Hatırası", a, p)
    for q in ("ISTANBUL", "istanbul", "İstanbul"):
        assert titles(client, librarian, q=q) == ["İstanbul Hatırası"], q
'''),
    dict(id="T-SRCH-01-b", req="LIB-SRCH-01", type="Boundary", input="Book `Işık Avcısı`; `q` = `işik`, `IŞIK`, `isik`", expected="Found, found, not found (`ş` is not folded)", code='''
def TEST(client, librarian):
    a, p = author(client, librarian, "Yazar"), publisher(client, librarian, "Yayınevi")
    book(client, librarian, "Işık Avcısı", a, p)
    assert titles(client, librarian, q="işik") == ["Işık Avcısı"]
    assert titles(client, librarian, q="IŞIK") == ["Işık Avcısı"]
    assert titles(client, librarian, q="isik") == []
'''),
    dict(id="T-SRCH-02-a", req="LIB-SRCH-02", type="Normal", input="`Kar` and `Kara Kitap` by Orhan Pamuk, `Kar Tanesi` by Ayşe Kulin; `q=kar pamuk`", expected="Both Pamuk books, not `Kar Tanesi` (every token must match)", code='''
def TEST(client, librarian):
    pamuk, kulin = author(client, librarian, "Orhan Pamuk"), author(client, librarian, "Ayşe Kulin")
    p = publisher(client, librarian, "İletişim")
    book(client, librarian, "Kar", pamuk, p)
    book(client, librarian, "Kara Kitap", pamuk, p)
    book(client, librarian, "Kar Tanesi", kulin, p)
    assert sorted(titles(client, librarian, q="kar pamuk")) == ["Kar", "Kara Kitap"]
'''),
    dict(id="T-SRCH-02-b", req="LIB-SRCH-02", type="Boundary", input="No `q`; `q` of spaces; `q` = the ISBN of one book", expected="All 2 books; all 2 books; only that book", code='''
def TEST(client, librarian):
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    book(client, librarian, "First", a, p, isbn="9780306406157")
    book(client, librarian, "Second", a, p, isbn="9780140449136")
    assert search(client, librarian)["total"] == 2
    assert search(client, librarian, q="   ")["total"] == 2
    assert titles(client, librarian, q="9780140449136") == ["Second"]
'''),
    dict(id="T-SRCH-03-a", req="LIB-SRCH-03", type="Normal", input="Filters `author=pamuk`, `publisher=YAPI`, `language=en`, `year_from=2000&year_to=2005`, `classification_prefix=81`, combined", expected="Each filter returns the matching books; combined filters are AND", code='''
def TEST(client, librarian):
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
'''),
    dict(id="T-SRCH-03-b", req="LIB-SRCH-03", type="Error", input="`year_from=2010&year_to=2000`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, librarian):
    r = client.get("/api/v1/search/books", headers=librarian, params={"year_from": 2010, "year_to": 2000})
    assert r.status_code == 422
'''),
    dict(id="T-SRCH-04-a", req="LIB-SRCH-04", type="Normal", input="Book X: copy at A lent; book Y: copy available at B; `available_only=true`; with `branch_id=A`; `branch_id=B` alone", expected="Y; none; Y", code='''
def TEST(client, librarian, branch_a, branch_b):
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    x = book(client, librarian, "Xbook", a, p)
    y = book(client, librarian, "Ybook", a, p)
    cx = add_copy(client, librarian, x["id"], home_branch_id=branch_a["id"])
    add_copy(client, librarian, y["id"], home_branch_id=branch_b["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], cx["id"])
    assert titles(client, librarian, available_only="true") == ["Ybook"]
    assert titles(client, librarian, available_only="true", branch_id=branch_a["id"]) == []
    assert titles(client, librarian, branch_id=branch_b["id"]) == ["Ybook"]
'''),
    dict(id="T-SRCH-05-a", req="LIB-SRCH-05", type="Normal", input="`q=kar`: title `Kar`, author `Karl May`, publisher `Karınca`, title `Kar` by author `Karl May` (both)", expected="Scores 3, 2, 1 and 3 (highest per token, not summed)", code='''
def TEST(client, librarian):
    karl, other = author(client, librarian, "Karl May"), author(client, librarian, "Zeynep")
    kar_pub, plain = publisher(client, librarian, "Karınca"), publisher(client, librarian, "Plain")
    book(client, librarian, "Kar", other, plain)
    book(client, librarian, "Winnetou", karl, plain)
    book(client, librarian, "Deniz", other, kar_pub)
    book(client, librarian, "Kar Masalı", karl, plain)
    scores = {i["book"]["title"]: i["score"] for i in search(client, librarian, q="kar")["items"]}
    assert scores == {"Kar": 3, "Winnetou": 2, "Deniz": 1, "Kar Masalı": 3}
'''),
    dict(id="T-SRCH-05-b", req="LIB-SRCH-05", type="Boundary", input="`q` = exact ISBN plus a title word; no `q`", expected="10 + 3 = 13; score 0", code='''
def TEST(client, librarian):
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    book(client, librarian, "Deniz Feneri", a, p, isbn="9780306406157")
    assert search(client, librarian, q="9780306406157 deniz")["items"][0]["score"] == 13
    assert search(client, librarian)["items"][0]["score"] == 0
'''),
    dict(id="T-SRCH-06-a", req="LIB-SRCH-06", type="Normal", input="Sorts `relevance` (tie on score), `title`, `year_desc`, `year_asc`", expected="Score then title; title; years descending and ascending with title as tie-breaker", code='''
def TEST(client, librarian):
    a, p = author(client, librarian, "A"), publisher(client, librarian, "P")
    book(client, librarian, "beta kar", a, p, publication_year=2001)
    book(client, librarian, "Alfa Kar", a, p, publication_year=2005)
    book(client, librarian, "Gama", a, p, publication_year=2005)
    assert titles(client, librarian, q="kar") == ["Alfa Kar", "beta kar"]
    assert titles(client, librarian, sort="title") == ["Alfa Kar", "beta kar", "Gama"]
    assert titles(client, librarian, sort="year_desc") == ["Alfa Kar", "Gama", "beta kar"]
    assert titles(client, librarian, sort="year_asc") == ["beta kar", "Alfa Kar", "Gama"]
'''),
    dict(id="T-SRCH-06-b", req="LIB-SRCH-06", type="Normal", input="`sort=popularity`: book B lent twice (one returned), book A once, book C never", expected="B, A, C; `loan_count` 2, 1, 0", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SRCH-07-a", req="LIB-SRCH-07", type="Normal", input="25 books; `page=2&page_size=10`; member searches", expected="Paginated envelope (`total` 25, 10 items); each item has `book` (`BookOut`), `score`, `loan_count`; members may search", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SRCH-08-a", req="LIB-SRCH-08", type="Static", input="Workload W1 data set (100,000 books, 200,000 copies)", expected="Results equal those of a reference filter over the same data (checked by the benchmark script)", code=None),
]
