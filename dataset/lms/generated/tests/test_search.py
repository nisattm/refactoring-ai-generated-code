import datetime
import time

import sqlalchemy as sa

from lms.catalog.models import Author, Book, BookAuthor, Copy, Publisher
from tests.test_auth import admin_h, err  # noqa: F401
from tests.test_loans import API, at, lend, lib, member_h, mk_member, new_copy, ret  # noqa: F401
from tests.test_catalog import book_body, mk_author, mk_publisher

ISBNS = ["9780306406157", "9780131103627", "9780201633610", "9780596007126", "9781491950296", "9781449355739"]


def add_book(client, hd, n, **kw):
    r = client.post(f"{API}/books", headers=hd, json=book_body(isbn=ISBNS[n], **kw))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def search(client, hd, **params):
    return client.get(f"{API}/search/books", headers=hd, params=params)


def ids(r):
    assert r.status_code == 200, r.text
    return [i["book"]["id"] for i in r.json()["items"]]


def test_permissions_and_validation(client, lib):
    mk_member(client, lib)
    assert err(client.get(f"{API}/search/books"), 401, "UNAUTHENTICATED")
    assert search(client, member_h(client, 1)).status_code == 200
    assert err(search(client, lib, q="x" * 201), 422, "VALIDATION_ERROR")
    assert search(client, lib, q="x" * 200).status_code == 200
    assert err(search(client, lib, year_from=2020, year_to=2019), 422, "VALIDATION_ERROR")
    assert err(search(client, lib, sort="nope"), 422, "VALIDATION_ERROR")
    assert err(search(client, lib, year_from="abc"), 422, "VALIDATION_ERROR")
    assert err(search(client, lib, page_size=101), 422, "VALIDATION_ERROR")
    assert search(client, lib).json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_turkish_normalization_and_tokens(client, lib):
    a = add_book(client, lib, 0, title="İstanbul Hatırası", subtitle="Şehir ve Işık")
    b = add_book(client, lib, 1, title="Other Book")
    for q in ("istanbul", "ISTANBUL", "İSTANBUL", "hatırası", "HATIRASI"):
        assert ids(search(client, lib, q=q)) == [a], q
    # ı -> i, so the dotless form matches the dotted one
    assert ids(search(client, lib, q="hatirasi")) == [a]
    assert ids(search(client, lib, q="IŞIK")) == [a]
    assert ids(search(client, lib, q="işik")) == [a]
    assert ids(search(client, lib, q="isik")) == []  # ş is not folded
    assert ids(search(client, lib, q="  istanbul   şehir ")) == [a]
    assert ids(search(client, lib, q="istanbul other")) == []
    assert sorted(ids(search(client, lib))) == [a, b]
    assert sorted(ids(search(client, lib, q="   "))) == [a, b]


def test_token_fields(client, lib, admin_h):
    mk_author(client, admin_h, "Grace Hopper")
    mk_publisher(client, admin_h, "Zeta Press")
    a = add_book(client, lib, 0, title="Alpha", subtitle="compilers", a=2, p=2)
    assert ids(search(client, lib, q="hopper")) == [a]
    assert ids(search(client, lib, q="zeta")) == [a]
    assert ids(search(client, lib, q="compil")) == [a]
    assert ids(search(client, lib, q="978030640")) == [a]  # ISBN substring
    assert ids(search(client, lib, q="alpha grace compilers")) == [a]
    assert ids(search(client, lib, author="HOPPER")) == [a]
    assert ids(search(client, lib, author="lovelace")) == []
    assert ids(search(client, lib, publisher="ZETA")) == [a]
    assert ids(search(client, lib, publisher="pub")) == []


def test_filters(client, lib):
    a = add_book(client, lib, 0, title="A", publication_year=2000, language="tr", classification="005.133")
    b = add_book(client, lib, 1, title="B", publication_year=2010, language="en", classification="813")
    c = add_book(client, lib, 2, title="C", publication_year=2020, language="en", classification="005")
    assert ids(search(client, lib, language="en")) == [b, c]
    assert ids(search(client, lib, language="EN")) == []
    assert ids(search(client, lib, year_from=2010)) == [b, c]
    assert ids(search(client, lib, year_to=2010)) == [a, b]
    assert ids(search(client, lib, year_from=2010, year_to=2010)) == [b]
    assert ids(search(client, lib, classification_prefix="005")) == [a, c]
    assert ids(search(client, lib, classification_prefix="005", language="en")) == [c]


def test_availability_filters(client, lib):
    a = add_book(client, lib, 0, title="A")
    b = add_book(client, lib, 1, title="B")
    c = add_book(client, lib, 2, title="C")
    m = mk_member(client, lib)
    ca = new_copy(client, lib, a, "BC-0001", branch=1)
    new_copy(client, lib, b, "BC-0002", branch=2)
    cc = new_copy(client, lib, c, "BC-0003", branch=1)
    assert ids(search(client, lib, branch_id=1)) == [a, c]
    assert ids(search(client, lib, branch_id=2)) == [b]
    assert ids(search(client, lib, available_only="true")) == [a, b, c]
    assert ids(search(client, lib, available_only="true", branch_id=2)) == [b]
    lend(client, lib, m, ca)
    assert ids(search(client, lib, available_only="true")) == [b, c]
    assert ids(search(client, lib, branch_id=1)) == [a, c]  # on loan still counts without available_only
    assert ids(search(client, lib, available_only="false", branch_id=1)) == [a, c]
    client.post(f"{API}/loans/1/report-lost", headers=lib)
    assert ids(search(client, lib, branch_id=1)) == [c]  # lost copies do not count
    assert cc


def test_relevance_score_and_order(client, lib, admin_h):
    mk_author(client, admin_h, "Python Smith")
    mk_publisher(client, admin_h, "Python Books")
    t = add_book(client, lib, 0, title="Learning Python")  # title: 3
    au = add_book(client, lib, 1, title="Zzz", a=2)  # author: 2
    pub = add_book(client, lib, 2, title="Aaa", p=2)  # publisher: 1
    sub = add_book(client, lib, 3, title="Bbb", subtitle="python tricks")  # subtitle: 1
    r = search(client, lib, q="python")
    assert ids(r) == [t, au, pub, sub]  # score desc, then title
    assert [i["score"] for i in r.json()["items"]] == [3, 2, 1, 1]
    r = search(client, lib, q="9780596007126 python")  # ISBN equals (10) + subtitle (1)
    assert ids(r) == [sub] and r.json()["items"][0]["score"] == 11
    # token equal to the ISBN scores 10; the other token must match too
    r = search(client, lib, q="9780596007126 bbb")
    assert ids(r) == [sub] and r.json()["items"][0]["score"] == 13
    r = search(client, lib)
    assert all(i["score"] == 0 for i in r.json()["items"])
    assert ids(r) == [pub, sub, t, au]  # title order when scores tie
    # multiple tokens add up
    r = search(client, lib, q="python learning")
    assert r.json()["items"][0]["score"] == 6


def test_sorting_and_popularity(client, lib):
    a = add_book(client, lib, 0, title="Beta", publication_year=2001)
    b = add_book(client, lib, 1, title="alpha", publication_year=2005)
    c = add_book(client, lib, 2, title="Gamma", publication_year=2005)
    d = add_book(client, lib, 3, title="Delta", publication_year=1999)
    assert ids(search(client, lib, sort="title")) == [b, a, d, c]
    assert ids(search(client, lib, sort="year_desc")) == [b, c, a, d]
    assert ids(search(client, lib, sort="year_asc")) == [d, a, b, c]
    m = mk_member(client, lib)
    cc = new_copy(client, lib, c, "BC-0003")
    cd = new_copy(client, lib, d, "BC-0004")
    new_copy(client, lib, d, "BC-0005")
    for _ in range(2):
        loan = lend(client, lib, m, cc).json()
        assert ret(client, lib, loan["id"]).status_code == 200
    loan = lend(client, lib, m, cd).json()
    r = search(client, lib, sort="popularity")
    assert ids(r) == [c, d, b, a]
    assert [i["loan_count"] for i in r.json()["items"]] == [2, 1, 0, 0]
    r = search(client, lib, sort="relevance")
    assert {i["book"]["id"]: i["loan_count"] for i in r.json()["items"]} == {a: 0, b: 0, c: 2, d: 1}
    assert loan


def test_response_shape_and_paging(client, lib):
    a = add_book(client, lib, 0, title="A")
    add_book(client, lib, 1, title="B")
    add_book(client, lib, 2, title="C")
    new_copy(client, lib, a, "BC-0001")
    r = search(client, lib, sort="title", page=2, page_size=2)
    body = r.json()
    assert (body["page"], body["page_size"], body["total"], len(body["items"])) == (2, 2, 3, 1)
    assert search(client, lib, page=5).json()["items"] == []
    item = search(client, lib, q="A", sort="title").json()["items"][0]
    assert set(item) == {"book", "score", "loan_count"}
    assert item["book"]["availability"] == [{"branch_id": 1, "available": 1, "total": 1}]
    assert item["book"]["authors"] == [{"id": 1, "name": "Ada Lovelace"}]


def test_scale(app, client, lib):
    n = 20000
    with app.state.session_factory.begin() as s:
        stamp = datetime.datetime(2026, 11, 2, tzinfo=datetime.timezone.utc)
        s.execute(sa.insert(Book), [
            {"isbn": f"{9780000000000 + i}", "title": f"Title {i} İstanbul", "title_key": f"title {i} istanbul",
             "subtitle": f"Sub {i}", "publisher_id": 1, "publication_year": 2000 + i % 25, "language": "en",
             "classification": "005", "created_at": stamp}
            for i in range(n)
        ])
        s.execute(sa.insert(BookAuthor), [{"book_id": i, "author_id": 1, "position": 0} for i in range(1, n + 1)])
    t0 = time.perf_counter()
    r = search(client, lib, q="istanbul title 777", sort="popularity")
    assert r.status_code == 200 and r.json()["total"] >= 1
    r = search(client, lib, q="lovelace", sort="relevance", page_size=100)
    assert r.json()["total"] == n
    assert time.perf_counter() - t0 < 5
