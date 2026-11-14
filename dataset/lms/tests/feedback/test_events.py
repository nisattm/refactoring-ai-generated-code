"""Feedback tests: module 20 (Events). Generated from cases/events.md."""
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


def test_t_evt_01_a(client, admin, librarian, branch_a):
    """T-EVT-01-a (LIB-EVT-01): 201 draft; fee 0.00, audience all, room and series null"""
    sid = staff(client, admin, branch_a)
    e = event(client, librarian, branch_a, sid, title="Yazar Söyleşisi")
    assert (e["title"], e["kind"], e["status"], e["fee"], e["audience"], e["room_id"], e["series_id"], e["capacity"], e["staff_id"]) == ("Yazar Söyleşisi", "talk", "draft", "0.00", "all", None, None, 10, sid)
    assert (e["date"], e["start_time"], e["end_time"]) == (WED, "14:00", "16:00")


def test_t_evt_02_a(client, admin, librarian, branch_a):
    """T-EVT-02-a (LIB-EVT-02): EVENT_IN_PAST; BRANCH_NOT_OPEN with reason weekend; OUTSIDE_BRANCH_HOURS; ROOM_INACTIVE"""
    sid = staff(client, admin, branch_a)
    err(try_event(client, librarian, branch_a, sid, day="2026-10-30"), 409, "EVENT_IN_PAST")
    assert err(try_event(client, librarian, branch_a, sid, day=SAT), 409, "BRANCH_NOT_OPEN")["details"]["reason"] == "weekend"
    err(try_event(client, librarian, branch_a, sid, start="19:00", end="21:00"), 409, "OUTSIDE_BRANCH_HOURS")
    r = group_room(client, admin, branch_a)
    ok(client.patch(f"/api/v1/rooms/{r['id']}", headers=admin, json={"is_active": False}))
    err(try_event(client, librarian, branch_a, sid, room_id=r["id"]), 409, "ROOM_INACTIVE")


def test_t_evt_02_c(client, admin, librarian, branch_a):
    """T-EVT-02-c (LIB-EVT-02): STAFF_INACTIVE; BRANCH_INACTIVE"""
    sid = staff(client, admin, branch_a)
    ok(client.patch(f"/api/v1/staff/{sid}", headers=admin, json={"is_active": False}))
    err(try_event(client, librarian, branch_a, sid), 409, "STAFF_INACTIVE")
    qq = create_branch(client, admin, "QQ")
    deactivate_branch(client, admin, qq["id"])
    err(try_event(client, librarian, qq, staff(client, admin, branch_a)), 409, "BRANCH_INACTIVE")


def test_t_evt_03_a(client, admin, librarian, branch_a):
    """T-EVT-03-a (LIB-EVT-03): 200 published with published_at; 409 INVALID_EVENT_STATUS with details.status published"""
    sid = on_shift(client, admin, branch_a, WED)
    e = event(client, librarian, branch_a, sid)
    out = ok(publish(client, librarian, e["id"]))
    assert out["status"] == "published" and same(out["published_at"], MON, 9)
    assert err(publish(client, librarian, e["id"]), 409, "INVALID_EVENT_STATUS")["details"]["status"] == "published"


def test_t_evt_03_c(client, admin, librarian, branch_a):
    """T-EVT-03-c (LIB-EVT-03): First published (exactly 24 hours); second 409 EVENT_TOO_SOON"""
    sid = on_shift(client, admin, branch_a, TUE, start="08:00", end="12:00")
    ok(publish(client, librarian, event(client, librarian, branch_a, sid, day=TUE, start="09:00", end="10:00")["id"]))
    e = event(client, librarian, branch_a, sid, day=TUE, start="08:30", end="09:30")
    err(publish(client, librarian, e["id"]), 409, "EVENT_TOO_SOON")


def test_t_evt_04_a(client, admin, librarian, branch_a):
    """T-EVT-04-a (LIB-EVT-04): 200; 422; 409 INVALID_EVENT_STATUS"""
    sid = staff(client, admin, branch_a)
    e = event(client, librarian, branch_a, sid)
    out = ok(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"title": "Yeni Başlık", "capacity": 20}))
    assert (out["title"], out["capacity"]) == ("Yeni Başlık", 20)
    assert client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"audience": "students"}).status_code == 422
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    err(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"title": "X"}), 409, "INVALID_EVENT_STATUS")


def test_t_evt_05_a(client, admin, librarian, branch_a):
    """T-EVT-05-a (LIB-EVT-05): 200; 409 FEE_LOCKED"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    assert ok(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"fee": "15.00"}))["fee"] == "15.00"
    register(client, librarian, e["id"], member(client, librarian, branch_a))
    err(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"fee": "20.00"}), 409, "FEE_LOCKED")


def test_t_evt_07_a(client, admin, librarian, branch_a):
    """T-EVT-07-a (LIB-EVT-07): One event_changed notification each for M1 and M2"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    ok(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"start_time": "15:00"}))
    assert [len(notes(client, librarian, m["id"], "event_changed")) for m in (m1, m2)] == [1, 1]


def test_t_evt_08_a(client, admin, librarian, branch_a):
    """T-EVT-08-a (LIB-EVT-08): Member: E1, E2; librarian: E1, D, E2 (by date and time); kind=workshop → E1; E2 registered 1, free_places 1"""
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


def test_t_evt_09_a(client, admin, librarian, branch_a):
    """T-EVT-09-a (LIB-EVT-09): staff_covered true, then false; the event stays published"""
    sid = staff(client, admin, branch_a)
    s = shift(client, admin, sid, branch_a, WED)
    e = published(client, librarian, branch_a, sid)
    assert get(client, librarian, f"events/{e['id']}")["staff_covered"] is True
    ok(post(client, admin, f"shifts/{s['id']}/cancel"))
    out = get(client, librarian, f"events/{e['id']}")
    assert (out["staff_covered"], out["status"]) == (False, "published")


def test_t_evt_10_a(client, admin, librarian, branch_a):
    """T-EVT-10-a (LIB-EVT-10): Event cancelled (staff_request); both registrations cancelled with event_cancelled; M1's fee waived; one event_cancelled notification each"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, fee="20.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    out = ok(post(client, librarian, f"events/{e['id']}/cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_request")
    assert [(x["status"], x["cancel_reason"]) for x in regs_of(client, librarian, e["id"])] == [("cancelled", "event_cancelled")] * 2
    assert fees_of(client, librarian, m1["id"]) == [("event_fee", "20.00", "waived")]
    assert [len(notes(client, librarian, m["id"], "event_cancelled")) for m in (m1, m2)] == [1, 1]


def test_t_evt_11_a(client, admin, librarian, branch_a):
    """T-EVT-11-a (LIB-EVT-11): 409 ROOM_ALREADY_BOOKED with details.event_id; slots 14:00–15:30 not free with booking_id null; the room is not listed"""
    r = group_room(client, admin, branch_a)
    e = event(client, librarian, branch_a, staff(client, admin, branch_a), room_id=r["id"])
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    body = {"room_id": r["id"], "date": WED, "start_time": "15:00", "end_time": "16:00", "member_id": m1["id"], "participant_ids": [m2["id"]]}
    assert err(post(client, librarian, "room-bookings", body), 409, "ROOM_ALREADY_BOOKED")["details"]["event_id"] == e["id"]
    slots = {s["start"]: s for s in get(client, librarian, f"rooms/{r['id']}/availability", date=WED)["slots"]}
    assert [(slots[t]["free"], slots[t]["booking_id"]) for t in ("14:00", "15:30", "16:00")] == [(False, None), (False, None), (True, None)]
    free = items(get(client, librarian, "rooms/free", date=WED, start_time="14:00", end_time="15:00", branch_id=branch_a["id"]))
    assert r["id"] not in [x["id"] for x in free]


def test_t_evt_13_a(client, admin, librarian, branch_a):
    """T-EVT-13-a (LIB-EVT-13): 201: 3 draft events on 11-10, 11-17, 11-24 with the same series_id; skipped empty"""
    sid = staff(client, admin, branch_a)
    body = {"title": "Kitap Kulübü", "kind": "book_club", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "18:00",
            "end_time": "19:00", "capacity": 12, "staff_id": sid, "weeks": 3}
    out = ok(post(client, librarian, "event-series", body), 201)
    assert out["skipped"] == [] and len(out["created"]) == 3
    evs = [get(client, librarian, f"events/{i}") for i in out["created"]]
    assert [(x["date"], x["status"], x["series_id"]) for x in evs] == [(d, "draft", out["series_id"]) for d in ("2026-11-10", "2026-11-17", "2026-11-24")]


def test_t_evt_15_a(client, admin, librarian, branch_a):
    """T-EVT-15-a (LIB-EVT-15): Created 11-10, 11-17, 12-01; skipped {date 2026-11-24, error_code BRANCH_NOT_OPEN}"""
    sid = staff(client, admin, branch_a)
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": "2026-11-24", "reason": "Sayım"}), 201)
    body = {"title": "Atölye", "kind": "workshop", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "14:00", "end_time": "16:00", "capacity": 8, "staff_id": sid, "weeks": 4}
    out = ok(post(client, librarian, "event-series", body), 201)
    assert [get(client, librarian, f"events/{i}")["date"] for i in out["created"]] == ["2026-11-10", "2026-11-17", "2026-12-01"]
    assert out["skipped"] == [{"date": "2026-11-24", "error_code": "BRANCH_NOT_OPEN"}]


def test_t_evt_17_a(client, clock, admin, librarian, branch_a):
    """T-EVT-17-a (LIB-EVT-17): cancelled lists the 2nd and 3rd events (series_cancelled); the first is unchanged; 404"""
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


def test_t_evt_19_a(client, admin, librarian, branch_a):
    """T-EVT-19-a (LIB-EVT-19): 201 registered (position null); 201 waitlisted with position 1"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = ok(reg(client, member_headers(client, m1), e["id"]), 201)
    assert (r1["event_id"], r1["member_id"], r1["status"], r1["position"]) == (e["id"], m1["id"], "registered", None)
    r2 = register(client, librarian, e["id"], m2)
    assert (r2["status"], r2["position"]) == ("waitlisted", 1)


def test_t_evt_20_a(client, admin, librarian, branch_a):
    """T-EVT-20-a (LIB-EVT-20): 409 EVENT_NOT_OPEN each"""
    sid = on_shift(client, admin, branch_a, WED)
    d = event(client, librarian, branch_a, sid)
    c = published(client, librarian, branch_a, sid, start="10:00", end="11:00")
    ok(post(client, librarian, f"events/{c['id']}/cancel"))
    m, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    for ev, mm in ((d, m), (c, m), (d, p)):
        err(reg(client, librarian, ev["id"], mm["id"]), 409, "EVENT_NOT_OPEN")


def test_t_evt_20_c(client, admin, librarian, branch_a):
    """T-EVT-20-c (LIB-EVT-20): 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt '50.00'; 201"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(reg(client, librarian, e["id"], m1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(reg(client, librarian, e["id"], m2["id"]), 201)


def test_t_evt_20_e(client, admin, librarian, branch_a):
    """T-EVT-20-e (LIB-EVT-20): 409 EVENT_REGISTRATION_LIMIT_REACHED with details.limit 5"""
    sid = on_shift(client, admin, branch_a, WED)
    evs = [published(client, librarian, branch_a, sid, start=f"{h:02d}:00", end=f"{h + 1:02d}:00") for h in range(8, 14)]
    m = member(client, librarian, branch_a)
    for e in evs[:5]:
        register(client, librarian, e["id"], m)
    assert err(reg(client, librarian, evs[5]["id"], m["id"]), 409, "EVENT_REGISTRATION_LIMIT_REACHED")["details"]["limit"] == 5


def test_t_evt_21_a(client, admin, librarian, branch_a):
    """T-EVT-21-a (LIB-EVT-21): M1 gets an event_fee 25.00 with event_registration_id (= fee_id); M2 no fee until promoted, then 25.00"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, fee="25.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = register(client, librarian, e["id"], m1)
    register(client, librarian, e["id"], m2)
    fee = items(member_fees(client, librarian, m1["id"]))[0]
    assert (fee["kind"], fee["amount"], fee["event_registration_id"], fee["id"]) == ("event_fee", "25.00", r1["id"], r1["fee_id"])
    assert member_fees(client, librarian, m2["id"])["total"] == 0
    ok(cancel_reg(client, librarian, r1["id"]))
    assert fees_of(client, librarian, m2["id"]) == [("event_fee", "25.00", "open")]


def test_t_evt_23_a(client, admin, librarian, branch_a):
    """T-EVT-23-a (LIB-EVT-23): M3 registered with promoted_at; M4 waitlisted position 1; one event_promoted notification for M3"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=2)
    ms = [member(client, librarian, branch_a) for _ in range(4)]
    rs = [register(client, librarian, e["id"], m) for m in ms]
    assert [(r["status"], r["position"]) for r in rs] == [("registered", None), ("registered", None), ("waitlisted", 1), ("waitlisted", 2)]
    ok(cancel_reg(client, member_headers(client, ms[1]), rs[1]["id"]))
    r3, r4 = reg_of(client, librarian, e["id"], ms[2]["id"]), reg_of(client, librarian, e["id"], ms[3]["id"])
    assert r3["status"] == "registered" and r3["promoted_at"] is not None and (r4["status"], r4["position"]) == ("waitlisted", 1)
    assert len(notes(client, librarian, ms[2]["id"], "event_promoted")) == 1


def test_t_evt_25_a(client, admin, librarian, branch_a):
    """T-EVT-25-a (LIB-EVT-25): 409 EVENT_TIME_CONFLICT with details.event_id; 201; the waiting registration causes no conflict"""
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


def test_t_evt_27_a(client, admin, librarian, branch_a):
    """T-EVT-27-a (LIB-EVT-27): 200 cancelled, member_request, cancelled_at; 409 REGISTRATION_NOT_ACTIVE; 403"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r = register(client, librarian, e["id"], m)
    r2 = register(client, librarian, e["id"], other)
    mh = member_headers(client, m)
    assert cancel_reg(client, mh, r2["id"]).status_code == 403
    out = ok(cancel_reg(client, mh, r["id"]))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "member_request") and same(out["cancelled_at"], MON, 9)
    err(cancel_reg(client, mh, r["id"]), 409, "REGISTRATION_NOT_ACTIVE")


def test_t_evt_29_a(client, clock, admin, librarian, branch_a):
    """T-EVT-29-a (LIB-EVT-29): M1 late_cancellation true and fee stays open; M2 late_cancellation false"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), fee="30.00", capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = register(client, librarian, e["id"], m1), register(client, librarian, e["id"], m2)
    at(clock, WED, 10)
    out2 = ok(cancel_reg(client, librarian, r2["id"]))
    out1 = ok(cancel_reg(client, librarian, r1["id"]))
    assert (out1["late_cancellation"], out2["late_cancellation"]) == (True, False)
    assert fees_of(client, librarian, m1["id"]) == [("event_fee", "30.00", "open")]


def test_t_evt_31_a(client, clock, admin, librarian, branch_a):
    """T-EVT-31-a (LIB-EVT-31): M2 stays waitlisted (no promotion in the last hour)"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = register(client, librarian, e["id"], m1)
    register(client, librarian, e["id"], m2)
    at(clock, WED, 13, 1)
    ok(cancel_reg(client, librarian, r1["id"]))
    assert reg_of(client, librarian, e["id"], m2["id"])["status"] == "waitlisted"


def test_t_evt_33_a(client, clock, admin, librarian, branch_a):
    """T-EVT-33-a (LIB-EVT-33): First all 0; then {completed_events 1, no_shows 1, bans 0, reminders 0}; event completed; M2 no_show; M3 cancelled (event_cancelled)"""
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


def test_t_evt_35_a(client, clock, admin, librarian, branch_a):
    """T-EVT-35-a (LIB-EVT-35): The 12-01 registration cancelled with member_banned, fee waived; M2 promoted"""
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


def test_t_evt_37_a(client, librarian, branch_a):
    """T-EVT-37-a (LIB-EVT-37): 200 (empty list); 403"""
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    mh = member_headers(client, m)
    assert get(client, mh, f"members/{m['id']}/event-bans")["total"] == 0
    assert client.get(f"/api/v1/members/{other['id']}/event-bans", headers=mh).status_code == 403


def test_t_evt_39_a(client, admin, librarian, branch_a):
    """T-EVT-39-a (LIB-EVT-39): events = {registered 1, waitlisted 1, no_shows_90_days 0, banned_until null}"""
    sid = on_shift(client, admin, branch_a, WED)
    e1 = published(client, librarian, branch_a, sid)
    full = published(client, librarian, branch_a, sid, start="10:00", end="11:00", capacity=1)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e1["id"], m)
    register(client, librarian, full["id"], other); register(client, librarian, full["id"], m)
    s = get(client, librarian, f"members/{m['id']}/summary")
    assert s["events"] == {"registered": 1, "waitlisted": 1, "no_shows_90_days": 0, "banned_until": None}


def test_t_evt_41_a(client, admin, librarian, branch_a):
    """T-EVT-41-a (LIB-EVT-41): M2 gets one event_promoted notification"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    deactivate_member(client, librarian, m1["id"])
    assert len(notes(client, librarian, m2["id"], "event_promoted")) == 1


def test_t_evt_43_a(client, admin, librarian, branch_a):
    """T-EVT-43-a (LIB-EVT-43): 409 STAFF_HAS_EVENTS with details.event_ids; then 200"""
    sid = staff(client, admin, branch_a)
    e = event(client, librarian, branch_a, sid)
    url = f"/api/v1/staff/{sid}"
    assert err(client.patch(url, headers=admin, json={"is_active": False}), 409, "STAFF_HAS_EVENTS")["details"]["event_ids"] == [e["id"]]
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    assert ok(client.patch(url, headers=admin, json={"is_active": False}))["is_active"] is False


def test_t_evt_44_a(client, admin, librarian, branch_a):
    """T-EVT-44-a (LIB-EVT-44): The member has no notifications"""
    sid = on_shift(client, admin, branch_a, WED)
    e1, e2 = published(client, librarian, branch_a, sid), published(client, librarian, branch_a, sid, start="10:00", end="11:00")
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    r = ok(reg(client, mh, e1["id"]), 201)
    ok(cancel_reg(client, mh, r["id"]))
    ok(reg(client, mh, e2["id"]), 201)
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0


def test_t_evt_45_a(client, admin, librarian, branch_a):
    """T-EVT-45-a (LIB-EVT-45): One entry each"""
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


def test_t_evt_46_a(client, clock, admin, librarian, branch_a):
    """T-EVT-46-a (LIB-EVT-46): E1 {status completed, capacity 3, registered 2, attended 1, no_shows 1, late_cancellations 1, fees_charged 30.00}, E2 cancelled with zeros; D not listed"""
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


def test_t_evt_47_a(client, admin, librarian, branch_a):
    """T-EVT-47-a (LIB-EVT-47): The export has exactly the keys of 22.1"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    register(client, librarian, e["id"], member(client, librarian, branch_a))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
