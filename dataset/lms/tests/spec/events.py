MODULE = "events"
TITLE = "module 20 (Events)"

HEADER = '''
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, balance, create_book, create_branch, deactivate_branch, deactivate_member, error_code, items, lend,
    member_fees, member_headers, pay, register_member, return_loan,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, WED, THU, FRI, SAT = "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); default branch hours 08:00-20:00


def at(clock, day, hh=9, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    clock.set(datetime(y, m, d, hh, mm, ss, tzinfo=TR))


def same(value, day, hh, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    return datetime.fromisoformat(value) == datetime(y, m, d, hh, mm, ss, tzinfo=TR)


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def err(r, status, code):
    assert r.status_code == status and error_code(r) == code, r.text
    return r.json()["error"]


def post(client, headers, path, body=None):
    return client.post(f"/api/v1/{path}", headers=headers, json=body)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def staff(client, admin, branch):
    """Id of a new active staff profile (module 19) with home ``branch``."""
    _seq[0] += 1
    email = f"evstaff{_seq[0]}@library.local"
    u = ok(post(client, admin, "users", {"email": email, "full_name": f"Staff {_seq[0]}", "role": "librarian", "password": "Staff12345"}), 201)
    p = ok(post(client, admin, "staff", {"user_id": u["id"], "home_branch_id": branch["id"], "employment": "full_time", "started_on": "2020-01-01"}), 201)
    return p["id"]


def shift(client, admin, staff_id, branch, day, start="08:00", end="18:00"):
    return ok(post(client, admin, "shifts", {"staff_id": staff_id, "branch_id": branch["id"], "date": day, "start_time": start, "end_time": end}), 201)


def on_shift(client, admin, branch, *days, start="08:00", end="18:00"):
    """A staff profile with a shift on each of ``days`` at ``branch``."""
    sid = staff(client, admin, branch)
    for day in days:
        shift(client, admin, sid, branch, day, start, end)
    return sid


def try_event(client, headers, branch, staff_id, *, day=WED, start="14:00", end="16:00", capacity=10, title=None, **fields):
    _seq[0] += 1
    body = {"title": title or f"Event {_seq[0]:03d}", "kind": "talk", "branch_id": branch["id"], "date": day,
            "start_time": start, "end_time": end, "capacity": capacity, "staff_id": staff_id}
    body.update(fields)
    return client.post("/api/v1/events", headers=headers, json=body)


def event(client, headers, branch, staff_id, **kw):
    return ok(try_event(client, headers, branch, staff_id, **kw), 201)


def publish(client, headers, event_id):
    return post(client, headers, f"events/{event_id}/publish")


def published(client, lib, branch, staff_id, **kw):
    ev = event(client, lib, branch, staff_id, **kw)
    return ok(publish(client, lib, ev["id"]))


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def reg(client, headers, event_id, member_id=None):
    return post(client, headers, f"events/{event_id}/registrations", {} if member_id is None else {"member_id": member_id})


def register(client, lib, event_id, member_):
    return ok(reg(client, lib, event_id, member_["id"]), 201)


def cancel_reg(client, headers, registration_id):
    return post(client, headers, f"event-registrations/{registration_id}/cancel")


def regs_of(client, lib, event_id, **params):
    return items(get(client, lib, f"events/{event_id}/registrations", **params))


def reg_of(client, lib, event_id, member_id):
    return [x for x in regs_of(client, lib, event_id) if x["member_id"] == member_id][0]


def group_room(client, admin, branch, capacity=6):
    _seq[0] += 1
    return ok(post(client, admin, "rooms", {"branch_id": branch["id"], "code": f"G{_seq[0]}", "name": f"Group {_seq[0]}", "kind": "group",
              "opens_at": "08:00", "closes_at": "20:00", "capacity": capacity, "min_participants": 2}), 201)


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def fees_of(client, lib, member_id):
    return [(f["kind"], f["amount"], f["status"]) for f in items(member_fees(client, lib, member_id))]


def process(client, lib):
    return ok(post(client, lib, "events/process"))


def debt(client, lib, branch, member_, amount="50.00"):
    copy = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch["id"])
    loan = lend(client, lib, member_["id"], copy["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=amount)
'''


CASES = [
    # ---------------------------------------------------------------- events
    dict(id="T-EVT-01-a", req="LIB-EVT-01", type="Normal", input="Librarian creates a talk on Wed 14:00–16:00, capacity 10, without description, room, fee, audience", expected="201 `draft`; fee 0.00, audience `all`, room and series null", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    e = event(client, librarian, branch_a, sid, title="Yazar Söyleşisi")
    assert (e["title"], e["kind"], e["status"], e["fee"], e["audience"], e["room_id"], e["series_id"], e["capacity"], e["staff_id"]) == ("Yazar Söyleşisi", "talk", "draft", "0.00", "all", None, None, 10, sid)
    assert (e["date"], e["start_time"], e["end_time"]) == (WED, "14:00", "16:00")
'''),
    dict(id="T-EVT-01-b", req="LIB-EVT-01", type="Error", input="30 minutes; 4.5 hours; capacity 0 and 201; fee 200.01; kind `concert`; an individual room; a room of another branch; capacity 7 in a room for 6; unknown staff; member creates", expected="`422` ten times; `403`", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    sid = staff(client, admin, branch_a)
    indiv = ok(post(client, admin, "rooms", {"branch_id": branch_a["id"], "code": "IND1", "name": "Single", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}), 201)
    small, other = group_room(client, admin, branch_a, 6), group_room(client, admin, branch_b)
    bad = [dict(end="14:30"), dict(end="18:30"), dict(capacity=0), dict(capacity=201), dict(fee="200.01"), dict(kind="concert"),
           dict(room_id=indiv["id"]), dict(room_id=other["id"]), dict(room_id=small["id"], capacity=7)]
    for fields in bad:
        assert try_event(client, librarian, branch_a, sid, **fields).status_code == 422, fields
    assert try_event(client, librarian, branch_a, 999999).status_code == 422
    assert try_event(client, member_headers(client, member(client, librarian, branch_a)), branch_a, sid).status_code == 403
'''),
    dict(id="T-EVT-02-a", req="LIB-EVT-02", type="Error", input="Event yesterday; on Saturday; Wed 19:00–21:00; in an inactive room", expected="`EVENT_IN_PAST`; `BRANCH_NOT_OPEN` with reason `weekend`; `OUTSIDE_BRANCH_HOURS`; `ROOM_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    err(try_event(client, librarian, branch_a, sid, day="2026-10-30"), 409, "EVENT_IN_PAST")
    assert err(try_event(client, librarian, branch_a, sid, day=SAT), 409, "BRANCH_NOT_OPEN")["details"]["reason"] == "weekend"
    err(try_event(client, librarian, branch_a, sid, start="19:00", end="21:00"), 409, "OUTSIDE_BRANCH_HOURS")
    r = group_room(client, admin, branch_a)
    ok(client.patch(f"/api/v1/rooms/{r['id']}", headers=admin, json={"is_active": False}))
    err(try_event(client, librarian, branch_a, sid, room_id=r["id"], capacity=6), 409, "ROOM_INACTIVE")
'''),
    dict(id="T-EVT-02-b", req="LIB-EVT-02", type="Boundary", input="Group room booked Wed 14:00–15:00; event in that room 14:00–16:00; event 15:00–17:00; another event 16:00–17:00", expected="`ROOM_NOT_AVAILABLE` with `details.booking_id`; 201; `ROOM_NOT_AVAILABLE` with `details.event_id`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    r = group_room(client, admin, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = ok(post(client, librarian, "room-bookings", {"room_id": r["id"], "date": WED, "start_time": "14:00", "end_time": "15:00", "member_id": m1["id"], "participant_ids": [m2["id"]]}), 201)
    assert err(try_event(client, librarian, branch_a, sid, room_id=r["id"], capacity=6), 409, "ROOM_NOT_AVAILABLE")["details"]["booking_id"] == b["id"]
    e = event(client, librarian, branch_a, sid, room_id=r["id"], capacity=6, start="15:00", end="17:00")
    assert err(try_event(client, librarian, branch_a, sid, room_id=r["id"], capacity=6, start="16:00", end="17:00"), 409, "ROOM_NOT_AVAILABLE")["details"]["event_id"] == e["id"]
'''),
    dict(id="T-EVT-02-c", req="LIB-EVT-02", type="Error", input="Inactive staff profile; inactive branch (no staff home)", expected="`STAFF_INACTIVE`; `BRANCH_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    ok(client.patch(f"/api/v1/staff/{sid}", headers=admin, json={"is_active": False}))
    err(try_event(client, librarian, branch_a, sid), 409, "STAFF_INACTIVE")
    qq = create_branch(client, admin, "QQ")
    deactivate_branch(client, admin, qq["id"])
    err(try_event(client, librarian, qq, staff(client, admin, branch_a)), 409, "BRANCH_INACTIVE")
'''),
    dict(id="T-EVT-03-a", req="LIB-EVT-03", type="Normal", input="Staff on shift Wed 08:00–18:00; event Wed 14:00–16:00 published; published again", expected="200 `published` with `published_at`; `409 INVALID_EVENT_STATUS` with `details.status` `published`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    e = event(client, librarian, branch_a, sid)
    out = ok(publish(client, librarian, e["id"]))
    assert out["status"] == "published" and same(out["published_at"], MON, 9)
    assert err(publish(client, librarian, e["id"]), 409, "INVALID_EVENT_STATUS")["details"]["status"] == "published"
'''),
    dict(id="T-EVT-03-b", req="LIB-EVT-03", type="Error", input="Event Wed 14:00–16:00: staff without a shift; staff with a shift 10:00–15:00; staff with a shift at another branch 08:00–18:00", expected="`409 STAFF_NOT_ON_SHIFT` each", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    for sid in (staff(client, admin, branch_a), on_shift(client, admin, branch_a, WED, start="10:00", end="15:00"), on_shift(client, admin, branch_b, WED)):
        e = event(client, librarian, branch_a, sid)
        err(publish(client, librarian, e["id"]), 409, "STAFF_NOT_ON_SHIFT")
'''),
    dict(id="T-EVT-03-c", req="LIB-EVT-03", type="Boundary", input="Now Mon 09:00; events Tue 09:00–10:00 and Tue 08:30–09:30 (staff on shift Tue 08:00–12:00)", expected="First published (exactly 24 hours); second `409 EVENT_TOO_SOON`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, TUE, start="08:00", end="12:00")
    ok(publish(client, librarian, event(client, librarian, branch_a, sid, day=TUE, start="09:00", end="10:00")["id"]))
    e = event(client, librarian, branch_a, sid, day=TUE, start="08:30", end="09:30")
    err(publish(client, librarian, e["id"]), 409, "EVENT_TOO_SOON")
'''),
    dict(id="T-EVT-04-a", req="LIB-EVT-04", type="Error", input="PATCH title and capacity of a draft; PATCH `audience`; PATCH a cancelled event", expected="200; `422`; `409 INVALID_EVENT_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    e = event(client, librarian, branch_a, sid)
    out = ok(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"title": "Yeni Başlık", "capacity": 20}))
    assert (out["title"], out["capacity"]) == ("Yeni Başlık", 20)
    assert client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"audience": "students"}).status_code == 422
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    err(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"title": "X"}), 409, "INVALID_EVENT_STATUS")
'''),
    dict(id="T-EVT-04-b", req="LIB-EVT-04", type="Error", input="Published event Wed 14:00–16:00 (staff shift 08:00–18:00) moved to 17:00–19:00", expected="`409 STAFF_NOT_ON_SHIFT`; the event keeps its times", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    err(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"start_time": "17:00", "end_time": "19:00"}), 409, "STAFF_NOT_ON_SHIFT")
    assert get(client, librarian, f"events/{e['id']}")["start_time"] == "14:00"
'''),
    dict(id="T-EVT-05-a", req="LIB-EVT-05", type="Error", input="Fee changed to 15.00 before any registration; after a registration changed to 20.00", expected="200; `409 FEE_LOCKED`", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    assert ok(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"fee": "15.00"}))["fee"] == "15.00"
    register(client, librarian, e["id"], member(client, librarian, branch_a))
    err(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"fee": "20.00"}), 409, "FEE_LOCKED")
'''),
    dict(id="T-EVT-06-a", req="LIB-EVT-06", type="Normal", input="Capacity 2: M1, M2 registered, M3 waiting; capacity set to 1; then to 3", expected="`409 CAPACITY_BELOW_REGISTERED` with `details.registered` 2; then 200 and M3 `registered`", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=2)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    for m in (m1, m2, m3):
        register(client, librarian, e["id"], m)
    url = f"/api/v1/events/{e['id']}"
    assert err(client.patch(url, headers=librarian, json={"capacity": 1}), 409, "CAPACITY_BELOW_REGISTERED")["details"]["registered"] == 2
    ok(client.patch(url, headers=librarian, json={"capacity": 3}))
    assert reg_of(client, librarian, e["id"], m3["id"])["status"] == "registered"
'''),
    dict(id="T-EVT-07-a", req="LIB-EVT-07", type="Normal", input="Published event with M1 registered and M2 waiting (capacity 1); start moved to 15:00–16:00", expected="One `event_changed` notification each for M1 and M2", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    ok(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"start_time": "15:00"}))
    assert [len(notes(client, librarian, m["id"], "event_changed")) for m in (m1, m2)] == [1, 1]
'''),
    dict(id="T-EVT-08-a", req="LIB-EVT-08", type="Normal", input="Published E2 (Thu, capacity 2, one registration), published E1 (Wed, workshop), draft D (Wed); member and librarian list", expected="Member: E1, E2; librarian: E1, D, E2 (by date and time); `kind=workshop` → E1; E2 `registered` 1, `free_places` 1", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED, THU)
    e2 = published(client, librarian, branch_a, sid, day=THU, capacity=2)
    e1 = published(client, librarian, branch_a, sid, start="10:00", end="11:00", kind="workshop")
    d = event(client, librarian, branch_a, sid, start="12:00", end="13:00")
    m = member(client, librarian, branch_a)
    register(client, librarian, e2["id"], m)
    mh = member_headers(client, m)
    assert [x["id"] for x in items(get(client, mh, "events"))] == [e1["id"], e2["id"]]
    assert [x["id"] for x in items(get(client, librarian, "events"))] == [e1["id"], d["id"], e2["id"]]
    assert [x["id"] for x in items(get(client, librarian, "events", kind="workshop"))] == [e1["id"]]
    row = get(client, mh, f"events/{e2['id']}")
    assert (row["registered"], row["waitlisted"], row["free_places"]) == (1, 0, 1)
'''),
    dict(id="T-EVT-08-b", req="LIB-EVT-08", type="Error", input="Member reads a draft event", expected="`404 NOT_FOUND`", code='''
def TEST(client, admin, librarian, branch_a):
    d = event(client, librarian, branch_a, staff(client, admin, branch_a))
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/events/{d['id']}", headers=mh).status_code == 404
'''),
    dict(id="T-EVT-09-a", req="LIB-EVT-09", type="Normal", input="Published event; the staff member's shift is cancelled afterwards", expected="`staff_covered` true, then false; the event stays `published`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    s = shift(client, admin, sid, branch_a, WED)
    e = published(client, librarian, branch_a, sid)
    assert get(client, librarian, f"events/{e['id']}")["staff_covered"] is True
    ok(post(client, admin, f"shifts/{s['id']}/cancel"))
    out = get(client, librarian, f"events/{e['id']}")
    assert (out["staff_covered"], out["status"]) == (False, "published")
'''),
    dict(id="T-EVT-10-a", req="LIB-EVT-10", type="Normal", input="Event with fee 20.00, capacity 1: M1 registered (fee open), M2 waiting; librarian cancels the event", expected="Event `cancelled` (`staff_request`); both registrations `cancelled` with `event_cancelled`; M1's fee `waived`; one `event_cancelled` notification each", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, fee="20.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    out = ok(post(client, librarian, f"events/{e['id']}/cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_request")
    assert [(x["status"], x["cancel_reason"]) for x in regs_of(client, librarian, e["id"])] == [("cancelled", "event_cancelled")] * 2
    assert fees_of(client, librarian, m1["id"]) == [("event_fee", "20.00", "waived")]
    assert [len(notes(client, librarian, m["id"], "event_cancelled")) for m in (m1, m2)] == [1, 1]
'''),
    dict(id="T-EVT-10-b", req="LIB-EVT-10", type="Error", input="Cancel a cancelled event; member cancels an event", expected="`409 INVALID_EVENT_STATUS`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    e = event(client, librarian, branch_a, staff(client, admin, branch_a))
    assert post(client, member_headers(client, member(client, librarian, branch_a)), f"events/{e['id']}/cancel").status_code == 403
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    err(post(client, librarian, f"events/{e['id']}/cancel"), 409, "INVALID_EVENT_STATUS")
'''),
    dict(id="T-EVT-11-a", req="LIB-EVT-11", type="Normal", input="Draft event in a group room Wed 14:00–16:00; a room booking 15:00–16:00; availability; free rooms 14:00–15:00", expected="`409 ROOM_ALREADY_BOOKED` with `details.event_id`; slots 14:00–15:30 not free with `booking_id` null; the room is not listed", code='''
def TEST(client, admin, librarian, branch_a):
    r = group_room(client, admin, branch_a)
    e = event(client, librarian, branch_a, staff(client, admin, branch_a), room_id=r["id"], capacity=6)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    body = {"room_id": r["id"], "date": WED, "start_time": "15:00", "end_time": "16:00", "member_id": m1["id"], "participant_ids": [m2["id"]]}
    assert err(post(client, librarian, "room-bookings", body), 409, "ROOM_ALREADY_BOOKED")["details"]["event_id"] == e["id"]
    slots = {s["start"]: s for s in get(client, librarian, f"rooms/{r['id']}/availability", date=WED)["slots"]}
    assert [(slots[t]["free"], slots[t]["booking_id"]) for t in ("14:00", "15:30", "16:00")] == [(False, None), (False, None), (True, None)]
    free = items(get(client, librarian, "rooms/free", date=WED, start_time="14:00", end_time="15:00", branch_id=branch_a["id"]))
    assert r["id"] not in [x["id"] for x in free]
'''),
    dict(id="T-EVT-12-a", req="LIB-EVT-12", type="Normal", input="Published event Wed with M registered; draft event Wed; closure of the branch on Wed", expected="`cancelled_events` 2; events `cancelled` with `branch_closed`; M's registration `cancelled` (`event_cancelled`) and one `event_cancelled` notification", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    e = published(client, librarian, branch_a, sid)
    d = event(client, librarian, branch_a, sid, start="10:00", end="11:00")
    m = member(client, librarian, branch_a)
    register(client, librarian, e["id"], m)
    c = ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": WED, "reason": "Sayım"}), 201)
    assert c["cancelled_events"] == 2
    assert [get(client, librarian, f"events/{x['id']}")["cancel_reason"] for x in (e, d)] == ["branch_closed", "branch_closed"]
    assert reg_of(client, librarian, e["id"], m["id"])["cancel_reason"] == "event_cancelled"
    assert len(notes(client, librarian, m["id"], "event_cancelled")) == 1
'''),
    # ---------------------------------------------------------------- series
    dict(id="T-EVT-13-a", req="LIB-EVT-13", type="Normal", input="Series of 3 weeks from Tue 2026-11-10, 18:00–19:00, book club", expected="201: 3 draft events on 11-10, 11-17, 11-24 with the same `series_id`; `skipped` empty", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    body = {"title": "Kitap Kulübü", "kind": "book_club", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "18:00",
            "end_time": "19:00", "capacity": 12, "staff_id": sid, "weeks": 3}
    out = ok(post(client, librarian, "event-series", body), 201)
    assert out["skipped"] == [] and len(out["created"]) == 3
    evs = [get(client, librarian, f"events/{i}") for i in out["created"]]
    assert [(x["date"], x["status"], x["series_id"]) for x in evs] == [(d, "draft", out["series_id"]) for d in ("2026-11-10", "2026-11-17", "2026-11-24")]
'''),
    dict(id="T-EVT-13-b", req="LIB-EVT-13", type="Error", input="Series with `weeks` 1 and 13", expected="`422` both", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    for weeks in (1, 13):
        body = {"title": "Seri", "kind": "talk", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "18:00", "end_time": "19:00", "capacity": 5, "staff_id": sid, "weeks": weeks}
        assert post(client, librarian, "event-series", body).status_code == 422
'''),
    dict(id="T-EVT-14-a", req="LIB-EVT-14", type="Error", input="Series of 2 weeks starting on Saturday 2026-11-07 (every date fails)", expected="`409 SERIES_EMPTY`; no event is created", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    body = {"title": "Hafta sonu", "kind": "talk", "branch_id": branch_a["id"], "first_date": SAT, "start_time": "10:00", "end_time": "11:00", "capacity": 5, "staff_id": sid, "weeks": 2}
    err(post(client, librarian, "event-series", body), 409, "SERIES_EMPTY")
    assert get(client, librarian, "events")["total"] == 0
'''),
    dict(id="T-EVT-15-a", req="LIB-EVT-15", type="Normal", input="Series of 4 weeks from Tue 2026-11-10; closure of the branch on Tue 2026-11-24", expected="Created 11-10, 11-17, 12-01; skipped `{date 2026-11-24, error_code BRANCH_NOT_OPEN}`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": "2026-11-24", "reason": "Sayım"}), 201)
    body = {"title": "Atölye", "kind": "workshop", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "14:00", "end_time": "16:00", "capacity": 8, "staff_id": sid, "weeks": 4}
    out = ok(post(client, librarian, "event-series", body), 201)
    assert [get(client, librarian, f"events/{i}")["date"] for i in out["created"]] == ["2026-11-10", "2026-11-17", "2026-12-01"]
    assert out["skipped"] == [{"date": "2026-11-24", "error_code": "BRANCH_NOT_OPEN"}]
'''),
    dict(id="T-EVT-16-a", req="LIB-EVT-16", type="Normal", input="Series of 2 weeks (staff on shift both Tuesdays); the first event is published", expected="First `published`, second still `draft`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, "2026-11-10", "2026-11-17")
    body = {"title": "Seri", "kind": "talk", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "14:00", "end_time": "15:00", "capacity": 5, "staff_id": sid, "weeks": 2}
    first, second = ok(post(client, librarian, "event-series", body), 201)["created"]
    ok(publish(client, librarian, first))
    assert [get(client, librarian, f"events/{i}")["status"] for i in (first, second)] == ["published", "draft"]
'''),
    dict(id="T-EVT-17-a", req="LIB-EVT-17", type="Normal", input="Series of 3 weeks from Wed 2026-11-04 14:00 (first published); on Wed 15:00 the series is cancelled; unknown series", expected="`cancelled` lists the 2nd and 3rd events (`series_cancelled`); the first is unchanged; `404`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    body = {"title": "Seri", "kind": "talk", "branch_id": branch_a["id"], "first_date": WED, "start_time": "14:00", "end_time": "16:00", "capacity": 5, "staff_id": sid, "weeks": 3}
    out = ok(post(client, librarian, "event-series", body), 201)
    ok(publish(client, librarian, out["created"][0]))
    at(clock, WED, 15)
    res = ok(post(client, librarian, f"event-series/{out['series_id']}/cancel"))
    assert sorted(res["cancelled"]) == sorted(out["created"][1:])
    assert get(client, librarian, f"events/{out['created'][0]}")["status"] == "published"
    assert get(client, librarian, f"events/{out['created'][1]}")["cancel_reason"] == "series_cancelled"
    assert post(client, librarian, "event-series/999999/cancel").status_code == 404
'''),
    dict(id="T-EVT-18-a", req="LIB-EVT-18", type="Normal", input="Both events of a 2-week series published; a member registers for the first", expected="The member has one registration", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, "2026-11-10", "2026-11-17")
    body = {"title": "Seri", "kind": "talk", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "14:00", "end_time": "15:00", "capacity": 5, "staff_id": sid, "weeks": 2}
    ids = ok(post(client, librarian, "event-series", body), 201)["created"]
    for i in ids:
        ok(publish(client, librarian, i))
    m = member(client, librarian, branch_a)
    register(client, librarian, ids[0], m)
    assert get(client, librarian, f"members/{m['id']}/event-registrations")["total"] == 1
'''),
    # ---------------------------------------------------------------- registrations
    dict(id="T-EVT-19-a", req="LIB-EVT-19", type="Normal", input="Capacity 1: member registers herself; librarian registers a second member", expected="201 `registered` (position null); 201 `waitlisted` with position 1", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = ok(reg(client, member_headers(client, m1), e["id"]), 201)
    assert (r1["event_id"], r1["member_id"], r1["status"], r1["position"]) == (e["id"], m1["id"], "registered", None)
    r2 = register(client, librarian, e["id"], m2)
    assert (r2["status"], r2["position"]) == ("waitlisted", 1)
'''),
    dict(id="T-EVT-19-b", req="LIB-EVT-19", type="Error", input="Librarian without `member_id`; member with `member_id`", expected="`422` both", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    m = member(client, librarian, branch_a)
    assert reg(client, librarian, e["id"]).status_code == 422
    assert reg(client, member_headers(client, m), e["id"], m["id"]).status_code == 422
'''),
    dict(id="T-EVT-20-a", req="LIB-EVT-20", type="Error", input="Registration for a draft; for a cancelled event; a passive member for a draft", expected="`409 EVENT_NOT_OPEN` each", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    d = event(client, librarian, branch_a, sid)
    c = published(client, librarian, branch_a, sid, start="10:00", end="11:00")
    ok(post(client, librarian, f"events/{c['id']}/cancel"))
    m, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    for ev, mm in ((d, m), (c, m), (d, p)):
        err(reg(client, librarian, ev["id"], mm["id"]), 409, "EVENT_NOT_OPEN")
'''),
    dict(id="T-EVT-20-b", req="LIB-EVT-20", type="Error", input="Passive member; event on Tue 2027-11-02 for a member whose membership ends 2027-11-01", expected="`409 MEMBER_PASSIVE`; `409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED, "2027-11-02")
    e = published(client, librarian, branch_a, sid)
    late = published(client, librarian, branch_a, sid, day="2027-11-02")
    p, m = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(reg(client, librarian, e["id"], p["id"]), 409, "MEMBER_PASSIVE")
    err(reg(client, librarian, late["id"], m["id"]), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-EVT-20-c", req="LIB-EVT-20", type="Boundary", input="Member with debt 50.00; member with debt 49.99", expected="`409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` \"50.00\"; 201", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(reg(client, librarian, e["id"], m1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(reg(client, librarian, e["id"], m2["id"]), 201)
'''),
    dict(id="T-EVT-20-d", req="LIB-EVT-20", type="Error", input="Member registers twice (registered); a waiting member registers again", expected="`409 ALREADY_REGISTERED` both", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    err(reg(client, librarian, e["id"], m1["id"]), 409, "ALREADY_REGISTERED")
    err(reg(client, librarian, e["id"], m2["id"]), 409, "ALREADY_REGISTERED")
'''),
    dict(id="T-EVT-20-e", req="LIB-EVT-20", type="Boundary", input="Student registered for 5 upcoming events registers for a sixth", expected="`409 EVENT_REGISTRATION_LIMIT_REACHED` with `details.limit` 5", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    evs = [published(client, librarian, branch_a, sid, start=f"{h:02d}:00", end=f"{h + 1:02d}:00") for h in range(8, 14)]
    m = member(client, librarian, branch_a)
    for e in evs[:5]:
        register(client, librarian, e["id"], m)
    assert err(reg(client, librarian, evs[5]["id"], m["id"]), 409, "EVENT_REGISTRATION_LIMIT_REACHED")["details"]["limit"] == 5
'''),
    dict(id="T-EVT-20-f", req="LIB-EVT-20", type="Boundary", input="Capacity 1: M1 registered, M2 waiting; M3 registers", expected="`409 WAITLIST_FULL`", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    err(reg(client, librarian, e["id"], m3["id"]), 409, "WAITLIST_FULL")
'''),
    dict(id="T-EVT-21-a", req="LIB-EVT-21", type="Normal", input="Fee 25.00, capacity 1: M1 registers, M2 waits; M1 cancels in time", expected="M1 gets an `event_fee` 25.00 with `event_registration_id` (= `fee_id`); M2 no fee until promoted, then 25.00", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, fee="25.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = register(client, librarian, e["id"], m1)
    register(client, librarian, e["id"], m2)
    fee = items(member_fees(client, librarian, m1["id"]))[0]
    assert (fee["kind"], fee["amount"], fee["event_registration_id"], fee["id"]) == ("event_fee", "25.00", r1["id"], r1["fee_id"])
    assert member_fees(client, librarian, m2["id"])["total"] == 0
    ok(cancel_reg(client, librarian, r1["id"]))
    assert fees_of(client, librarian, m2["id"]) == [("event_fee", "25.00", "open")]
'''),
    dict(id="T-EVT-22-a", req="LIB-EVT-22", type="Normal", input="Capacity 1: M2 registered at 09:00, M3 waiting, M1 cancelled; list of the event; M3's own list", expected="Order M2 (registered), M3 (waitlisted), M1 (cancelled); `status=waitlisted` → M3; M3's list has `event_title`", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, title="Şiir Akşamı")
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    r1 = register(client, librarian, e["id"], m1)
    ok(cancel_reg(client, librarian, r1["id"]))
    register(client, librarian, e["id"], m2); register(client, librarian, e["id"], m3)
    assert [x["member_id"] for x in regs_of(client, librarian, e["id"])] == [m2["id"], m3["id"], m1["id"]]
    assert [x["member_id"] for x in regs_of(client, librarian, e["id"], status="waitlisted")] == [m3["id"]]
    own = items(get(client, member_headers(client, m3), f"members/{m3['id']}/event-registrations"))
    assert [(x["event_title"], x["event_date"], x["start_time"]) for x in own] == [("Şiir Akşamı", WED, "14:00")]
'''),
    dict(id="T-EVT-23-a", req="LIB-EVT-23", type="Normal", input="Capacity 2: M1, M2 registered; M3, M4 waiting; M2 cancels", expected="M3 `registered` with `promoted_at`; M4 `waitlisted` position 1; one `event_promoted` notification for M3", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=2)
    ms = [member(client, librarian, branch_a) for _ in range(4)]
    rs = [register(client, librarian, e["id"], m) for m in ms]
    assert [(r["status"], r["position"]) for r in rs] == [("registered", None), ("registered", None), ("waitlisted", 1), ("waitlisted", 2)]
    ok(cancel_reg(client, member_headers(client, ms[1]), rs[1]["id"]))
    r3, r4 = reg_of(client, librarian, e["id"], ms[2]["id"]), reg_of(client, librarian, e["id"], ms[3]["id"])
    assert r3["status"] == "registered" and r3["promoted_at"] is not None and (r4["status"], r4["position"]) == ("waitlisted", 1)
    assert len(notes(client, librarian, ms[2]["id"], "event_promoted")) == 1
'''),
    dict(id="T-EVT-24-a", req="LIB-EVT-24", type="Normal", input="Audience `students`: a student and an academic register; audience `all`: a guest; audience `academics`: a staff member (membership type `staff`)", expected="201; `409 EVENT_NOT_FOR_TYPE`; 201; `409 EVENT_NOT_FOR_TYPE`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    stu = published(client, librarian, branch_a, sid, audience="students", start="10:00", end="11:00")
    allx = published(client, librarian, branch_a, sid, start="12:00", end="13:00")
    aca = published(client, librarian, branch_a, sid, audience="academics", start="14:00", end="15:00")
    s, a = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    g, st = member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a, membership_type="staff")
    ok(reg(client, librarian, stu["id"], s["id"]), 201)
    err(reg(client, librarian, stu["id"], a["id"]), 409, "EVENT_NOT_FOR_TYPE")
    ok(reg(client, librarian, allx["id"], g["id"]), 201)
    err(reg(client, librarian, aca["id"], st["id"]), 409, "EVENT_NOT_FOR_TYPE")
'''),
    dict(id="T-EVT-25-a", req="LIB-EVT-25", type="Boundary", input="M registered for Wed 14:00–16:00; registers for 15:30–17:00, then 16:00–17:00; M waiting for a full event 10:00–12:00, then registers for 11:00–12:00", expected="`409 EVENT_TIME_CONFLICT` with `details.event_id`; 201; the waiting registration causes no conflict", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED, start="09:00", end="18:00")
    e1 = published(client, librarian, branch_a, sid)
    e2 = published(client, librarian, branch_a, sid, start="15:30", end="17:00")
    e3 = published(client, librarian, branch_a, sid, start="16:00", end="17:00")
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e1["id"], m)
    assert err(reg(client, librarian, e2["id"], m["id"]), 409, "EVENT_TIME_CONFLICT")["details"]["event_id"] == e1["id"]
    ok(reg(client, librarian, e3["id"], m["id"]), 201)
    full = published(client, librarian, branch_a, sid, start="10:00", end="12:00", capacity=1)
    register(client, librarian, full["id"], other)
    assert register(client, librarian, full["id"], m)["status"] == "waitlisted"
    ok(reg(client, librarian, published(client, librarian, branch_a, sid, start="11:00", end="12:00")["id"], m["id"]), 201)
'''),
    dict(id="T-EVT-26-a", req="LIB-EVT-26", type="Boundary", input="Event Tue 18:00–19:00 (staff on shift 10:00–20:00); registrations at Tue 16:59 and 17:00", expected="201; `409 REGISTRATION_CLOSED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, TUE, start="10:00", end="20:00"), day=TUE, start="18:00", end="19:00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 16, 59)
    ok(reg(client, librarian, e["id"], m1["id"]), 201)
    at(clock, TUE, 17, 0)
    err(reg(client, librarian, e["id"], m2["id"]), 409, "REGISTRATION_CLOSED")
'''),
    # ---------------------------------------------------------------- cancellation, attendance
    dict(id="T-EVT-27-a", req="LIB-EVT-27", type="Normal", input="Member cancels own registration; cancels again; another member cancels a registration", expected="200 `cancelled`, `member_request`, `cancelled_at`; `409 REGISTRATION_NOT_ACTIVE`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r = register(client, librarian, e["id"], m)
    r2 = register(client, librarian, e["id"], other)
    mh = member_headers(client, m)
    assert cancel_reg(client, mh, r2["id"]).status_code == 403
    out = ok(cancel_reg(client, mh, r["id"]))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "member_request") and same(out["cancelled_at"], MON, 9)
    err(cancel_reg(client, mh, r["id"]), 409, "REGISTRATION_NOT_ACTIVE")
'''),
    dict(id="T-EVT-27-b", req="LIB-EVT-27", type="Error", input="Librarian cancels a registration at Wed 14:00 (event started)", expected="`409 EVENT_STARTED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    r = register(client, librarian, e["id"], member(client, librarian, branch_a))
    at(clock, WED, 14)
    err(cancel_reg(client, librarian, r["id"]), 409, "EVENT_STARTED")
'''),
    dict(id="T-EVT-28-a", req="LIB-EVT-28", type="Normal", input="Fee 30.00; member cancels on Mon (more than 24 hours before Wed 14:00)", expected="Fee `waived`; `late_cancellation` false", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), fee="30.00")
    m = member(client, librarian, branch_a)
    r = register(client, librarian, e["id"], m)
    assert ok(cancel_reg(client, member_headers(client, m), r["id"]))["late_cancellation"] is False
    assert fees_of(client, librarian, m["id"]) == [("event_fee", "30.00", "waived")]
'''),
    dict(id="T-EVT-29-a", req="LIB-EVT-29", type="Normal", input="Fee 30.00, capacity 1: M1 registered, M2 waiting; both cancel on Wed 10:00", expected="M1 `late_cancellation` true and fee stays `open`; M2 `late_cancellation` false", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), fee="30.00", capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = register(client, librarian, e["id"], m1), register(client, librarian, e["id"], m2)
    at(clock, WED, 10)
    out2 = ok(cancel_reg(client, librarian, r2["id"]))
    out1 = ok(cancel_reg(client, librarian, r1["id"]))
    assert (out1["late_cancellation"], out2["late_cancellation"]) == (True, False)
    assert fees_of(client, librarian, m1["id"]) == [("event_fee", "30.00", "open")]
'''),
    dict(id="T-EVT-30-a", req="LIB-EVT-30", type="Boundary", input="Event Thu 18:00–19:00, fee 10.00; M1 cancels at Wed 18:00, M2 at Wed 18:00:01", expected="M1 in time (fee `waived`); M2 late (fee `open`)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, THU, start="10:00", end="20:00"), day=THU, start="18:00", end="19:00", fee="10.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = register(client, librarian, e["id"], m1), register(client, librarian, e["id"], m2)
    at(clock, WED, 18, 0, 0)
    assert ok(cancel_reg(client, librarian, r1["id"]))["late_cancellation"] is False
    at(clock, WED, 18, 0, 1)
    assert ok(cancel_reg(client, librarian, r2["id"]))["late_cancellation"] is True
    assert (fees_of(client, librarian, m1["id"])[0][2], fees_of(client, librarian, m2["id"])[0][2]) == ("waived", "open")
'''),
    dict(id="T-EVT-31-a", req="LIB-EVT-31", type="Boundary", input="Capacity 1: M1 registered, M2 waiting; M1 cancels at Wed 13:01 (event 14:00)", expected="M2 stays `waitlisted` (no promotion in the last hour)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = register(client, librarian, e["id"], m1)
    register(client, librarian, e["id"], m2)
    at(clock, WED, 13, 1)
    ok(cancel_reg(client, librarian, r1["id"]))
    assert reg_of(client, librarian, e["id"], m2["id"])["status"] == "waitlisted"
'''),
    dict(id="T-EVT-32-a", req="LIB-EVT-32", type="Boundary", input="Event Wed 14:00–16:00: check-in at 13:29 and 13:30; another at 16:00; a waiting registration", expected="`409 CHECK_IN_NOT_OPEN`; 200 `attended`; `409 EVENT_OVER`; `409 REGISTRATION_NOT_ACTIVE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=2)
    ms = [member(client, librarian, branch_a) for _ in range(3)]
    r1, r2, r3 = (register(client, librarian, e["id"], m) for m in ms)
    at(clock, WED, 13, 29)
    err(post(client, librarian, f"event-registrations/{r1['id']}/check-in"), 409, "CHECK_IN_NOT_OPEN")
    at(clock, WED, 13, 30)
    out = ok(post(client, librarian, f"event-registrations/{r1['id']}/check-in"))
    assert out["status"] == "attended" and same(out["attended_at"], WED, 13, 30)
    err(post(client, librarian, f"event-registrations/{r3['id']}/check-in"), 409, "REGISTRATION_NOT_ACTIVE")
    at(clock, WED, 16)
    err(post(client, librarian, f"event-registrations/{r2['id']}/check-in"), 409, "EVENT_OVER")
'''),
    dict(id="T-EVT-33-a", req="LIB-EVT-33", type="Boundary", input="Event Wed 14:00–16:00, capacity 2: M1 attended, M2 registered, M3 waiting; process at 16:00 and 16:00:01", expected="First all 0; then `{completed_events 1, no_shows 1, bans 0, reminders 0}`; event `completed`; M2 `no_show`; M3 `cancelled` (`event_cancelled`)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=2)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    r1 = register(client, librarian, e["id"], m1)
    register(client, librarian, e["id"], m2); register(client, librarian, e["id"], m3)
    at(clock, WED, 14)
    ok(post(client, librarian, f"event-registrations/{r1['id']}/check-in"))
    at(clock, WED, 16)
    assert process(client, librarian)["completed_events"] == 0
    at(clock, WED, 16, 0, 1)
    assert process(client, librarian) == {"completed_events": 1, "no_shows": 1, "bans": 0, "reminders": 0}
    assert get(client, librarian, f"events/{e['id']}")["status"] == "completed"
    assert [reg_of(client, librarian, e["id"], m["id"])["status"] for m in (m1, m2, m3)] == ["attended", "no_show", "cancelled"]
'''),
    dict(id="T-EVT-33-b", req="LIB-EVT-33", type="Boundary", input="Event Thu 10:00 with M1 registered and M2 waiting (capacity 1); process Wed 09:59, Wed 10:00, again", expected="`reminders` 0, 1, 0; M1 has one `event_reminder`, M2 none", code='''
def TEST(client, clock, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, THU), day=THU, start="10:00", end="11:00", capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    at(clock, WED, 9, 59)
    assert process(client, librarian)["reminders"] == 0
    at(clock, WED, 10)
    assert process(client, librarian)["reminders"] == 1
    assert process(client, librarian)["reminders"] == 0
    assert [len(notes(client, librarian, m["id"], "event_reminder")) for m in (m1, m2)] == [1, 0]
'''),
    dict(id="T-EVT-34-a", req="LIB-EVT-34", type="Normal", input="Member is a no-show at events on Wed 11-04 and Wed 11-11; processed after each", expected="No ban after two no-shows (`bans` 0); the member can still register", code='''
def TEST(client, clock, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED, "2026-11-11", "2026-11-18")
    evs = [published(client, librarian, branch_a, sid, day=d) for d in (WED, "2026-11-11", "2026-11-18")]
    m = member(client, librarian, branch_a)
    for e in evs[:2]:
        register(client, librarian, e["id"], m)
    for d in (WED, "2026-11-11"):
        at(clock, d, 17)
        assert process(client, librarian)["bans"] == 0
    ok(reg(client, librarian, evs[2]["id"], m["id"]), 201)
'''),
    dict(id="T-EVT-35-a", req="LIB-EVT-35", type="Normal", input="Member with no-shows on 11-03, 11-10 and a registration (fee 15.00) for an event on 12-01 where M2 waits; third no-show on 11-17 processed", expected="The 12-01 registration `cancelled` with `member_banned`, fee waived; M2 promoted", code='''
def TEST(client, clock, admin, librarian, branch_a):
    days = (TUE, "2026-11-10", "2026-11-17")
    sid = on_shift(client, admin, branch_a, *days, "2026-12-01")
    evs = [published(client, librarian, branch_a, sid, day=d, start="10:00", end="11:00") for d in days]
    later = published(client, librarian, branch_a, sid, day="2026-12-01", capacity=1, fee="15.00")
    m, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    for e in evs:
        register(client, librarian, e["id"], m)
    r = register(client, librarian, later["id"], m)
    register(client, librarian, later["id"], m2)
    for d in days:
        at(clock, d, 12)
        process(client, librarian)
    out = reg_of(client, librarian, later["id"], m["id"])
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "member_banned")
    assert [f for f in fees_of(client, librarian, m["id"]) if f[1] == "15.00"] == [("event_fee", "15.00", "waived")]
    assert reg_of(client, librarian, later["id"], m2["id"])["status"] == "registered"
'''),
    dict(id="T-EVT-36-a", req="LIB-EVT-36", type="Normal", input="No-shows on events of Tue 2026-11-03, 11-10 and 11-17, processed on each day; registration for another event afterwards", expected="Third process: `bans` 1; ban 2026-11-17 – 2026-12-16 with one `event_ban_started` notification; `409 MEMBER_BANNED_FROM_EVENTS` with `details.ends_on` 2026-12-16", code='''
def TEST(client, clock, admin, librarian, branch_a):
    days = (TUE, "2026-11-10", "2026-11-17")
    sid = on_shift(client, admin, branch_a, *days, "2026-11-25")
    evs = [published(client, librarian, branch_a, sid, day=d, start="10:00", end="11:00") for d in days]
    other = published(client, librarian, branch_a, sid, day="2026-11-25")
    m = member(client, librarian, branch_a)
    for e in evs:
        register(client, librarian, e["id"], m)
    results = []
    for d in days:
        at(clock, d, 12)
        results.append(process(client, librarian)["bans"])
    assert results == [0, 0, 1]
    bans = items(get(client, librarian, f"members/{m['id']}/event-bans"))
    assert [(b["starts_on"], b["ends_on"]) for b in bans] == [("2026-11-17", "2026-12-16")]
    assert len(notes(client, librarian, m["id"], "event_ban_started")) == 1
    assert err(reg(client, librarian, other["id"], m["id"]), 409, "MEMBER_BANNED_FROM_EVENTS")["details"]["ends_on"] == "2026-12-16"
'''),
    dict(id="T-EVT-37-a", req="LIB-EVT-37", type="Error", input="Member reads own bans; another member's bans", expected="200 (empty list); `403`", code='''
def TEST(client, librarian, branch_a):
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    mh = member_headers(client, m)
    assert get(client, mh, f"members/{m['id']}/event-bans")["total"] == 0
    assert client.get(f"/api/v1/members/{other['id']}/event-bans", headers=mh).status_code == 403
'''),
    # ---------------------------------------------------------------- effects and reports
    dict(id="T-EVT-38-a", req="LIB-EVT-38", type="Normal", input="Event fee 40.00; payment 15.00; balance", expected="Fee paid 15.00, outstanding 25.00; `outstanding_fees` 25.00; fee list `kind=event_fee` has it", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), fee="40.00")
    m = member(client, librarian, branch_a)
    register(client, librarian, e["id"], m)
    pay(client, librarian, m["id"], "15.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    assert (fee["paid_amount"], fee["outstanding"]) == ("15.00", "25.00")
    assert balance(client, librarian, m["id"])["outstanding_fees"] == "25.00"
    assert [f["id"] for f in items(get(client, librarian, "fees", kind="event_fee"))] == [fee["id"]]
'''),
    dict(id="T-EVT-39-a", req="LIB-EVT-39", type="Normal", input="Member registered for one upcoming event and waiting for another (capacity 1)", expected="`events` = `{registered 1, waitlisted 1, no_shows_90_days 0, banned_until null}`", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    e1 = published(client, librarian, branch_a, sid)
    full = published(client, librarian, branch_a, sid, start="10:00", end="11:00", capacity=1)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e1["id"], m)
    register(client, librarian, full["id"], other); register(client, librarian, full["id"], m)
    s = get(client, librarian, f"members/{m['id']}/summary")
    assert s["events"] == {"registered": 1, "waitlisted": 1, "no_shows_90_days": 0, "banned_until": None}
'''),
    dict(id="T-EVT-40-a", req="LIB-EVT-40", type="Normal", input="Capacity 1: M1 registered (fee 12.00, unpaid), M2 waiting; M1 deactivated", expected="200; M1's registration `cancelled` with `member_deactivated`, fee stays `open`; M2 `registered`", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, fee="12.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    deactivate_member(client, librarian, m1["id"])
    assert reg_of(client, librarian, e["id"], m1["id"])["cancel_reason"] == "member_deactivated"
    assert fees_of(client, librarian, m1["id"]) == [("event_fee", "12.00", "open")]
    assert reg_of(client, librarian, e["id"], m2["id"])["status"] == "registered"
'''),
    dict(id="T-EVT-41-a", req="LIB-EVT-41", type="Normal", input="Capacity 1: M1 registered, M2 waiting; M1 deactivated (no fee)", expected="M2 gets one `event_promoted` notification", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    deactivate_member(client, librarian, m1["id"])
    assert len(notes(client, librarian, m2["id"], "event_promoted")) == 1
'''),
    dict(id="T-EVT-42-a", req="LIB-EVT-42", type="Error", input="Branch QQ (no staff home) has a draft event; QQ deactivated", expected="`409 BRANCH_IN_USE`", code='''
def TEST(client, admin, librarian, branch_a):
    qq = create_branch(client, admin, "QQ")
    event(client, librarian, qq, staff(client, admin, branch_a))
    err(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
'''),
    dict(id="T-EVT-43-a", req="LIB-EVT-43", type="Error", input="Staff profile responsible for a draft event is deactivated; after the event is cancelled", expected="`409 STAFF_HAS_EVENTS` with `details.event_ids`; then 200", code='''
def TEST(client, admin, librarian, branch_a):
    sid = staff(client, admin, branch_a)
    e = event(client, librarian, branch_a, sid)
    url = f"/api/v1/staff/{sid}"
    assert err(client.patch(url, headers=admin, json={"is_active": False}), 409, "STAFF_HAS_EVENTS")["details"]["event_ids"] == [e["id"]]
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    assert ok(client.patch(url, headers=admin, json={"is_active": False}))["is_active"] is False
'''),
    dict(id="T-EVT-44-a", req="LIB-EVT-44", type="Normal", input="Member registers for a free event and cancels; registers for another", expected="The member has no notifications", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    e1, e2 = published(client, librarian, branch_a, sid), published(client, librarian, branch_a, sid, start="10:00", end="11:00")
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    r = ok(reg(client, mh, e1["id"]), 201)
    ok(cancel_reg(client, mh, r["id"]))
    ok(reg(client, mh, e2["id"]), 201)
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0
'''),
    dict(id="T-EVT-44-b", req="LIB-EVT-44", type="Normal", input="Event \"Masal Saati\" cancelled with a registered member", expected="The `event_cancelled` notification has `event_id` and contains the title and the date", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), title="Masal Saati")
    m = member(client, librarian, branch_a)
    register(client, librarian, e["id"], m)
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    n = notes(client, librarian, m["id"], "event_cancelled")[0]
    assert n["event_id"] == e["id"] and "Masal Saati" in n["message"] and WED in n["message"]
'''),
    dict(id="T-EVT-45-a", req="LIB-EVT-45", type="Normal", input="Event created, changed, published; registration created and cancelled; event cancelled; process; audit log by event", expected="One entry each", code='''
def TEST(client, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED)
    e = event(client, librarian, branch_a, sid)
    ok(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"title": "Değişti"}))
    ok(publish(client, librarian, e["id"]))
    r = register(client, librarian, e["id"], member(client, librarian, branch_a))
    ok(cancel_reg(client, librarian, r["id"]))
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    process(client, librarian)
    for name in ("event_created", "event_updated", "event_published", "event_registration_created", "event_registration_cancelled", "event_cancelled", "events_processed"):
        assert len(items(get(client, admin, "audit-log", event=name))) == 1, name
'''),
    dict(id="T-EVT-46-a", req="LIB-EVT-46", type="Normal", input="Event E1 Wed (fee 10.00, capacity 3): M1 attended, M2 no-show, M3 late cancellation; event E2 Thu cancelled; draft D; report 2026-11-02 – 2026-11-08", expected="E1 `{status completed, capacity 3, registered 2, attended 1, no_shows 1, late_cancellations 1, fees_charged 30.00}`, E2 `cancelled` with zeros; D not listed", code='''
def TEST(client, clock, admin, librarian, branch_a):
    sid = on_shift(client, admin, branch_a, WED, THU)
    e1 = published(client, librarian, branch_a, sid, capacity=3, fee="10.00")
    e2 = published(client, librarian, branch_a, sid, day=THU)
    event(client, librarian, branch_a, sid, start="09:00", end="10:00")
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    r1, _, r3 = (register(client, librarian, e1["id"], m) for m in (m1, m2, m3))
    ok(post(client, librarian, f"events/{e2['id']}/cancel"))
    at(clock, WED, 13, 45)
    ok(cancel_reg(client, librarian, r3["id"]))
    ok(post(client, librarian, f"event-registrations/{r1['id']}/check-in"))
    at(clock, WED, 17)
    process(client, librarian)
    rows = items(get(client, librarian, "reports/event-attendance", **{"from": MON, "to": "2026-11-08"}))
    keys = ("event_id", "status", "capacity", "registered", "attended", "no_shows", "late_cancellations", "fees_charged")
    assert [tuple(r[k] for k in keys) for r in rows] == [(e1["id"], "completed", 3, 2, 1, 1, 1, "30.00"), (e2["id"], "cancelled", 10, 0, 0, 0, 0, "0.00")]
'''),
    dict(id="T-EVT-46-b", req="LIB-EVT-46", type="Error", input="`from` > `to`; range of 367 days; member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/event-attendance"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": WED}).status_code == 403
'''),
    dict(id="T-EVT-47-a", req="LIB-EVT-47", type="Normal", input="An event and a registration exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, librarian, branch_a):
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    register(client, librarian, e["id"], member(client, librarian, branch_a))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
]
