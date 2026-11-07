"""Module 15: Study rooms (LIB-ROOM-01 to LIB-ROOM-45)."""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.fines.models import Fee
from lms.notifications.models import Notification
from lms.rooms.models import RoomBan, RoomBooking
from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_branches import lib_h, member_body, mk_branch
from tests.test_members import guest_body, reg

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def at(day, hhmm="09:00"):
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def mk_room(client, admin_h, code="R1", branch_id=1, kind="individual", **kw):
    body = {"branch_id": branch_id, "code": code, "name": f"Room {code}", "kind": kind, "opens_at": "08:00", "closes_at": "20:00"}
    if kind == "group":
        body.update(capacity=6, min_participants=2)
    body.update(kw)
    r = client.post(f"{API}/rooms", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def book(client, headers, expect=201, **kw):
    body = {"room_id": 1, "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}
    body.update(kw)
    r = client.post(f"{API}/room-bookings", headers=headers, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def member_token(client, email, password="Passw0rd1"):
    return h(token_of(client, email, password))


@pytest.fixture
def world(client, admin_h):
    mk_branch(client, admin_h)
    lh = lib_h(client, admin_h)
    m1 = reg(client, admin_h)
    m2 = reg(client, admin_h, email="b@example.com", university_id="20230002", full_name="Bora")
    m3 = reg(client, admin_h, email="c@example.com", university_id="20230003", full_name="Cem")
    return {"lh": lh, "m": [m1, m2, m3], "mh": member_token(client, "ayse@example.edu.tr")}


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


# --- rooms -----------------------------------------------------------------------------------


def test_create_room(client, admin_h, world, app):
    r = client.post(
        f"{API}/rooms",
        headers=admin_h,
        json={"branch_id": 1, "code": "g1", "name": " Big ", "kind": "group", "capacity": 8, "min_participants": 3,
              "features": ["projector", "whiteboard"], "opens_at": "09:00", "closes_at": "18:30"},
    )
    assert r.status_code == 201
    assert r.json() == {
        "id": 1, "branch_id": 1, "code": "G1", "name": "Big", "kind": "group", "capacity": 8, "min_participants": 3,
        "features": ["whiteboard", "projector"], "opens_at": "09:00", "closes_at": "18:30", "is_active": True,
        "created_at": "2026-11-02T09:30:00+03:00",
    }
    ind = client.post(f"{API}/rooms", headers=admin_h, json={"branch_id": 1, "code": "I1", "name": "x", "kind": "individual", "opens_at": "07:00", "closes_at": "23:00"})
    assert ind.status_code == 201 and ind.json()["capacity"] == 1 and ind.json()["features"] == []
    assert [a.entity_id for a in audit(app, "room_created")] == [1, 2]


@pytest.mark.parametrize(
    "patch",
    [
        {"code": "A"}, {"code": "a-b"}, {"name": " "}, {"kind": "big"}, {"opens_at": "06:30"}, {"opens_at": "08:15"},
        {"closes_at": "23:30"}, {"closes_at": "08:00"}, {"opens_at": "20:00", "closes_at": "09:00"}, {"features": ["tv"]},
        {"features": ["projector", "projector"]}, {"kind": "individual", "capacity": 2}, {"capacity": 2},
        {"capacity": 13}, {"min_participants": 1}, {"min_participants": 7}, {"extra": 1}, {"opens_at": "8:00"},
    ],
)
def test_create_room_validation(client, admin_h, world, patch):
    body = {"branch_id": 1, "code": "G1", "name": "x", "kind": "group", "capacity": 6, "min_participants": 2, "opens_at": "08:00", "closes_at": "20:00"}
    body.update(patch)
    err(client.post(f"{API}/rooms", headers=admin_h, json=body), 422, "VALIDATION_ERROR")


def test_create_group_room_requires_capacity(client, admin_h, world):
    body = {"branch_id": 1, "code": "G1", "name": "x", "kind": "group", "opens_at": "08:00", "closes_at": "20:00"}
    err(client.post(f"{API}/rooms", headers=admin_h, json=body), 422, "VALIDATION_ERROR")


def test_create_room_conflicts_and_branches(client, admin_h, world):
    mk_room(client, admin_h)
    e = err(client.post(f"{API}/rooms", headers=admin_h, json={"branch_id": 1, "code": "r1", "name": "x", "kind": "individual", "opens_at": "08:00", "closes_at": "09:00"}), 409, "CONFLICT")
    assert e["details"]["field"] == "code"
    mk_branch(client, admin_h, "B2")
    assert mk_room(client, admin_h, branch_id=2)["id"] == 2
    e = err(client.post(f"{API}/rooms", headers=admin_h, json={"branch_id": 99, "code": "R9", "name": "x", "kind": "individual", "opens_at": "08:00", "closes_at": "09:00"}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "branch_id", "id": 99}
    mk_branch(client, admin_h, "B3")
    assert client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False}).status_code == 200
    err(client.post(f"{API}/rooms", headers=admin_h, json={"branch_id": 3, "code": "R9", "name": "x", "kind": "individual", "opens_at": "08:00", "closes_at": "09:00"}), 409, "BRANCH_INACTIVE")


def test_room_permissions(client, admin_h, world):
    body = {"branch_id": 1, "code": "R1", "name": "x", "kind": "individual", "opens_at": "08:00", "closes_at": "09:00"}
    err(client.post(f"{API}/rooms", json=body), 401, "UNAUTHENTICATED")
    err(client.post(f"{API}/rooms", headers=world["lh"], json=body), 403, "FORBIDDEN")
    err(client.post(f"{API}/rooms", headers=world["mh"], json=body), 403, "FORBIDDEN")
    mk_room(client, admin_h)
    err(client.patch(f"{API}/rooms/1", headers=world["lh"], json={"name": "y"}), 403, "FORBIDDEN")
    assert client.get(f"{API}/rooms", headers=world["mh"]).status_code == 200
    assert client.get(f"{API}/rooms/1", headers=world["mh"]).status_code == 200
    err(client.get(f"{API}/rooms/7", headers=world["mh"]), 404, "NOT_FOUND")


def test_list_rooms_filters(client, admin_h, world):
    mk_branch(client, admin_h, "B2")
    mk_room(client, admin_h, "R2")
    mk_room(client, admin_h, "R1")
    mk_room(client, admin_h, "G1", kind="group", features=["projector", "whiteboard"])
    mk_room(client, admin_h, "G2", branch_id=2, kind="group", capacity=10, min_participants=2, features=["projector"])
    r = client.get(f"{API}/rooms", headers=world["mh"]).json()
    assert [x["code"] for x in r["items"]] == ["G1", "R1", "R2", "G2"] and r["total"] == 4
    codes = lambda q: [x["code"] for x in client.get(f"{API}/rooms?{q}", headers=world["mh"]).json()["items"]]  # noqa: E731
    assert codes("branch_id=2") == ["G2"]
    assert codes("kind=individual") == ["R1", "R2"]
    assert codes("min_capacity=8") == ["G2"]
    assert codes("feature=projector&feature=whiteboard") == ["G1"]
    assert codes("feature=projector") == ["G1", "G2"]
    assert codes("is_active=false") == []


def test_update_room(client, admin_h, world, app):
    mk_room(client, admin_h, "G1", kind="group")
    r = client.patch(f"{API}/rooms/1", headers=admin_h, json={"name": "New", "capacity": 10, "features": ["accessible", "projector"], "closes_at": "21:00"})
    assert r.status_code == 200
    j = r.json()
    assert j["name"] == "New" and j["capacity"] == 10 and j["features"] == ["projector", "accessible"] and j["closes_at"] == "21:00"
    assert "room_updated" in [a.event for a in audit(app)]
    err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"kind": "individual"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"branch_id": 2}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"min_participants": 11}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"opens_at": "21:30"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"name": None}), 422, "VALIDATION_ERROR")


def test_update_room_conflicting_bookings(client, admin_h, world):
    mk_room(client, admin_h, "G1", kind="group")
    b1 = book(client, world["lh"], member_id=1, participant_ids=[2, 3], start_time="09:00", end_time="10:00")
    b2 = book(client, world["lh"], member_id=1, participant_ids=[2], start_time="17:00", end_time="18:00", date="2026-11-04")
    e = err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"opens_at": "09:30"}), 409, "ROOM_HAS_BOOKINGS")
    assert e["details"]["booking_ids"] == [b1["id"]]
    e = err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"closes_at": "17:30", "opens_at": "09:30"}), 409, "ROOM_HAS_BOOKINGS")
    assert e["details"]["booking_ids"] == [b1["id"], b2["id"]]
    e = err(client.patch(f"{API}/rooms/1", headers=admin_h, json={"capacity": 3, "min_participants": 3}), 409, "ROOM_HAS_BOOKINGS")
    assert e["details"]["booking_ids"] == [b2["id"]]
    assert client.get(f"{API}/room-bookings/{b1['id']}", headers=world["lh"]).json()["status"] == "booked"


def test_deactivate_room_cancels_future_bookings(client, admin_h, world, app, clock):
    mk_room(client, admin_h, "G1", kind="group")
    b1 = book(client, world["lh"], member_id=1, participant_ids=[2], start_time="10:00", end_time="11:00")
    b2 = book(client, world["lh"], member_id=1, participant_ids=[2], start_time="09:00", end_time="10:00", date="2026-11-04")
    r = client.patch(f"{API}/rooms/1", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    for b in (b1, b2):
        got = client.get(f"{API}/room-bookings/{b['id']}", headers=world["lh"]).json()
        assert got["status"] == "cancelled" and got["cancel_reason"] == "room_closed" and got["late_cancellation"] is False
        assert got["closed_at"] == "2026-11-02T09:30:00+03:00"
    notes = sel(app, sa.select(Notification).where(Notification.type == "room_booking_cancelled"))
    assert sorted((n.member_id, n.room_booking_id) for n in notes) == [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert "G1" in notes[0].message and "2026-11-03" in notes[0].message and "10:00" in notes[0].message
    e = err(client.post(f"{API}/room-bookings", headers=world["lh"], json={"room_id": 1, "member_id": 1, "date": "2026-11-05", "start_time": "10:00", "end_time": "11:00", "participant_ids": [2]}), 409, "ROOM_INACTIVE")
    assert client.get(f"{API}/rooms/free?date=2026-11-05&start_time=10:00&end_time=11:00", headers=world["mh"]).json()["items"] == []


def test_availability_and_free(client, admin_h, world, clock):
    mk_room(client, admin_h, "R1", opens_at="09:00", closes_at="11:00")
    mk_room(client, admin_h, "R2")
    b = book(client, world["lh"], member_id=1, start_time="09:30", end_time="10:30")
    r = client.get(f"{API}/rooms/1/availability?date=2026-11-03", headers=world["lh"]).json()
    assert r["open"] is True
    assert r["slots"] == [
        {"start": "09:00", "end": "09:30", "free": True, "booking_id": None},
        {"start": "09:30", "end": "10:00", "free": False, "booking_id": b["id"]},
        {"start": "10:00", "end": "10:30", "free": False, "booking_id": b["id"]},
        {"start": "10:30", "end": "11:00", "free": True, "booking_id": None},
    ]
    other = client.get(f"{API}/rooms/1/availability?date=2026-11-03", headers=member_token(client, "b@example.com")).json()
    assert [s["booking_id"] for s in other["slots"]] == [None] * 4 and [s["free"] for s in other["slots"]] == [True, False, False, True]
    own = client.get(f"{API}/rooms/1/availability?date=2026-11-03", headers=world["mh"]).json()
    assert own["slots"][1]["booking_id"] == b["id"]
    sat = client.get(f"{API}/rooms/1/availability?date=2026-11-07", headers=world["mh"]).json()
    assert sat == {"room_id": 1, "date": "2026-11-07", "open": False, "slots": []}
    err(client.get(f"{API}/rooms/1/availability", headers=world["mh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/rooms/1/availability?date=x", headers=world["mh"]), 422, "VALIDATION_ERROR")
    free = lambda q: [x["code"] for x in client.get(f"{API}/rooms/free?{q}", headers=world["mh"]).json()["items"]]  # noqa: E731
    assert free("date=2026-11-03&start_time=09:00&end_time=09:30") == ["R1", "R2"]
    assert free("date=2026-11-03&start_time=09:00&end_time=10:00") == ["R2"]
    assert free("date=2026-11-03&start_time=10:30&end_time=11:30") == ["R2"]
    assert free("date=2026-11-03&start_time=10:30&end_time=11:00") == ["R1", "R2"]
    assert free("date=2026-11-07&start_time=10:00&end_time=11:00") == []
    err(client.get(f"{API}/rooms/free?date=2026-11-03&start_time=10:15&end_time=11:00", headers=world["mh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/rooms/free?date=2026-11-03&start_time=11:00&end_time=10:00", headers=world["mh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/rooms/free?date=2026-11-03", headers=world["mh"]), 422, "VALIDATION_ERROR")


# --- booking ---------------------------------------------------------------------------------


def test_create_booking_by_member(client, admin_h, world, app):
    mk_room(client, admin_h)
    b = book(client, world["mh"], purpose="study")
    assert b == {
        "id": 1, "room_id": 1, "member_id": 1, "participant_ids": [], "date": "2026-11-03", "start_time": "10:00",
        "end_time": "11:00", "status": "booked", "purpose": "study", "created_at": "2026-11-02T09:30:00+03:00",
        "created_by": 3, "checked_in_at": None, "closed_at": None, "cancel_reason": None, "late_cancellation": False,
        "room_code": "R1", "branch_id": 1, "duration_minutes": 60,
    }
    assert [a.entity_id for a in audit(app, "room_booking_created")] == [1]
    assert client.get(f"{API}/room-bookings/1", headers=world["mh"]).json() == b


def test_create_booking_validation(client, admin_h, world):
    mk_room(client, admin_h, "G1", kind="group")
    mh, lh = world["mh"], world["lh"]
    bad = [
        {"start_time": "10:15"}, {"end_time": "11:10"}, {"start_time": "11:00", "end_time": "10:00"},
        {"start_time": "10:00", "end_time": "10:00"}, {"start_time": "10:00", "end_time": "14:30"},
        {"participant_ids": [2, 2]}, {"participant_ids": list(range(2, 14))}, {"purpose": "x" * 201},
        {"date": "03.11.2026"}, {"member_id": 1}, {"extra": 1},
    ]
    for patch in bad:
        err(client.post(f"{API}/room-bookings", headers=mh, json={"room_id": 1, "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00", **patch}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 1, "participant_ids": [1], "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/room-bookings", headers=mh, json={"room_id": 1, "participant_ids": [1], "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 422, "VALIDATION_ERROR")
    e = err(client.post(f"{API}/room-bookings", headers=mh, json={"room_id": 9, "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "room_id", "id": 9}
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 77, "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 404, "NOT_FOUND")
    assert e["details"]["field"] == "member_id"
    e = err(client.post(f"{API}/room-bookings", headers=mh, json={"room_id": 1, "participant_ids": [88], "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 404, "NOT_FOUND")
    assert e["details"]["id"] == 88
    err(client.post(f"{API}/room-bookings", json={}), 401, "UNAUTHENTICATED")


def test_booking_check_order(client, admin_h, world, app, clock):
    mk_room(client, admin_h, "R1", opens_at="09:00", closes_at="18:00")
    mk_room(client, admin_h, "G1", kind="group")
    lh = world["lh"]
    reg(client, admin_h, email="d@example.com", university_id="20230004")
    reg(client, admin_h, email="e@example.com", university_id="20230005")
    reg(client, admin_h, email="f@example.com", university_id="20230006")
    reg(client, admin_h, email="g@example.com", university_id="20230007")

    def attempt(code, **kw):
        body = {"room_id": 1, "member_id": 1, "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}
        body.update(kw)
        return err(client.post(f"{API}/room-bookings", headers=lh, json=body), 409, code)

    attempt("ROOM_CLOSED", date="2026-11-07")
    attempt("ROOM_CLOSED", date="2026-11-08", start_time="07:00")
    attempt("OUTSIDE_ROOM_HOURS", start_time="08:30", end_time="09:30")
    attempt("OUTSIDE_ROOM_HOURS", start_time="17:30", end_time="18:30")
    attempt("BOOKING_IN_PAST", date="2026-11-02", start_time="09:30", end_time="10:30")
    attempt("BOOKING_IN_PAST", date="2026-11-02", start_time="09:00", end_time="10:00")
    ok = book(client, lh, member_id=1, date="2026-11-02", start_time="10:00", end_time="10:30")
    assert ok["status"] == "booked"
    e = attempt("BOOKING_TOO_FAR_AHEAD", date="2026-11-10")
    assert e["details"]["latest_date"] == "2026-11-09"
    book(client, lh, member_id=2, date="2026-11-09")
    # participants
    attempt("PARTICIPANTS_NOT_ALLOWED", participant_ids=[2])
    attempt("NOT_ENOUGH_PARTICIPANTS", room_id=2, start_time="12:00", end_time="13:00")
    # ROOM_CAPACITY_EXCEEDED: capacity 6 -> 7 persons
    e = attempt("ROOM_CAPACITY_EXCEEDED", room_id=2, participant_ids=[2, 3, 4, 5, 6, 7])
    assert e["details"]["capacity"] == 6


def test_participant_rules(client, admin_h, world, app):
    mk_room(client, admin_h, "G1", kind="group", capacity=4, min_participants=3)
    lh = world["lh"]
    g = client.post(f"{API}/members", headers=admin_h, json=guest_body()).json()
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 1, "participant_ids": [2], "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 409, "NOT_ENOUGH_PARTICIPANTS")
    assert e["details"]["min_participants"] == 3
    body = {"room_id": 1, "member_id": 1, "participant_ids": [2, g["id"]], "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}
    e = err(client.post(f"{API}/room-bookings", headers=lh, json=body), 409, "PARTICIPANT_NOT_ELIGIBLE")
    assert e["details"] == {"member_id": g["id"], "reason": "ROOM_NOT_ALLOWED_FOR_TYPE"}
    # passive participant
    client.post(f"{API}/members/3/deactivate", headers=lh)
    body["participant_ids"] = [2, 3]
    e = err(client.post(f"{API}/room-bookings", headers=lh, json=body), 409, "PARTICIPANT_NOT_ELIGIBLE")
    assert e["details"] == {"member_id": 3, "reason": "MEMBER_PASSIVE"}
    client.post(f"{API}/members/3/activate", headers=lh)
    ok = client.post(f"{API}/room-bookings", headers=lh, json=body)
    assert ok.status_code == 201 and ok.json()["participant_ids"] == [2, 3]
    notes = sel(app, sa.select(Notification).where(Notification.type == "room_participant_added").order_by(Notification.id))
    assert [n.member_id for n in notes] == [2, 3]


def test_organizer_checks(client, admin_h, world, app, clock):
    mk_room(client, admin_h)
    lh = world["lh"]
    g = client.post(f"{API}/members", headers=admin_h, json=guest_body()).json()
    body = {"room_id": 1, "member_id": g["id"], "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}
    err(client.post(f"{API}/room-bookings", headers=lh, json=body), 409, "ROOM_NOT_ALLOWED_FOR_TYPE")
    client.post(f"{API}/members/3/deactivate", headers=lh)
    err(client.post(f"{API}/room-bookings", headers=lh, json={**body, "member_id": 3}), 409, "MEMBER_PASSIVE")
    # membership expires before the booking date
    clock.set(at(2, "09:30") + datetime.timedelta(days=364))
    lh = h(token_of(client, "lib@example.com", "Passw0rd1"))
    err(client.post(f"{API}/room-bookings", headers=lh, json={**body, "member_id": 1, "date": "2027-11-04"}), 409, "MEMBERSHIP_EXPIRED")


def test_debt_blocks_booking(client, admin_h, world, app):
    mk_room(client, admin_h)
    with app.state.session_factory.begin() as s:
        from lms.core.money import quantize

        s.add(Fee(member_id=1, kind="lost_book", amount=quantize("50.00"), paid_amount=quantize("0"), status="open", created_on=datetime.date(2026, 11, 2)))
    e = err(client.post(f"{API}/room-bookings", headers=world["lh"], json={"room_id": 1, "member_id": 1, "date": "2026-11-03", "start_time": "10:00", "end_time": "11:00"}), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"


def test_overlap_and_double_booking(client, admin_h, world):
    mk_room(client, admin_h, "R1")
    mk_room(client, admin_h, "R2")
    lh = world["lh"]
    book(client, lh, member_id=1, start_time="10:00", end_time="11:00")
    book(client, lh, member_id=2, start_time="11:00", end_time="12:00")
    book(client, lh, member_id=2, start_time="09:00", end_time="10:00", room_id=2)
    body = {"room_id": 1, "member_id": 3, "date": "2026-11-03", "start_time": "10:30", "end_time": "11:30"}
    err(client.post(f"{API}/room-bookings", headers=lh, json=body), 409, "ROOM_ALREADY_BOOKED")
    body.update(room_id=2, member_id=1)
    e = err(client.post(f"{API}/room-bookings", headers=lh, json=body), 409, "MEMBER_DOUBLE_BOOKED")
    assert e["details"]["member_id"] == 1
    mk_room(client, admin_h, "G1", kind="group")
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 3, "member_id": 3, "participant_ids": [2, 1], "date": "2026-11-03", "start_time": "10:30", "end_time": "11:30"}), 409, "MEMBER_DOUBLE_BOOKED")
    assert e["details"]["member_id"] == 1


def test_quota_examples(client, admin_h, world):
    mk_room(client, admin_h, "R1")
    mk_room(client, admin_h, "R2")
    lh = world["lh"]
    book(client, lh, member_id=1, start_time="08:00", end_time="09:30")
    book(client, lh, member_id=1, start_time="10:00", end_time="10:30")
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 2, "member_id": 1, "date": "2026-11-03", "start_time": "12:00", "end_time": "13:00"}), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert e["details"] == {"member_id": 1, "limit": "2.0", "used": "3.0"}


def test_daily_quota_used_value(client, admin_h, world):
    mk_room(client, admin_h, "R1")
    lh = world["lh"]
    book(client, lh, member_id=1, start_time="08:00", end_time="09:30")
    book(client, lh, member_id=1, start_time="10:00", end_time="10:30")
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 1, "date": "2026-11-03", "start_time": "12:00", "end_time": "12:30"}), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert e["details"] == {"member_id": 1, "limit": "2.0", "used": "2.5"}


def test_weekly_quota_and_future_limit(client, admin_h, world, clock):
    mk_room(client, admin_h, "R1")
    lh = world["lh"]
    clock.set(at(2, "07:00"))
    book(client, lh, member_id=1, date="2026-11-02", start_time="08:00", end_time="10:00")
    book(client, lh, member_id=1, date="2026-11-03", start_time="08:00", end_time="10:00")
    # future-booking limit of a student is 2
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 1, "date": "2026-11-04", "start_time": "08:00", "end_time": "10:00"}), 409, "ROOM_BOOKING_LIMIT_REACHED")
    assert e["details"] == {"member_id": 1, "limit": 2, "used": 3}
    # member 2: three bookings of 2 hours in one week via a later clock position
    clock.set(at(2, "07:00"))
    book(client, lh, member_id=2, date="2026-11-02", start_time="10:00", end_time="12:00")
    clock.set(at(3, "07:00"))
    # bookings that started count for quota but not for the future limit once they are past
    clock.set(at(4, "07:00"))
    book(client, lh, member_id=2, date="2026-11-04", start_time="10:00", end_time="12:00")
    book(client, lh, member_id=2, date="2026-11-05", start_time="10:00", end_time="12:00")
    clock.set(at(5, "06:00"))
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 2, "date": "2026-11-06", "start_time": "10:00", "end_time": "12:00"}), 409, "WEEKLY_ROOM_QUOTA_EXCEEDED")
    assert e["details"] == {"member_id": 2, "limit": "6.0", "used": "8.0"}
    nxt = client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 2, "date": "2026-11-09", "start_time": "10:00", "end_time": "12:00"})
    assert nxt.status_code in (201, 409)
    if nxt.status_code == 409:
        assert nxt.json()["error"]["code"] != "WEEKLY_ROOM_QUOTA_EXCEEDED"


def test_quota_applies_to_participants(client, admin_h, world):
    mk_room(client, admin_h, "G1", kind="group")
    lh = world["lh"]
    book(client, lh, member_id=2, participant_ids=[3], start_time="08:00", end_time="10:00")
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 1, "participant_ids": [3], "date": "2026-11-03", "start_time": "12:00", "end_time": "13:00"}), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert e["details"]["member_id"] == 3 and e["details"]["used"] == "3.0"


def test_booking_lists_and_read_permissions(client, admin_h, world):
    mk_room(client, admin_h, "G1", kind="group")
    lh = world["lh"]
    b1 = book(client, lh, member_id=1, participant_ids=[2], start_time="10:00", end_time="11:00", date="2026-11-04")
    b2 = book(client, lh, member_id=2, participant_ids=[1], start_time="09:00", end_time="10:00")
    m2 = member_token(client, "b@example.com")
    m3 = member_token(client, "c@example.com")
    r = client.get(f"{API}/room-bookings", headers=lh).json()
    assert [x["id"] for x in r["items"]] == [b2["id"], b1["id"]]
    assert [x["id"] for x in client.get(f"{API}/room-bookings?from=2026-11-04", headers=lh).json()["items"]] == [b1["id"]]
    assert [x["id"] for x in client.get(f"{API}/room-bookings?to=2026-11-03&status=booked&room_id=1&branch_id=1&member_id=1", headers=lh).json()["items"]] == [b2["id"]]
    assert client.get(f"{API}/room-bookings?status=done", headers=lh).status_code == 422
    err(client.get(f"{API}/room-bookings", headers=m2), 403, "FORBIDDEN")
    r = client.get(f"{API}/members/2/room-bookings", headers=m2).json()
    assert r["total"] == 2
    err(client.get(f"{API}/members/2/room-bookings", headers=m3), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/9/room-bookings", headers=lh), 404, "NOT_FOUND")
    assert client.get(f"{API}/room-bookings/{b1['id']}", headers=m2).status_code == 200
    err(client.get(f"{API}/room-bookings/{b1['id']}", headers=m3), 403, "FORBIDDEN")
    err(client.get(f"{API}/room-bookings/55", headers=m3), 404, "NOT_FOUND")


def test_patch_booking(client, admin_h, world, app):
    mk_room(client, admin_h, "G1", kind="group")
    lh = world["lh"]
    b = book(client, lh, member_id=1, participant_ids=[2])
    m1, m2 = world["mh"], member_token(client, "b@example.com")
    err(client.patch(f"{API}/room-bookings/1", headers=m2, json={"purpose": "x"}), 403, "FORBIDDEN")
    r = client.patch(f"{API}/room-bookings/1", headers=m1, json={"participant_ids": [3, 2], "purpose": "exam"})
    assert r.status_code == 200 and r.json()["participant_ids"] == [2, 3] and r.json()["purpose"] == "exam"
    notes = sel(app, sa.select(Notification).where(Notification.type == "room_participant_added", Notification.member_id == 3))
    assert len(notes) == 1
    assert len(audit(app, "room_booking_updated")) == 1
    err(client.patch(f"{API}/room-bookings/1", headers=m1, json={"participant_ids": [1]}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/room-bookings/1", headers=m1, json={"participant_ids": []}), 409, "NOT_ENOUGH_PARTICIPANTS")
    err(client.patch(f"{API}/room-bookings/1", headers=m1, json={"participant_ids": [44]}), 404, "NOT_FOUND")
    err(client.patch(f"{API}/room-bookings/1", headers=m1, json={"date": "2026-11-04"}), 422, "VALIDATION_ERROR")
    client.post(f"{API}/room-bookings/1/cancel", headers=m1)
    err(client.patch(f"{API}/room-bookings/1", headers=m1, json={"purpose": "x"}), 409, "BOOKING_NOT_CHANGEABLE")


def test_leave_booking(client, admin_h, world, app):
    mk_room(client, admin_h, "G1", kind="group", capacity=5, min_participants=3)
    lh = world["lh"]
    m4 = reg(client, admin_h, email="d@example.com", university_id="20230004")
    book(client, lh, member_id=1, participant_ids=[2, 3, 4])
    m2, m1 = member_token(client, "b@example.com"), world["mh"]
    err(client.post(f"{API}/room-bookings/1/leave", headers=m1), 403, "FORBIDDEN")
    err(client.post(f"{API}/room-bookings/1/leave", headers=lh), 403, "FORBIDDEN")
    r = client.post(f"{API}/room-bookings/1/leave", headers=m2)
    assert r.status_code == 200 and r.json()["participant_ids"] == [3, 4] and r.json()["status"] == "booked"
    assert len(audit(app, "room_participant_left")) == 1
    err(client.post(f"{API}/room-bookings/1/leave", headers=m2), 403, "FORBIDDEN")
    r = client.post(f"{API}/room-bookings/1/leave", headers=member_token(client, "c@example.com"))
    assert r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "not_enough_participants"
    notes = sel(app, sa.select(Notification).where(Notification.type == "room_booking_cancelled"))
    assert sorted(n.member_id for n in notes) == [1, m4["id"]]
    client.post(f"{API}/room-bookings/1/cancel", headers=m1)


def test_cancel_and_late_cancellation(client, admin_h, world, clock, app):
    mk_room(client, admin_h)
    lh, m1 = world["lh"], world["mh"]
    clock.set(at(3, "07:00"))
    book(client, m1, start_time="14:00", end_time="15:00")
    book(client, lh, member_id=2, start_time="16:00", end_time="17:00")
    clock.set(at(3, "12:00"))
    r = client.post(f"{API}/room-bookings/1/cancel", headers=m1)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "cancelled" and j["cancel_reason"] == "member_request" and j["late_cancellation"] is False
    assert j["closed_at"] == "2026-11-03T12:00:00+03:00"
    err(client.post(f"{API}/room-bookings/1/cancel", headers=m1), 409, "BOOKING_NOT_ACTIVE")
    clock.set(at(3, "14:01"))
    j = client.post(f"{API}/room-bookings/2/cancel", headers=lh).json()
    assert j["cancel_reason"] == "staff_request" and j["late_cancellation"] is False
    assert len(audit(app, "room_booking_cancelled")) == 2
    assert sel(app, sa.select(Notification).where(Notification.type == "room_booking_cancelled")) == []


def test_late_cancellation_boundary(client, admin_h, world, clock):
    mk_room(client, admin_h)
    m1 = world["mh"]
    clock.set(at(3, "07:00"))
    book(client, m1, start_time="14:00", end_time="15:00")
    book(client, m1, start_time="16:00", end_time="17:00")
    clock.set(at(3, "12:01"))
    j = client.post(f"{API}/room-bookings/1/cancel", headers=m1).json()
    assert j["late_cancellation"] is True
    # after start, within the grace period: allowed and late
    clock.set(at(3, "16:10"))
    j = client.post(f"{API}/room-bookings/2/cancel", headers=m1).json()
    assert j["late_cancellation"] is True


def test_cancel_after_grace_and_participant_cancel(client, admin_h, world, clock):
    mk_room(client, admin_h, "G1", kind="group")
    m1, m2 = world["mh"], member_token(client, "b@example.com")
    clock.set(at(3, "07:00"))
    book(client, world["lh"], member_id=1, participant_ids=[2], start_time="10:00", end_time="11:00")
    err(client.post(f"{API}/room-bookings/1/cancel", headers=m2), 403, "FORBIDDEN")
    clock.set(at(3, "10:15"))
    clock.advance(minutes=1)
    err(client.post(f"{API}/room-bookings/1/cancel", headers=m1), 409, "BOOKING_NOT_ACTIVE")
    err(client.post(f"{API}/room-bookings/1/cancel", headers=world["lh"]), 409, "BOOKING_NOT_ACTIVE")


def test_check_in_window(client, admin_h, world, clock):
    mk_room(client, admin_h)
    m1 = world["mh"]
    clock.set(at(3, "07:00"))
    book(client, m1, start_time="10:00", end_time="12:00")
    book(client, world["lh"], member_id=2, start_time="14:00", end_time="15:00")
    clock.set(at(3, "09:49"))
    clock.advance(minutes=0)
    e = err(client.post(f"{API}/room-bookings/1/check-in", headers=m1), 409, "CHECK_IN_TOO_EARLY")
    assert e["details"]["earliest"] == "2026-11-03T09:50:00+03:00"
    err(client.post(f"{API}/room-bookings/1/check-in", headers=member_token(client, "b@example.com")), 403, "FORBIDDEN")
    clock.set(at(3, "09:50"))
    r = client.post(f"{API}/room-bookings/1/check-in", headers=m1)
    assert r.status_code == 200 and r.json()["status"] == "checked_in" and r.json()["checked_in_at"] == "2026-11-03T09:50:00+03:00"
    err(client.post(f"{API}/room-bookings/1/check-in", headers=m1), 409, "BOOKING_NOT_ACTIVE")
    clock.set(at(3, "14:15"))
    assert client.post(f"{API}/room-bookings/2/check-in", headers=world["lh"]).status_code == 200


def test_check_in_too_late(client, admin_h, world, clock):
    mk_room(client, admin_h)
    clock.set(at(3, "07:00"))
    book(client, world["mh"], start_time="10:00", end_time="12:00")
    clock.set(at(3, "10:15"))
    clock.advance(minutes=1)
    err(client.post(f"{API}/room-bookings/1/check-in", headers=world["mh"]), 409, "CHECK_IN_TOO_LATE")


def test_check_out_rounding(client, admin_h, world, clock, app):
    mk_room(client, admin_h)
    m1 = world["mh"]
    clock.set(at(3, "07:00"))
    book(client, m1, start_time="10:00", end_time="12:00")
    clock.set(at(3, "10:00"))
    client.post(f"{API}/room-bookings/1/check-in", headers=m1)
    clock.set(at(3, "10:41"))
    r = client.post(f"{API}/room-bookings/1/check-out", headers=m1)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "completed" and j["end_time"] == "11:00" and j["duration_minutes"] == 60
    assert j["closed_at"] == "2026-11-03T10:41:00+03:00"
    # slots 11:00-12:00 are free again
    av = client.get(f"{API}/rooms/1/availability?date=2026-11-03", headers=m1).json()
    assert [s["free"] for s in av["slots"] if "11:00" <= s["start"] < "12:00"] == [True, True]
    err(client.post(f"{API}/room-bookings/1/check-out", headers=m1), 409, "BOOKING_NOT_ACTIVE")
    assert len(audit(app, "room_checked_out")) == 1


def test_check_out_minimum_and_maximum(client, admin_h, world, clock):
    mk_room(client, admin_h)
    m1, lh = world["mh"], world["lh"]
    clock.set(at(3, "07:00"))
    book(client, m1, start_time="10:00", end_time="12:00")
    book(client, lh, member_id=2, start_time="13:00", end_time="14:00")
    clock.set(at(3, "09:55"))
    client.post(f"{API}/room-bookings/1/check-in", headers=m1)
    clock.set(at(3, "10:05"))
    assert client.post(f"{API}/room-bookings/1/check-out", headers=m1).json()["end_time"] == "10:30"
    clock.set(at(3, "13:00"))
    client.post(f"{API}/room-bookings/2/check-in", headers=lh)
    clock.set(at(3, "16:00"))
    assert client.post(f"{API}/room-bookings/2/check-out", headers=lh).json()["end_time"] == "14:00"
    err(client.post(f"{API}/room-bookings/2/check-out", headers=world["mh"]), 403, "FORBIDDEN")


def test_process_no_show_fee_and_completion(client, admin_h, world, clock, app):
    mk_room(client, admin_h)
    mk_room(client, admin_h, "R2")
    lh, m1 = world["lh"], world["mh"]
    clock.set(at(3, "07:00"))
    book(client, m1, start_time="10:00", end_time="11:00")
    book(client, lh, member_id=2, start_time="10:00", end_time="11:00", room_id=2)
    clock.set(at(3, "09:59"))
    client.post(f"{API}/room-bookings/2/check-in", headers=lh)
    clock.set(at(3, "10:15"))
    assert client.post(f"{API}/room-bookings/process", headers=lh).json() == {"no_shows": 0, "completed": 0, "bans": 0}
    clock.set(at(3, "10:16"))
    assert client.post(f"{API}/room-bookings/process", headers=lh).json() == {"no_shows": 1, "completed": 0, "bans": 0}
    j = client.get(f"{API}/room-bookings/1", headers=lh).json()
    assert j["status"] == "no_show" and j["closed_at"] == "2026-11-03T10:16:00+03:00"
    fees = sel(app, sa.select(Fee))
    assert len(fees) == 1 and fees[0].kind == "no_show_fee" and str(fees[0].amount) == "10.00"
    assert fees[0].member_id == 1 and fees[0].room_booking_id == 1 and fees[0].loan_id is None
    fl = client.get(f"{API}/members/1/fees", headers=m1).json()["items"]
    assert fl[0]["kind"] == "no_show_fee" and fl[0]["room_booking_id"] == 1 and fl[0]["amount"] == "10.00"
    assert client.get(f"{API}/members/1/balance", headers=m1).json()["total_debt"] == "10.00"
    types = sorted(n.type for n in sel(app, sa.select(Notification).where(Notification.member_id == 1)))
    assert types == ["fee_created", "room_no_show"]
    clock.set(at(3, "11:00"))
    assert client.post(f"{API}/room-bookings/process", headers=lh).json() == {"no_shows": 0, "completed": 1, "bans": 0}
    assert client.get(f"{API}/room-bookings/2", headers=lh).json()["status"] == "completed"
    assert client.post(f"{API}/room-bookings/process", headers=lh).json() == {"no_shows": 0, "completed": 0, "bans": 0}
    assert [a.details for a in audit(app, "room_bookings_processed")] == [
        {"no_shows": 0, "completed": 0, "bans": 0},
        {"no_shows": 1, "completed": 0, "bans": 0},
        {"no_shows": 0, "completed": 1, "bans": 0},
        {"no_shows": 0, "completed": 0, "bans": 0},
    ]
    err(client.post(f"{API}/room-bookings/process", headers=m1), 403, "FORBIDDEN")


def test_unprocessed_no_show_is_not_active(client, admin_h, world, clock):
    mk_room(client, admin_h)
    lh = world["lh"]
    clock.set(at(3, "07:00"))
    book(client, lh, member_id=1, start_time="10:00", end_time="11:00")
    clock.set(at(3, "10:16"))
    book(client, lh, member_id=2, start_time="10:30", end_time="11:30")
    assert client.get(f"{API}/room-bookings/1", headers=lh).json()["status"] == "booked"
    # the member of the unprocessed no-show can book elsewhere in time without MEMBER_DOUBLE_BOOKED
    mk_room(client, admin_h, "R2")
    book(client, lh, member_id=1, start_time="10:30", end_time="11:00", room_id=2)
    err(client.post(f"{API}/room-bookings/1/check-in", headers=lh), 409, "CHECK_IN_TOO_LATE")


def test_automatic_ban_after_three_incidents(client, admin_h, world, clock, app):
    mk_room(client, admin_h)
    lh, m1 = world["lh"], world["mh"]
    for day in (3, 4):
        clock.set(at(2, "07:00"))
        book(client, lh, member_id=1, date=f"2026-11-0{day}", start_time="10:00", end_time="11:00")
    clock.set(at(5, "07:00"))
    clock.set(at(5, "12:00"))
    assert client.post(f"{API}/room-bookings/process", headers=lh).json()["no_shows"] == 2
    # third incident: a late cancellation of a booking dated this week
    clock.set(at(5, "07:00"))
    book(client, lh, member_id=1, date="2026-11-06", start_time="10:00", end_time="11:00")
    clock.set(at(5, "07:00"))
    b3 = client.get(f"{API}/room-bookings?status=booked", headers=lh).json()["items"][0]
    clock.set(at(6, "08:30"))
    j = client.post(f"{API}/room-bookings/{b3['id']}/cancel", headers=m1).json()
    assert j["late_cancellation"] is True
    bans = sel(app, sa.select(RoomBan))
    assert len(bans) == 1
    ban = bans[0]
    assert ban.reason == "no_shows" and ban.created_by is None
    assert (ban.starts_on, ban.ends_on) == (datetime.date(2026, 11, 6), datetime.date(2026, 11, 19))
    lst = client.get(f"{API}/members/1/room-bans", headers=m1).json()
    assert lst["items"][0]["in_force"] is True and lst["items"][0]["reason"] == "no_shows"
    notes = sel(app, sa.select(Notification).where(Notification.type == "room_ban_started"))
    assert len(notes) == 1 and "2026-11-06" in notes[0].message and "2026-11-19" in notes[0].message
    assert len(audit(app, "room_ban_started")) == 1
    summary = client.get(f"{API}/members/1/summary", headers=m1).json()
    assert summary["rooms"]["banned_until"] == "2026-11-19"
    e = err(client.post(f"{API}/room-bookings", headers=lh, json={"room_id": 1, "member_id": 1, "date": "2026-11-09", "start_time": "10:00", "end_time": "11:00"}), 409, "MEMBER_BANNED_FROM_ROOMS")
    assert e["details"]["ends_on"] == "2026-11-19"


def test_ban_cancels_bookings_and_removes_from_groups(client, admin_h, world, clock, app):
    mk_room(client, admin_h, "G1", kind="group", capacity=5, min_participants=2)
    mk_room(client, admin_h, "R1")
    lh = world["lh"]
    book(client, lh, member_id=1, room_id=2, date="2026-11-04")
    book(client, lh, member_id=2, participant_ids=[1, 3], date="2026-11-05")
    book(client, lh, member_id=3, participant_ids=[1], date="2026-11-06", start_time="12:00", end_time="13:00")
    book(client, lh, member_id=1, room_id=2, date="2026-11-09", start_time="12:00", end_time="13:00")
    r = client.post(f"{API}/members/1/room-bans", headers=admin_h, json={"starts_on": "2026-11-03", "ends_on": "2026-11-06", "note": " strike "})
    assert r.status_code == 201
    j = r.json()
    assert j["reason"] == "staff" and j["note"] == "strike" and j["created_by"] == 1 and j["in_force"] is False and j["lifted_at"] is None
    got = lambda i: client.get(f"{API}/room-bookings/{i}", headers=lh).json()  # noqa: E731
    assert got(1)["status"] == "cancelled" and got(1)["cancel_reason"] == "member_banned"
    assert got(2)["participant_ids"] == [3] and got(2)["status"] == "booked"
    assert got(3)["status"] == "cancelled" and got(3)["cancel_reason"] == "not_enough_participants"
    assert got(4)["status"] == "booked"
    assert len(audit(app, "room_ban_started")) == 1


def test_ban_validation_and_lift(client, admin_h, world, clock, app):
    mk_room(client, admin_h)
    lh = world["lh"]
    body = {"starts_on": "2026-11-02", "ends_on": "2026-11-03"}
    err(client.post(f"{API}/members/1/room-bans", headers=lh, json=body), 403, "FORBIDDEN")
    err(client.post(f"{API}/members/1/room-bans", headers=world["mh"], json=body), 403, "FORBIDDEN")
    err(client.post(f"{API}/members/1/room-bans", headers=admin_h, json={"starts_on": "2026-11-01", "ends_on": "2026-11-03"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/members/1/room-bans", headers=admin_h, json={"starts_on": "2026-11-03", "ends_on": "2026-11-02"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/members/1/room-bans", headers=admin_h, json={"starts_on": "2026-11-03", "ends_on": "2026-11-04", "note": "x" * 501}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/members/9/room-bans", headers=admin_h, json=body), 404, "NOT_FOUND")
    ban = client.post(f"{API}/members/1/room-bans", headers=admin_h, json=body).json()
    assert ban["in_force"] is True
    client.post(f"{API}/members/1/room-bans", headers=admin_h, json={"starts_on": "2026-11-02", "ends_on": "2026-11-10"})
    err(client.post(f"{API}/room-bans/{ban['id']}/lift", headers=lh), 403, "FORBIDDEN")
    j = client.post(f"{API}/room-bans/{ban['id']}/lift", headers=admin_h).json()
    assert j["lifted_by"] == 1 and j["lifted_at"] == "2026-11-02T09:30:00+03:00" and j["in_force"] is False
    err(client.post(f"{API}/room-bans/{ban['id']}/lift", headers=admin_h), 409, "BAN_NOT_ACTIVE")
    err(client.post(f"{API}/room-bans/99/lift", headers=admin_h), 404, "NOT_FOUND")
    clock.set(at(12, "09:00"))
    admin_h = h(token_of(client))
    err(client.post(f"{API}/room-bans/2/lift", headers=admin_h), 409, "BAN_NOT_ACTIVE")
    mh = member_token(client, "ayse@example.edu.tr")
    assert [x["id"] for x in client.get(f"{API}/members/1/room-bans", headers=mh).json()["items"]] == [2, 1]
    err(client.get(f"{API}/members/1/room-bans", headers=member_token(client, "b@example.com")), 403, "FORBIDDEN")
    assert len(audit(app, "room_ban_lifted")) == 1


def test_incidents_do_not_count_again_after_ban(client, admin_h, world, clock, app):
    mk_room(client, admin_h)
    lh = world["lh"]
    clock.set(at(2, "07:00"))
    book(client, lh, member_id=1, date="2026-11-03", start_time="10:00", end_time="11:00")
    book(client, lh, member_id=1, date="2026-11-04", start_time="10:00", end_time="11:00")
    clock.set(at(4, "12:00"))
    assert client.post(f"{API}/room-bookings/process", headers=lh).json() == {"no_shows": 2, "completed": 0, "bans": 0}
    book(client, lh, member_id=1, date="2026-11-05", start_time="10:00", end_time="11:00")
    book(client, lh, member_id=1, date="2026-11-06", start_time="10:00", end_time="11:00")
    clock.set(at(6, "12:00"))
    # the third no-show starts a ban; the fourth is processed afterwards and does not count again
    assert client.post(f"{API}/room-bookings/process", headers=lh).json() == {"no_shows": 2, "completed": 0, "bans": 1}
    assert len(sel(app, sa.select(RoomBan))) == 1
    assert len(sel(app, sa.select(Fee))) == 4


def test_member_deactivation_effects(client, admin_h, world, clock, app):
    mk_room(client, admin_h, "G1", kind="group", capacity=5, min_participants=2)
    mk_room(client, admin_h, "R1")
    lh = world["lh"]
    book(client, lh, member_id=1, room_id=2)
    book(client, lh, member_id=2, participant_ids=[1, 3], date="2026-11-05")
    book(client, lh, member_id=3, participant_ids=[1], date="2026-11-06", start_time="12:00", end_time="13:00")
    r = client.post(f"{API}/members/1/deactivate", headers=lh)
    assert r.status_code == 200
    got = lambda i: client.get(f"{API}/room-bookings/{i}", headers=lh).json()  # noqa: E731
    assert got(1)["cancel_reason"] == "member_deactivated"
    assert got(2)["participant_ids"] == [3] and got(2)["status"] == "booked"
    assert got(3)["cancel_reason"] == "not_enough_participants"
    notes = sel(app, sa.select(Notification).where(Notification.type == "room_booking_cancelled"))
    assert sorted(n.member_id for n in notes) == [1, 3]


def test_member_in_room_blocks_deactivation(client, admin_h, world, clock):
    mk_room(client, admin_h, "G1", kind="group")
    lh = world["lh"]
    clock.set(at(3, "07:00"))
    book(client, lh, member_id=1, participant_ids=[2], start_time="10:00", end_time="11:00")
    clock.set(at(3, "10:00"))
    client.post(f"{API}/room-bookings/1/check-in", headers=lh)
    err(client.post(f"{API}/members/2/deactivate", headers=lh), 409, "MEMBER_IN_ROOM")
    err(client.post(f"{API}/members/1/deactivate", headers=lh), 409, "MEMBER_IN_ROOM")
    assert client.post(f"{API}/members/3/deactivate", headers=lh).status_code == 200


def test_type_change_to_guest(client, admin_h, world):
    mk_room(client, admin_h, "G1", kind="group")
    lh = world["lh"]
    book(client, lh, member_id=1, participant_ids=[2])
    book(client, lh, member_id=2, participant_ids=[3], date="2026-11-04")
    r = client.patch(f"{API}/members/1", headers=lh, json={"membership_type": "guest", "phone": "+90 532 123 45 67"})
    assert r.status_code == 200
    got = lambda i: client.get(f"{API}/room-bookings/{i}", headers=lh).json()  # noqa: E731
    assert got(1)["status"] == "cancelled" and got(1)["cancel_reason"] == "staff_request"
    assert got(2)["status"] == "booked"
    # student -> academic does not touch bookings
    client.patch(f"{API}/members/2", headers=lh, json={"membership_type": "academic"})
    assert got(2)["status"] == "booked"


def test_branch_in_use_by_room(client, admin_h, world):
    mk_branch(client, admin_h, "B2")
    mk_room(client, admin_h, "R1", branch_id=2)
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.patch(f"{API}/rooms/1", headers=admin_h, json={"is_active": False})
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200


def test_branch_in_use_by_room_booking(client, admin_h, world, clock):
    mk_branch(client, admin_h, "B2")
    mk_room(client, admin_h, "R1", branch_id=2)
    clock.set(at(3, "07:00"))
    book(client, world["lh"], member_id=1, start_time="10:00", end_time="11:00")
    client.patch(f"{API}/rooms/1", headers=admin_h, json={"is_active": False})
    # cancelled by room closure: no active booking is left
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200


def test_member_summary_rooms(client, admin_h, world, clock):
    mk_room(client, admin_h)
    mk_room(client, admin_h, "R2")
    lh, m1 = world["lh"], world["mh"]
    assert client.get(f"{API}/members/1/summary", headers=m1).json()["rooms"] == {"upcoming_bookings": 0, "banned_until": None, "hours_this_week": "0.0"}
    book(client, lh, member_id=1, start_time="10:00", end_time="11:30")
    book(client, lh, member_id=1, start_time="09:00", end_time="09:30", date="2026-11-09", room_id=2)
    j = client.get(f"{API}/members/1/summary", headers=m1).json()
    assert j["rooms"] == {"upcoming_bookings": 2, "banned_until": None, "hours_this_week": "1.5"}
    assert "borrowing" in j and "balance" in j


def test_run_reminders(client, admin_h, world, clock, app):
    mk_room(client, admin_h, "G1", kind="group")
    lh = world["lh"]
    clock.set(at(6, "10:00"))
    book(client, lh, member_id=1, participant_ids=[2], date="2026-11-09")
    book(client, lh, member_id=3, participant_ids=[2], date="2026-11-10", start_time="12:00", end_time="13:00")
    err(client.post(f"{API}/room-bookings/run-reminders", headers=world["mh"]), 403, "FORBIDDEN")
    clock.set(at(6, "11:00"))
    r = client.post(f"{API}/room-bookings/run-reminders", headers=lh)
    assert r.status_code == 200 and r.json() == {"room_reminders": 2}
    assert client.post(f"{API}/room-bookings/run-reminders", headers=lh).json() == {"room_reminders": 0}
    notes = sel(app, sa.select(Notification).where(Notification.type == "room_reminder"))
    assert sorted((n.member_id, n.room_booking_id) for n in notes) == [(1, 1), (2, 1)]
    assert client.post(f"{API}/notifications/run-reminders", headers=lh).json() == {"due_reminders": 0, "overdue_notices": 0}
    r = client.get(f"{API}/members/2/notifications?type=room_reminder", headers=member_token(client, "b@example.com")).json()
    assert r["items"][0]["room_booking_id"] == 1
    assert len(audit(app, "room_reminders_run")) == 2


def test_room_usage_report(client, admin_h, world, clock):
    mk_room(client, admin_h, "R1", opens_at="09:00", closes_at="11:00")
    mk_room(client, admin_h, "R2")
    lh = world["lh"]
    clock.set(at(3, "07:00"))
    book(client, lh, member_id=1, start_time="09:00", end_time="10:00")
    book(client, lh, member_id=2, start_time="10:00", end_time="10:30")
    clock.set(at(3, "09:00"))
    client.post(f"{API}/room-bookings/1/check-in", headers=lh)
    clock.set(at(3, "12:00"))
    client.post(f"{API}/room-bookings/process", headers=lh)
    r = client.get(f"{API}/reports/room-usage?from=2026-11-02&to=2026-11-06", headers=lh)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0] == {
        "room_id": 1, "room_code": "R1", "branch_id": 1, "open_hours": "10.0", "booked_hours": "1.5",
        "used_hours": "1.0", "no_shows": 1, "late_cancellations": 0, "utilization": "10.0",
    }
    assert items[1]["room_code"] == "R2" and items[1]["open_hours"] == "60.0" and items[1]["utilization"] == "0.0"
    assert client.get(f"{API}/reports/room-usage?from=2026-11-07&to=2026-11-08&kind=individual", headers=lh).json()["items"][0]["open_hours"] == "0.0"
    err(client.get(f"{API}/reports/room-usage?from=2026-11-07&to=2026-11-06", headers=lh), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/room-usage?from=2026-01-01&to=2027-01-02", headers=lh), 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/reports/room-usage?from=2026-01-01&to=2027-01-01", headers=lh).status_code == 200
    err(client.get(f"{API}/reports/room-usage?from=2026-11-02", headers=lh), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/room-usage?from=2026-11-02&to=2026-11-03", headers=world["mh"]), 403, "FORBIDDEN")


def test_import_rejected_when_rooms_exist(client, admin_h, world):
    mk_room(client, admin_h)
    data = {"format_version": 1, "branches": [], "authors": [], "publishers": [], "books": [], "copies": [], "members": [], "loans": []}
    err(client.post(f"{API}/import", headers=admin_h, json=data), 409, "DATABASE_NOT_EMPTY")
    assert "rooms" not in client.get(f"{API}/export", headers=admin_h).json()
