"""Module 26: Reading programs (LIB-RDP-01 to LIB-RDP-47).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (AAA) and 2 (BBB), books 0 to 5, students 1 to 4. The default
program runs 2026-11-02 – 2026-11-30 with a goal of 2 books.
"""

import pytest
import sqlalchemy as sa

import lms
from lms.fines.models import Fee
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_loans import API, at, lend, lib, mk_book, mk_member, member_h, new_copy, ret  # noqa: F401


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def prog(client, hd, expect=201, **kw):
    body = {"name": "Winter reading", "starts_on": "2026-11-02", "ends_on": "2026-11-30", "goal_books": 2, **kw}
    r = client.post(f"{API}/programs", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def published(client, hd, **kw):
    p = prog(client, hd, **kw)
    r = client.post(f"{API}/programs/{p['id']}/publish", headers=hd)
    assert r.status_code == 200, r.text
    return r.json()


def join(client, hd, pid, expect=201, **kw):
    r = client.post(f"{API}/programs/{pid}/join", headers=hd, json=kw)
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture
def world(client, lib):
    books = [mk_book(client, lib, n) for n in range(6)]
    members = [mk_member(client, lib, n) for n in range(1, 5)]
    mh = [member_h(client, n) for n in range(1, 5)]
    return {"lib": lib, "books": books, "members": members, "mh": mh, "n": 0}


def read(client, world, member, book_index, branch=1):
    """The member borrows and returns a book; returns the loan."""
    world["n"] += 1
    copy = new_copy(client, world["lib"], world["books"][book_index], f"BC{world['n']:04d}", branch)
    r = lend(client, world["lib"], world["members"][member], copy)
    assert r.status_code == 201, r.text
    loan_id = r.json()["id"]
    r = ret(client, world["lib"], loan_id, branch)
    assert r.status_code == 200, r.text
    return r.json()


def participation_of(client, hd, pid, member):
    items = client.get(f"{API}/programs/{pid}/participants", headers=hd).json()["items"]
    return next(i for i in items if i["member_id"] == member)


def entries_of(client, hd, part_id, query=""):
    r = client.get(f"{API}/participations/{part_id}/entries{query}", headers=hd)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


def notes(app, type_):
    return sel(app, sa.select(Notification).where(Notification.type == type_).order_by(Notification.id))


# --- programs -------------------------------------------------------------------------------------


def test_create_and_read(client, world, app):
    lib = world["lib"]
    p = prog(client, lib, description="Read!", max_participants=10, reward_waiver="20.00", branch_id=1)
    assert p["status"] == "draft" and p["published_at"] is None and p["audience"] == "all"
    assert p["participants"] == 0 and p["completed"] == 0 and p["free_places"] == 10
    assert p["reward_waiver"] == "20.00" and "my_participation" not in p
    assert len(audit(client.app, "program_created")) == 1
    assert client.get(f"{API}/programs/{p['id']}", headers=lib).json() == p
    err(client.post(f"{API}/programs", headers=world["mh"][0], json={}), 403, "FORBIDDEN")


@pytest.mark.parametrize(
    "kw",
    [
        {"name": " "},
        {"name": "x" * 201},
        {"description": "x" * 1001},
        {"ends_on": "2026-11-14"},  # 12 days
        {"ends_on": "2027-03-03"},  # 121 days
        {"goal_books": 0},
        {"goal_books": 51},
        {"max_participants": 0},
        {"max_participants": 1001},
        {"reward_waiver": "50.01"},
        {"reward_waiver": 5},
        {"audience": "guests"},
        {"branch_id": 99},
        {"unknown": 1},
    ],
)
def test_create_validation(client, world, kw):
    r = client.post(
        f"{API}/programs",
        headers=world["lib"],
        json={"name": "P", "starts_on": "2026-11-02", "ends_on": "2026-11-30", "goal_books": 2, **kw},
    )
    err(r, 422, "VALIDATION_ERROR")
    assert r.json()["error"]["details"]["fields"]


def test_create_limits_and_conflicts(client, world, admin_h):
    lib = world["lib"]
    prog(client, lib, name="Limits", ends_on="2026-11-15", goal_books=1, max_participants=1, reward_waiver="0.00")
    prog(client, lib, name="Limits 2", ends_on="2027-03-02", goal_books=50, max_participants=1000, reward_waiver="50.00")
    r = client.post(f"{API}/programs", headers=lib, json={"name": "LIMITS", "starts_on": "2026-11-02",
                                                           "ends_on": "2026-11-30", "goal_books": 2})
    assert err(r, 409, "CONFLICT")["details"]["field"] == "name"
    p = prog(client, lib, name="Gone")
    client.post(f"{API}/programs/{p['id']}/cancel", headers=lib)
    prog(client, lib, name="gone")  # a cancelled program does not block the name
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/programs", headers=lib, json={"name": "B", "starts_on": "2026-11-02",
                                                           "ends_on": "2026-11-30", "goal_books": 2,
                                                           "branch_id": 2}), 409, "BRANCH_INACTIVE")


def test_update_draft_and_published(client, world):
    lib = world["lib"]
    p = prog(client, lib)
    r = client.patch(f"{API}/programs/{p['id']}", headers=lib, json={"name": "Renamed", "goal_books": 3,
                                                                     "starts_on": "2026-11-03"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["starts_on"] == "2026-11-03"
    err(client.patch(f"{API}/programs/{p['id']}", headers=lib, json={"ends_on": "2026-11-10"}), 422, "VALIDATION_ERROR")
    other = prog(client, lib, name="Other")
    err(client.patch(f"{API}/programs/{other['id']}", headers=lib, json={"name": "renamed"}), 409, "CONFLICT")
    client.post(f"{API}/programs/{p['id']}/publish", headers=lib)
    err(client.patch(f"{API}/programs/{p['id']}", headers=lib, json={"name": "X"}), 409, "PROGRAM_PUBLISHED")
    r = client.patch(f"{API}/programs/{p['id']}", headers=lib, json={"description": "d", "ends_on": "2026-12-05",
                                                                     "max_participants": 5})
    assert r.status_code == 200 and r.json()["ends_on"] == "2026-12-05" and r.json()["free_places"] == 5
    err(client.patch(f"{API}/programs/{p['id']}", headers=lib, json={"ends_on": "2026-12-01"}), 422, "VALIDATION_ERROR")
    join(client, world["mh"][0], p["id"])
    join(client, world["mh"][1], p["id"])
    e = err(client.patch(f"{API}/programs/{p['id']}", headers=lib, json={"max_participants": 1}), 409,
            "PARTICIPANTS_ABOVE_LIMIT")
    assert e["details"]["participants"] == 2
    client.post(f"{API}/programs/{p['id']}/cancel", headers=lib)
    e = err(client.patch(f"{API}/programs/{p['id']}", headers=lib, json={"description": "z"}), 409,
            "INVALID_PROGRAM_STATUS")
    assert e["details"]["status"] == "cancelled"


def test_publish(client, world, clock):
    lib = world["lib"]
    p = prog(client, lib)
    r = client.post(f"{API}/programs/{p['id']}/publish", headers=lib)
    assert r.status_code == 200 and r.json()["status"] == "published"
    assert r.json()["published_at"] == "2026-11-02T09:30:00+03:00"
    err(client.post(f"{API}/programs/{p['id']}/publish", headers=lib), 409, "INVALID_PROGRAM_STATUS")
    old = prog(client, lib, name="Old", starts_on="2026-10-01", ends_on="2026-10-20")
    err(client.post(f"{API}/programs/{old['id']}/publish", headers=lib), 409, "PROGRAM_ENDED")
    err(client.post(f"{API}/programs/99/publish", headers=lib), 404, "NOT_FOUND")


def test_cancel_notifies_and_keeps_completed(client, world, app):
    lib = world["lib"]
    p = published(client, lib, goal_books=1)
    join(client, world["mh"][0], p["id"])
    join(client, world["mh"][1], p["id"])
    read(client, world, 0, 0)  # member 1 completes
    r = client.post(f"{API}/programs/{p['id']}/cancel", headers=lib)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    one = participation_of(client, lib, p["id"], world["members"][0])
    two = participation_of(client, lib, p["id"], world["members"][1])
    assert one["status"] == "completed" and two["status"] == "left"
    n = notes(app, "program_cancelled")
    assert [x.member_id for x in n] == [world["members"][1]] and "Winter reading" in n[0].message
    assert n[0].program_id == p["id"]
    err(client.post(f"{API}/programs/{p['id']}/cancel", headers=lib), 409, "INVALID_PROGRAM_STATUS")


def test_copy(client, world):
    lib = world["lib"]
    p = prog(client, lib, branch_id=1, max_participants=7, reward_waiver="5.00", audience="students")
    client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": world["books"][:2]})
    r = client.post(f"{API}/programs/{p['id']}/copy", headers=lib, json={"starts_on": "2026-12-07"})
    assert r.status_code == 201
    c = r.json()
    assert c["name"] == "Winter reading (copy)" and c["status"] == "draft"
    assert c["ends_on"] == "2027-01-04" and c["audience"] == "students" and c["max_participants"] == 7
    assert [b["book_id"] for b in client.get(f"{API}/programs/{c['id']}/books", headers=lib).json()["items"]] == \
        sorted(world["books"][:2])
    c2 = client.post(f"{API}/programs/{p['id']}/copy", headers=lib, json={"starts_on": "2027-02-01"}).json()
    assert c2["name"] == "Winter reading (copy 2)"
    client.post(f"{API}/programs/{p['id']}/cancel", headers=lib)
    assert client.post(f"{API}/programs/{p['id']}/copy", headers=lib, json={"starts_on": "2027-03-01"}).status_code == 201


def test_featured_books(client, world):
    lib = world["lib"]
    p = prog(client, lib)
    r = client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": [world["books"][1], world["books"][0]]})
    assert r.status_code == 200 and [b["title"] for b in r.json()["items"]] == ["Book 0", "Book 1"]
    err(client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": [999]}), 422, "VALIDATION_ERROR")
    err(client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": [1, 1]}), 422, "VALIDATION_ERROR")
    err(client.put(f"{API}/programs/{p['id']}/books", headers=world["mh"][0], json={"book_ids": []}), 403, "FORBIDDEN")
    assert client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": []}).json()["items"] == []
    assert client.get(f"{API}/programs/{p['id']}/books", headers=world["mh"][0]).status_code == 404  # draft
    client.post(f"{API}/programs/{p['id']}/cancel", headers=lib)
    err(client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": []}), 409, "INVALID_PROGRAM_STATUS")


def test_list_and_member_view(client, world, clock):
    lib = world["lib"]
    a = published(client, lib, name="A")
    prog(client, lib, name="B")  # draft
    c = published(client, lib, name="C", starts_on="2026-12-01", ends_on="2026-12-20", branch_id=2)
    join(client, world["mh"][0], a["id"])
    items = client.get(f"{API}/programs", headers=lib).json()
    assert [i["name"] for i in items["items"]] == ["A", "B", "C"] and items["total"] == 3
    assert all("my_participation" not in i for i in items["items"])
    assert [i["name"] for i in client.get(f"{API}/programs?running=true", headers=lib).json()["items"]] == ["A"]
    assert [i["name"] for i in client.get(f"{API}/programs?running=false", headers=lib).json()["items"]] == ["B", "C"]
    assert [i["name"] for i in client.get(f"{API}/programs?branch_id=2", headers=lib).json()["items"]] == ["C"]
    assert [i["name"] for i in client.get(f"{API}/programs?status=draft", headers=lib).json()["items"]] == ["B"]
    mine = client.get(f"{API}/programs", headers=world["mh"][0]).json()["items"]
    assert [i["name"] for i in mine] == ["A", "C"]
    assert mine[0]["my_participation"]["status"] == "active" and mine[1]["my_participation"] is None
    assert mine[0]["participants"] == 1 and mine[0]["completed"] == 0
    err(client.get(f"{API}/programs/{a['id'] + 1}", headers=world["mh"][0]), 404, "NOT_FOUND")
    assert client.get(f"{API}/programs/{c['id']}", headers=world["mh"][0]).status_code == 200


# --- joining ----------------------------------------------------------------------------------------


def test_join_and_leave(client, world, app):
    lib = world["lib"]
    p = published(client, lib)
    j = join(client, world["mh"][0], p["id"])
    assert j["status"] == "active" and j["points"] == 0 and j["books"] == 0 and j["level"] == "none"
    assert j["public"] is True and j["joined_at"] == "2026-11-02T09:30:00+03:00" and j["rank"] is None
    err(client.post(f"{API}/programs/{p['id']}/join", headers=world["mh"][0], json={}), 409, "ALREADY_JOINED")
    # staff send member_id, members must not
    err(client.post(f"{API}/programs/{p['id']}/join", headers=lib, json={}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/programs/{p['id']}/join", headers=world["mh"][1], json={"member_id": 2}), 422,
        "VALIDATION_ERROR")
    err(client.post(f"{API}/programs/{p['id']}/join", headers=lib, json={"member_id": 99}), 404, "NOT_FOUND")
    j2 = join(client, lib, p["id"], member_id=world["members"][1], public=False)
    assert j2["public"] is False
    assert client.post(f"{API}/programs/{p['id']}/join", headers=world["mh"][2]).status_code == 201  # no body
    r = client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][0])
    assert r.status_code == 200 and r.json()["status"] == "left" and r.json()["leave_reason"] == "member_request"
    assert r.json()["left_at"] == "2026-11-02T09:30:00+03:00"
    err(client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][0]), 409, "PARTICIPATION_NOT_ACTIVE")
    again = join(client, world["mh"][0], p["id"])
    assert again["id"] == j["id"] and again["status"] == "active" and again["left_at"] is None
    assert again["leave_reason"] is None
    assert audit(client.app, "program_joined") and audit(client.app, "program_left")
    assert not notes(app, "program_completed")


def test_join_checks_in_order(client, world, admin_h, clock):
    lib = world["lib"]
    d = prog(client, lib, name="Draft")
    err(client.post(f"{API}/programs/{d['id']}/join", headers=world["mh"][0], json={}), 409, "PROGRAM_NOT_OPEN")
    p = published(client, lib, name="Only students", audience="academics", max_participants=1)
    err(client.post(f"{API}/programs/{p['id']}/join", headers=world["mh"][0], json={}), 409, "PROGRAM_NOT_FOR_TYPE")
    q = published(client, lib, name="Small", max_participants=1)
    join(client, world["mh"][0], q["id"])
    err(client.post(f"{API}/programs/{q['id']}/join", headers=world["mh"][1], json={}), 409, "PROGRAM_FULL")
    old = published(client, lib, name="Soon over", ends_on="2026-11-15")
    clock.set(clock.now().replace(day=16))
    err(client.post(f"{API}/programs/{old['id']}/join", headers=lib, json={"member_id": 2}), 409, "PROGRAM_ENDED")


def test_join_member_checks(client, world, admin_h, clock):
    lib = world["lib"]
    p = published(client, lib)
    client.post(f"{API}/members/{world['members'][0]}/deactivate", headers=lib)
    err(client.post(f"{API}/programs/{p['id']}/join", headers=lib, json={"member_id": world["members"][0]}), 409,
        "MEMBER_PASSIVE")
    # an expired membership
    at(clock, 2027, 11, 5)
    err(client.post(f"{API}/programs/{p['id']}/join", headers=lib, json={"member_id": world["members"][1]}), 409,
        "PROGRAM_ENDED")


def test_join_debt_and_limit(client, world, app):
    lib = world["lib"]
    first = [published(client, lib, name=f"P{i}") for i in range(4)]
    for p in first[:3]:
        join(client, world["mh"][0], p["id"])
    e = err(client.post(f"{API}/programs/{first[3]['id']}/join", headers=world["mh"][0], json={}), 409,
            "PROGRAM_LIMIT_REACHED")
    assert e["details"]["limit"] == 3
    client.post(f"{API}/programs/{first[0]['id']}/leave", headers=world["mh"][0])
    join(client, world["mh"][0], first[3]["id"])
    with app.state.session_factory.begin() as s:
        s.add(Fee(member_id=world["members"][1], kind="late_fee", amount=__import__("decimal").Decimal("50.00"),
                  status="open", created_on=__import__("datetime").date(2026, 11, 2)))
    e = err(client.post(f"{API}/programs/{first[0]['id']}/join", headers=world["mh"][1], json={}), 409,
            "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"


def test_visibility(client, world):
    lib = world["lib"]
    p = published(client, lib)
    j = join(client, world["mh"][0], p["id"])
    r = client.patch(f"{API}/participations/{j['id']}", headers=world["mh"][0], json={"public": False})
    assert r.status_code == 200 and r.json()["public"] is False
    err(client.patch(f"{API}/participations/{j['id']}", headers=world["mh"][1], json={"public": True}), 403, "FORBIDDEN")
    err(client.patch(f"{API}/participations/{j['id']}", headers=lib, json={"public": True}), 403, "FORBIDDEN")
    err(client.patch(f"{API}/participations/99", headers=world["mh"][0], json={"public": True}), 404, "NOT_FOUND")


# --- loan entries -------------------------------------------------------------------------------------


def test_loan_entries_example(client, world, clock, app):
    lib = world["lib"]
    p = published(client, lib, branch_id=1, goal_books=5)
    j = join(client, world["mh"][0], p["id"])
    # on time on 2026-11-05
    at(clock, 2026, 11, 3)
    copy = new_copy(client, lib, world["books"][0], "XBC001")
    loan = lend(client, lib, world["members"][0], copy).json()
    at(clock, 2026, 11, 5)
    ret(client, lib, loan["id"])
    entries = entries_of(client, lib, j["id"])
    assert len(entries) == 1 and entries[0]["points"] == 10 and entries[0]["source"] == "loan"
    assert entries[0]["on"] == "2026-11-05" and entries[0]["book_title"] == "Book 0"
    assert entries[0]["loan_id"] == loan["id"] and entries[0]["event_id"] is None
    # the same book again: no entry
    copy = new_copy(client, lib, world["books"][0], "XBC002")
    loan = lend(client, lib, world["members"][0], copy).json()
    ret(client, lib, loan["id"])
    assert len(entries_of(client, lib, j["id"])) == 1
    # a loan from branch B: no entry
    copy = new_copy(client, lib, world["books"][1], "XBC003", branch=2)
    loan = lend(client, lib, world["members"][0], copy).json()
    ret(client, lib, loan["id"], branch=1)  # returned at A, but the loan's branch counts (LIB-RDP-41)
    assert len(entries_of(client, lib, j["id"])) == 1
    # a late loan from A: 5 points
    copy = new_copy(client, lib, world["books"][2], "XBC004")
    loan = lend(client, lib, world["members"][0], copy).json()
    at(clock, 2026, 11, 20)
    ret(client, lib, loan["id"], branch=2)
    late = entries_of(client, lib, j["id"])[-1]
    assert late["points"] == 5 and late["on"] == "2026-11-20"
    part = participation_of(client, lib, p["id"], world["members"][0])
    assert part["points"] == 15 and part["books"] == 2 and part["rank"] == 1
    # after the end: no entry
    copy = new_copy(client, lib, world["books"][3], "XBC005")
    loan = lend(client, lib, world["members"][0], copy).json()
    at(clock, 2026, 12, 1)
    ret(client, lib, loan["id"])
    assert len(entries_of(client, lib, j["id"])) == 2
    assert not notes(app, "program_completed")


def test_loans_before_joining_and_lost(client, world, clock):
    lib = world["lib"]
    p = published(client, lib)
    copy = new_copy(client, lib, world["books"][0], "YBC001")
    loan = lend(client, lib, world["members"][0], copy).json()
    at(clock, 2026, 11, 3, hh=11)
    j = join(client, world["mh"][0], p["id"])
    at(clock, 2026, 11, 4)
    ret(client, lib, loan["id"])  # made before joining, returned after: counts
    assert len(entries_of(client, lib, j["id"])) == 1
    copy = new_copy(client, lib, world["books"][1], "YBC002")
    loan = lend(client, lib, world["members"][0], copy).json()
    assert client.post(f"{API}/loans/{loan['id']}/report-lost", headers=lib).status_code == 200
    assert len(entries_of(client, lib, j["id"])) == 1


def test_returned_before_joining_does_not_count(client, world, clock):
    lib = world["lib"]
    p = published(client, lib)
    read(client, world, 0, 0)
    j = join(client, world["mh"][0], p["id"])
    assert entries_of(client, lib, j["id"]) == []


def test_inactive_or_left_participation_gets_no_entries(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=5)
    j = join(client, world["mh"][0], p["id"])
    client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][0])
    read(client, world, 0, 0)
    assert entries_of(client, lib, j["id"]) == []


# --- manual entries -----------------------------------------------------------------------------------


def test_manual_entries(client, world, app):
    lib = world["lib"]
    p = published(client, lib, goal_books=10)
    j = join(client, world["mh"][0], p["id"])
    url = f"{API}/participations/{j['id']}/entries"
    err(client.post(url, headers=world["mh"][0], json={"book_id": world["books"][0]}), 403, "FORBIDDEN")
    err(client.post(url, headers=lib, json={"book_id": 999}), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=lib, json={"book_id": world["books"][0], "note": "x" * 201}), 422, "VALIDATION_ERROR")
    r = client.post(url, headers=lib, json={"book_id": world["books"][0], "note": "nice"})
    assert r.status_code == 201
    e = r.json()
    assert e["source"] == "manual" and e["points"] == 10 and e["on"] == "2026-11-02" and e["note"] == "nice"
    assert e["book_title"] == "Book 0"
    err(client.post(url, headers=lib, json={"book_id": world["books"][0]}), 409, "BOOK_ALREADY_COUNTED")
    client.post(url, headers=lib, json={"book_id": world["books"][1]})
    client.post(url, headers=lib, json={"book_id": world["books"][2]})
    x = err(client.post(url, headers=lib, json={"book_id": world["books"][3]}), 409, "MANUAL_ENTRY_LIMIT")
    assert x["details"]["limit"] == 3
    assert audit(client.app, "program_entry_added")
    # remove
    r = client.delete(f"{API}/program-entries/{e['id']}", headers=lib)
    assert r.status_code == 204
    part = participation_of(client, lib, p["id"], world["members"][0])
    assert part["points"] == 20 and part["books"] == 2
    assert audit(client.app, "program_entry_removed")
    err(client.delete(f"{API}/program-entries/{e['id']}", headers=lib), 404, "NOT_FOUND")
    err(client.delete(f"{API}/program-entries/{e['id'] + 1}", headers=world["mh"][0]), 403, "FORBIDDEN")
    # a loan entry cannot be removed
    read(client, world, 0, 4)
    loan_entry = entries_of(client, lib, j["id"], "?source=loan")[0]
    err(client.delete(f"{API}/program-entries/{loan_entry['id']}", headers=lib), 409, "ENTRY_NOT_MANUAL")
    assert len(entries_of(client, lib, j["id"], "?source=manual")) == 2
    client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][0])
    err(client.post(url, headers=lib, json={"book_id": world["books"][5]}), 409, "PARTICIPATION_NOT_ACTIVE")
    manual = entries_of(client, lib, j["id"], "?source=manual")[0]
    err(client.delete(f"{API}/program-entries/{manual['id']}", headers=lib), 409, "PARTICIPATION_NOT_ACTIVE")


def test_manual_entry_needs_running_program(client, world, clock):
    lib = world["lib"]
    p = published(client, lib, starts_on="2026-11-09", ends_on="2026-11-30")
    j = join(client, world["mh"][0], p["id"])  # joining before the start is fine
    err(client.post(f"{API}/participations/{j['id']}/entries", headers=lib, json={"book_id": world["books"][0]}), 409,
        "PROGRAM_NOT_RUNNING")


def test_read_entries_ownership(client, world):
    lib = world["lib"]
    p = published(client, lib)
    j = join(client, world["mh"][0], p["id"])
    assert client.get(f"{API}/participations/{j['id']}/entries", headers=world["mh"][0]).status_code == 200
    err(client.get(f"{API}/participations/{j['id']}/entries", headers=world["mh"][1]), 403, "FORBIDDEN")
    err(client.get(f"{API}/participations/99/entries", headers=lib), 404, "NOT_FOUND")


# --- bonuses ------------------------------------------------------------------------------------------


def test_featured_bonus(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=10)
    client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": [world["books"][0], world["books"][1]]})
    j = join(client, world["mh"][0], p["id"])
    client.post(f"{API}/participations/{j['id']}/entries", headers=lib, json={"book_id": world["books"][0]})
    read(client, world, 0, 1)
    read(client, world, 0, 2)
    pts = [e["points"] for e in entries_of(client, lib, j["id"])]
    assert pts == [15, 15, 10]
    # changing the featured books does not change entries
    client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": []})
    assert [e["points"] for e in entries_of(client, lib, j["id"])] == [15, 15, 10]


def test_featured_late_loan(client, world, clock):
    lib = world["lib"]
    p = published(client, lib, goal_books=10)
    client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": [world["books"][0]]})
    j = join(client, world["mh"][0], p["id"])
    copy = new_copy(client, lib, world["books"][0], "LBC001")
    loan = lend(client, lib, world["members"][0], copy).json()
    at(clock, 2026, 11, 20)
    ret(client, lib, loan["id"])
    assert entries_of(client, lib, j["id"])[0]["points"] == 10


def test_weekly_bonus_example(client, world, clock):
    lib = world["lib"]
    p = published(client, lib, goal_books=50)
    j = join(client, world["mh"][0], p["id"])
    url = f"{API}/participations/{j['id']}/entries"
    for day, book in ((3, 0), (5, 1), (10, 2)):
        at(clock, 2026, 11, day)
        r = client.post(url, headers=lib, json={"book_id": world["books"][book]})
        assert r.status_code == 201, r.text
    assert not entries_of(client, lib, j["id"], "?source=bonus")
    at(clock, 2026, 11, 17)
    read(client, world, 0, 3)  # the fourth book entry, from a loan
    bonus = entries_of(client, lib, j["id"], "?source=bonus")
    assert len(bonus) == 1 and bonus[0]["points"] == 10 and bonus[0]["on"] == "2026-11-17"
    assert bonus[0]["book_id"] is None and bonus[0]["book_title"] is None
    at(clock, 2026, 11, 24)
    read(client, world, 0, 4)
    assert len(entries_of(client, lib, j["id"], "?source=bonus")) == 1
    part = participation_of(client, lib, p["id"], world["members"][0])
    assert part["points"] == 4 * 10 + 10 + 10 and part["books"] == 5


# --- completion, levels, rewards ------------------------------------------------------------------------


def test_levels_and_completion(client, world, app):
    lib = world["lib"]
    p = published(client, lib, goal_books=2)
    j = join(client, world["mh"][0], p["id"])
    seen = []
    for i in range(6):
        read(client, world, 0, i)
        part = participation_of(client, lib, p["id"], world["members"][0])
        seen.append((part["books"], part["level"], part["status"]))
    assert seen == [(1, "none", "active"), (2, "bronze", "completed"), (3, "bronze", "completed"),
                    (4, "silver", "completed"), (5, "silver", "completed"), (6, "gold", "completed")]
    done = notes(app, "program_completed")
    assert len(done) == 1 and "Winter reading" in done[0].message and done[0].program_id == p["id"]
    levels = notes(app, "program_level_reached")
    assert len(levels) == 2 and "silver" in levels[0].message and "gold" in levels[1].message
    assert len(audit(client.app, "program_completed")) == 1
    shown = client.get(f"{API}/programs/{p['id']}", headers=lib).json()
    assert shown["participants"] == 1 and shown["completed"] == 1
    cert = client.get(f"{API}/participations/{j['id']}/certificate", headers=world["mh"][0])
    assert cert.status_code == 200
    c = cert.json()
    assert c["certificate_no"] == f"RP-{p['id']}-1" and c["program_name"] == "Winter reading"
    assert c["level"] == "gold" and c["books"] == 6 and c["points"] == 60 and c["member_name"]
    assert c["completed_at"].startswith("2026-11-02T")


def test_certificate_rules(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=1)
    j1 = join(client, world["mh"][0], p["id"])
    j2 = join(client, world["mh"][1], p["id"])
    err(client.get(f"{API}/participations/{j1['id']}/certificate", headers=lib), 409, "NOT_COMPLETED")
    read(client, world, 1, 0)
    read(client, world, 0, 1)
    assert client.get(f"{API}/participations/{j2['id']}/certificate", headers=lib).json()["certificate_no"] == \
        f"RP-{p['id']}-1"
    assert client.get(f"{API}/participations/{j1['id']}/certificate", headers=lib).json()["certificate_no"] == \
        f"RP-{p['id']}-2"
    err(client.get(f"{API}/participations/{j1['id']}/certificate", headers=world["mh"][1]), 403, "FORBIDDEN")


def test_completed_cannot_leave_and_removal_keeps_completion(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=2)
    j = join(client, world["mh"][0], p["id"])
    url = f"{API}/participations/{j['id']}/entries"
    e1 = client.post(url, headers=lib, json={"book_id": world["books"][0]}).json()
    client.post(url, headers=lib, json={"book_id": world["books"][1]})
    part = participation_of(client, lib, p["id"], world["members"][0])
    assert part["status"] == "completed" and part["level"] == "bronze"
    err(client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][0]), 409, "PARTICIPATION_NOT_ACTIVE")
    assert client.delete(f"{API}/program-entries/{e1['id']}", headers=lib).status_code == 204
    part = participation_of(client, lib, p["id"], world["members"][0])
    assert part["status"] == "completed" and part["level"] == "bronze" and part["books"] == 1
    err(client.post(f"{API}/programs/{p['id']}/join", headers=world["mh"][0], json={}), 409, "ALREADY_JOINED")


def test_reward_example(client, world, app):
    import datetime
    from decimal import Decimal

    lib = world["lib"]
    p = published(client, lib, goal_books=1, reward_waiver="20.00")
    join(client, world["mh"][0], p["id"])
    member = world["members"][0]
    with app.state.session_factory.begin() as s:
        for amount, day in (("8.00", 2), ("15.00", 3), ("10.00", 4)):
            s.add(Fee(member_id=member, kind="late_fee", amount=Decimal(amount), status="open",
                      created_on=datetime.date(2026, 10, day)))
        s.add(Fee(member_id=member, kind="damage_fee", amount=Decimal("1.00"), status="open",
                  created_on=datetime.date(2026, 10, 1)))
    read(client, world, 0, 0)
    fees = sel(app, sa.select(Fee).where(Fee.member_id == member).order_by(Fee.id))
    assert [(f.kind, str(f.amount), f.status) for f in fees] == [
        ("late_fee", "8.00", "waived"), ("late_fee", "15.00", "open"), ("late_fee", "10.00", "waived"),
        ("damage_fee", "1.00", "open")]
    assert fees[0].waive_reason == "Reading program reward"
    part = participation_of(client, lib, p["id"], member)
    assert part["reward_waived"] == "18.00"
    assert len(notes(app, "fee_waived")) == 2


def test_reward_skips_partly_paid_fees(client, world, app):
    import datetime
    from decimal import Decimal

    lib = world["lib"]
    p = published(client, lib, goal_books=1, reward_waiver="50.00")
    join(client, world["mh"][0], p["id"])
    member = world["members"][0]
    with app.state.session_factory.begin() as s:
        s.add(Fee(member_id=member, kind="late_fee", amount=Decimal("5.00"), paid_amount=Decimal("1.00"),
                  status="open", created_on=datetime.date(2026, 10, 1)))
    read(client, world, 0, 0)
    assert participation_of(client, lib, p["id"], member)["reward_waived"] == "0.00"


def test_rejoin_keeps_entries_and_checks_completion_at_next_entry(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=2)
    j = join(client, world["mh"][0], p["id"])
    read(client, world, 0, 0)
    client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][0])
    assert join(client, world["mh"][0], p["id"])["books"] == 1
    read(client, world, 0, 1)
    part = participation_of(client, lib, p["id"], world["members"][0])
    assert part["status"] == "completed" and part["books"] == 2
    assert len(entries_of(client, lib, j["id"])) == 2


# --- events ---------------------------------------------------------------------------------------------


def test_event_entries(client, world, admin_h, clock, app):
    from tests.test_events import mk_event, publish, register, shift_on
    from tests.test_staff import mk_staff

    lib = world["lib"]
    mk_staff(client, admin_h, email="staff@example.com")
    shift_on(client, admin_h, "2026-11-05")
    ev = mk_event(client, admin_h)
    publish(client, admin_h, ev["id"])
    p = published(client, lib, goal_books=5, branch_id=1)
    other = published(client, lib, name="B only", goal_books=5, branch_id=2)
    j = join(client, world["mh"][0], p["id"])
    join(client, world["mh"][0], other["id"])
    reg_id = register(client, world["mh"][0], ev["id"])["id"]
    at(clock, 2026, 11, 5, hh=13)
    clock.set(clock.now().replace(minute=45))
    r = client.post(f"{API}/event-registrations/{reg_id}/check-in", headers=admin_h)
    assert r.status_code == 200, r.text
    entries = entries_of(client, lib, j["id"])
    assert len(entries) == 1 and entries[0]["source"] == "event" and entries[0]["points"] == 15
    assert entries[0]["event_id"] == ev["id"] and entries[0]["book_id"] is None and entries[0]["book_title"] is None
    part = participation_of(client, lib, p["id"], world["members"][0])
    assert part["points"] == 15 and part["books"] == 0 and part["level"] == "none" and part["rank"] == 1
    assert participation_of(client, lib, other["id"], world["members"][0])["points"] == 0


# --- ranking and leaderboard ----------------------------------------------------------------------------


def test_rank_and_leaderboard(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=2)
    for i in range(4):
        join(client, world["mh"][i], p["id"])
    read(client, world, 2, 0)
    read(client, world, 0, 0)
    read(client, world, 0, 1)  # member 1: 20 points, completed
    read(client, world, 1, 0)
    read(client, world, 1, 1)  # member 2: 20 points, completed later
    client.patch(f"{API}/participations/{participation_of(client, lib, p['id'], world['members'][2])['participation_id']}",
                 headers=world["mh"][2], json={"public": False})
    board = client.get(f"{API}/programs/{p['id']}/leaderboard", headers=world["mh"][3]).json()
    assert [(i["rank"], i["points"]) for i in board["items"]] == [(1, 20), (2, 20), (3, 10)]
    assert board["items"][2]["name"] == "Anonymous" and "member_id" not in board["items"][0]
    assert board["items"][0]["name"] == "Ayşe Y." and board["items"][0]["books"] == 2
    assert board["items"][0]["level"] == "bronze"
    staff = client.get(f"{API}/programs/{p['id']}/leaderboard", headers=lib).json()["items"]
    assert [i["member_id"] for i in staff] == [world["members"][0], world["members"][1], world["members"][2]]
    listing = client.get(f"{API}/programs/{p['id']}/participants", headers=lib).json()["items"]
    assert [i["rank"] for i in listing] == [1, 2, 3, None]
    assert listing[3]["points"] == 0 and listing[0]["full_name"] and listing[0]["reward_waived"] == "0.00"
    done = client.get(f"{API}/programs/{p['id']}/participants?status=completed", headers=lib).json()["items"]
    assert [i["member_id"] for i in done] == [world["members"][0], world["members"][1]]
    err(client.get(f"{API}/programs/{p['id']}/participants", headers=world["mh"][0]), 403, "FORBIDDEN")
    # left participations are not ranked
    client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][2])
    assert len(client.get(f"{API}/programs/{p['id']}/leaderboard", headers=lib).json()["items"]) == 2
    d = prog(client, lib, name="Draft")
    err(client.get(f"{API}/programs/{d['id']}/leaderboard", headers=world["mh"][0]), 404, "NOT_FOUND")
    assert client.get(f"{API}/programs/{d['id']}/leaderboard", headers=lib).status_code == 200


def test_member_programs(client, world):
    lib = world["lib"]
    a = published(client, lib, name="A")
    b = published(client, lib, name="B", goal_books=1)
    join(client, world["mh"][0], a["id"])
    join(client, world["mh"][0], b["id"])
    read(client, world, 0, 0)
    r = client.get(f"{API}/members/{world['members'][0]}/programs", headers=world["mh"][0])
    items = r.json()["items"]
    assert [i["program_name"] for i in items] == ["B", "A"]  # same joined_at: newest id first
    assert items[0]["status"] == "completed" and items[0]["rank"] == 1 and items[0]["goal_books"] == 1
    assert items[1]["status"] == "active" and items[1]["points"] == 10
    err(client.get(f"{API}/members/{world['members'][0]}/programs", headers=world["mh"][1]), 403, "FORBIDDEN")
    assert client.get(f"{API}/members/{world['members'][0]}/programs", headers=lib).status_code == 200
    err(client.get(f"{API}/members/99/programs", headers=lib), 404, "NOT_FOUND")


# --- process --------------------------------------------------------------------------------------------


def test_close_example(client, world, clock):
    lib = world["lib"]
    p = published(client, lib, goal_books=1)
    join(client, world["mh"][0], p["id"])
    join(client, world["mh"][1], p["id"])
    read(client, world, 0, 0)
    at(clock, 2026, 11, 30)
    r = client.post(f"{API}/programs/process", headers=lib)
    assert r.status_code == 200 and r.json()["closed"] == 0
    at(clock, 2026, 12, 1)
    r = client.post(f"{API}/programs/process", headers=lib)
    assert r.json() == {"closed": 1, "participants_completed": 1, "participants_not_completed": 1, "reminders": 0}
    shown = client.get(f"{API}/programs/{p['id']}", headers=lib).json()
    assert shown["status"] == "closed" and shown["closed_at"] == "2026-12-01T09:00:00+03:00"
    world["mh"][0].update(member_h(client, 1))
    assert client.post(f"{API}/programs/process", headers=lib).json()["closed"] == 0
    assert audit(client.app, "programs_processed")
    err(client.post(f"{API}/programs/process", headers=world["mh"][0]), 403, "FORBIDDEN")
    assert client.get(f"{API}/programs/{p['id']}", headers=world["mh"][0]).status_code == 200


def test_ending_reminder_example(client, world, clock, app):
    lib = world["lib"]
    p = published(client, lib)
    join(client, world["mh"][0], p["id"])
    join(client, world["mh"][1], p["id"])
    client.post(f"{API}/programs/{p['id']}/leave", headers=world["mh"][1])
    at(clock, 2026, 11, 26)
    assert client.post(f"{API}/programs/process", headers=lib).json()["reminders"] == 0
    at(clock, 2026, 11, 27)
    assert client.post(f"{API}/programs/process", headers=lib).json()["reminders"] == 1
    n = notes(app, "program_ending")
    assert len(n) == 1 and n[0].member_id == world["members"][0] and "Winter reading" in n[0].message
    assert client.post(f"{API}/programs/process", headers=lib).json()["reminders"] == 0
    at(clock, 2026, 11, 28)
    assert client.post(f"{API}/programs/process", headers=lib).json()["reminders"] == 0


# --- other modules --------------------------------------------------------------------------------------


def test_deactivation_and_summary(client, world, clock, app):
    lib = world["lib"]
    a = published(client, lib, name="A", goal_books=1)
    b = published(client, lib, name="B", goal_books=5)
    ja = join(client, world["mh"][0], a["id"])
    jb = join(client, world["mh"][0], b["id"])
    read(client, world, 0, 0)  # completes A (10 points in A and 10 in B)
    s = client.get(f"{API}/members/{world['members'][0]}/summary", headers=lib).json()
    assert s["programs"] == {"active": 1, "completed_this_year": 1, "points_this_year": 20}
    assert client.get(f"{API}/members/{world['members'][1]}/summary", headers=lib).json()["programs"] == {
        "active": 0, "completed_this_year": 0, "points_this_year": 0}
    before = len(sel(app, sa.select(Notification)))
    r = client.post(f"{API}/members/{world['members'][0]}/deactivate", headers=lib)
    assert r.status_code == 200
    mine = client.get(f"{API}/members/{world['members'][0]}/programs", headers=lib).json()["items"]
    assert {i["program_name"]: i["status"] for i in mine} == {"A": "completed", "B": "left"}
    assert len(sel(app, sa.select(Notification))) == before + 1  # only member_deactivated
    assert ja["id"] != jb["id"]


def test_deactivated_member_sets_reason(client, world, app):
    from lms.programs.models import Participation

    lib = world["lib"]
    p = published(client, lib)
    join(client, world["mh"][0], p["id"])
    client.post(f"{API}/members/{world['members'][0]}/deactivate", headers=lib)
    part = sel(app, sa.select(Participation))[0]
    assert part.status == "left" and part.leave_reason == "member_deactivated" and part.left_at is not None


def test_branch_in_use(client, world, admin_h):
    lib = world["lib"]
    d = prog(client, lib, branch_id=2)
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/programs/{d['id']}/cancel", headers=lib)
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200


def test_notification_program_id(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=1)
    join(client, world["mh"][0], p["id"])
    read(client, world, 0, 0)
    items = client.get(f"{API}/members/{world['members'][0]}/notifications?type=program_completed",
                       headers=world["mh"][0]).json()["items"]
    assert len(items) == 1 and items[0]["program_id"] == p["id"] and items[0]["loan_id"] is None
    other = client.get(f"{API}/members/{world['members'][0]}/notifications?type=loan_returned",
                       headers=world["mh"][0]).json()["items"]
    assert other[0]["program_id"] is None


# --- report ---------------------------------------------------------------------------------------------


def test_programs_report(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=1, name="Reported")
    prog(client, lib, name="Draft is not reported")
    published(client, lib, name="Later", starts_on="2027-03-01", ends_on="2027-03-20")
    for i in range(3):
        join(client, world["mh"][i], p["id"])
    read(client, world, 0, 0)
    read(client, world, 1, 0)
    read(client, world, 2, 1)
    client.put(f"{API}/programs/{p['id']}/books", headers=lib, json={"book_ids": []})
    r = client.get(f"{API}/reports/programs?from=2026-11-01&to=2026-12-31", headers=lib)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["program_id"] == p["id"] and row["name"] == "Reported" and row["status"] == "published"
    assert row["participants"] == 3 and row["completed"] == 3 and row["completion_rate"] == "100.0"
    assert row["books_counted"] == 3 and row["points"] == 30 and row["rewards_waived"] == "0.00"
    assert row["top_books"] == [{"book_id": world["books"][0], "title": "Book 0", "count": 2},
                                {"book_id": world["books"][1], "title": "Book 1", "count": 1}]
    err(client.get(f"{API}/reports/programs?from=2026-11-01&to=2027-12-31", headers=lib), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/programs?from=2026-12-01&to=2026-11-01", headers=lib), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/programs?from=2026-11-01&to=2026-12-31", headers=world["mh"][0]), 403, "FORBIDDEN")
    empty = client.get(f"{API}/reports/programs?from=2027-01-01&to=2027-01-31", headers=lib).json()["items"]
    assert empty == []


def test_rate_with_one_decimal(client, world):
    lib = world["lib"]
    p = published(client, lib, goal_books=1)
    for i in range(3):
        join(client, world["mh"][i], p["id"])
    read(client, world, 0, 0)
    row = client.get(f"{API}/reports/programs?from=2026-11-01&to=2026-11-30", headers=lib).json()["items"][0]
    assert row["completion_rate"] == "33.3"
    assert client.get(f"{API}/reports/programs?from=2026-11-01&to=2026-11-30", headers=lib).json()["total"] == 1
