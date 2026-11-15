"""Module 25: Purchase suggestions (LIB-SUG-01 to LIB-SUG-47).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (MERKEZ) and 2 (KAMPUS), books 1 (ISBN1) and 2 (ISBN2), members
1 and 2 (students), 3 (academic), 4 (staff), 5 (guest). Librarian: lib@example.com; supplier 1.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_branches import mk_branch
from tests.test_catalog import book_body, mk_author, mk_copy, mk_publisher
from tests.test_members import guest_body, reg
from tests.test_purchasing import mk_supplier

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))
ISBN1 = "9780306406157"
ISBN2 = "9780804429573"
ISBN3 = "9781402894626"  # not a book of the world


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


@pytest.fixture
def world(client, admin_h):
    mk_branch(client, admin_h, "MERKEZ")
    mk_branch(client, admin_h, "KAMPUS")
    mk_author(client, admin_h)
    mk_publisher(client, admin_h)
    for i, isbn in enumerate(("978-0-306-40615-7", "978-0-8044-2957-3"), start=1):
        r = client.post(f"{API}/books", headers=admin_h, json=book_body(isbn=isbn, title=f"Book {i}"))
        assert r.status_code == 201, r.text
    reg(client, admin_h, email="m1@example.edu.tr", university_id="STUD0001", full_name="Member One")
    reg(client, admin_h, email="m2@example.edu.tr", university_id="STUD0002", full_name="Member Two")
    reg(client, admin_h, email="m3@example.edu.tr", university_id="ACAD0003", full_name="Member Three",
        membership_type="academic")
    reg(client, admin_h, email="m4@example.edu.tr", university_id="STAF0004", full_name="Member Four",
        membership_type="staff")
    r = client.post(f"{API}/members", headers=admin_h, json=guest_body(full_name="Member Five"))
    assert r.status_code == 201, r.text
    make_user(client, admin_h)
    mk_supplier(client, admin_h)
    world = {f"m{i}": h(token_of(client, f"m{i}@example.edu.tr", "Passw0rd1")) for i in range(1, 5)}
    world["m5"] = h(token_of(client, "guest@example.com", "Passw0rd1"))
    world["lib"] = h(token_of(client, "lib@example.com", "Passw0rd1"))
    return world


def relogin(client, world):
    """Tokens expire after at most 168 hours: log in again after the clock moved far."""
    emails = {f"m{i}": f"m{i}@example.edu.tr" for i in range(1, 5)} | {"m5": "guest@example.com",
                                                                      "lib": "lib@example.com"}
    for key, email in emails.items():
        world[key] = h(token_of(client, email, "Passw0rd1"))


def body(**kw):
    return {"title": "Dune", "author_text": "F. Herbert", "isbn": None, "publication_year": 1965,
            "reason": "classic", "branch_id": 1, **kw}


def suggest(client, hd, expect=201, **kw):
    r = client.post(f"{API}/suggestions", headers=hd, json=body(**kw))
    assert r.status_code == expect, r.text
    return r.json()


def isbn_n(n):
    """A valid ISBN-13 that is not a book of the world."""
    stem = f"97800000{n:04d}"
    check = (10 - sum(int(d) * (1, 3)[i % 2] for i, d in enumerate(stem)) % 10) % 10
    return stem + str(check)


def sup(client, hd, sid, expect=201, **kw):
    r = client.post(f"{API}/suggestions/{sid}/support", headers=hd, json=kw)
    assert r.status_code == expect, r.text
    return r.json()


def approve(client, hd, sid, expect=200, book_id=1, quantity=1, price="40.00", **kw):
    r = client.post(f"{API}/suggestions/{sid}/approve", headers=hd,
                    json={"book_id": book_id, "quantity": quantity, "estimated_price": price, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


def notes(app, type_):
    return sel(app, sa.select(Notification).where(Notification.type == type_).order_by(Notification.id))


def deactivate(client, hd, member_id=5, expect=200):
    r = client.post(f"{API}/members/{member_id}/deactivate", headers=hd)
    assert r.status_code == expect, r.text


# --- suggesting ---------------------------------------------------------------------------------


def test_suggest_and_representation(client, world, app):
    s = suggest(client, world["m1"], isbn=ISBN3)
    assert s == {"id": 1, "title": "Dune", "author_text": "F. Herbert", "isbn": ISBN3, "publication_year": 1965,
                 "reason": "classic", "branch_id": 1, "status": "submitted", "reject_reason": None,
                 "review_note": "", "book_id": None, "quantity": None, "estimated_price": None,
                 "purchase_order_id": None, "merged_into_id": None, "withdraw_reason": None,
                 "submitted_at": "2026-11-02T09:30:00+03:00", "reviewed_at": None, "ordered_at": None,
                 "available_at": None, "score": 1, "supporters": 0, "supported_by_me": False, "mine": True,
                 "member_id": 1}
    assert [a.entity_id for a in audit(app, "suggestion_submitted")] == [1]
    staff = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert staff["member_id"] == 1 and "mine" not in staff and "supported_by_me" not in staff
    other = client.get(f"{API}/suggestions/1", headers=world["m2"]).json()
    assert "member_id" not in other and other["mine"] is False and other["supported_by_me"] is False


def test_suggest_defaults_and_validation(client, world):
    r = client.post(f"{API}/suggestions", headers=world["m1"], json={"title": " Minimal ", "branch_id": 2})
    s = r.json()
    assert r.status_code == 201 and s["title"] == "Minimal" and s["author_text"] == "" and s["isbn"] is None
    assert s["publication_year"] is None and s["reason"] == ""
    # ISBN-10 is normalized
    assert suggest(client, world["m1"], isbn="1-4028-9462-7")["isbn"] == ISBN3
    for bad in ({"title": ""}, {"title": "x" * 301}, {"author_text": "x" * 201}, {"reason": "x" * 501},
                {"isbn": "123"}, {"publication_year": 1449}, {"publication_year": 2027}, {"publication_year": "x"},
                {"branch_id": None}, {"extra": 1}):
        r = client.post(f"{API}/suggestions", headers=world["m1"], json=body(**bad))
        err(r, 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/suggestions", headers=world["m1"], json=body(branch_id=99))
    assert err(r, 422, "VALIDATION_ERROR")["details"]["fields"][0]["field"] == "branch_id"
    err(client.post(f"{API}/suggestions", headers=world["m1"], json=body(member_id=2)), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/suggestions", headers=world["lib"], json=body()), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/suggestions", json=body()), 401, "UNAUTHENTICATED")


def test_staff_suggests_for_member(client, world):
    s = suggest(client, world["lib"], member_id=2)
    assert s["member_id"] == 2
    r = client.post(f"{API}/suggestions", headers=world["lib"], json=body(member_id=99))
    assert err(r, 404, "NOT_FOUND")["details"] == {"field": "member_id", "id": 99}


def test_suggest_checks_in_order(client, world, admin_h, app, clock):
    deactivate(client, admin_h, 2)
    err(client.post(f"{API}/suggestions", headers=world["m2"], json=body()), 409, "MEMBER_PASSIVE")
    err(client.post(f"{API}/suggestions", headers=world["m5"], json=body()), 409, "MEMBERSHIP_TYPE_NOT_ALLOWED")
    # branch inactive comes before the limit
    mk_branch(client, admin_h, "THIRD")
    client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/suggestions", headers=world["m1"], json=body(branch_id=3)), 409, "BRANCH_INACTIVE")
    for n in range(3):
        suggest(client, world["m1"], isbn=isbn_n(n))
    e = err(client.post(f"{API}/suggestions", headers=world["m1"], json=body(isbn=isbn_n(9))), 409,
            "SUGGESTION_LIMIT_REACHED")
    assert e["details"]["limit"] == 3
    # after a withdrawal it is allowed again
    assert client.post(f"{API}/suggestions/1/withdraw", headers=world["m1"]).status_code == 200
    suggest(client, world["m1"], isbn=isbn_n(9))
    # limits per type
    for n in range(10):
        suggest(client, world["m3"], isbn=isbn_n(20 + n))
    assert err(client.post(f"{API}/suggestions", headers=world["m3"], json=body(isbn=isbn_n(40))), 409,
               "SUGGESTION_LIMIT_REACHED")["details"]["limit"] == 10
    for n in range(5):
        suggest(client, world["m4"], isbn=isbn_n(50 + n))
    assert err(client.post(f"{API}/suggestions", headers=world["m4"], json=body(isbn=isbn_n(60))), 409,
               "SUGGESTION_LIMIT_REACHED")["details"]["limit"] == 5


def test_already_owned_and_duplicate(client, world, admin_h):
    # a book without copies does not stop a suggestion (LIB-SUG-25)
    suggest(client, world["m1"], isbn=ISBN1)
    r = mk_copy(client, admin_h, book_id=2, barcode="BC-0002")
    assert r.status_code == 201
    e = err(client.post(f"{API}/suggestions", headers=world["m2"], json=body(isbn=ISBN2)), 409, "BOOK_ALREADY_OWNED")
    assert e["details"]["book_id"] == 2
    e = err(client.post(f"{API}/suggestions", headers=world["m2"], json=body(isbn=ISBN1)), 409, "DUPLICATE_SUGGESTION")
    assert e["details"]["suggestion_id"] == 1
    # withdrawn copies do not count as owned
    client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "worn out copy"})
    assert client.post(f"{API}/suggestions", headers=world["m2"], json=body(isbn=ISBN2)).status_code == 201


def test_recently_rejected(client, world, clock):
    s = suggest(client, world["m1"], isbn=ISBN3)
    r = client.post(f"{API}/suggestions/{s['id']}/reject", headers=world["lib"],
                    json={"reject_reason": "out_of_scope", "review_note": "no"})
    assert r.status_code == 200
    clock.set(datetime.datetime(2027, 4, 30, 9, 30, tzinfo=TZ))
    relogin(client, world)
    e = err(client.post(f"{API}/suggestions", headers=world["m1"], json=body(isbn=ISBN3)), 409,
            "SUGGESTION_RECENTLY_REJECTED")
    assert e["details"]["until"] == "2027-05-01"
    # another member is not affected
    assert client.post(f"{API}/suggestions", headers=world["m2"], json=body(isbn=ISBN3)).status_code == 201
    clock.set(datetime.datetime(2027, 5, 1, 9, 30, tzinfo=TZ))
    relogin(client, world)
    err(client.post(f"{API}/suggestions", headers=world["m1"], json=body(isbn=ISBN3)), 409, "DUPLICATE_SUGGESTION")
    client.post(f"{API}/suggestions/2/withdraw", headers=world["m2"])
    assert client.post(f"{API}/suggestions", headers=world["m1"], json=body(isbn=ISBN3)).status_code == 201


# --- change and withdraw ----------------------------------------------------------------------


def test_patch(client, world, app, admin_h):
    suggest(client, world["m1"])
    suggest(client, world["m2"], isbn=isbn_n(1))
    r = client.patch(f"{API}/suggestions/1", headers=world["m1"],
                     json={"title": "Dune Messiah", "publication_year": None, "isbn": None, "branch_id": 2})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Dune Messiah" and r.json()["isbn"] is None and r.json()["branch_id"] == 2
    assert len(audit(app, "suggestion_updated")) == 1
    err(client.patch(f"{API}/suggestions/1", headers=world["m1"], json={"isbn": isbn_n(1)}), 409, "DUPLICATE_SUGGESTION")
    err(client.patch(f"{API}/suggestions/1", headers=world["m1"], json={"title": None}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/suggestions/1", headers=world["m1"], json={"branch_id": 99}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/suggestions/1", headers=world["m2"], json={"title": "x"}), 403, "FORBIDDEN")
    err(client.patch(f"{API}/suggestions/1", headers=world["lib"], json={"title": "x"}), 403, "FORBIDDEN")
    err(client.patch(f"{API}/suggestions/99", headers=world["m1"], json={"title": "x"}), 404, "NOT_FOUND")
    client.post(f"{API}/suggestions/1/approve", headers=world["lib"],
                json={"book_id": 1, "quantity": 1, "estimated_price": "10.00"})
    e = err(client.patch(f"{API}/suggestions/1", headers=world["m1"], json={"title": "x"}), 409,
            "INVALID_SUGGESTION_STATUS")
    assert e["details"]["status"] == "approved"


def test_patch_owned_isbn_and_inactive_branch(client, world, admin_h):
    suggest(client, world["m1"])
    mk_copy(client, admin_h, book_id=1, barcode="BC-0001")
    err(client.patch(f"{API}/suggestions/1", headers=world["m1"], json={"isbn": ISBN1}), 409, "BOOK_ALREADY_OWNED")
    mk_branch(client, admin_h, "THIRD")
    client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False})
    err(client.patch(f"{API}/suggestions/1", headers=world["m1"], json={"branch_id": 3}), 409, "BRANCH_INACTIVE")


def test_withdraw(client, world, app):
    suggest(client, world["m1"])
    suggest(client, world["m1"], isbn=None)
    suggest(client, world["m2"], isbn=None)
    err(client.post(f"{API}/suggestions/1/withdraw", headers=world["m2"]), 403, "FORBIDDEN")
    r = client.post(f"{API}/suggestions/1/withdraw", headers=world["m1"])
    assert r.status_code == 200 and r.json()["status"] == "withdrawn" and r.json()["withdraw_reason"] == "member_request"
    err(client.post(f"{API}/suggestions/1/withdraw", headers=world["m1"]), 409, "INVALID_SUGGESTION_STATUS")
    err(client.post(f"{API}/suggestions/1/withdraw", headers=world["lib"]), 409, "INVALID_SUGGESTION_STATUS")
    # approved: only staff may withdraw
    approve(client, world["lib"], 2)
    err(client.post(f"{API}/suggestions/2/withdraw", headers=world["m1"]), 409, "INVALID_SUGGESTION_STATUS")
    assert client.post(f"{API}/suggestions/2/withdraw", headers=world["lib"]).status_code == 200
    assert len(audit(app, "suggestion_withdrawn")) == 2


def test_withdraw_with_supporters(client, world):
    suggest(client, world["m1"])
    sup(client, world["m2"], 1)
    sup(client, world["m3"], 1)
    sup(client, world["m4"], 1)
    err(client.post(f"{API}/suggestions/1/withdraw", headers=world["m1"]), 409, "SUGGESTION_HAS_SUPPORTERS")
    assert client.post(f"{API}/suggestions/1/withdraw", headers=world["lib"]).status_code == 200


# --- support ------------------------------------------------------------------------------------


def test_support_and_score(client, world, app):
    suggest(client, world["m1"])
    r = client.post(f"{API}/suggestions/1/support", headers=world["m3"])
    assert r.status_code == 201
    assert r.json()["supported_by_me"] is True and r.json()["mine"] is False and "member_id" not in r.json()
    sup(client, world["m4"], 1, reserve_on_arrival=False)
    s = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert (s["score"], s["supporters"]) == (4, 2)
    assert client.delete(f"{API}/suggestions/1/support", headers=world["m3"]).status_code == 204
    s = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert (s["score"], s["supporters"]) == (2, 1)
    assert len(audit(app, "suggestion_supported")) == 2 and len(audit(app, "suggestion_support_removed")) == 1
    r = client.get(f"{API}/suggestions/1/supporters", headers=world["lib"])
    assert r.json() == {"items": [{"member_id": 4, "full_name": "Member Four", "membership_type": "staff",
                                   "reserve_on_arrival": False, "created_at": "2026-11-02T09:30:00+03:00"}],
                        "page": 1, "page_size": 20, "total": 1}
    err(client.get(f"{API}/suggestions/1/supporters", headers=world["m1"]), 403, "FORBIDDEN")


def test_support_checks(client, world, admin_h):
    suggest(client, world["m1"])
    err(client.post(f"{API}/suggestions/1/support", headers=world["lib"]), 403, "FORBIDDEN")
    err(client.post(f"{API}/suggestions/1/support", headers=world["m5"]), 409, "MEMBERSHIP_TYPE_NOT_ALLOWED")
    err(client.post(f"{API}/suggestions/1/support", headers=world["m1"]), 409, "CANNOT_SUPPORT_OWN")
    sup(client, world["m2"], 1)
    err(client.post(f"{API}/suggestions/1/support", headers=world["m2"]), 409, "ALREADY_SUPPORTED")
    err(client.post(f"{API}/suggestions/99/support", headers=world["m2"]), 404, "NOT_FOUND")
    err(client.post(f"{API}/suggestions/1/support", headers=world["m3"], json={"reserve_on_arrival": "yes"}), 422,
        "VALIDATION_ERROR")
    err(client.delete(f"{API}/suggestions/1/support", headers=world["m3"]), 404, "NOT_FOUND")
    client.post(f"{API}/suggestions/1/withdraw", headers=world["m1"])
    err(client.post(f"{API}/suggestions/1/support", headers=world["m3"]), 409, "INVALID_SUGGESTION_STATUS")
    err(client.delete(f"{API}/suggestions/1/support", headers=world["m2"]), 409, "INVALID_SUGGESTION_STATUS")
    deactivate(client, admin_h, 4)
    suggest(client, world["m1"], isbn=isbn_n(1))
    err(client.post(f"{API}/suggestions/2/support", headers=world["m4"]), 409, "MEMBER_PASSIVE")


def test_support_limit(client, world, admin_h):
    for k in (6, 7):
        reg(client, admin_h, email=f"m{k}@example.edu.tr", university_id=f"ACAD{k:04d}", full_name=f"Member {k}",
            membership_type="academic")
    for member_id in (3, 6, 7):
        for n in range(10):
            suggest(client, world["lib"], member_id=member_id, isbn=isbn_n(member_id * 10 + n))
    for sid in range(1, 21):
        sup(client, world["m1"], sid)
    e = err(client.post(f"{API}/suggestions/21/support", headers=world["m1"]), 409, "SUPPORT_LIMIT_REACHED")
    assert e["details"]["limit"] == 20
    # closed suggestions do not count
    client.post(f"{API}/suggestions/1/withdraw", headers=world["lib"])
    assert client.post(f"{API}/suggestions/21/support", headers=world["m1"]).status_code == 201


def test_member_suggestions(client, world):
    suggest(client, world["m1"])
    suggest(client, world["m2"], isbn=isbn_n(1))
    suggest(client, world["m2"], isbn=isbn_n(2))
    sup(client, world["m1"], 2)
    client.post(f"{API}/suggestions/3/withdraw", headers=world["m2"])
    r = client.get(f"{API}/members/1/suggestions", headers=world["m1"])
    body_ = r.json()
    assert [s["id"] for s in body_["own"]] == [1] and [s["id"] for s in body_["supported"]] == [2]
    assert "member_id" not in body_["supported"][0]
    r = client.get(f"{API}/members/2/suggestions", headers=world["lib"])
    assert [s["id"] for s in r.json()["own"]] == [3, 2] and r.json()["supported"] == []
    err(client.get(f"{API}/members/2/suggestions", headers=world["m1"]), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/99/suggestions", headers=world["lib"]), 404, "NOT_FOUND")


def test_list_and_visibility(client, world):
    suggest(client, world["m1"], title="Dune", author_text="Herbert")
    suggest(client, world["m2"], title="Emma", isbn=isbn_n(1), author_text="Jane Austen")
    suggest(client, world["m3"], title="Çay", isbn=isbn_n(2))  # score 2
    suggest(client, world["m4"], title="Hidden", isbn=isbn_n(3))
    client.post(f"{API}/suggestions/4/withdraw", headers=world["m4"])
    r = client.get(f"{API}/suggestions", headers=world["lib"])
    assert [s["id"] for s in r.json()["items"]] == [3, 1, 2, 4] and r.json()["total"] == 4
    assert all("member_id" in s for s in r.json()["items"])
    r = client.get(f"{API}/suggestions", headers=world["m1"])
    assert [s["id"] for s in r.json()["items"]] == [3, 1, 2]
    assert all("member_id" not in s for s in r.json()["items"])
    assert [s["mine"] for s in r.json()["items"]] == [False, True, False]
    assert client.get(f"{API}/suggestions?q=AUSTEN", headers=world["lib"]).json()["total"] == 1
    assert client.get(f"{API}/suggestions?q=çay", headers=world["lib"]).json()["total"] == 1
    assert client.get(f"{API}/suggestions?status=withdrawn", headers=world["lib"]).json()["total"] == 1
    assert client.get(f"{API}/suggestions?status=withdrawn", headers=world["m1"]).json()["total"] == 0
    assert client.get(f"{API}/suggestions?member_id=2", headers=world["lib"]).json()["total"] == 1
    assert client.get(f"{API}/suggestions?branch_id=2", headers=world["lib"]).json()["total"] == 0
    assert client.get(f"{API}/suggestions?isbn={isbn_n(1)}", headers=world["lib"]).json()["total"] == 1
    err(client.get(f"{API}/suggestions?isbn=12", headers=world["lib"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/suggestions/4", headers=world["m1"]), 404, "NOT_FOUND")
    assert client.get(f"{API}/suggestions/4", headers=world["m4"]).status_code == 200
    assert client.get(f"{API}/suggestions/4", headers=world["lib"]).status_code == 200
    err(client.get(f"{API}/suggestions"), 401, "UNAUTHENTICATED")


# --- review -------------------------------------------------------------------------------------


def test_approve(client, world, app):
    suggest(client, world["m1"])
    s = approve(client, world["lib"], 1, quantity=2, price="40.00", review_note="ok")
    assert s["status"] == "approved" and s["book_id"] == 1 and s["quantity"] == 2
    assert s["estimated_price"] == "40.00" and s["review_note"] == "ok"
    assert s["reviewed_at"] == "2026-11-02T09:30:00+03:00"
    n = notes(app, "suggestion_approved")
    assert len(n) == 1 and n[0].member_id == 1 and "Dune" in n[0].message and n[0].suggestion_id == 1
    assert len(audit(app, "suggestion_approved")) == 1
    err(client.post(f"{API}/suggestions/1/approve", headers=world["lib"],
                    json={"book_id": 1, "quantity": 1, "estimated_price": "1.00"}), 409, "INVALID_SUGGESTION_STATUS")


def test_approve_validation_and_checks(client, world):
    suggest(client, world["m1"], isbn=ISBN1)
    suggest(client, world["m2"], isbn=isbn_n(1))
    for bad in ({"quantity": 0}, {"quantity": 11}, {"estimated_price": "0.00"}, {"estimated_price": "5000.01"},
                {"estimated_price": 5}, {"review_note": "x" * 501}, {"book_id": None}):
        payload = {"book_id": 1, "quantity": 1, "estimated_price": "10.00", **bad}
        err(client.post(f"{API}/suggestions/1/approve", headers=world["lib"], json=payload), 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/suggestions/1/approve", headers=world["lib"],
                    json={"book_id": 99, "quantity": 1, "estimated_price": "10.00"})
    assert err(r, 422, "VALIDATION_ERROR")["details"]["fields"]
    err(client.post(f"{API}/suggestions/99/approve", headers=world["lib"],
                    json={"book_id": 1, "quantity": 1, "estimated_price": "10.00"}), 404, "NOT_FOUND")
    err(client.post(f"{API}/suggestions/1/approve", headers=world["m1"],
                    json={"book_id": 1, "quantity": 1, "estimated_price": "10.00"}), 403, "FORBIDDEN")
    approve(client, world["lib"], 1, book_id=1)
    # ISBN of the suggestion differs from the book (book 2 has ISBN2)
    err(client.post(f"{API}/suggestions/2/approve", headers=world["lib"],
                    json={"book_id": 2, "quantity": 1, "estimated_price": "10.00"}), 409, "ISBN_MISMATCH")
    # several suggestions for the same book
    suggest(client, world["m3"], isbn=None)
    approve(client, world["lib"], 3, book_id=1)


def test_approval_limit_for_librarians(client, world, admin_h):
    suggest(client, world["m1"])
    suggest(client, world["m2"], isbn=None)
    suggest(client, world["m3"], isbn=None)
    approve(client, world["lib"], 1, quantity=3, price="100.00")
    r = client.post(f"{API}/suggestions/2/approve", headers=world["lib"],
                    json={"book_id": 1, "quantity": 3, "estimated_price": "100.01"})
    err(r, 403, "FORBIDDEN")
    approve(client, admin_h, 2, quantity=3, price="100.01")
    # LIB-SUG-24: the limit applies to the new total
    approve(client, world["lib"], 3, quantity=1, price="100.00")
    r = client.patch(f"{API}/suggestions/3/approval", headers=world["lib"], json={"quantity": 4})
    err(r, 403, "FORBIDDEN")
    r = client.patch(f"{API}/suggestions/3/approval", headers=admin_h, json={"quantity": 4, "review_note": "more"})
    assert r.status_code == 200 and r.json()["quantity"] == 4 and r.json()["review_note"] == "more"
    r = client.patch(f"{API}/suggestions/3/approval", headers=world["lib"], json={"estimated_price": "70.00"})
    assert r.status_code == 200 and r.json()["estimated_price"] == "70.00"


def test_change_approval_status(client, world, app):
    suggest(client, world["m1"])
    err(client.patch(f"{API}/suggestions/1/approval", headers=world["lib"], json={"quantity": 2}), 409,
        "INVALID_SUGGESTION_STATUS")
    approve(client, world["lib"], 1)
    r = client.patch(f"{API}/suggestions/1/approval", headers=world["lib"], json={"quantity": 2})
    assert r.status_code == 200
    assert len(audit(app, "suggestion_approval_changed")) == 1
    err(client.patch(f"{API}/suggestions/1/approval", headers=world["lib"], json={"quantity": 0}), 422,
        "VALIDATION_ERROR")
    err(client.patch(f"{API}/suggestions/1/approval", headers=world["m1"], json={"quantity": 2}), 403, "FORBIDDEN")


def test_reject(client, world, app):
    suggest(client, world["m1"])
    suggest(client, world["m2"], isbn=None)
    r = client.post(f"{API}/suggestions/1/reject", headers=world["lib"],
                    json={"reject_reason": "too_expensive", "review_note": "pricey"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected" and r.json()["reject_reason"] == "too_expensive"
    assert r.json()["reviewed_at"] == "2026-11-02T09:30:00+03:00"
    n = notes(app, "suggestion_rejected")
    assert len(n) == 1 and "too_expensive" in n[0].message and "Dune" in n[0].message
    err(client.post(f"{API}/suggestions/1/reject", headers=world["lib"], json={"reject_reason": "other"}), 409,
        "INVALID_SUGGESTION_STATUS")
    err(client.post(f"{API}/suggestions/2/reject", headers=world["lib"], json={"reject_reason": "nope"}), 422,
        "VALIDATION_ERROR")
    err(client.post(f"{API}/suggestions/2/reject", headers=world["m2"], json={"reject_reason": "other"}), 403,
        "FORBIDDEN")
    approve(client, world["lib"], 2)
    assert client.post(f"{API}/suggestions/2/reject", headers=world["lib"],
                       json={"reject_reason": "not_available"}).status_code == 200
    assert len(audit(app, "suggestion_rejected")) == 2


def test_reject_already_owned_reserves(client, world, admin_h, app):
    suggest(client, world["m1"], isbn=None)
    sup(client, world["m2"], 1)
    sup(client, world["m3"], 1, reserve_on_arrival=False)
    err(client.post(f"{API}/suggestions/1/reject", headers=world["lib"], json={"reject_reason": "already_owned"}),
        422, "VALIDATION_ERROR")
    err(client.post(f"{API}/suggestions/1/reject", headers=world["lib"],
                    json={"reject_reason": "already_owned", "book_id": 99}), 404, "NOT_FOUND")
    mk_copy(client, admin_h, book_id=1, barcode="BC-0001", branch=2)
    # a loan so that no copy is available at the pickup branch (branch 1)
    r = client.post(f"{API}/suggestions/1/reject", headers=world["lib"],
                    json={"reject_reason": "already_owned", "book_id": 1})
    assert r.status_code == 200, r.text
    reservations = client.get(f"{API}/reservations", headers=world["lib"]).json()["items"]
    assert [(x["member_id"], x["book_id"], x["pickup_branch_id"]) for x in reservations] == [(1, 1, 1), (2, 1, 1)]
    # the copy is at branch 2, so the first reservation got it (RES-05)
    assert reservations[0]["status"] == "in_transit"


def test_merge(client, world, app):
    suggest(client, world["m1"])                      # S1 by A (m1)
    suggest(client, world["m3"], isbn=isbn_n(1))      # S2 by C (m3, academic)
    sup(client, world["m2"], 1)                       # B supports S1
    sup(client, world["m2"], 2)                       # B supports S2
    r = client.post(f"{API}/suggestions/1/merge", headers=world["lib"], json={"into_suggestion_id": 2})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == 2 and r.json()["supporters"] == 2 and r.json()["score"] == 2 + 1 + 1
    sups = client.get(f"{API}/suggestions/2/supporters", headers=world["lib"]).json()["items"]
    assert [(x["member_id"], x["reserve_on_arrival"]) for x in sups] == [(1, True), (2, True)]
    s1 = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert s1["status"] == "merged" and s1["merged_into_id"] == 2
    assert len(audit(app, "suggestion_merged")) == 1
    err(client.post(f"{API}/suggestions/1/merge", headers=world["lib"], json={"into_suggestion_id": 2}), 409,
        "INVALID_SUGGESTION_STATUS")
    suggest(client, world["m4"], isbn=None)
    err(client.post(f"{API}/suggestions/3/merge", headers=world["lib"], json={"into_suggestion_id": 3}), 422,
        "VALIDATION_ERROR")
    err(client.post(f"{API}/suggestions/3/merge", headers=world["lib"], json={"into_suggestion_id": 99}), 404,
        "NOT_FOUND")
    err(client.post(f"{API}/suggestions/3/merge", headers=world["lib"], json={"into_suggestion_id": 1}), 409,
        "INVALID_SUGGESTION_STATUS")
    approve(client, world["lib"], 3)
    # an approved suggestion cannot be the source; it can be the target
    suggest(client, world["m1"], isbn=isbn_n(3))
    assert client.post(f"{API}/suggestions/4/merge", headers=world["lib"],
                       json={"into_suggestion_id": 3}).status_code == 200
    err(client.post(f"{API}/suggestions/3/merge", headers=world["lib"], json={"into_suggestion_id": 2}), 409,
        "INVALID_SUGGESTION_STATUS")
    err(client.post(f"{API}/suggestions/2/merge", headers=world["m1"], json={"into_suggestion_id": 3}), 403,
        "FORBIDDEN")


# --- ordering and arrival ------------------------------------------------------------------------


def test_order_example(client, world, app):
    for who, n in (("m1", 1), ("m2", 2), ("m3", 3)):
        suggest(client, world[who], isbn=None)
    approve(client, world["lib"], 1, book_id=1, quantity=2, price="40.00")
    approve(client, world["lib"], 2, book_id=1, quantity=1, price="45.00")
    approve(client, world["lib"], 3, book_id=2, quantity=1, price="20.00")
    for bad in ({"suggestion_ids": []}, {"suggestion_ids": [1, 1]}, {"suggestion_ids": list(range(1, 52))}):
        r = client.post(f"{API}/suggestions/order", headers=world["lib"],
                        json={"supplier_id": 1, "branch_id": 1, "suggestion_ids": [1], **bad})
        err(r, 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/suggestions/order", headers=world["lib"],
                    json={"supplier_id": 1, "branch_id": 1, "suggestion_ids": [3, 1, 2]})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "draft" and o["total"] == "155.00" and o["suggestion_ids"] == [1, 2, 3]
    assert [(ln["book_id"], ln["quantity"], ln["unit_price"]) for ln in o["lines"]] == [(1, 3, "45.00"), (2, 1, "20.00")]
    s = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert s["status"] == "ordered" and s["purchase_order_id"] == o["id"]
    assert s["ordered_at"] == "2026-11-02T09:30:00+03:00"
    assert len(notes(app, "suggestion_ordered")) == 3
    assert len(audit(app, "suggestions_ordered")) == 1
    assert client.get(f"{API}/purchase-orders/1", headers=world["lib"]).json()["suggestion_ids"] == [1, 2, 3]
    plain = client.post(f"{API}/purchase-orders", headers=world["lib"],
                        json={"supplier_id": 1, "branch_id": 1, "lines": []}).json()
    assert plain["suggestion_ids"] == []
    b = client.get(f"{API}/books/1", headers=world["lib"]).json()
    assert b["open_suggestions"] == 2
    err(client.delete(f"{API}/books/1", headers=world["lib"]), 409, "IN_USE")


def test_order_checks(client, world, admin_h):
    suggest(client, world["m1"], isbn=None)
    suggest(client, world["m2"], isbn=None)
    suggest(client, world["m3"], isbn=None, branch_id=2)
    approve(client, world["lib"], 1)
    approve(client, world["lib"], 3)
    mk_supplier(client, admin_h, name="Other")
    client.patch(f"{API}/suppliers/2", headers=admin_h, json={"is_active": False})

    def order(**kw):
        return client.post(f"{API}/suggestions/order", headers=world["lib"],
                           json={"supplier_id": 1, "branch_id": 1, "suggestion_ids": [1], **kw})

    err(order(supplier_id=99), 404, "NOT_FOUND")
    err(order(branch_id=99), 404, "NOT_FOUND")
    err(order(suggestion_ids=[1, 99]), 404, "NOT_FOUND")
    err(order(supplier_id=2), 409, "SUPPLIER_INACTIVE")
    e = err(order(suggestion_ids=[1, 2]), 409, "INVALID_SUGGESTION_STATUS")
    assert e["details"]["suggestion_id"] == 2
    e = err(order(suggestion_ids=[1, 3]), 409, "SUGGESTION_BRANCH_MISMATCH")
    assert e["details"]["suggestion_id"] == 3
    err(client.post(f"{API}/suggestions/order", headers=world["m1"],
                    json={"supplier_id": 1, "branch_id": 1, "suggestion_ids": [1]}), 403, "FORBIDDEN")
    # all or nothing
    assert client.get(f"{API}/purchase-orders", headers=world["lib"]).json()["total"] == 0
    assert client.get(f"{API}/suggestions/1", headers=world["lib"]).json()["status"] == "approved"
    assert order().status_code == 201
    e = err(order(), 409, "INVALID_SUGGESTION_STATUS")
    assert e["details"]["suggestion_id"] == 1
    err(client.post(f"{API}/suggestions/1/withdraw", headers=world["lib"]), 409, "INVALID_SUGGESTION_STATUS")


def test_order_changes_revert_suggestions(client, world):
    suggest(client, world["m1"], isbn=None)
    suggest(client, world["m2"], isbn=None)
    approve(client, world["lib"], 1, book_id=1)
    approve(client, world["lib"], 2, book_id=2)
    r = client.post(f"{API}/suggestions/order", headers=world["lib"],
                    json={"supplier_id": 1, "branch_id": 1, "suggestion_ids": [1, 2]})
    oid = r.json()["id"]
    r = client.patch(f"{API}/purchase-orders/{oid}", headers=world["lib"],
                     json={"lines": [{"book_id": 1, "quantity": 1, "unit_price": "40.00"}]})
    assert r.status_code == 200 and r.json()["suggestion_ids"] == [1]
    s2 = client.get(f"{API}/suggestions/2", headers=world["lib"]).json()
    assert s2["status"] == "approved" and s2["purchase_order_id"] is None and s2["ordered_at"] is None
    assert client.get(f"{API}/suggestions/1", headers=world["lib"]).json()["status"] == "ordered"
    assert client.post(f"{API}/purchase-orders/{oid}/cancel", headers=world["lib"]).status_code == 200
    s1 = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert s1["status"] == "approved" and s1["purchase_order_id"] is None
    assert client.get(f"{API}/purchase-orders/{oid}", headers=world["lib"]).json()["suggestion_ids"] == []
    # they can be ordered again
    r = client.post(f"{API}/suggestions/order", headers=world["lib"],
                    json={"supplier_id": 1, "branch_id": 1, "suggestion_ids": [1, 2]})
    assert r.status_code == 201


def order_and_submit(client, hd, ids, supplier=1, branch=1):
    r = client.post(f"{API}/suggestions/order", headers=hd,
                    json={"supplier_id": supplier, "branch_id": branch, "suggestion_ids": ids})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    assert client.post(f"{API}/purchase-orders/{oid}/submit", headers=hd).status_code == 200
    return r.json()


def test_arrival_example(client, world, app):
    suggest(client, world["m1"], isbn=ISBN1)                      # S1 by A = m1, pickup branch 1
    sup(client, world["m2"], 1)                                   # B, reserve_on_arrival
    sup(client, world["m3"], 1, reserve_on_arrival=False)         # C, without
    approve(client, world["lib"], 1, book_id=1, quantity=2)
    o = order_and_submit(client, world["lib"], [1])
    line = o["lines"][0]["id"]
    r = client.post(f"{API}/purchase-orders/{o['id']}/receive", headers=world["lib"],
                    json={"lines": [{"line_id": line, "barcodes": ["NEW-0001"]}]})
    assert r.status_code == 200, r.text
    s = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert s["status"] == "available" and s["available_at"] == "2026-11-02T09:30:00+03:00"
    res = client.get(f"{API}/reservations", headers=world["lib"]).json()["items"]
    assert [(x["member_id"], x["status"], x["copy_id"]) for x in res] == [(1, "ready", 1), (2, "waiting", None)]
    copy = client.get(f"{API}/copies/1", headers=world["lib"]).json()
    assert copy["status"] == "on_hold"
    assert sorted(n.member_id for n in notes(app, "suggestion_available")) == [1, 2, 3]
    assert [n.type for n in sel(app, sa.select(Notification).where(Notification.member_id == 1)
                                 .order_by(Notification.id))] == ["suggestion_approved", "suggestion_ordered",
                                                                  "suggestion_available", "reservation_ready"]
    assert len(audit(app, "suggestion_available")) == 1
    # partial arrival: the second copy does not change the suggestion, B now gets it
    r = client.post(f"{API}/purchase-orders/{o['id']}/receive", headers=world["lib"],
                    json={"lines": [{"line_id": line, "barcodes": ["NEW-0002"]}]})
    assert r.status_code == 200
    res = client.get(f"{API}/reservations", headers=world["lib"]).json()["items"]
    assert [(x["member_id"], x["status"]) for x in res] == [(1, "ready"), (2, "ready")]
    assert len(notes(app, "suggestion_available")) == 3
    # summary and book effects
    summ = client.get(f"{API}/members/1/summary", headers=world["m1"]).json()["suggestions"]
    assert summ == {"open": 0, "supported": 0, "available_this_year": 1}
    err(client.delete(f"{API}/books/1", headers=world["lib"]), 409, "BOOK_HAS_COPIES")


def test_arrival_other_branch_and_skipped(client, world, admin_h):
    suggest(client, world["m1"], isbn=ISBN1, branch_id=2)
    sup(client, world["m2"], 1)
    # m2 already has a reservation for the book: skipped
    mk_copy(client, admin_h, book_id=1, barcode="OLD-0001", branch=1)
    approve(client, world["lib"], 1, book_id=1, quantity=1)
    o = order_and_submit(client, world["lib"], [1], branch=2)
    line = o["lines"][0]["id"]
    r = client.post(f"{API}/purchase-orders/{o['id']}/receive", headers=world["lib"],
                    json={"lines": [{"line_id": line, "barcodes": ["NEW-0001"]}]})
    assert r.status_code == 200, r.text
    res = client.get(f"{API}/reservations", headers=world["lib"]).json()["items"]
    # RES-05: the old copy at branch 1 goes to the first reservation; the new copy at branch 2 to the next one
    assert [(x["member_id"], x["pickup_branch_id"], x["status"]) for x in res] == [(1, 2, "in_transit"), (2, 2, "ready")]


def test_receive_without_suggestions_is_unchanged(client, world):
    o = client.post(f"{API}/purchase-orders", headers=world["lib"],
                    json={"supplier_id": 1, "branch_id": 1, "lines": [{"book_id": 1, "quantity": 1, "unit_price": "9.00"}]})
    oid = o.json()["id"]
    client.post(f"{API}/purchase-orders/{oid}/submit", headers=world["lib"])
    r = client.post(f"{API}/purchase-orders/{oid}/receive", headers=world["lib"],
                    json={"lines": [{"line_id": 1, "barcodes": ["NEW-0001"]}]})
    assert r.status_code == 200
    assert client.get(f"{API}/copies/1", headers=world["lib"]).json()["status"] == "available"


# --- process --------------------------------------------------------------------------------------


def test_process(client, world, clock, app):
    suggest(client, world["m1"], isbn=None)
    suggest(client, world["m2"], isbn=None)
    approve(client, world["lib"], 2)
    clock.set(datetime.datetime(2027, 3, 2, 9, 30, tzinfo=TZ))
    relogin(client, world)
    r = client.post(f"{API}/suggestions/process", headers=world["lib"])
    assert r.status_code == 200 and r.json() == {"expired_submitted": 0, "expired_approved": 1}
    clock.set(datetime.datetime(2027, 3, 2, 9, 30, 1, tzinfo=TZ))
    relogin(client, world)
    r = client.post(f"{API}/suggestions/process", headers=world["lib"])
    assert r.json() == {"expired_submitted": 1, "expired_approved": 0}
    assert client.get(f"{API}/suggestions/1", headers=world["lib"]).json()["status"] == "expired"
    assert [n.member_id for n in notes(app, "suggestion_expired")] == [2, 1]
    assert len(audit(app, "suggestions_processed")) == 2
    err(client.post(f"{API}/suggestions/process", headers=world["m1"]), 403, "FORBIDDEN")
    err(client.post(f"{API}/suggestions/1/withdraw", headers=world["m1"]), 409, "INVALID_SUGGESTION_STATUS")


# --- effects on other modules ------------------------------------------------------------------


def test_member_deactivation(client, world, admin_h, app):
    suggest(client, world["m1"], isbn=None)
    suggest(client, world["m1"], isbn=None)
    suggest(client, world["m2"], isbn=None)
    approve(client, world["lib"], 2)
    sup(client, world["m1"], 3)
    deactivate(client, admin_h, 1)
    s = client.get(f"{API}/suggestions/1", headers=world["lib"]).json()
    assert s["status"] == "withdrawn" and s["withdraw_reason"] == "member_deactivated"
    assert client.get(f"{API}/suggestions/2", headers=world["lib"]).json()["status"] == "approved"
    assert client.get(f"{API}/suggestions/3", headers=world["lib"]).json()["supporters"] == 0


def test_type_change_to_guest(client, world, admin_h):
    suggest(client, world["m1"], isbn=isbn_n(1))
    suggest(client, world["m2"], isbn=isbn_n(2))
    sup(client, world["m1"], 2)
    r = client.patch(f"{API}/members/1", headers=admin_h, json={"membership_type": "guest", "phone": "+90 532 123 45 67"})
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/members/1/suggestions", headers=world["m1"]).json()["supported"][0]["id"] == 2
    assert client.get(f"{API}/suggestions/1", headers=world["m1"]).json()["status"] == "submitted"
    err(client.post(f"{API}/suggestions", headers=world["m1"], json=body(isbn=isbn_n(5))), 409,
        "MEMBERSHIP_TYPE_NOT_ALLOWED")


def test_member_summary(client, world):
    suggest(client, world["m1"], isbn=isbn_n(1))
    suggest(client, world["m1"], isbn=isbn_n(2))
    suggest(client, world["m2"], isbn=isbn_n(3))
    sup(client, world["m1"], 3)
    r = client.get(f"{API}/members/1/summary", headers=world["m1"])
    assert r.json()["suggestions"] == {"open": 2, "supported": 1, "available_this_year": 0}


def test_branch_deactivation(client, world, admin_h):
    mk_branch(client, admin_h, "THIRD")
    suggest(client, world["m1"], branch_id=3)
    r = client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False})
    assert err(r, 409, "BRANCH_IN_USE")
    client.post(f"{API}/suggestions/1/withdraw", headers=world["m1"])
    assert client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False}).status_code == 200


def test_notification_filter_and_field(client, world):
    suggest(client, world["m1"], isbn=None)
    approve(client, world["lib"], 1)
    r = client.get(f"{API}/members/1/notifications?type=suggestion_approved", headers=world["m1"])
    assert r.status_code == 200 and r.json()["total"] == 1
    assert r.json()["items"][0]["suggestion_id"] == 1 and r.json()["items"][0]["donation_id"] is None


# --- report ---------------------------------------------------------------------------------------


def test_report(client, world, clock):
    suggest(client, world["m1"], isbn=None)                  # 1: available
    suggest(client, world["m2"], isbn=None)                  # 2: rejected too_expensive
    suggest(client, world["m3"], isbn=None)                  # 3: approved, score 2
    suggest(client, world["m4"], isbn=None, branch_id=2)     # 4: submitted
    suggest(client, world["m1"], isbn=None)                  # 5: withdrawn
    client.post(f"{API}/suggestions/5/withdraw", headers=world["m1"])
    sup(client, world["m3"], 1)
    approve(client, world["lib"], 1)
    approve(client, world["lib"], 3)
    client.post(f"{API}/suggestions/2/reject", headers=world["lib"], json={"reject_reason": "too_expensive"})
    o = order_and_submit(client, world["lib"], [1])
    clock.advance(days=10)
    relogin(client, world)
    client.post(f"{API}/purchase-orders/{o['id']}/receive", headers=world["lib"],
                json={"lines": [{"line_id": 1, "barcodes": ["NEW-0001"]}]})
    r = client.get(f"{API}/reports/suggestions?from=2026-11-01&to=2026-11-30", headers=world["lib"])
    assert r.status_code == 200, r.text
    assert r.json() == {
        "submitted": 5, "approved": 2,
        "rejected": {"already_owned": 0, "out_of_scope": 0, "too_expensive": 1, "not_available": 0, "other": 0},
        "ordered": 0, "available": 1, "withdrawn": 1, "merged": 0, "expired": 0,
        "average_days_to_available": "10.0",
        "top": [{"suggestion_id": 1, "title": "Dune", "score": 3}, {"suggestion_id": 3, "title": "Dune", "score": 2},
                {"suggestion_id": 2, "title": "Dune", "score": 1}, {"suggestion_id": 4, "title": "Dune", "score": 1},
                {"suggestion_id": 5, "title": "Dune", "score": 1}],
    }
    r = client.get(f"{API}/reports/suggestions?from=2026-11-01&to=2026-11-30&branch_id=2", headers=world["lib"])
    assert r.json()["submitted"] == 1 and r.json()["average_days_to_available"] is None
    for q in ("", "?from=2026-11-02", "?from=2026-11-05&to=2026-11-01", "?from=2026-01-01&to=2027-01-02",
              "?from=x&to=2026-11-01"):
        err(client.get(f"{API}/reports/suggestions{q}", headers=world["lib"]), 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/reports/suggestions?from=2026-01-01&to=2027-01-01", headers=world["lib"]).status_code == 200
    err(client.get(f"{API}/reports/suggestions?from=2026-11-01&to=2026-11-30", headers=world["m1"]), 403, "FORBIDDEN")


def test_not_exported(client, world, admin_h):
    suggest(client, world["m1"])
    r = client.get(f"{API}/export", headers=admin_h)
    assert r.status_code == 200 and "suggestions" not in r.json()
