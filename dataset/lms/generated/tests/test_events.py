"""Module 20: Events (LIB-EVT-01 to LIB-EVT-47).

The clock starts on Mon 2026-11-02 09:30. The default event is on Thu 2026-11-05, 14:00-16:00, and the
responsible staff member (profile 1) has a shift that day from 08:00 to 16:00.
"""

import datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

import lms
from lms.fines.models import Fee
from lms.members.models import Member
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_branches import mk_branch
from tests.test_members import reg
from tests.test_rooms import book, mk_room
from tests.test_staff import mk_shift, mk_staff

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def at(day, hhmm="09:00", month=11):
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime(2026, month, day, hour, minute, tzinfo=TZ)


EVENT = {
    "title": "Poetry night",
    "description": "Evening of poems",
    "kind": "talk",
    "branch_id": 1,
    "date": "2026-11-05",
    "start_time": "14:00",
    "end_time": "16:00",
    "capacity": 2,
    "staff_id": 1,
}


def body_of(**kw):
    """The default event body; a value of ``...`` removes the field."""
    return {k: v for k, v in {**EVENT, **kw}.items() if v is not ...}


def mk_event(client, headers, expect=201, **kw):
    r = client.post(f"{API}/events", headers=headers, json=body_of(**kw))
    assert r.status_code == expect, r.text
    return r.json()


def publish(client, headers, event_id, expect=200):
    r = client.post(f"{API}/events/{event_id}/publish", headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def register(client, headers, event_id, expect=201, **body):
    r = client.post(f"{API}/events/{event_id}/registrations", headers=headers, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def cancel_reg(client, headers, reg_id, expect=200):
    r = client.post(f"{API}/event-registrations/{reg_id}/cancel", headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def get_event(client, headers, event_id):
    r = client.get(f"{API}/events/{event_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def process(client, headers):
    r = client.post(f"{API}/events/process", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def regs_of_event(client, headers, event_id, query=""):
    return client.get(f"{API}/events/{event_id}/registrations{query}", headers=headers).json()["items"]


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


def notifications(app, member_id=None, type_=None):
    stmt = sa.select(Notification).order_by(Notification.id)
    if member_id is not None:
        stmt = stmt.where(Notification.member_id == member_id)
    if type_ is not None:
        stmt = stmt.where(Notification.type == type_)
    return sel(app, stmt)


def shift_on(client, admin_h, day, start="08:00", end="16:00", **kw):
    return mk_shift(client, admin_h, date=day, start=start, end=end, **kw)


@pytest.fixture
def world(client, admin_h):
    mk_branch(client, admin_h)
    mk_staff(client, admin_h, email="lib@example.com")
    lh = h(token_of(client, "lib@example.com", "Passw0rd1"))
    shift_on(client, admin_h, "2026-11-05")
    for i in range(1, 5):
        reg(client, admin_h, email=f"m{i}@example.edu.tr", university_id=f"2023000{i}", full_name=f"Member {i}")
    mh = [h(token_of(client, f"m{i}@example.edu.tr", "Passw0rd1")) for i in range(1, 5)]
    return {"lh": lh, "mh": mh}


# --- create ---------------------------------------------------------------------------------------


def test_create_event(client, admin_h, world, app):
    e = mk_event(client, admin_h)
    assert e["id"] == 1 and e["status"] == "draft" and e["fee"] == "0.00" and e["audience"] == "all"
    assert e["room_id"] is None and e["series_id"] is None and e["cancel_reason"] is None and e["published_at"] is None
    assert (e["registered"], e["waitlisted"], e["free_places"], e["staff_covered"]) == (0, 0, 2, True)
    assert e["start_time"] == "14:00" and e["date"] == "2026-11-05" and e["created_at"] == "2026-11-02T09:30:00+03:00"
    assert [a.entity_id for a in audit(app, "event_created")] == [1]
    e2 = mk_event(client, world["lh"], title="  Tour  ", description=..., fee="12.50", audience="students", kind="tour")
    assert e2["title"] == "Tour" and e2["fee"] == "12.50" and e2["description"] == "" and e2["audience"] == "students"


def test_create_event_permissions(client, admin_h, world):
    err(client.post(f"{API}/events", headers=world["mh"][0], json=body_of()), 403, "FORBIDDEN")
    assert client.post(f"{API}/events", json=body_of()).status_code == 401


@pytest.mark.parametrize(
    "kw",
    [
        {"title": " "},
        {"title": "x" * 201},
        {"description": "x" * 2001},
        {"kind": "party"},
        {"start_time": "14:15"},
        {"end_time": "14:30"},
        {"end_time": "18:30"},
        {"start_time": "16:00", "end_time": "14:00"},
        {"capacity": 0},
        {"capacity": 201},
        {"capacity": "2"},
        {"fee": "200.01"},
        {"fee": 5},
        {"fee": "-1.00"},
        {"fee": "1.234"},
        {"audience": "everyone"},
        {"date": "2026-13-01"},
        {"date": ...},
        {"staff_id": ...},
        {"title": ...},
        {"unknown": 1},
        {"room_id": 99},
        {"staff_id": 99},
    ],
)
def test_create_event_validation(client, admin_h, world, kw):
    e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(**kw)), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"]


def test_event_limits_ok(client, admin_h, world):
    mk_event(client, admin_h, start_time="14:00", end_time="15:00", capacity=1, fee="200.00")
    mk_event(client, admin_h, start_time="10:00", end_time="14:00", capacity=200, date="2026-11-06", fee="0.00")


def test_unknown_branch_is_404(client, admin_h, world):
    e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(branch_id=9)), 404, "NOT_FOUND")
    assert e["details"] == {"field": "branch_id", "id": 9}


def test_room_rules(client, admin_h, world):
    mk_room(client, admin_h, code="G1", kind="group", capacity=6)  # 1
    mk_room(client, admin_h, code="I1")  # 2: individual
    mk_branch(client, admin_h, "B2")
    mk_room(client, admin_h, code="G2", branch_id=2, kind="group", capacity=6)  # 3: other branch
    for room in (2, 3):
        e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(room_id=room)), 422, "VALIDATION_ERROR")
        assert e["details"]["fields"][0]["field"] == "room_id"
    e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(room_id=1, capacity=7)), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "capacity"
    assert mk_event(client, admin_h, room_id=1, capacity=6)["room_id"] == 1


def test_event_checks_in_order(client, admin_h, world):
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(date="2026-11-02", start_time="09:30", end_time="11:00")), 409, "EVENT_IN_PAST")
    mk_event(client, admin_h, date="2026-11-02", start_time="10:00", end_time="12:00")  # starts after now
    e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(date="2026-11-07")), 409, "BRANCH_NOT_OPEN")
    assert e["details"]["reason"] == "weekend"
    client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-17", "reason": "Sayım"})
    e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(date="2026-11-17")), 409, "BRANCH_NOT_OPEN")
    assert e["details"]["reason"] == "closure"
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(start_time="19:00", end_time="21:00")), 409, "OUTSIDE_BRANCH_HOURS")
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(start_time="07:00", end_time="09:00")), 409, "OUTSIDE_BRANCH_HOURS")
    mk_room(client, admin_h, code="G1", kind="group", capacity=6, opens_at="10:00", closes_at="15:00")
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(room_id=1)), 409, "OUTSIDE_BRANCH_HOURS")
    # the order: a past event on a closed day reports the past first
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(date="2026-11-01")), 409, "EVENT_IN_PAST")


def test_room_checks(client, admin_h, world, app):
    mk_room(client, admin_h, code="G1", kind="group", capacity=6)
    b = book(client, world["mh"][0], room_id=1, date="2026-11-05", start_time="14:00", end_time="15:00", participant_ids=[2])
    e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(room_id=1, start_time="13:00", end_time="15:00")), 409, "ROOM_NOT_AVAILABLE")
    assert e["details"] == {"booking_id": b["id"]}
    ev = mk_event(client, admin_h, room_id=1, start_time="15:00", end_time="17:00")  # touching is fine
    e = err(client.post(f"{API}/events", headers=admin_h, json=body_of(room_id=1, start_time="16:00", end_time="18:00")), 409, "ROOM_NOT_AVAILABLE")
    assert e["details"] == {"event_id": ev["id"]}
    client.post(f"{API}/events/{ev['id']}/cancel", headers=admin_h)
    mk_event(client, admin_h, room_id=1, start_time="16:00", end_time="18:00")  # cancelled events do not block
    client.patch(f"{API}/rooms/1", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(room_id=1, date="2026-11-06")), 409, "ROOM_INACTIVE")


def test_inactive_branch_and_staff(client, admin_h, world):
    mk_branch(client, admin_h, "B2")
    mk_staff(client, admin_h, email="other@example.com", branch=1)  # staff 2
    assert client.patch(f"{API}/staff/2", headers=admin_h, json={"is_active": False}).status_code == 200
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(staff_id=2)), 409, "STAFF_INACTIVE")
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200
    err(client.post(f"{API}/events", headers=admin_h, json=body_of(branch_id=2)), 409, "BRANCH_INACTIVE")


# --- publish ------------------------------------------------------------------------------------------


def test_publish(client, admin_h, world, app):
    mk_event(client, admin_h)
    p = publish(client, admin_h, 1)
    assert p["status"] == "published" and p["published_at"] == "2026-11-02T09:30:00+03:00"
    assert [a.entity_id for a in audit(app, "event_published")] == [1]
    x = err(client.post(f"{API}/events/1/publish", headers=admin_h), 409, "INVALID_EVENT_STATUS")
    assert x["details"]["status"] == "published"
    err(client.post(f"{API}/events/99/publish", headers=admin_h), 404, "NOT_FOUND")
    err(client.post(f"{API}/events/1/publish", headers=world["mh"][0]), 403, "FORBIDDEN")


def test_publish_needs_a_shift(client, admin_h, world):
    mk_event(client, admin_h, date="2026-11-06")
    e = err(client.post(f"{API}/events/1/publish", headers=admin_h), 409, "STAFF_NOT_ON_SHIFT")
    assert get_event(client, admin_h, 1)["staff_covered"] is False
    shift_on(client, admin_h, "2026-11-06", "09:00", "15:00")  # does not cover 14:00-16:00
    err(client.post(f"{API}/events/1/publish", headers=admin_h), 409, "STAFF_NOT_ON_SHIFT")
    mk_event(client, admin_h, date="2026-11-06", start_time="10:00", end_time="12:00")
    publish(client, admin_h, 2)  # the shift covers 10:00-12:00 (and the first event does not overlap)
    assert e["details"]["staff_id"] == 1


def test_publish_too_soon(client, admin_h, world, clock):
    shift_on(client, admin_h, "2026-11-03")
    mk_event(client, admin_h, date="2026-11-03", start_time="10:00", end_time="12:00")
    clock.set(datetime.datetime(2026, 11, 2, 10, 0, 1, tzinfo=TZ))
    err(client.post(f"{API}/events/1/publish", headers=admin_h), 409, "EVENT_TOO_SOON")
    clock.set(at(2, "10:00"))
    publish(client, admin_h, 1)  # exactly 24 hours


def test_publish_runs_event_checks(client, admin_h, world, clock):
    mk_event(client, admin_h, date="2026-11-02", start_time="10:00", end_time="12:00")
    clock.set(at(2, "10:30"))
    err(client.post(f"{API}/events/1/publish", headers=admin_h), 409, "EVENT_IN_PAST")


def test_staff_covered_follows_shift(client, admin_h, world):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    assert client.post(f"{API}/shifts/1/cancel", headers=admin_h).status_code == 200
    e = get_event(client, admin_h, 1)
    assert e["staff_covered"] is False and e["status"] == "published"


# --- change ---------------------------------------------------------------------------------------------


def test_update_event(client, admin_h, world, app):
    mk_event(client, admin_h)
    r = client.patch(f"{API}/events/1", headers=admin_h, json={"title": "New", "capacity": 5, "fee": "10.00", "description": "d"})
    assert r.status_code == 200 and r.json()["title"] == "New" and r.json()["fee"] == "10.00"
    diff = audit(app, "event_updated")[0].details
    assert diff["title"] == {"old": "Poetry night", "new": "New"} and diff["fee"] == {"old": "0.00", "new": "10.00"}
    for body in (
        {"kind": "tour"}, {"branch_id": 1}, {"audience": "all"}, {"title": None}, {"capacity": 0}, {"start_time": "14:10"},
        {"end_time": "14:30"}, {"room_id": 99}, {"staff_id": 99}, {"fee": "300.00"}, {"series_id": 1}, {"status": "draft"},
    ):
        err(client.patch(f"{API}/events/1", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"date": "2026-11-01"}), 409, "EVENT_IN_PAST")
    err(client.patch(f"{API}/events/9", headers=admin_h, json={"title": "x"}), 404, "NOT_FOUND")
    err(client.patch(f"{API}/events/1", headers=world["mh"][0], json={"title": "x"}), 403, "FORBIDDEN")
    # a draft may move to a day without a shift; a published event may not
    assert client.patch(f"{API}/events/1", headers=admin_h, json={"date": "2026-11-06"}).status_code == 200
    assert client.patch(f"{API}/events/1", headers=admin_h, json={"date": "2026-11-05"}).status_code == 200
    publish(client, admin_h, 1)
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"date": "2026-11-06"}), 409, "STAFF_NOT_ON_SHIFT")
    assert client.patch(f"{API}/events/1", headers=admin_h, json={"start_time": "15:00", "end_time": "16:00"}).status_code == 200
    client.post(f"{API}/events/1/cancel", headers=admin_h)
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"title": "x"}), 409, "INVALID_EVENT_STATUS")


def test_update_checks_apply(client, admin_h, world):
    mk_event(client, admin_h)
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"date": "2026-11-07"}), 409, "BRANCH_NOT_OPEN")
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"end_time": "20:30"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"start_time": "19:30", "end_time": "20:30"}), 409, "OUTSIDE_BRANCH_HOURS")
    mk_staff(client, admin_h, email="o@example.com", branch=1)
    client.patch(f"{API}/staff/2", headers=admin_h, json={"is_active": False})
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"staff_id": 2}), 409, "STAFF_INACTIVE")


def test_update_started_event_rejected(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    clock.set(at(5, "14:00"))
    e = err(client.patch(f"{API}/events/1", headers=admin_h, json={"title": "x"}), 409, "INVALID_EVENT_STATUS")
    assert e["details"]["status"] == "published"
    err(client.post(f"{API}/events/1/cancel", headers=admin_h), 409, "INVALID_EVENT_STATUS")


def test_update_room_conflict_ignores_self(client, admin_h, world):
    mk_room(client, admin_h, code="G1", kind="group", capacity=6)
    mk_event(client, admin_h, room_id=1)
    assert client.patch(f"{API}/events/1", headers=admin_h, json={"start_time": "14:30", "end_time": "16:00"}).status_code == 200
    r = client.patch(f"{API}/events/1", headers=admin_h, json={"room_id": None})
    assert r.status_code == 200 and r.json()["room_id"] is None
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"room_id": 1, "capacity": 7}), 422, "VALIDATION_ERROR")
    mk_event(client, admin_h, room_id=1, start_time="16:00", end_time="17:00")
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"room_id": 1, "end_time": "16:30"}), 409, "ROOM_NOT_AVAILABLE")


def test_fee_locked_and_capacity(client, admin_h, world):
    mk_event(client, admin_h, capacity=3, fee="10.00")
    publish(client, admin_h, 1)
    m1, m2 = world["mh"][0], world["mh"][1]
    register(client, m1, 1)
    register(client, m2, 1)
    err(client.patch(f"{API}/events/1", headers=admin_h, json={"fee": "5.00"}), 409, "FEE_LOCKED")
    assert client.patch(f"{API}/events/1", headers=admin_h, json={"fee": "10.00"}).status_code == 200
    e = err(client.patch(f"{API}/events/1", headers=admin_h, json={"capacity": 1}), 409, "CAPACITY_BELOW_REGISTERED")
    assert e["details"]["registered"] == 2
    assert client.patch(f"{API}/events/1", headers=admin_h, json={"capacity": 2}).status_code == 200
    # the lock holds for a registration of any status
    mk_event(client, admin_h, start_time="08:00", end_time="09:00", capacity=1, fee="3.00")
    publish(client, admin_h, 2)
    r = register(client, m1, 2)
    cancel_reg(client, m1, r["id"])
    err(client.patch(f"{API}/events/2", headers=admin_h, json={"fee": "4.00"}), 409, "FEE_LOCKED")


def test_capacity_increase_promotes(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=2)
    publish(client, admin_h, 1)
    mh = world["mh"]
    for i in range(4):
        register(client, mh[i], 1)
    client.patch(f"{API}/events/1", headers=admin_h, json={"capacity": 3})
    items = regs_of_event(client, admin_h, 1)
    assert [(r["member_id"], r["status"], r["position"]) for r in items] == [
        (1, "registered", None), (2, "registered", None), (3, "registered", None), (4, "waitlisted", 1)]
    assert items[2]["promoted_at"] == "2026-11-02T09:30:00+03:00" and items[0]["promoted_at"] is None
    assert [n.member_id for n in notifications(app, type_="event_promoted")] == [3]


def test_time_change_notifies(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=1)
    client.patch(f"{API}/events/1", headers=admin_h, json={"start_time": "13:00"})  # draft
    publish(client, admin_h, 1)
    register(client, world["mh"][0], 1)
    register(client, world["mh"][1], 1)  # waitlisted
    register(client, world["mh"][2], 1, expect=409)  # the waiting list holds one
    client.patch(f"{API}/events/1", headers=admin_h, json={"title": "Renamed"})
    assert notifications(app, type_="event_changed") == []
    client.patch(f"{API}/events/1", headers=admin_h, json={"start_time": "14:00", "end_time": "16:00"})
    ns = notifications(app, type_="event_changed")
    assert [n.member_id for n in ns] == [1, 2] and all(n.event_id == 1 for n in ns)
    for part in ("2026-11-05", "14:00", "16:00", "Renamed"):
        assert part in ns[0].message
    n = client.get(f"{API}/members/1/notifications", headers=world["mh"][0]).json()["items"][0]
    assert n["event_id"] == 1 and n["type"] == "event_changed"
    assert get_event(client, admin_h, 1)["registered"] == 1  # registrations stay
    client.patch(f"{API}/events/1", headers=admin_h, json={"start_time": "15:00"})
    assert len(notifications(app, type_="event_changed")) == 4


# --- read ---------------------------------------------------------------------------------------------


def test_read_events(client, admin_h, world):
    mk_event(client, admin_h, title="Ay Işığı", kind="tour", date="2026-11-06")  # 1 draft
    mk_event(client, admin_h, title="İstanbul talk")  # 2
    mk_event(client, admin_h, title="Club", kind="book_club", start_time="10:00", end_time="12:00")  # 3
    publish(client, admin_h, 2)
    mh = world["mh"][0]
    r = client.get(f"{API}/events", headers=admin_h).json()
    assert [e["id"] for e in r["items"]] == [3, 2, 1] and r["total"] == 3 and r["page"] == 1
    r = client.get(f"{API}/events", headers=mh).json()
    assert [e["id"] for e in r["items"]] == [2]
    assert client.get(f"{API}/events?status=draft", headers=mh).json()["total"] == 0
    err(client.get(f"{API}/events/1", headers=mh), 404, "NOT_FOUND")
    assert client.get(f"{API}/events/2", headers=mh).status_code == 200
    err(client.get(f"{API}/events/99", headers=mh), 404, "NOT_FOUND")

    def q(s):
        return [e["id"] for e in client.get(f"{API}/events{s}", headers=admin_h).json()["items"]]

    assert q("?kind=tour") == [1] and q("?status=published") == [2] and q("?q=ISTANBUL") == [2] and q("?q=ışığı") == [1]
    assert q("?from=2026-11-06") == [1] and q("?to=2026-11-05") == [3, 2] and q("?branch_id=2") == []
    assert q("?page_size=1&page=2") == [2] and q("?q=%20") == [3, 2, 1]
    for bad in ("?from=xx", "?kind=party", "?status=x", "?page=0", "?to=2026-02-30"):
        err(client.get(f"{API}/events{bad}", headers=admin_h), 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/events").status_code == 401


def test_event_counts(client, admin_h, world):
    mk_event(client, admin_h, capacity=2)
    publish(client, admin_h, 1)
    for i in range(3):
        register(client, world["mh"][i], 1)
    e = get_event(client, world["mh"][0], 1)
    assert (e["registered"], e["waitlisted"], e["free_places"]) == (2, 1, 0)


# --- cancel event, closures, series ------------------------------------------------------------------------


def test_cancel_event(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=1, fee="20.00")
    publish(client, admin_h, 1)
    r1 = register(client, world["mh"][0], 1)
    register(client, world["mh"][1], 1)
    assert client.post(f"{API}/members/1/payments", headers=admin_h, json={"amount": "5.00", "method": "cash"}).status_code == 201
    c = client.post(f"{API}/events/1/cancel", headers=world["lh"])
    assert c.status_code == 200 and c.json()["status"] == "cancelled" and c.json()["cancel_reason"] == "staff_request"
    items = regs_of_event(client, admin_h, 1)
    assert [(r["status"], r["cancel_reason"], r["late_cancellation"]) for r in items] == [("cancelled", "event_cancelled", False)] * 2
    fee = client.get(f"{API}/members/1/fees", headers=admin_h).json()["items"][0]
    assert fee["kind"] == "event_fee" and fee["status"] == "waived" and fee["waive_reason"] == "Event cancelled"
    assert fee["event_registration_id"] == r1["id"] and fee["paid_amount"] == "5.00"
    assert sorted(n.member_id for n in notifications(app, type_="event_cancelled")) == [1, 2]
    assert [a.entity_id for a in audit(app, "event_cancelled")] == [1]
    err(client.post(f"{API}/events/1/cancel", headers=admin_h), 409, "INVALID_EVENT_STATUS")
    err(client.post(f"{API}/events/1/registrations", headers=admin_h, json={"member_id": 3}), 409, "EVENT_NOT_OPEN")
    mk_event(client, admin_h, date="2026-11-06")  # a draft can be cancelled too
    assert client.post(f"{API}/events/2/cancel", headers=admin_h).json()["status"] == "cancelled"
    err(client.post(f"{API}/events/1/cancel", headers=world["mh"][0]), 403, "FORBIDDEN")
    err(client.post(f"{API}/events/9/cancel", headers=admin_h), 404, "NOT_FOUND")


def test_closure_cancels_events(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=2)
    publish(client, admin_h, 1)
    mk_event(client, admin_h, start_time="09:00", end_time="10:00")  # draft, same date
    mk_event(client, admin_h, date="2026-11-06")
    register(client, world["mh"][0], 1)
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-05", "reason": "Sayım"})
    assert r.status_code == 201 and r.json()["cancelled_events"] == 2 and r.json()["cancelled_shifts"] == 1
    assert [get_event(client, admin_h, i)["cancel_reason"] for i in (1, 2, 3)] == ["branch_closed", "branch_closed", None]
    reg1 = regs_of_event(client, admin_h, 1)[0]
    assert reg1["status"] == "cancelled" and reg1["cancel_reason"] == "event_cancelled"
    assert len(notifications(app, 1, "event_cancelled")) == 1
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-09", "reason": "x"})
    assert r.json()["cancelled_events"] == 0


def test_series_example(client, admin_h, world):
    client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-24", "reason": "Sayım"})
    body = {"title": "Weekly club", "kind": "book_club", "branch_id": 1, "first_date": "2026-11-10", "start_time": "14:00",
            "end_time": "16:00", "capacity": 10, "staff_id": 1, "weeks": 4}
    r = client.post(f"{API}/event-series", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    assert r.json() == {"series_id": 1, "created": [1, 2, 3], "skipped": [{"date": "2026-11-24", "error_code": "BRANCH_NOT_OPEN"}]}
    evs = client.get(f"{API}/events?series_id=1", headers=admin_h).json()["items"]
    assert [(e["date"], e["status"], e["series_id"], e["kind"]) for e in evs] == [
        ("2026-11-10", "draft", 1, "book_club"), ("2026-11-17", "draft", 1, "book_club"), ("2026-12-01", "draft", 1, "book_club")]


SERIES = {"title": "S", "kind": "talk", "branch_id": 1, "first_date": "2026-11-10", "start_time": "14:00",
          "end_time": "16:00", "capacity": 10, "staff_id": 1, "weeks": 2}


def test_series_validation_and_empty(client, admin_h, world, app):
    for kw in ({"weeks": 1}, {"weeks": 13}, {"date": "2026-11-10"}, {"first_date": "x"}, {"weeks": ...}, {"staff_id": 9}, {"first_date": ...}):
        body = {k: v for k, v in {**SERIES, **kw}.items() if v is not ...}
        err(client.post(f"{API}/event-series", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/event-series", headers=world["mh"][0], json=SERIES), 403, "FORBIDDEN")
    e = err(client.post(f"{API}/event-series", headers=admin_h, json={**SERIES, "first_date": "2026-11-14", "weeks": 3}), 409, "SERIES_EMPTY")
    assert e["details"]["skipped"][0]["error_code"] == "BRANCH_NOT_OPEN"
    assert client.get(f"{API}/events", headers=admin_h).json()["total"] == 0
    r = client.post(f"{API}/event-series", headers=admin_h, json={**SERIES, "first_date": "2026-10-26", "weeks": 3})
    assert r.json()["skipped"] == [{"date": "2026-10-26", "error_code": "EVENT_IN_PAST"}] and r.json()["series_id"] == 1
    assert [a.entity_id for a in audit(app, "event_series_created")] == [1]


def test_cancel_series(client, admin_h, world, clock, app):
    client.post(f"{API}/event-series", headers=admin_h, json={**SERIES, "weeks": 3})
    shift_on(client, admin_h, "2026-11-17")
    publish(client, admin_h, 2)
    register(client, world["mh"][0], 2)
    clock.set(at(10, "15:00"))  # the first event has started
    fresh = h(token_of(client))
    r = client.post(f"{API}/event-series/1/cancel", headers=fresh)
    assert r.status_code == 200 and r.json() == {"cancelled": [2, 3]}
    assert [get_event(client, fresh, i)["status"] for i in (1, 2, 3)] == ["draft", "cancelled", "cancelled"]
    assert get_event(client, fresh, 2)["cancel_reason"] == "series_cancelled"
    assert len(notifications(app, 1, "event_cancelled")) == 1
    assert client.post(f"{API}/event-series/1/cancel", headers=fresh).json() == {"cancelled": []}
    err(client.post(f"{API}/event-series/9/cancel", headers=fresh), 404, "NOT_FOUND")
    assert [a.entity_id for a in audit(app, "event_series_cancelled")] == [1, 1]


# --- registrations --------------------------------------------------------------------------------------------


def test_register_and_waitlist_example(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=2)
    publish(client, admin_h, 1)
    mh = world["mh"]
    r1 = register(client, mh[0], 1)
    assert r1["status"] == "registered" and r1["position"] is None and r1["event_title"] == "Poetry night"
    assert r1["event_date"] == "2026-11-05" and r1["start_time"] == "14:00" and r1["fee_id"] is None
    assert r1["late_cancellation"] is False and r1["cancel_reason"] is None and r1["created_at"] == "2026-11-02T09:30:00+03:00"
    r2 = register(client, mh[1], 1)
    r3 = register(client, mh[2], 1)
    r4 = register(client, mh[3], 1)
    assert (r3["status"], r3["position"], r4["position"]) == ("waitlisted", 1, 2)
    c = cancel_reg(client, mh[1], r2["id"])
    assert c["status"] == "cancelled" and c["cancel_reason"] == "member_request" and c["cancelled_at"]
    items = {r["member_id"]: r for r in regs_of_event(client, admin_h, 1)}
    assert items[3]["status"] == "registered" and items[3]["promoted_at"] and items[4]["position"] == 1
    assert [n.member_id for n in notifications(app, type_="event_promoted")] == [3]
    assert notifications(app, type_="event_cancelled") == []
    assert len(audit(app, "event_registration_created")) == 4 and len(audit(app, "event_registration_cancelled")) == 1
    types = {n["type"] for n in client.get(f"{API}/members/3/notifications", headers=mh[2]).json()["items"]}
    assert types == {"event_promoted"}


def test_register_body_rules(client, admin_h, world):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    err(client.post(f"{API}/events/1/registrations", headers=world["mh"][0], json={"member_id": 1}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/events/1/registrations", headers=admin_h, json={}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/events/1/registrations", headers=world["lh"], json={"member_id": 99}), 404, "NOT_FOUND")
    err(client.post(f"{API}/events/9/registrations", headers=world["mh"][0], json={}), 404, "NOT_FOUND")
    err(client.post(f"{API}/events/1/registrations", headers=world["mh"][0], json={"x": 1}), 422, "VALIDATION_ERROR")
    assert client.post(f"{API}/events/1/registrations", json={}).status_code == 401
    assert register(client, world["lh"], 1, member_id=2)["member_id"] == 2


def test_registration_checks(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=1)
    err(client.post(f"{API}/events/1/registrations", headers=world["mh"][0], json={}), 409, "EVENT_NOT_OPEN")
    publish(client, admin_h, 1)
    mh = world["mh"]
    client.post(f"{API}/members/4/deactivate", headers=admin_h)
    err(client.post(f"{API}/events/1/registrations", headers=mh[3], json={}), 409, "MEMBER_PASSIVE")
    old = reg(client, admin_h, email="old@example.edu.tr", university_id="99990001")
    with app.state.session_factory.begin() as s:
        s.get(Member, old["id"]).valid_until = datetime.date(2026, 11, 4)
    oh = h(token_of(client, "old@example.edu.tr", "Passw0rd1"))
    err(client.post(f"{API}/events/1/registrations", headers=oh, json={}), 409, "MEMBERSHIP_EXPIRED")
    with app.state.session_factory.begin() as s:
        s.add(Fee(member_id=1, kind="damage_fee", amount=Decimal("50.00"), status="open", created_on=datetime.date(2026, 11, 2)))
    e = err(client.post(f"{API}/events/1/registrations", headers=mh[0], json={}), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"
    register(client, mh[1], 1)
    err(client.post(f"{API}/events/1/registrations", headers=mh[1], json={}), 409, "ALREADY_REGISTERED")
    register(client, mh[2], 1)  # waitlisted: one of one
    err(client.post(f"{API}/events/1/registrations", headers=mh[2], json={}), 409, "ALREADY_REGISTERED")
    m5 = reg(client, admin_h, email="m5@example.edu.tr", university_id="20230005")
    err(client.post(f"{API}/events/1/registrations", headers=admin_h, json={"member_id": m5["id"]}), 409, "WAITLIST_FULL")


def test_debt_below_limit_is_allowed(client, admin_h, world, app):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    with app.state.session_factory.begin() as s:
        s.add(Fee(member_id=1, kind="damage_fee", amount=Decimal("49.99"), status="open", created_on=datetime.date(2026, 11, 2)))
    register(client, world["mh"][0], 1)


def test_registration_closed_boundary(client, admin_h, world, clock):
    shift_on(client, admin_h, "2026-11-03", "10:00", "20:00")
    mk_event(client, admin_h, date="2026-11-03", start_time="18:00", end_time="20:00")
    publish(client, admin_h, 1)
    clock.set(datetime.datetime(2026, 11, 3, 16, 59, 59, tzinfo=TZ))
    register(client, world["mh"][0], 1)
    clock.set(at(3, "17:00"))
    err(client.post(f"{API}/events/1/registrations", headers=world["mh"][1], json={}), 409, "REGISTRATION_CLOSED")


def test_audience_rules(client, admin_h, world):
    mk_event(client, admin_h, audience="students")
    mk_event(client, admin_h, audience="academics", start_time="12:00", end_time="13:00")
    mk_event(client, admin_h, start_time="09:00", end_time="10:00")
    for i in (1, 2, 3):
        publish(client, admin_h, i)
    reg(client, admin_h, email="prof@example.edu.tr", university_id="55550001", membership_type="academic")
    reg(client, admin_h, email="staff@example.edu.tr", university_id="55550002", membership_type="staff")
    reg(client, admin_h, email="guest@example.com", membership_type="guest", phone="+90 532 123 45 67", university_id=None)
    ach = h(token_of(client, "prof@example.edu.tr", "Passw0rd1"))
    sth = h(token_of(client, "staff@example.edu.tr", "Passw0rd1"))
    guh = h(token_of(client, "guest@example.com", "Passw0rd1"))
    register(client, world["mh"][0], 1)
    err(client.post(f"{API}/events/1/registrations", headers=ach, json={}), 409, "EVENT_NOT_FOR_TYPE")
    register(client, ach, 2)
    err(client.post(f"{API}/events/2/registrations", headers=world["mh"][0], json={}), 409, "EVENT_NOT_FOR_TYPE")
    err(client.post(f"{API}/events/1/registrations", headers=sth, json={}), 409, "EVENT_NOT_FOR_TYPE")
    err(client.post(f"{API}/events/2/registrations", headers=sth, json={}), 409, "EVENT_NOT_FOR_TYPE")
    err(client.post(f"{API}/events/2/registrations", headers=guh, json={}), 409, "EVENT_NOT_FOR_TYPE")
    register(client, guh, 3)
    register(client, sth, 3)


def test_overlap_example(client, admin_h, world):
    client.post(f"{API}/shifts/1/cancel", headers=admin_h)
    shift_on(client, admin_h, "2026-11-05", "08:00", "18:00")
    mk_event(client, admin_h, capacity=1)  # 14:00-16:00
    mk_event(client, admin_h, start_time="15:30", end_time="17:00", capacity=1)
    mk_event(client, admin_h, start_time="16:00", end_time="17:00", capacity=1)
    for i in (1, 2, 3):
        publish(client, admin_h, i)
    mh = world["mh"]
    register(client, mh[0], 1)
    e = err(client.post(f"{API}/events/2/registrations", headers=mh[0], json={}), 409, "EVENT_TIME_CONFLICT")
    assert e["details"]["event_id"] == 1
    register(client, mh[0], 3)  # touching intervals are fine
    register(client, mh[1], 1)  # waitlisted
    register(client, mh[1], 2)  # a waitlisted registration does not conflict


def test_registration_limits(client, admin_h, world):
    # a student may hold 5 active registrations; six one-hour events in a row on the same day
    ids = []
    for hour in range(8, 14):
        e = mk_event(client, admin_h, start_time=f"{hour:02d}:00", end_time=f"{hour + 1:02d}:00", capacity=5)
        publish(client, admin_h, e["id"])
        ids.append(e["id"])
    mh = world["mh"][0]
    regs = [register(client, mh, i) for i in ids[:5]]
    e = err(client.post(f"{API}/events/{ids[5]}/registrations", headers=mh, json={}), 409, "EVENT_REGISTRATION_LIMIT_REACHED")
    assert e["details"]["limit"] == 5
    cancel_reg(client, mh, regs[0]["id"])
    register(client, mh, ids[5])


@pytest.mark.parametrize("kind,limit", [("student", 5), ("academic", 10), ("staff", 10), ("guest", 2)])
def test_limits_by_type(client, admin_h, world, kind, limit):
    client.post(f"{API}/shifts/1/cancel", headers=admin_h)
    shift_on(client, admin_h, "2026-11-05", "08:00", "18:00")
    shift_on(client, admin_h, "2026-11-06", "08:00", "18:00")
    extra = {"phone": "+90 532 123 45 67", "university_id": None} if kind == "guest" else {"university_id": "7777"}
    reg(client, admin_h, email="t@example.com", membership_type=kind, **extra)
    th = h(token_of(client, "t@example.com", "Passw0rd1"))
    ids = []
    for n in range(limit + 1):
        day = "2026-11-05" if n < 10 else "2026-11-06"
        hour = 8 + n % 10
        e = mk_event(client, admin_h, start_time=f"{hour:02d}:00", end_time=f"{hour + 1:02d}:00", date=day)
        publish(client, admin_h, e["id"])
        ids.append(e["id"])
    for i in ids[:limit]:
        register(client, th, i)
    e = err(client.post(f"{API}/events/{ids[limit]}/registrations", headers=th, json={}), 409, "EVENT_REGISTRATION_LIMIT_REACHED")
    assert e["details"]["limit"] == limit


def test_fee_on_registered_and_promotion(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=1, fee="30.00")
    publish(client, admin_h, 1)
    mh = world["mh"]
    r1 = register(client, mh[0], 1)
    r2 = register(client, mh[1], 1)
    assert r1["fee_id"] == 1 and r2["fee_id"] is None
    assert client.get(f"{API}/members/2/fees", headers=admin_h).json()["total"] == 0
    fee = client.get(f"{API}/members/1/fees", headers=admin_h).json()["items"][0]
    assert fee["kind"] == "event_fee" and fee["amount"] == "30.00" and fee["event_registration_id"] == r1["id"]
    assert fee["loan_id"] is None and fee["status"] == "open"
    assert [n.member_id for n in notifications(app, type_="fee_created")] == [1]
    c = cancel_reg(client, mh[0], r1["id"])  # timely
    assert c["late_cancellation"] is False
    fees = client.get(f"{API}/fees", headers=admin_h).json()["items"]
    assert [(f["member_id"], f["status"], f["waive_reason"]) for f in fees] == [
        (1, "waived", "Registration cancelled in time"), (2, "open", None)]
    assert client.get(f"{API}/members/2/event-registrations", headers=mh[1]).json()["items"][0]["fee_id"] == 2
    assert client.get(f"{API}/fees?kind=event_fee", headers=admin_h).json()["total"] == 2
    assert client.get(f"{API}/members/2/balance", headers=mh[1]).json()["total_debt"] == "30.00"
    assert client.post(f"{API}/members/2/payments", headers=admin_h, json={"amount": "30.00", "method": "card"}).status_code == 201
    assert client.get(f"{API}/members/2/fees", headers=admin_h).json()["items"][0]["status"] == "paid"


def test_timely_and_late_cancellation(client, admin_h, world, clock):
    shift_on(client, admin_h, "2026-11-06", "10:00", "20:00")
    mk_event(client, admin_h, date="2026-11-06", start_time="18:00", end_time="20:00", capacity=3, fee="10.00")
    publish(client, admin_h, 1)
    mh = world["mh"]
    ra = register(client, mh[0], 1)
    rb = register(client, mh[1], 1)
    rc = register(client, mh[2], 1)
    clock.set(at(5, "18:00"))
    assert cancel_reg(client, mh[0], ra["id"])["late_cancellation"] is False
    clock.set(datetime.datetime(2026, 11, 5, 18, 0, 1, tzinfo=TZ))
    assert cancel_reg(client, mh[1], rb["id"])["late_cancellation"] is True
    fees = {f["member_id"]: f for f in client.get(f"{API}/fees", headers=admin_h).json()["items"]}
    assert (fees[1]["status"], fees[2]["status"], fees[3]["status"]) == ("waived", "open", "open")
    err(client.post(f"{API}/event-registrations/{ra['id']}/cancel", headers=mh[0]), 409, "REGISTRATION_NOT_ACTIVE")
    clock.set(at(6, "18:00"))
    err(client.post(f"{API}/event-registrations/{rc['id']}/cancel", headers=mh[2]), 409, "EVENT_STARTED")


def test_timely_cancellation_with_payment_keeps_fee(client, admin_h, world):
    mk_event(client, admin_h, capacity=2, fee="10.00")
    publish(client, admin_h, 1)
    r = register(client, world["mh"][0], 1)
    client.post(f"{API}/members/1/payments", headers=admin_h, json={"amount": "4.00", "method": "cash"})
    cancel_reg(client, world["mh"][0], r["id"])
    fee = client.get(f"{API}/members/1/fees", headers=admin_h).json()["items"][0]
    assert fee["status"] == "open" and fee["paid_amount"] == "4.00"


def test_staff_cancellation_can_be_late(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    r = register(client, world["mh"][0], 1)
    clock.set(at(5, "10:00"))
    c = cancel_reg(client, world["lh"], r["id"])
    assert c["cancel_reason"] == "staff_request" and c["late_cancellation"] is True


def test_waitlisted_cancellation_never_late(client, admin_h, world, clock):
    mk_event(client, admin_h, capacity=1)
    publish(client, admin_h, 1)
    register(client, world["mh"][0], 1)
    w = register(client, world["mh"][1], 1)
    clock.set(at(5, "10:00"))
    c = cancel_reg(client, world["mh"][1], w["id"])
    assert c["late_cancellation"] is False and c["cancel_reason"] == "member_request"


def test_cancel_ownership(client, admin_h, world):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    r = register(client, world["mh"][0], 1)
    err(client.post(f"{API}/event-registrations/{r['id']}/cancel", headers=world["mh"][1]), 403, "FORBIDDEN")
    err(client.post(f"{API}/event-registrations/99/cancel", headers=world["mh"][1]), 404, "NOT_FOUND")
    assert cancel_reg(client, world["lh"], r["id"])["cancel_reason"] == "staff_request"


@pytest.mark.parametrize("hhmm,promoted", [("13:59", True), ("14:00", False)])
def test_promotion_cutoff(client, admin_h, world, clock, hhmm, promoted):
    mk_event(client, admin_h, capacity=1, start_time="15:00", end_time="16:00")
    publish(client, admin_h, 1)
    r1 = register(client, world["mh"][0], 1)
    register(client, world["mh"][1], 1)
    clock.set(at(5, hhmm))
    cancel_reg(client, world["mh"][0], r1["id"])
    e = get_event(client, admin_h, 1)
    assert (e["registered"], e["waitlisted"]) == ((1, 0) if promoted else (0, 1))


def test_read_registrations(client, admin_h, world):
    mk_event(client, admin_h, capacity=2)
    mk_event(client, admin_h, start_time="09:00", end_time="10:00")
    publish(client, admin_h, 1)
    publish(client, admin_h, 2)
    mh = world["mh"]
    a = register(client, mh[0], 1)
    for i in (1, 2, 3):
        register(client, mh[i], 1)
    cancel_reg(client, mh[0], a["id"])  # promotes member 3
    register(client, mh[0], 1)  # waitlisted again
    register(client, mh[0], 2)
    items = regs_of_event(client, admin_h, 1)
    assert [(i["member_id"], i["status"], i["position"]) for i in items] == [
        (2, "registered", None), (3, "registered", None), (4, "waitlisted", 1), (1, "waitlisted", 2), (1, "cancelled", None)]
    assert client.get(f"{API}/events/1/registrations?status=cancelled", headers=admin_h).json()["total"] == 1
    err(client.get(f"{API}/events/1/registrations?status=x", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/events/1/registrations", headers=mh[0]), 403, "FORBIDDEN")
    err(client.get(f"{API}/events/9/registrations", headers=admin_h), 404, "NOT_FOUND")
    mine = client.get(f"{API}/members/1/event-registrations", headers=mh[0]).json()["items"]
    assert [(i["event_id"], i["status"]) for i in mine] == [(2, "registered"), (1, "cancelled"), (1, "waitlisted")]
    assert mine[0]["start_time"] == "09:00" and mine[0]["event_title"] == "Poetry night"
    assert client.get(f"{API}/members/1/event-registrations?status=waitlisted", headers=admin_h).json()["total"] == 1
    assert client.get(f"{API}/members/1/event-registrations?from=2026-11-06", headers=admin_h).json()["total"] == 0
    assert client.get(f"{API}/members/1/event-registrations?to=2026-11-05", headers=admin_h).json()["total"] == 3
    err(client.get(f"{API}/members/1/event-registrations", headers=mh[1]), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/99/event-registrations", headers=admin_h), 404, "NOT_FOUND")


# --- check-in, process ----------------------------------------------------------------------------------------


def test_check_in(client, admin_h, world, clock, app):
    mk_event(client, admin_h, capacity=1)
    publish(client, admin_h, 1)
    r1 = register(client, world["mh"][0], 1)
    r2 = register(client, world["mh"][1], 1)
    err(client.post(f"{API}/event-registrations/{r1['id']}/check-in", headers=world["mh"][0]), 403, "FORBIDDEN")
    clock.set(datetime.datetime(2026, 11, 5, 13, 29, 59, tzinfo=TZ))
    err(client.post(f"{API}/event-registrations/{r1['id']}/check-in", headers=admin_h), 409, "CHECK_IN_NOT_OPEN")
    clock.set(at(5, "13:30"))
    err(client.post(f"{API}/event-registrations/{r2['id']}/check-in", headers=admin_h), 409, "REGISTRATION_NOT_ACTIVE")
    r = client.post(f"{API}/event-registrations/{r1['id']}/check-in", headers=world["lh"])
    assert r.status_code == 200 and r.json()["status"] == "attended" and r.json()["attended_at"] == "2026-11-05T13:30:00+03:00"
    err(client.post(f"{API}/event-registrations/{r1['id']}/check-in", headers=admin_h), 409, "REGISTRATION_NOT_ACTIVE")
    assert [a.entity_id for a in audit(app, "event_attended")] == [r1["id"]]
    err(client.post(f"{API}/event-registrations/99/check-in", headers=admin_h), 404, "NOT_FOUND")


def test_check_in_event_over(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    r1 = register(client, world["mh"][0], 1)
    clock.set(datetime.datetime(2026, 11, 5, 15, 59, 59, tzinfo=TZ))
    err(client.post(f"{API}/event-registrations/{r1['id']}/cancel", headers=world["mh"][0]), 409, "EVENT_STARTED")
    assert client.post(f"{API}/event-registrations/{r1['id']}/check-in", headers=admin_h).status_code == 200
    r2 = register(client, world["mh"][1], 1, expect=409)
    assert r2["error"]["code"] == "REGISTRATION_CLOSED"


def test_check_in_at_end(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    r1 = register(client, world["mh"][0], 1)
    clock.set(at(5, "16:00"))
    err(client.post(f"{API}/event-registrations/{r1['id']}/check-in", headers=admin_h), 409, "EVENT_OVER")


def test_process_no_show_and_completion(client, admin_h, world, clock, app):
    mk_event(client, admin_h, capacity=1, fee="10.00")
    publish(client, admin_h, 1)
    mh = world["mh"]
    r1 = register(client, mh[0], 1)
    r2 = register(client, mh[1], 1)  # waitlisted
    clock.set(at(5, "15:00"))
    assert process(client, admin_h) == {"completed_events": 0, "no_shows": 0, "bans": 0, "reminders": 0}
    clock.set(at(5, "16:00"))
    assert process(client, admin_h)["completed_events"] == 0  # the end is not before now
    clock.set(datetime.datetime(2026, 11, 5, 16, 0, 1, tzinfo=TZ))
    err(client.post(f"{API}/events/process", headers=mh[0]), 403, "FORBIDDEN")
    assert process(client, world["lh"]) == {"completed_events": 1, "no_shows": 1, "bans": 0, "reminders": 0}
    assert get_event(client, admin_h, 1)["status"] == "completed"
    items = {i["id"]: i for i in regs_of_event(client, admin_h, 1)}
    assert items[r1["id"]]["status"] == "no_show"
    assert (items[r2["id"]]["status"], items[r2["id"]]["cancel_reason"]) == ("cancelled", "event_cancelled")
    assert client.get(f"{API}/members/1/fees", headers=admin_h).json()["items"][0]["status"] == "open"
    assert notifications(app, 2) == []
    assert [a.entity_id for a in audit(app, "event_no_show")] == [r1["id"]]
    assert len(audit(app, "events_processed")) == 3
    assert process(client, admin_h)["completed_events"] == 0
    err(client.post(f"{API}/events/process", headers={}), 401, "UNAUTHENTICATED")


def test_attended_is_not_no_show(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    r1 = register(client, world["mh"][0], 1)
    register(client, world["mh"][1], 1)
    clock.set(at(5, "14:05"))
    client.post(f"{API}/event-registrations/{r1['id']}/check-in", headers=admin_h)
    clock.set(at(5, "17:00"))
    assert process(client, admin_h)["no_shows"] == 1
    assert client.get(f"{API}/members/1/event-registrations", headers=admin_h).json()["items"][0]["status"] == "attended"


def test_unprocessed_started_event_stays_published(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    clock.set(at(5, "17:00"))
    assert get_event(client, admin_h, 1)["status"] == "published"
    err(client.post(f"{API}/events/1/registrations", headers=world["mh"][0], json={}), 409, "REGISTRATION_CLOSED")


def test_reminders(client, admin_h, world, clock, app):
    shift_on(client, admin_h, "2026-11-03")
    shift_on(client, admin_h, "2026-11-04")
    mk_event(client, admin_h, date="2026-11-03", start_time="10:00", end_time="12:00", capacity=1)
    mk_event(client, admin_h, date="2026-11-04", start_time="10:00", end_time="12:00")
    clock.set(at(2, "09:00"))
    publish(client, admin_h, 1)
    publish(client, admin_h, 2)
    mh = world["mh"]
    register(client, mh[0], 1)
    register(client, mh[1], 1)  # waitlisted: no reminder
    register(client, mh[2], 2)
    clock.set(at(2, "10:00"))  # event 1 starts in exactly 24 hours, event 2 in 48
    assert process(client, admin_h)["reminders"] == 1
    assert process(client, admin_h)["reminders"] == 0
    ns = notifications(app, type_="event_reminder")
    assert [(n.member_id, n.event_id) for n in ns] == [(1, 1)]
    for part in ("Poetry night", "2026-11-03", "10:00", "12:00"):
        assert part in ns[0].message
    clock.set(at(3, "10:00"))  # event 1 has started; event 2 is 24 hours away
    assert process(client, admin_h)["reminders"] == 1
    assert [(n.member_id, n.event_id) for n in notifications(app, type_="event_reminder")] == [(1, 1), (3, 2)]


def test_reminder_window_edge(client, admin_h, world, clock):
    shift_on(client, admin_h, "2026-11-03")
    mk_event(client, admin_h, date="2026-11-03", start_time="10:00", end_time="12:00")
    clock.set(at(2, "09:00"))
    publish(client, admin_h, 1)
    register(client, world["mh"][0], 1)
    clock.set(datetime.datetime(2026, 11, 2, 9, 59, 59, tzinfo=TZ))
    assert process(client, admin_h)["reminders"] == 0
    clock.set(at(2, "10:00"))
    assert process(client, admin_h)["reminders"] == 1


def test_reminder_per_registration(client, admin_h, world, clock):
    shift_on(client, admin_h, "2026-11-03")
    mk_event(client, admin_h, date="2026-11-03")
    publish(client, admin_h, 1)
    r = register(client, world["mh"][0], 1)
    clock.set(at(2, "15:00"))
    assert process(client, admin_h)["reminders"] == 1
    cancel_reg(client, world["mh"][0], r["id"])
    register(client, world["mh"][0], 1)
    assert process(client, admin_h)["reminders"] == 1  # a new registration, a new reminder


# --- bans ------------------------------------------------------------------------------------------------------


def three_no_shows(client, admin_h, world, clock, member=0):
    """Member 1 does not show up for the events of Tue 3, Wed 4 and Thu 5 November; processed on the 5th."""
    for day in ("2026-11-03", "2026-11-04"):
        shift_on(client, admin_h, day)
    for day in ("2026-11-03", "2026-11-04", "2026-11-05"):
        e = mk_event(client, admin_h, date=day)
        publish(client, admin_h, e["id"])
        register(client, world["mh"][member], e["id"])
    clock.set(at(5, "17:00"))
    return process(client, admin_h)


def test_ban_after_three_no_shows(client, admin_h, world, clock, app):
    shift_on(client, admin_h, "2026-11-20")
    shift_on(client, admin_h, "2026-12-30")
    mh = world["mh"]
    e4 = mk_event(client, admin_h, date="2026-11-20", start_time="10:00", end_time="11:00", fee="7.00")
    e5 = mk_event(client, admin_h, date="2026-12-30", start_time="10:00", end_time="11:00")
    publish(client, admin_h, e4["id"])
    publish(client, admin_h, e5["id"])
    # M1 and M2 hold the two places of event 4, M3 and M4 wait
    for i in range(4):
        register(client, mh[i], e4["id"])
    register(client, mh[0], e5["id"])
    assert three_no_shows(client, admin_h, world, clock) == {"completed_events": 3, "no_shows": 3, "bans": 1, "reminders": 0}
    bans = client.get(f"{API}/members/1/event-bans", headers=mh[0]).json()
    assert bans["total"] == 1
    b = bans["items"][0]
    assert (b["id"], b["member_id"], b["starts_on"], b["ends_on"]) == (1, 1, "2026-11-05", "2026-12-04")
    assert b["created_at"] == "2026-11-05T17:00:00+03:00"
    ns = notifications(app, type_="event_ban_started")
    assert [n.member_id for n in ns] == [1] and "2026-11-05" in ns[0].message and "2026-12-04" in ns[0].message
    # the registration within the ban is cancelled, the one outside stays
    mine = {i["event_id"]: i for i in client.get(f"{API}/members/1/event-registrations", headers=admin_h).json()["items"]}
    assert (mine[e4["id"]]["status"], mine[e4["id"]]["cancel_reason"], mine[e4["id"]]["late_cancellation"]) == ("cancelled", "member_banned", False)
    assert mine[e5["id"]]["status"] == "registered"
    # fee waived regardless of time, place freed, the first waiting member promoted
    fee = client.get(f"{API}/members/1/fees", headers=admin_h).json()["items"][0]
    assert (fee["amount"], fee["status"], fee["waive_reason"]) == ("7.00", "waived", "Registration cancelled in time")
    event4 = get_event(client, admin_h, e4["id"])
    assert (event4["registered"], event4["waitlisted"]) == (2, 1)
    assert [n.member_id for n in notifications(app, type_="event_promoted")] == [3]
    assert notifications(app, 1, "event_cancelled") == []
    e = err(client.post(f"{API}/events/{e5['id']}/registrations", headers=mh[0], json={}), 409, "MEMBER_BANNED_FROM_EVENTS")
    assert e["details"]["ends_on"] == "2026-12-04"
    summary = client.get(f"{API}/members/1/summary", headers=mh[0]).json()["events"]
    assert summary == {"registered": 1, "waitlisted": 0, "no_shows_90_days": 3, "banned_until": "2026-12-04"}
    assert [a.entity_id for a in audit(app, "event_ban_started")] == [1]
    assert process(client, admin_h)["bans"] == 0
    err(client.get(f"{API}/members/1/event-bans", headers=mh[1]), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/9/event-bans", headers=admin_h), 404, "NOT_FOUND")
    assert client.get(f"{API}/members/1/event-bans", headers=admin_h).json()["total"] == 1


def test_ban_blocks_registration_on_event_date(client, admin_h, world, clock):
    """A ban in force on the event date blocks too, also when it starts later (LIB-EVT-20 (6))."""
    three_no_shows(client, admin_h, world, clock)
    clock.set(at(6, "09:00"))
    shift_on(client, admin_h, "2026-12-07")
    e = mk_event(client, admin_h, date="2026-12-07")
    publish(client, admin_h, e["id"])
    err(client.post(f"{API}/events/{e['id']}/registrations", headers=world["mh"][0], json={}), 409, "MEMBER_BANNED_FROM_EVENTS")


def test_ban_example_three_in_window(client, admin_h, world, clock):
    """LIB-EVT-36: no-shows on events of 2026-11-03, 2026-11-10 and 2026-11-17 processed on 2026-11-17."""
    mh = world["mh"][0]
    for day in ("2026-11-03", "2026-11-10", "2026-11-17"):
        shift_on(client, admin_h, day) if day != "2026-11-05" else None
        e = mk_event(client, admin_h, date=day)
        publish(client, admin_h, e["id"])
        register(client, mh, e["id"])
    clock.set(at(17, "17:00"))
    fresh = h(token_of(client))
    assert process(client, fresh) == {"completed_events": 3, "no_shows": 3, "bans": 1, "reminders": 0}
    b = client.get(f"{API}/members/1/event-bans", headers=fresh).json()["items"][0]
    assert (b["starts_on"], b["ends_on"]) == ("2026-11-17", "2026-12-16")


def test_ban_example_window(client, admin_h, world, clock):
    """LIB-EVT-36: one of the three no-shows lies outside the 90 days, so there is no ban."""
    clock.set(datetime.datetime(2026, 7, 1, 9, 0, tzinfo=TZ))
    for day in ("2026-07-31", "2026-09-30", "2026-11-03"):
        shift_on(client, admin_h, day)
        e = mk_event(client, admin_h, date=day)
        publish(client, admin_h, e["id"])
        register(client, world["mh"][0], e["id"])
    clock.set(at(17, "17:00"))
    fresh = h(token_of(client))
    assert process(client, fresh) == {"completed_events": 3, "no_shows": 3, "bans": 0, "reminders": 0}
    assert client.get(f"{API}/members/1/event-bans", headers=fresh).json()["total"] == 0
    assert client.get(f"{API}/members/1/summary", headers=fresh).json()["events"]["no_shows_90_days"] == 2


def test_only_no_shows_after_latest_ban_count(client, admin_h, world, clock):
    three_no_shows(client, admin_h, world, clock)
    clock.set(at(5, "12:00", month=12))  # the ban ended on 2026-12-04
    fresh = h(token_of(client))
    for day in ("2026-12-07", "2026-12-08", "2026-12-09"):
        shift_on(client, fresh, day)
        e = mk_event(client, fresh, date=day)
        publish(client, fresh, e["id"])
        register(client, fresh, e["id"], member_id=1)
    clock.set(at(7, "17:00", month=12))
    assert process(client, fresh)["bans"] == 0  # one new no-show; the three before the ban do not count again
    clock.set(at(9, "17:00", month=12))
    assert process(client, fresh) == {"completed_events": 2, "no_shows": 2, "bans": 1, "reminders": 0}
    bans = client.get(f"{API}/members/1/event-bans", headers=fresh).json()["items"]
    assert [(b["starts_on"], b["ends_on"]) for b in bans] == [("2026-11-05", "2026-12-04"), ("2026-12-09", "2027-01-07")]


# --- effects on other modules --------------------------------------------------------------------------------


def test_member_deactivation_cancels_registrations(client, admin_h, world, app):
    mk_event(client, admin_h, capacity=1, fee="10.00")
    publish(client, admin_h, 1)
    mh = world["mh"]
    register(client, mh[0], 1)
    register(client, mh[1], 1)
    assert client.post(f"{API}/members/1/deactivate", headers=admin_h).status_code == 200
    items = {i["member_id"]: i for i in regs_of_event(client, admin_h, 1)}
    assert (items[1]["status"], items[1]["cancel_reason"], items[1]["late_cancellation"]) == ("cancelled", "member_deactivated", False)
    assert items[2]["status"] == "registered"
    assert client.get(f"{API}/members/1/fees", headers=admin_h).json()["items"][0]["status"] == "open"  # fees stay
    assert [n.member_id for n in notifications(app, type_="event_promoted")] == [2]
    assert client.get(f"{API}/members/2/fees", headers=admin_h).json()["total"] == 1
    assert [n.type for n in notifications(app, 1)] == ["fee_created", "member_deactivated"]


def test_deactivation_ignores_started_events(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    register(client, world["mh"][0], 1)
    clock.set(at(5, "14:30"))
    client.post(f"{API}/members/1/deactivate", headers=admin_h)
    assert regs_of_event(client, admin_h, 1)[0]["status"] == "registered"


def test_member_summary(client, admin_h, world):
    mk_event(client, admin_h, capacity=1)
    mk_event(client, admin_h, start_time="09:00", end_time="10:00", capacity=1)
    publish(client, admin_h, 1)
    publish(client, admin_h, 2)
    mh = world["mh"]
    zero = {"registered": 0, "waitlisted": 0, "no_shows_90_days": 0, "banned_until": None}
    assert client.get(f"{API}/members/1/summary", headers=mh[0]).json()["events"] == zero
    register(client, mh[0], 1)
    register(client, mh[1], 1)
    register(client, mh[1], 2)
    assert client.get(f"{API}/members/2/summary", headers=mh[1]).json()["events"] == {**zero, "registered": 1, "waitlisted": 1}


def test_branch_deactivation_blocked_by_events(client, admin_h, world):
    mk_branch(client, admin_h, "B2")
    e = mk_event(client, admin_h, branch_id=2)
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/events/{e['id']}/cancel", headers=admin_h)
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200


def test_branch_deactivation_published_event(client, admin_h, world):
    mk_branch(client, admin_h, "B2")
    shift_on(client, admin_h, "2026-11-06", branch_id=2)
    e = mk_event(client, admin_h, branch_id=2, date="2026-11-06")
    publish(client, admin_h, e["id"])
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")


def test_staff_with_events_cannot_be_deactivated(client, admin_h, world):
    mk_event(client, admin_h)
    mk_event(client, admin_h, date="2026-11-06")
    e = err(client.patch(f"{API}/staff/1", headers=admin_h, json={"is_active": False}), 409, "STAFF_HAS_EVENTS")
    assert e["details"]["event_ids"] == [1, 2]
    client.post(f"{API}/events/1/cancel", headers=admin_h)
    err(client.patch(f"{API}/staff/1", headers=admin_h, json={"is_active": False}), 409, "STAFF_HAS_EVENTS")
    client.post(f"{API}/events/2/cancel", headers=admin_h)
    assert client.patch(f"{API}/staff/1", headers=admin_h, json={"is_active": False}).status_code == 200


def test_staff_with_started_event_can_be_deactivated(client, admin_h, world, clock):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    clock.set(at(5, "14:30"))
    assert client.patch(f"{API}/staff/1", headers=admin_h, json={"is_active": False}).status_code == 200


def test_user_deactivation_blocked_by_events(client, admin_h, world):
    mk_event(client, admin_h)
    err(client.patch(f"{API}/users/2", headers=admin_h, json={"is_active": False}), 409, "STAFF_HAS_EVENTS")


def test_room_use_blocks_bookings(client, admin_h, world):
    mk_room(client, admin_h, code="G1", kind="group", capacity=6)
    mk_room(client, admin_h, code="G2", kind="group", capacity=6)
    ev = mk_event(client, admin_h, room_id=1)
    mh = world["mh"]
    e = err(client.post(f"{API}/room-bookings", headers=mh[0], json={
        "room_id": 1, "date": "2026-11-05", "start_time": "15:00", "end_time": "16:00", "participant_ids": [2]}), 409, "ROOM_ALREADY_BOOKED")
    assert e["details"] == {"event_id": ev["id"]}
    book(client, mh[0], room_id=1, date="2026-11-05", start_time="16:00", end_time="17:00", participant_ids=[2])
    av = client.get(f"{API}/rooms/1/availability?date=2026-11-05", headers=mh[2]).json()
    slots = {s["start"]: s for s in av["slots"]}
    assert slots["14:00"]["free"] is False and slots["14:00"]["booking_id"] is None
    assert slots["15:30"]["free"] is False and slots["13:30"]["free"] is True and slots["16:00"]["free"] is False
    assert slots["16:00"]["booking_id"] is None and slots["17:30"]["free"] is True
    admin_slots = {s["start"]: s for s in client.get(f"{API}/rooms/1/availability?date=2026-11-05", headers=admin_h).json()["slots"]}
    assert admin_slots["14:00"]["booking_id"] is None and admin_slots["16:00"]["booking_id"] == 1

    def free(start, end):
        r = client.get(f"{API}/rooms/free?date=2026-11-05&start_time={start}&end_time={end}", headers=mh[0])
        return [x["id"] for x in r.json()["items"]]

    assert free("15:00", "15:30") == [2] and free("16:00", "17:00") == [2] and free("17:00", "18:00") == [1, 2]
    assert free("13:00", "14:00") == [1, 2]
    client.post(f"{API}/events/{ev['id']}/cancel", headers=admin_h)  # a cancelled event frees the room
    book(client, mh[1], room_id=1, date="2026-11-05", start_time="14:00", end_time="15:00", participant_ids=[3])
    assert free("15:00", "15:30") == [1, 2]


def test_attendance_report(client, admin_h, world, clock):
    mk_event(client, admin_h, capacity=2, fee="10.00")  # 1
    mk_event(client, admin_h, date="2026-11-06", capacity=2)  # 2: draft, not listed
    mk_event(client, admin_h, start_time="09:00", end_time="10:00", fee="5.00", kind="tour", capacity=3)  # 3
    publish(client, admin_h, 1)
    publish(client, admin_h, 3)
    mh = world["mh"]
    register(client, mh[0], 1)
    r2 = register(client, mh[1], 1)
    r3 = register(client, mh[2], 1)  # waitlisted
    register(client, mh[0], 3)
    register(client, mh[1], 3)
    clock.set(at(5, "09:30"))
    cancel_reg(client, mh[1], r2["id"])  # registered, less than 24 hours before the start: late; promotes member 3
    # a place is still taken at the start: member 1 attends, member 3 is a no-show
    clock.set(at(5, "14:00"))
    client.post(f"{API}/events/process", headers=admin_h)
    assert r3["id"]
    clock.set(at(5, "17:00"))
    process(client, admin_h)
    rep = client.get(f"{API}/reports/event-attendance?from=2026-11-01&to=2026-11-30", headers=admin_h).json()
    assert [e["event_id"] for e in rep["items"]] == [3, 1] and rep["total"] == 2
    assert rep["items"][1] == {"event_id": 1, "title": "Poetry night", "kind": "talk", "date": "2026-11-05", "status": "completed",
                               "capacity": 2, "registered": 2, "attended": 0, "no_shows": 2, "late_cancellations": 1, "fees_charged": "30.00"}
    assert rep["items"][0] == {"event_id": 3, "title": "Poetry night", "kind": "tour", "date": "2026-11-05", "status": "completed",
                               "capacity": 3, "registered": 2, "attended": 0, "no_shows": 2, "late_cancellations": 0, "fees_charged": "10.00"}
    assert client.get(f"{API}/reports/event-attendance?from=2026-11-01&to=2026-11-30&kind=tour", headers=admin_h).json()["total"] == 1
    assert client.get(f"{API}/reports/event-attendance?from=2026-11-01&to=2026-11-30&branch_id=2", headers=admin_h).json()["total"] == 0
    assert client.get(f"{API}/reports/event-attendance?from=2026-11-06&to=2026-11-30", headers=admin_h).json()["total"] == 0


@pytest.mark.parametrize(
    "query", ["", "?from=2026-11-01", "?to=2026-11-01", "?from=2026-11-05&to=2026-11-01", "?from=2025-01-01&to=2026-11-30", "?from=x&to=2026-11-01"]
)
def test_attendance_report_validation(client, admin_h, world, query):
    err(client.get(f"{API}/reports/event-attendance{query}", headers=admin_h), 422, "VALIDATION_ERROR")


def test_attendance_report_range_and_permissions(client, admin_h, world):
    assert client.get(f"{API}/reports/event-attendance?from=2025-11-14&to=2026-11-14", headers=admin_h).status_code == 200
    err(client.get(f"{API}/reports/event-attendance?from=2025-11-13&to=2026-11-14", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/event-attendance?from=2026-11-01&to=2026-11-30", headers=world["mh"][0]), 403, "FORBIDDEN")
    assert client.get(f"{API}/reports/event-attendance?from=2026-11-01&to=2026-11-30", headers=world["lh"]).status_code == 200


def test_fees_charged_ignores_waived(client, admin_h, world):
    mk_event(client, admin_h, fee="10.00", capacity=2)
    publish(client, admin_h, 1)
    register(client, world["mh"][0], 1)
    r2 = register(client, world["mh"][1], 1)
    cancel_reg(client, world["mh"][1], r2["id"])
    item = client.get(f"{API}/reports/event-attendance?from=2026-11-01&to=2026-11-30", headers=admin_h).json()["items"][0]
    assert item["fees_charged"] == "10.00" and item["registered"] == 1


def test_event_notification_fields(client, admin_h, world):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    register(client, world["mh"][0], 1)
    client.post(f"{API}/events/1/cancel", headers=admin_h)
    r = client.get(f"{API}/members/1/notifications?type=event_cancelled", headers=world["mh"][0]).json()
    assert r["total"] == 1 and r["items"][0]["event_id"] == 1
    for part in ("Poetry night", "14:00", "16:00", "2026-11-05"):
        assert part in r["items"][0]["message"]
    assert client.get(f"{API}/notifications?type=event_cancelled", headers=admin_h).json()["total"] == 1
    assert client.get(f"{API}/members/1/notifications", headers=world["mh"][0]).json()["items"][0]["event_id"] == 1


def test_registering_does_not_notify(client, admin_h, world, app):
    mk_event(client, admin_h)
    publish(client, admin_h, 1)
    r = register(client, world["mh"][0], 1)
    cancel_reg(client, world["mh"][0], r["id"])
    assert notifications(app) == []
