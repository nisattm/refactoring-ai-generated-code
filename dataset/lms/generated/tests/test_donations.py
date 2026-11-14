"""Module 22: Donations (LIB-DON-01 to LIB-DON-47).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (MERKEZ) and 2 (KAMPUS), books 1 and 2, member 1 (student,
the member donor) and member 2 (student). Librarian: lib@example.com.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.catalog.models import Copy
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_branches import mk_branch
from tests.test_catalog import book_body, mk_author, mk_copy, mk_publisher
from tests.test_members import reg

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))
ISBN1 = "9780306406157"
ISBN2 = "9780804429573"


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def item(**kw):
    return {"title": "Old Novel", "author_text": "A. Writer", "isbn": None, "publication_year": 2010,
            "condition": "good", "quantity": 1, **kw}


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
    make_user(client, admin_h)
    return {"m1": h(token_of(client, "m1@example.edu.tr", "Passw0rd1")),
            "m2": h(token_of(client, "m2@example.edu.tr", "Passw0rd1")),
            "lib": h(token_of(client, "lib@example.com", "Passw0rd1"))}


def mk_donor(client, hd, expect=201, **kw):
    r = client.post(f"{API}/donors", headers=hd, json={"kind": "person", "name": "Dora Donor", **kw})
    assert r.status_code == expect, r.text
    return r.json()


def offer(client, hd, expect=201, **kw):
    body = {"donor_id": 1, "branch_id": 1, "items": [item()], **kw}
    r = client.post(f"{API}/donations", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def accept(item_id, book_id=1, qty=1, value="40.00"):
    return {"item_id": item_id, "decision": "accepted", "book_id": book_id, "accepted_quantity": qty,
            "estimated_value": value}


def decline(item_id, reason="other"):
    return {"item_id": item_id, "decision": "declined", "decline_reason": reason}


def review(client, hd, donation_id, items, expect=200):
    r = client.post(f"{API}/donations/{donation_id}/review", headers=hd, json={"items": items})
    assert r.status_code == expect, r.text
    return r.json()


def receive(client, hd, donation_id, items, expect=200):
    r = client.post(f"{API}/donations/{donation_id}/receive", headers=hd, json={"items": items})
    assert r.status_code == expect, r.text
    return r.json()


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


def notes(app, type_):
    return sel(app, sa.select(Notification).where(Notification.type == type_).order_by(Notification.id))


# --- donors ------------------------------------------------------------------------------------


def test_create_donor(client, admin_h, world, app):
    d = mk_donor(client, admin_h, email="Dora@Example.com", phone="+90 532 123 45 67")
    assert d == {"id": 1, "kind": "person", "name": "Dora Donor", "email": "dora@example.com",
                 "phone": "+90 532 123 45 67", "member_id": None, "anonymous": False, "is_active": True,
                 "merged_into_id": None, "created_at": "2026-11-02T09:30:00+03:00", "level": "none",
                 "value_this_year": "0.00"}
    assert [a.entity_id for a in audit(app, "donor_created")] == [1]
    r = client.post(f"{API}/donors", headers=admin_h, json={"kind": "person", "name": "X", "email": "DORA@example.com"})
    assert err(r, 409, "CONFLICT")["details"]["field"] == "email"


def test_create_donor_validation(client, admin_h, world, app):
    for body in ({"kind": "team", "name": "X"}, {"kind": "person"}, {"kind": "person", "name": " "},
                 {"kind": "person", "name": "X", "email": "nope"}, {"kind": "person", "name": "X", "extra": 1},
                 {"kind": "organization", "name": "X", "member_id": 1}):
        err(client.post(f"{API}/donors", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/donors", headers=admin_h, json={"kind": "person", "name": "X", "member_id": 99})
    assert err(r, 422, "VALIDATION_ERROR")["details"]["fields"]
    mk_donor(client, admin_h, member_id=1)
    r = client.post(f"{API}/donors", headers=admin_h, json={"kind": "person", "name": "Y", "member_id": 1})
    assert err(r, 409, "CONFLICT")["details"]["field"] == "member_id"


def test_donor_permissions(client, admin_h, world):
    for hd in (world["m1"],):
        err(client.post(f"{API}/donors", headers=hd, json={"kind": "person", "name": "X"}), 403, "FORBIDDEN")
        err(client.get(f"{API}/donors", headers=hd), 403, "FORBIDDEN")
        err(client.get(f"{API}/donors/1/history", headers=hd), 403, "FORBIDDEN")
    mk_donor(client, admin_h)
    mk_donor(client, admin_h, name="Other")
    err(client.post(f"{API}/donors/1/merge", headers=world["lib"], json={"into_donor_id": 2}), 403, "FORBIDDEN")
    err(client.get(f"{API}/donors"), 401, "UNAUTHENTICATED")
    assert client.get(f"{API}/donor-wall", headers=world["m1"]).status_code == 200


def test_list_and_patch_donors(client, admin_h, world, app):
    mk_donor(client, admin_h, name="beta org", kind="organization", email="b@x.org")
    mk_donor(client, admin_h, name="Alpha")
    mk_donor(client, admin_h, name="İstanbul Friends", kind="organization")
    r = client.get(f"{API}/donors", headers=admin_h).json()
    assert [d["name"] for d in r["items"]] == ["Alpha", "beta org", "İstanbul Friends"] and r["total"] == 3
    assert client.get(f"{API}/donors?q=B@X", headers=admin_h).json()["total"] == 1
    assert client.get(f"{API}/donors?kind=organization", headers=admin_h).json()["total"] == 2
    assert client.get(f"{API}/donors?level=gold", headers=admin_h).json()["total"] == 0
    assert client.get(f"{API}/donors?level=none", headers=admin_h).json()["total"] == 3
    r = client.patch(f"{API}/donors/2", headers=admin_h, json={"name": "Alpha 2", "anonymous": True, "email": None})
    assert r.status_code == 200 and r.json()["name"] == "Alpha 2" and r.json()["anonymous"] is True
    assert [a.entity_id for a in audit(app, "donor_updated")] == [2]
    for body in ({"kind": "organization"}, {"member_id": 1}, {"name": None}, {"email": "bad"}):
        err(client.patch(f"{API}/donors/2", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/donors/2", headers=admin_h, json={"email": "b@x.org"}), 409, "CONFLICT")
    err(client.get(f"{API}/donors/9", headers=admin_h), 404, "NOT_FOUND")


def test_member_donor_created_on_offer(client, admin_h, world, app):
    mk_donor(client, admin_h, name="Someone", email="m1@example.edu.tr")
    d = offer(client, world["m1"], donor_id=None)
    assert d["donor_id"] == 2 and d["status"] == "offered"
    donor = client.get(f"{API}/donors/2", headers=admin_h).json()
    assert donor["name"] == "Member One" and donor["member_id"] == 1 and donor["email"] is None
    d2 = offer(client, world["m1"], donor_id=None)
    assert d2["donor_id"] == 2
    err(client.post(f"{API}/donations", headers=world["m1"],
                    json={"donor_id": 1, "branch_id": 1, "items": [item()]}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/donations", headers=admin_h, json={"branch_id": 1, "items": [item()]}), 422,
        "VALIDATION_ERROR")


def test_deactivate_donor(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h)
    r = client.patch(f"{API}/donors/1", headers=admin_h, json={"is_active": False})
    assert err(r, 409, "DONOR_HAS_OPEN_DONATIONS")["details"]["donation_ids"] == [1]
    client.post(f"{API}/donations/1/cancel", headers=admin_h)
    assert client.patch(f"{API}/donors/1", headers=admin_h, json={"is_active": False}).status_code == 200
    err(client.post(f"{API}/donations", headers=admin_h,
                    json={"donor_id": 1, "branch_id": 1, "items": [item()]}), 409, "DONOR_INACTIVE")


def test_merge(client, admin_h, world, app):
    mk_donor(client, admin_h, name="A", member_id=1, email="a@x.org")
    mk_donor(client, admin_h, name="B")
    mk_donor(client, admin_h, name="C", member_id=2)
    offer(client, admin_h, donor_id=1)
    err(client.post(f"{API}/donors/1/merge", headers=admin_h, json={"into_donor_id": 1}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/donors/1/merge", headers=admin_h, json={"into_donor_id": 9}), 404, "NOT_FOUND")
    err(client.post(f"{API}/donors/1/merge", headers=admin_h, json={"into_donor_id": 3}), 409,
        "DONOR_MERGE_CONFLICT")
    r = client.post(f"{API}/donors/1/merge", headers=admin_h, json={"into_donor_id": 2})
    assert r.status_code == 200
    target = r.json()
    assert target["id"] == 2 and target["member_id"] == 1 and target["email"] == "a@x.org"
    source = client.get(f"{API}/donors/1", headers=admin_h).json()
    assert source["is_active"] is False and source["merged_into_id"] == 2 and source["member_id"] is None
    assert client.get(f"{API}/donations/1", headers=admin_h).json()["donor_id"] == 2
    assert [a.event for a in audit(app, "donors_merged")] == ["donors_merged"]
    err(client.post(f"{API}/donors/1/merge", headers=admin_h, json={"into_donor_id": 3}), 409, "DONOR_MERGED")
    err(client.post(f"{API}/donors/3/merge", headers=admin_h, json={"into_donor_id": 1}), 409, "DONOR_MERGED")
    err(client.patch(f"{API}/donors/1", headers=admin_h, json={"name": "Z"}), 409, "DONOR_MERGED")


# --- offers ------------------------------------------------------------------------------------


def test_offer_by_staff(client, admin_h, world, app):
    mk_donor(client, admin_h)
    d = offer(client, admin_h, note=" hello ", items=[item(isbn="0-306-40615-2"), item(title="Two", quantity=3)])
    assert d["status"] == "offered" and d["note"] == "hello" and d["offered_at"] == "2026-11-02T09:30:00+03:00"
    assert d["items_count"] == 2 and d["copies_offered"] == 4 and d["items"][0]["isbn"] == ISBN1
    assert d["items"][0]["decision"] == "pending" and d["items"][0]["received_quantity"] == 0
    assert d["reviewed_at"] is None and d["expected_by"] is None and d["receipt_no"] is None
    assert [a.entity_id for a in audit(app, "donation_offered")] == [1]


def test_offer_validation(client, admin_h, world):
    mk_donor(client, admin_h)
    bad = [
        {"items": []},
        {"items": [item() for _ in range(31)]},
        {"items": [item(isbn=ISBN1), item(isbn="0-306-40615-2")]},
        {"items": [item(quantity=20)] * 5 + [item(quantity=1)]},
        {"items": [item(quantity=0)]}, {"items": [item(quantity=21)]},
        {"items": [item(publication_year=1449)]}, {"items": [item(publication_year=2027)]},
        {"items": [item(condition="mint")]}, {"items": [item(title=" ")]}, {"items": [item(isbn="123")]},
        {"items": [item(title="x" * 301)]}, {"note": "x" * 501},
    ]
    for body in bad:
        r = client.post(f"{API}/donations", headers=admin_h, json={"donor_id": 1, "branch_id": 1, "items": [item()], **body})
        err(r, 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/donations", headers=admin_h, json={"donor_id": 9, "branch_id": 1, "items": [item()]}), 404,
        "NOT_FOUND")
    err(client.post(f"{API}/donations", headers=admin_h, json={"donor_id": 1, "branch_id": 9, "items": [item()]}), 404,
        "NOT_FOUND")


def test_offer_checks(client, admin_h, world):
    mk_donor(client, admin_h)
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/donations", headers=admin_h, json={"donor_id": 1, "branch_id": 2, "items": [item()]}), 409,
        "BRANCH_INACTIVE")
    for _ in range(3):
        offer(client, admin_h)
    r = client.post(f"{API}/donations", headers=admin_h, json={"donor_id": 1, "branch_id": 1, "items": [item()]})
    assert err(r, 409, "DONOR_OFFER_LIMIT")["details"]["limit"] == 3
    client.post(f"{API}/donations/1/cancel", headers=admin_h)
    offer(client, admin_h)


def test_offer_by_passive_member(client, admin_h, world):
    assert client.post(f"{API}/members/1/deactivate", headers=admin_h).status_code == 200
    err(client.post(f"{API}/donations", headers=world["m1"], json={"branch_id": 1, "items": [item()]}), 409,
        "MEMBER_PASSIVE")


def test_change_and_cancel_offer(client, admin_h, world, app):
    mk_donor(client, admin_h)
    offer(client, admin_h)
    r = client.patch(f"{API}/donations/1", headers=admin_h, json={"branch_id": 2, "note": "n", "items": [item(quantity=2)]})
    assert r.status_code == 200 and r.json()["branch_id"] == 2 and r.json()["copies_offered"] == 2
    assert [a.entity_id for a in audit(app, "donation_updated")] == [1]
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code
    err(client.patch(f"{API}/donations/1", headers=admin_h, json={"branch_id": 1, "items": []}), 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/donations/1/cancel", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "staff_request"
    err(client.patch(f"{API}/donations/1", headers=admin_h, json={"note": "x"}), 409, "INVALID_DONATION_STATUS")
    r = client.post(f"{API}/donations/1/cancel", headers=admin_h)
    assert err(r, 409, "INVALID_DONATION_STATUS")["details"]["status"] == "cancelled"
    assert notes(app, "donation_reviewed") == []


def test_member_own_access(client, admin_h, world, app):
    d = offer(client, world["m1"], donor_id=None)
    assert client.get(f"{API}/donations/{d['id']}", headers=world["m1"]).status_code == 200
    err(client.get(f"{API}/donations/{d['id']}", headers=world["m2"]), 404, "NOT_FOUND")
    err(client.patch(f"{API}/donations/{d['id']}", headers=world["m2"], json={"note": "x"}), 403, "FORBIDDEN")
    err(client.post(f"{API}/donations/{d['id']}/cancel", headers=world["m2"]), 403, "FORBIDDEN")
    err(client.get(f"{API}/donations", headers=world["m1"]), 403, "FORBIDDEN")
    r = client.get(f"{API}/members/1/donations", headers=world["m1"])
    assert r.status_code == 200 and r.json()["total"] == 1
    err(client.get(f"{API}/members/1/donations", headers=world["m2"]), 403, "FORBIDDEN")
    assert client.get(f"{API}/members/1/donations", headers=world["lib"]).json()["total"] == 1
    assert client.patch(f"{API}/donations/{d['id']}", headers=world["m1"], json={"note": "x"}).status_code == 200
    r = client.post(f"{API}/donations/{d['id']}/cancel", headers=world["m1"])
    assert r.json()["cancel_reason"] == "donor_request"


def test_member_cannot_cancel_accepted(client, admin_h, world):
    d = offer(client, world["m1"], donor_id=None)
    review(client, admin_h, d["id"], [accept(d["items"][0]["id"])])
    err(client.post(f"{API}/donations/{d['id']}/cancel", headers=world["m1"]), 409, "INVALID_DONATION_STATUS")
    assert client.post(f"{API}/donations/{d['id']}/cancel", headers=admin_h).status_code == 200


def test_list_donations(client, admin_h, world, clock):
    mk_donor(client, admin_h)
    mk_donor(client, admin_h, name="Two")
    offer(client, admin_h)
    clock.advance(days=1)
    offer(client, admin_h, donor_id=2, branch_id=2)
    r = client.get(f"{API}/donations", headers=admin_h).json()
    assert [d["id"] for d in r["items"]] == [2, 1]
    assert [d["id"] for d in client.get(f"{API}/donations?donor_id=1", headers=admin_h).json()["items"]] == [1]
    assert [d["id"] for d in client.get(f"{API}/donations?branch_id=2", headers=admin_h).json()["items"]] == [2]
    assert [d["id"] for d in client.get(f"{API}/donations?from=2026-11-03", headers=admin_h).json()["items"]] == [2]
    assert [d["id"] for d in client.get(f"{API}/donations?to=2026-11-02", headers=admin_h).json()["items"]] == [1]
    assert client.get(f"{API}/donations?status=received", headers=admin_h).json()["total"] == 0
    err(client.get(f"{API}/donations?status=bogus", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/donations?from=x", headers=admin_h), 422, "VALIDATION_ERROR")


# --- review ------------------------------------------------------------------------------------


def test_suggestions(client, admin_h, world, app):
    mk_donor(client, admin_h)
    for i in range(3):
        assert mk_copy(client, admin_h, 1, f"BC-100{i}").status_code == 201
    with app.state.session_factory.begin() as s:
        s.get(Copy, 3).status = "lost"
    items = [
        item(condition="poor", publication_year=2020),
        item(title="Old", publication_year=1995),
        item(publication_year=1996, isbn=ISBN1),
        item(title="Unknown", isbn="978-1-4028-9462-6"),
        item(title="No ISBN"),
        item(title="Book 2", isbn=ISBN2),
    ]
    d = offer(client, admin_h, items=items)
    r = client.get(f"{API}/donations/1/suggestions", headers=admin_h).json()["items"]
    assert r == [
        {"item_id": 1, "decision": "declined", "decline_reason": "poor_condition", "book_id": None},
        {"item_id": 2, "decision": "declined", "decline_reason": "too_old", "book_id": None},
        {"item_id": 3, "decision": "accepted", "decline_reason": None, "book_id": 1},
        {"item_id": 4, "decision": None, "decline_reason": None, "book_id": None},
        {"item_id": 5, "decision": None, "decline_reason": None, "book_id": None},
        {"item_id": 6, "decision": "accepted", "decline_reason": None, "book_id": 2},
    ]
    assert mk_copy(client, admin_h, 1, "BC-1009").status_code == 201
    r = client.get(f"{API}/donations/1/suggestions", headers=admin_h).json()["items"]
    assert r[2] == {"item_id": 3, "decision": "declined", "decline_reason": "duplicate", "book_id": 1}
    err(client.get(f"{API}/donations/1/suggestions", headers=world["m1"]), 403, "FORBIDDEN")
    err(client.get(f"{API}/donations/9/suggestions", headers=admin_h), 404, "NOT_FOUND")
    assert d["id"] == 1


def test_review_result_and_notification(client, admin_h, world, app):
    d = offer(client, world["m1"], donor_id=None, items=[item(), item(title="B")])
    r = review(client, admin_h, d["id"], [accept(1, qty=1), decline(2, "too_old")])
    assert r["status"] == "accepted" and r["expected_by"] == "2026-11-16" and r["reviewed_at"].startswith("2026-11-02")
    assert r["items"][0]["decision"] == "accepted" and r["items"][0]["estimated_value"] == "40.00"
    assert r["items"][0]["book_id"] == 1 and r["items"][1]["decline_reason"] == "too_old"
    n = notes(app, "donation_reviewed")
    assert len(n) == 1 and n[0].member_id == 1 and n[0].donation_id == 1 and "1 item(s) accepted" in n[0].message
    assert [a.entity_id for a in audit(app, "donation_reviewed")] == [1]
    err(client.post(f"{API}/donations/1/review", headers=admin_h, json={"items": [decline(1), decline(2)]}), 409,
        "INVALID_DONATION_STATUS")
    out = client.get(f"{API}/members/1/notifications", headers=world["m1"]).json()["items"]
    assert out[0]["type"] == "donation_reviewed" and out[0]["donation_id"] == 1


def test_review_all_declined_rejects(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h)
    r = review(client, admin_h, 1, [decline(1, "poor_condition")])
    assert r["status"] == "rejected" and r["expected_by"] is None
    err(client.post(f"{API}/donations/1/cancel", headers=admin_h), 409, "INVALID_DONATION_STATUS")
    err(client.patch(f"{API}/donations/1", headers=admin_h, json={"note": "x"}), 409, "INVALID_DONATION_STATUS")
    err(client.post(f"{API}/donations/1/receive", headers=admin_h,
                    json={"items": [{"item_id": 1, "barcodes": ["DN-0001"]}]}), 409, "INVALID_DONATION_STATUS")


def test_review_validation(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h, items=[item(), item(title="B")])

    def post(items, status=422, code="VALIDATION_ERROR"):
        return err(client.post(f"{API}/donations/1/review", headers=admin_h, json={"items": items}), status, code)

    post([decline(1)])  # item 2 missing
    post([decline(1), decline(1)])
    post([decline(1), decline(7)])
    post([decline(1), {"item_id": 2, "decision": "declined"}])
    post([decline(1), {**decline(2), "book_id": 1}])
    post([decline(1), {"item_id": 2, "decision": "accepted", "book_id": 1, "accepted_quantity": 1}])
    post([decline(1), {**accept(2), "decline_reason": "other"}])
    post([decline(1), accept(2, qty=2)])
    post([decline(1), accept(2, value="0.00")])
    post([decline(1), accept(2, value="5000.01")])
    post([decline(1), accept(2, value=40)])
    post([decline(1), accept(2, book_id=9)])
    post([decline(1), {"item_id": 2, "decision": "pending"}])
    post([])
    r = client.post(f"{API}/donations/1/review", headers=admin_h, json={"items": [decline(1), accept(2, book_id=9)]})
    assert err(r, 422, "VALIDATION_ERROR")["details"]["fields"]
    err(client.post(f"{API}/donations/9/review", headers=admin_h, json={"items": [decline(1)]}), 404, "NOT_FOUND")
    err(client.post(f"{API}/donations/1/review", headers=world["m1"], json={"items": [decline(1)]}), 403, "FORBIDDEN")


def test_review_isbn_mismatch_and_inactive_branch(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h, branch_id=2, items=[item(isbn=ISBN1), item(title="B", isbn=ISBN2)])
    r = client.post(f"{API}/donations/1/review", headers=admin_h, json={"items": [accept(1), accept(2, book_id=1)]})
    assert err(r, 409, "ISBN_MISMATCH")["details"]["item_id"] == 2
    review(client, admin_h, 1, [accept(1), accept(2, book_id=2)])


def test_branch_in_use_by_open_donation(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h, branch_id=2)
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/donations/1/cancel", headers=admin_h)
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200


# --- receiving ---------------------------------------------------------------------------------


def two_item_donation(client, admin_h, member=False):
    if member:
        d = offer(client, admin_h, donor_id=None, items=[item(quantity=3), item(title="B"), item(title="C")])
    else:
        mk_donor(client, admin_h)
        d = offer(client, admin_h, items=[item(quantity=3), item(title="B"), item(title="C")])
    review(client, admin_h, d["id"], [accept(1, 1, 3, "40.00"), accept(2, 2, 1, "150.00"), decline(3)])


def test_receive_flow_and_receipt(client, admin_h, world, app):
    mk_donor(client, admin_h)
    two_item_donation(client, admin_h)
    err(client.get(f"{API}/donations/1/receipt", headers=admin_h), 409, "RECEIPT_NOT_AVAILABLE")
    r = receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0001", "dn-0002"]}])
    assert r["status"] == "partially_received" and r["receipt_no"] == "DN-2026-0001"
    assert r["items"][0]["received_quantity"] == 2 and r["received_at"].startswith("2026-11-02")
    copies = sel(app, sa.select(Copy).order_by(Copy.id))
    assert [c.barcode for c in copies] == ["DN-0001", "DN-0002"]
    assert all(c.donation_id == 1 and c.home_branch_id == 1 and str(c.price) == "40.00" for c in copies)
    assert all(c.acquired_on == datetime.date(2026, 11, 2) and c.status == "available" for c in copies)
    r = receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0003"]}, {"item_id": 2, "barcodes": ["DN-0004"]}])
    assert r["status"] == "received" and r["receipt_no"] == "DN-2026-0001"
    rc = client.get(f"{API}/donations/1/receipt", headers=admin_h).json()
    assert rc == {
        "receipt_no": "DN-2026-0001", "donor": {"id": 1, "name": "Dora Donor", "kind": "person"}, "branch_id": 1,
        "first_received_on": "2026-11-02", "last_received_on": "2026-11-02",
        "lines": [
            {"item_id": 1, "title": "Old Novel", "copies": 3, "value_per_copy": "40.00", "value": "120.00"},
            {"item_id": 2, "title": "B", "copies": 1, "value_per_copy": "150.00", "value": "150.00"},
        ],
        "total_copies": 4, "total_value": "270.00",
    }
    assert [a.entity_id for a in audit(app, "donation_received")] == [1, 1]
    err(client.post(f"{API}/donations/1/receive", headers=admin_h,
                    json={"items": [{"item_id": 1, "barcodes": ["DN-0009"]}]}), 409, "INVALID_DONATION_STATUS")
    h1 = client.get(f"{API}/donors/1/history", headers=admin_h).json()
    assert h1 == {"donor_id": 1, "donations": 1, "open_donations": 0, "copies_received": 4, "value_received": "270.00",
                  "first_received_on": "2026-11-02", "last_received_on": "2026-11-02",
                  "years": [{"year": 2026, "value": "270.00", "level": "none"}]}
    # the second receipt number of the year
    offer(client, admin_h, items=[item()])
    review(client, admin_h, 2, [accept(4, 1, 1, "10.00")])
    assert receive(client, admin_h, 2, [{"item_id": 4, "barcodes": ["DN-0010"]}])["receipt_no"] == "DN-2026-0002"


def test_receive_validation_and_checks(client, admin_h, world):
    mk_donor(client, admin_h)
    two_item_donation(client, admin_h)

    def post(items, status, code):
        return err(client.post(f"{API}/donations/1/receive", headers=admin_h, json={"items": items}), status, code)

    post([], 422, "VALIDATION_ERROR")
    post([{"item_id": 1, "barcodes": []}], 422, "VALIDATION_ERROR")
    post([{"item_id": 1, "barcodes": ["DN-0001"]}, {"item_id": 1, "barcodes": ["DN-0002"]}], 422, "VALIDATION_ERROR")
    post([{"item_id": 1, "barcodes": ["x"]}], 422, "VALIDATION_ERROR")
    post([{"item_id": 9, "barcodes": ["DN-0001"]}], 404, "NOT_FOUND")
    assert post([{"item_id": 3, "barcodes": ["DN-0001"]}], 409, "ITEM_NOT_ACCEPTED")["details"]["item_id"] == 3
    assert post([{"item_id": 2, "barcodes": ["DN-0001", "DN-0002"]}], 409, "RECEIVE_EXCEEDS_ACCEPTED")["details"][
        "item_id"] == 2
    post([{"item_id": 1, "barcodes": ["DN-0001", "DN-0001"]}], 409, "CONFLICT")
    assert mk_copy(client, admin_h, 1, "TAKEN-1").status_code == 201
    post([{"item_id": 1, "barcodes": ["DN-0001", "TAKEN-1"]}], 409, "CONFLICT")
    assert client.get(f"{API}/books/1/copies", headers=admin_h).json()["total"] == 1  # nothing was created
    err(client.post(f"{API}/donations/1/receive", headers=world["m1"],
                    json={"items": [{"item_id": 1, "barcodes": ["DN-0001"]}]}), 403, "FORBIDDEN")


def test_receive_releases_copy_to_reservation(client, admin_h, world):
    mk_donor(client, admin_h)
    two_item_donation(client, admin_h)
    assert mk_copy(client, admin_h, 1, "BC-0001").status_code == 201
    assert client.post(f"{API}/loans", headers=admin_h, json={"member_id": 1, "barcode": "BC-0001"}).status_code == 201
    r = client.post(f"{API}/reservations", headers=world["m2"], json={"book_id": 1, "pickup_branch_id": 1})
    assert r.status_code == 201, r.text
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0001"]}])
    res = client.get(f"{API}/reservations/{r.json()['id']}", headers=admin_h).json()
    assert res["status"] == "ready"


def test_receipt_access(client, admin_h, world):
    d = offer(client, world["m1"], donor_id=None)
    review(client, admin_h, d["id"], [accept(1)])
    receive(client, admin_h, d["id"], [{"item_id": 1, "barcodes": ["DN-0001"]}])
    assert client.get(f"{API}/donations/1/receipt", headers=world["m1"]).status_code == 200
    err(client.get(f"{API}/donations/1/receipt", headers=world["m2"]), 404, "NOT_FOUND")
    err(client.get(f"{API}/donations/1/receipt"), 401, "UNAUTHENTICATED")


def test_receive_notifications_and_levels(client, admin_h, world, app):
    d = offer(client, world["m1"], donor_id=None, items=[item(quantity=20), item(title="B", quantity=1)])
    review(client, admin_h, d["id"], [accept(1, 1, 20, "100.00"), accept(2, 2, 1, "5.00")])
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": [f"DN-{i:04d}" for i in range(4)]}])
    assert len(notes(app, "donation_received")) == 1 and "4 copy" in notes(app, "donation_received")[0].message
    assert notes(app, "donor_level_reached") == []  # 400.00
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": [f"DN-1{i:03d}" for i in range(2)]}])  # 600.00
    lv = notes(app, "donor_level_reached")
    assert len(lv) == 1 and "bronze" in lv[0].message and lv[0].member_id == 1
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-2000"]}])  # 700.00: same level
    assert len(notes(app, "donor_level_reached")) == 1
    s = client.get(f"{API}/members/1/summary", headers=world["m1"]).json()["donations"]
    assert s == {"open": 1, "copies_received": 7, "value_this_year": "700.00", "level": "bronze"}
    donor = client.get(f"{API}/donors/1", headers=admin_h).json()
    assert donor["level"] == "bronze" and donor["value_this_year"] == "700.00"
    assert client.get(f"{API}/donors?level=bronze", headers=admin_h).json()["total"] == 1


def test_staff_donor_without_member_is_not_notified(client, admin_h, world, app):
    mk_donor(client, admin_h)
    two_item_donation(client, admin_h)
    receive(client, admin_h, 1, [{"item_id": 2, "barcodes": ["DN-0001"]}])
    assert sel(app, sa.select(Notification)) == []


def test_expiry(client, admin_h, world, app, clock):
    a = offer(client, world["m1"], donor_id=None)
    b = offer(client, world["m1"], donor_id=None)
    c = offer(client, world["m1"], donor_id=None)
    review(client, admin_h, a["id"], [accept(1)])
    review(client, admin_h, b["id"], [accept(2)])
    receive(client, admin_h, b["id"], [{"item_id": 2, "barcodes": ["DN-0001"]}])
    r = client.post(f"{API}/donations/process", headers=admin_h)
    assert r.status_code == 200 and r.json() == {"expired": 0}
    err(client.post(f"{API}/donations/process", headers=world["m1"]), 403, "FORBIDDEN")
    clock.set(datetime.datetime(2026, 11, 16, 12, 0, tzinfo=TZ))  # expected_by 2026-11-16: not yet late
    admin_h = h(token_of(client, "admin@library.local", "ChangeMe123"))
    assert client.post(f"{API}/donations/process", headers=admin_h).json() == {"expired": 0}
    clock.set(datetime.datetime(2026, 11, 17, 0, 5, tzinfo=TZ))
    admin_h = h(token_of(client, "admin@library.local", "ChangeMe123"))
    assert client.post(f"{API}/donations/process", headers=admin_h).json() == {"expired": 1}
    assert client.get(f"{API}/donations/1", headers=admin_h).json()["status"] == "expired"
    assert client.get(f"{API}/donations/2", headers=admin_h).json()["status"] == "received"
    assert client.get(f"{API}/donations/3", headers=admin_h).json()["status"] == "offered"
    assert len(notes(app, "donation_expired")) == 1 and len(audit(app, "donations_processed")) == 3
    err(client.post(f"{API}/donations/1/cancel", headers=admin_h), 409, "INVALID_DONATION_STATUS")
    assert c["id"] == 3


# --- copies ------------------------------------------------------------------------------------


def test_keep_period(client, admin_h, world, clock):
    mk_donor(client, admin_h)
    offer(client, admin_h)
    review(client, admin_h, 1, [accept(1)])
    clock.set(datetime.datetime(2026, 11, 2, 9, 30, tzinfo=TZ))
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0001"]}])
    c = client.get(f"{API}/copies/1", headers=admin_h).json()
    assert c["donation_id"] == 1 and c["acquired_on"] == "2026-11-02"
    assert client.get(f"{API}/books/1/copies?donated=true", headers=admin_h).json()["total"] == 1
    assert client.get(f"{API}/books/1/copies?donated=false", headers=admin_h).json()["total"] == 0
    clock.set(datetime.datetime(2027, 4, 30, 10, 0, tzinfo=TZ))
    hd = h(token_of(client, "admin@library.local", "ChangeMe123"))
    r = client.post(f"{API}/copies/1/withdraw", headers=hd, json={"reason": "worn out"})
    assert err(r, 409, "DONATION_KEEP_PERIOD")["details"]["keep_until"] == "2027-05-01"
    clock.set(datetime.datetime(2027, 5, 1, 10, 0, tzinfo=TZ))
    hd = h(token_of(client, "admin@library.local", "ChangeMe123"))
    assert client.post(f"{API}/copies/1/withdraw", headers=hd, json={"reason": "worn out"}).status_code == 200


def test_keep_period_not_for_lost(client, admin_h, world, app):
    mk_donor(client, admin_h)
    offer(client, admin_h)
    review(client, admin_h, 1, [accept(1)])
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0001"]}])
    with app.state.session_factory.begin() as s:
        s.get(Copy, 1).status = "lost"
    assert client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "gone for good"}).status_code == 200


def test_book_delete_in_use(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h)
    review(client, admin_h, 1, [accept(1, book_id=2)])
    err(client.delete(f"{API}/books/2", headers=admin_h), 409, "IN_USE")


def test_purchase_order_pending(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h, items=[item(), item(title="B")])
    review(client, admin_h, 1, [accept(1, book_id=2), accept(2, book_id=1)])

    counter = iter(range(100))

    def order(branch):
        r = client.post(f"{API}/suppliers", headers=admin_h, json={"name": f"S{next(counter)}"})
        r = client.post(f"{API}/purchase-orders", headers=admin_h, json={
            "supplier_id": r.json()["id"], "branch_id": branch,
            "lines": [{"book_id": 2, "quantity": 1, "unit_price": "10.00"}, {"book_id": 1, "quantity": 1, "unit_price": "10.00"}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    r = client.post(f"{API}/purchase-orders/{order(1)}/submit", headers=admin_h)
    assert err(r, 409, "DONATION_PENDING")["details"]["book_ids"] == [1, 2]
    assert client.post(f"{API}/purchase-orders/{order(2)}/submit", headers=admin_h).status_code == 200
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0001"]}])
    r = client.post(f"{API}/purchase-orders/{order(1)}/submit", headers=admin_h)
    assert err(r, 409, "DONATION_PENDING")["details"]["book_ids"] == [1]


def test_member_deactivation_cancels_offers(client, admin_h, world, app):
    a = offer(client, world["m1"], donor_id=None)
    b = offer(client, world["m1"], donor_id=None)
    review(client, admin_h, b["id"], [accept(2)])
    assert client.post(f"{API}/members/1/deactivate", headers=admin_h).status_code == 200
    ra = client.get(f"{API}/donations/{a['id']}", headers=admin_h).json()
    assert ra["status"] == "cancelled" and ra["cancel_reason"] == "member_deactivated"
    assert client.get(f"{API}/donations/{b['id']}", headers=admin_h).json()["status"] == "accepted"
    assert [n.type for n in sel(app, sa.select(Notification).where(Notification.type.like("donation%")))] == [
        "donation_reviewed"]


def test_member_summary_without_donor(client, admin_h, world):
    s = client.get(f"{API}/members/2/summary", headers=admin_h).json()["donations"]
    assert s == {"open": 0, "copies_received": 0, "value_this_year": "0.00", "level": "none"}


# --- recognition -------------------------------------------------------------------------------


def give(client, hd, donor_id, _unused, barcode, quantity=1, per=None):
    """A donation of ``quantity`` copies worth ``per`` each, received at once."""
    d = offer(client, hd, donor_id=donor_id, items=[item(quantity=quantity)])
    item_id = d["items"][0]["id"]
    review(client, hd, d["id"], [accept(item_id, 1, quantity, per)])
    receive(client, hd, d["id"], [{"item_id": item_id, "barcodes": [f"{barcode}-{i}" for i in range(quantity)]}])
    return d["id"]


def test_level_boundaries_and_years(client, admin_h, world, clock):
    mk_donor(client, admin_h)
    give(client, admin_h, 1, None, "AAAAA", 2, "249.99")
    assert client.get(f"{API}/donors/1", headers=admin_h).json()["level"] == "none"  # 499.98
    give(client, admin_h, 1, None, "BBBBB", 1, "0.02")
    assert client.get(f"{API}/donors/1", headers=admin_h).json()["level"] == "bronze"  # 500.00
    give(client, admin_h, 1, None, "CCCCC", 3, "500.00")
    d = client.get(f"{API}/donors/1", headers=admin_h).json()
    assert d["level"] == "silver" and d["value_this_year"] == "2000.00"
    clock.set(datetime.datetime(2026, 12, 31, 23, 0, tzinfo=TZ))
    hd = h(token_of(client, "admin@library.local", "ChangeMe123"))
    give(client, hd, 1, None, "DDDDD", 4, "2000.00")  # 8000.00 in 2026 -> 10000.00
    assert client.get(f"{API}/donors/1", headers=hd).json()["level"] == "gold"
    clock.set(datetime.datetime(2027, 1, 4, 9, 0, tzinfo=TZ))
    hd = h(token_of(client, "admin@library.local", "ChangeMe123"))
    assert client.get(f"{API}/donors/1", headers=hd).json()["level"] == "none"
    h1 = client.get(f"{API}/donors/1/history", headers=hd).json()
    assert h1["years"] == [{"year": 2026, "value": "10000.00", "level": "gold"}]
    give(client, hd, 1, None, "EEEEE", 1, "600.00")
    h1 = client.get(f"{API}/donors/1/history", headers=hd).json()
    assert [y["year"] for y in h1["years"]] == [2026, 2027] and h1["years"][1]["level"] == "bronze"
    assert h1["last_received_on"] == "2027-01-04" and h1["first_received_on"] == "2026-11-02"


def test_donor_wall_and_report(client, admin_h, world):
    mk_donor(client, admin_h, name="Zed", kind="organization")
    mk_donor(client, admin_h, name="Amy")
    mk_donor(client, admin_h, name="Hidden", anonymous=True)
    mk_donor(client, admin_h, name="Small")
    mk_donor(client, admin_h, name="Big")
    give(client, admin_h, 1, None, "ZZZZZ", 1, "600.00")
    give(client, admin_h, 2, None, "AAAAA", 1, "700.00")
    give(client, admin_h, 3, None, "HHHHH", 1, "900.00")
    give(client, admin_h, 4, None, "SSSSS", 1, "100.00")
    give(client, admin_h, 5, None, "BBBBB", 2, "3000.00")
    w = client.get(f"{API}/donor-wall", headers=world["m1"]).json()
    assert w == {"year": 2026, "donors": [{"name": "Big", "level": "silver"}, {"name": "Amy", "level": "bronze"},
                                         {"name": "Zed", "level": "bronze"}], "anonymous_count": 1}
    assert client.get(f"{API}/donor-wall?year=2027", headers=world["m1"]).json() == {
        "year": 2027, "donors": [], "anonymous_count": 0}
    for y in ("1999", "2101", "x"):
        err(client.get(f"{API}/donor-wall?year={y}", headers=world["m1"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/donor-wall"), 401, "UNAUTHENTICATED")
    rep = client.get(f"{API}/reports/donors?year=2026", headers=admin_h).json()["items"]
    assert [(r["name"], r["value"], r["level"], r["copies"]) for r in rep] == [
        ("Big", "6000.00", "silver", 2), ("Hidden", "900.00", "bronze", 1), ("Amy", "700.00", "bronze", 1),
        ("Zed", "600.00", "bronze", 1), ("Small", "100.00", "none", 1)]
    assert rep[0]["donor_id"] == 5 and rep[0]["kind"] == "person"
    err(client.get(f"{API}/reports/donors?year=2026", headers=world["m1"]), 403, "FORBIDDEN")


def test_donations_report(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h, branch_id=2, items=[item(quantity=4), item(title="B", quantity=2), item(title="C"),
                                               item(title="D")])
    review(client, admin_h, 1, [accept(1, 1, 3, "10.00"), accept(2, 2, 1, "5.00"), decline(3, "duplicate"),
                                decline(4, "too_old")])
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0001", "DN-0002"]}])
    offer(client, admin_h, branch_id=1, items=[item()])
    r = client.get(f"{API}/reports/donations?from=2026-11-01&to=2026-11-30", headers=admin_h).json()["items"]
    zero = {"duplicate": 0, "poor_condition": 0, "out_of_scope": 0, "too_old": 0, "other": 0}
    assert r == [
        {"branch_id": 2, "donations": 1, "copies_offered": 8, "copies_accepted": 4, "copies_received": 2,
         "value_received": "20.00", "declined": {**zero, "duplicate": 1, "too_old": 1}},
        {"branch_id": 1, "donations": 1, "copies_offered": 1, "copies_accepted": 0, "copies_received": 0,
         "value_received": "0.00", "declined": zero},
    ]  # ordered by branch code: KAMPUS < MERKEZ
    assert client.get(f"{API}/reports/donations?from=2027-01-01&to=2027-01-31", headers=admin_h).json()["items"] == []
    for q in ("from=2026-11-05&to=2026-11-01", "from=2026-01-01&to=2027-01-02", "from=2026-11-01", ""):
        err(client.get(f"{API}/reports/donations?{q}", headers=admin_h), 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/reports/donations?from=2026-01-01&to=2026-12-31", headers=admin_h).status_code == 200
    assert client.get(f"{API}/reports/donations?from=2026-11-01&to=2026-11-30", headers=world["lib"]).status_code == 200
    err(client.get(f"{API}/reports/donations?from=2026-11-01&to=2026-11-30", headers=world["m1"]), 403, "FORBIDDEN")


def test_not_exported(client, admin_h, world):
    mk_donor(client, admin_h)
    offer(client, admin_h)
    review(client, admin_h, 1, [accept(1)])
    receive(client, admin_h, 1, [{"item_id": 1, "barcodes": ["DN-0001"]}])
    data = client.get(f"{API}/export", headers=admin_h).json()
    assert data["copies"] and all("donation_id" not in c for c in data["copies"])
    assert not {"donors", "donations", "receivings"} & set(data)
