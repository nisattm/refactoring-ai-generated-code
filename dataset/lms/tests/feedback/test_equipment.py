"""Feedback tests: module 16 (Equipment loans). Generated from cases/equipment.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, balance, create_book, create_branch, deactivate_branch, deactivate_member, error_code, items, lend,
    member_fees, member_headers, pay, register_member, return_loan, waive,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, WED, FRI, SAT = "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-06", "2026-11-07"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); the desk is open 08:00-20:00 on working days


def at(clock, day, hh=9, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    clock.set(datetime(y, m, d, hh, mm, ss, tzinfo=TR))


def ts(day, hh, mm=0, ss=0):
    return f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+03:00"


def same(value, day, hh, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    return datetime.fromisoformat(value) == datetime(y, m, d, hh, mm, ss, tzinfo=TR)


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def err(r, status, code):
    assert r.status_code == status and error_code(r) == code, r.text
    return r.json()["error"]


def etype(client, admin, *, code=None, unit="hours", period=4, fee="5.00", training=False, max_open=3, expect=201, **fields):
    """Equipment type; default: 4 hours, 5.00 per hour, no training, 3 open loans per member."""
    _seq[0] += 1
    body = {"code": code or f"T{_seq[0]}", "name": f"Type {_seq[0]}", "period_unit": unit, "period": period,
            "hourly_late_fee": fee, "requires_training": training, "max_open_per_member": max_open}
    body.update(fields)
    r = client.post("/api/v1/equipment-types", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def item(client, admin, type_, branch, *, tag=None, value="1000.00", expect=201, **fields):
    _seq[0] += 1
    body = {"type_id": type_["id"], "asset_tag": tag or f"EQ-{_seq[0]:04d}", "serial_no": f"SN{_seq[0]}",
            "branch_id": branch["id"], "value": value, "acquired_on": "2025-01-01"}
    body.update(fields)
    r = client.post("/api/v1/equipment-items", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def try_lend(client, headers, member_id, item_id=None, reservation_id=None):
    body = {"member_id": member_id}
    if item_id is not None:
        body["item_id"] = item_id
    if reservation_id is not None:
        body["reservation_id"] = reservation_id
    return client.post("/api/v1/equipment-loans", headers=headers, json=body)


def elend(client, headers, member_id, item_id):
    return ok(try_lend(client, headers, member_id, item_id), 201)


def ret(client, headers, loan_id, condition="good", damage_fee=None):
    body = {"condition": condition}
    if damage_fee is not None:
        body["damage_fee"] = damage_fee
    return client.post(f"/api/v1/equipment-loans/{loan_id}/return", headers=headers, json=body)


def act(client, headers, path):
    return client.post(f"/api/v1/{path}", headers=headers)


def try_reserve(client, headers, type_id, branch_id, starts_at, member_id=None):
    body = {"type_id": type_id, "branch_id": branch_id, "starts_at": starts_at}
    if member_id is not None:
        body["member_id"] = member_id
    return client.post("/api/v1/equipment-reservations", headers=headers, json=body)


def reserve(client, lib, type_, branch, member_, day, hh, mm=0):
    """Staff reservation for ``member_``."""
    return ok(try_reserve(client, lib, type_["id"], branch["id"], ts(day, hh, mm), member_id=member_["id"]), 201)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def process(client, lib):
    return ok(client.post("/api/v1/equipment/process", headers=lib))


def train(client, headers, member_id, type_id, completed_on):
    return client.post(f"/api/v1/members/{member_id}/equipment-trainings", headers=headers,
                       json={"type_id": type_id, "completed_on": completed_on})


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def fees_of(client, lib, member_id):
    return sorted((f["kind"], f["amount"]) for f in items(member_fees(client, lib, member_id)))


def debt(client, lib, branch, member_, amount="50.00"):
    """A book damage fee of ``amount`` for ``member_``."""
    copy = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch["id"])
    loan = lend(client, lib, member_["id"], copy["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=amount)


def test_t_eq_01_a(client, clock, admin, librarian, branch_a):
    """T-EQ-01-a (LIB-EQ-01): 409 DESK_CLOSED, then 201"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 7, 59, 59)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
    at(clock, TUE, 8, 0)
    ok(try_lend(client, librarian, m["id"], it["id"]), 201)


def test_t_eq_01_c(client, clock, admin, librarian, branch_a):
    """T-EQ-01-c (LIB-EQ-01): 409 DESK_CLOSED both"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    for day in (SAT, "2026-10-29"):
        at(clock, day, 10, 0)
        err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")


def test_t_eq_02_a(client, clock, admin, librarian, branch_a):
    """T-EQ-02-a (LIB-EQ-02): DESK_CLOSED with details.opens_at Mon 2026-11-09 08:00 both"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    for day, hh, mm in ((FRI, 20, 30), (SAT, 10, 0)):
        at(clock, day, hh, mm)
        e = err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
        assert same(e["details"]["opens_at"], "2026-11-09", 8, 0)


def test_t_eq_03_a(client, admin):
    """T-EQ-03-a (LIB-EQ-03): 201; code CHG_4, requires_training false, active"""
    body = {"code": "chg_4", "name": "Phone charger", "period_unit": "hours", "period": 4, "hourly_late_fee": "5.00", "max_open_per_member": 1}
    r = ok(client.post("/api/v1/equipment-types", headers=admin, json=body), 201)
    assert (r["code"], r["requires_training"], r["is_active"], r["period"], r["hourly_late_fee"]) == ("CHG_4", False, True, 4, "5.00")


def test_t_eq_03_c(client, admin):
    """T-EQ-03-c (LIB-EQ-03): 422 VALIDATION_ERROR each"""
    bad = [dict(period=9), dict(unit="working_days", period=11), dict(period=0), dict(fee="0.49"), dict(fee="50.01"),
           dict(max_open=4), dict(max_open=0), dict(code="A"), dict(code="AB-1"), dict(unit="days")]
    for fields in bad:
        etype(client, admin, expect=422, **fields)


def test_t_eq_04_a(client, admin):
    """T-EQ-04-a (LIB-EQ-04): 200 with the new values; 422 twice"""
    t = etype(client, admin)
    url = f"/api/v1/equipment-types/{t['id']}"
    r = ok(client.patch(url, headers=admin, json={"name": "Charger", "period": 6}))
    assert (r["name"], r["period"]) == ("Charger", 6)
    assert client.patch(url, headers=admin, json={"code": "NEW"}).status_code == 422
    assert client.patch(url, headers=admin, json={"period_unit": "working_days"}).status_code == 422


def test_t_eq_05_a(client, admin, librarian, branch_a):
    """T-EQ-05-a (LIB-EQ-05): Reservation cancelled with type_inactive; one equipment_reservation_cancelled notification"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = ok(try_reserve(client, member_headers(client, m), t["id"], branch_a["id"], ts(WED, 10)), 201)
    ok(client.patch(f"/api/v1/equipment-types/{t['id']}", headers=admin, json={"is_active": False}))
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["cancel_reason"]) == ("cancelled", "type_inactive")
    assert len(notes(client, librarian, m["id"], "equipment_reservation_cancelled")) == 1


def test_t_eq_06_a(client, admin, librarian, branch_a, branch_b):
    """T-EQ-06-a (LIB-EQ-06): Order AA, BB; AA items_total 2, items_available 1; BB 0 and 0"""
    bb, aa = etype(client, admin, code="BB"), etype(client, admin, code="AA")
    item(client, admin, aa, branch_a)
    on_loan, gone = item(client, admin, aa, branch_b), item(client, admin, aa, branch_a)
    elend(client, librarian, member(client, librarian, branch_a)["id"], on_loan["id"])
    ok(act(client, admin, f"equipment-items/{gone['id']}/retire"))
    rows = items(get(client, librarian, "equipment-types"))
    assert [(x["code"], x["items_total"], x["items_available"]) for x in rows] == [("AA", 2, 1), ("BB", 0, 0)]


def test_t_eq_07_a(client, admin, branch_a):
    """T-EQ-07-a (LIB-EQ-07): 201; asset_tag EQ-AB12, status available"""
    t = etype(client, admin)
    r = item(client, admin, t, branch_a, tag="eq-ab12", value="2500.00")
    assert (r["asset_tag"], r["status"], r["value"], r["type_id"], r["branch_id"]) == ("EQ-AB12", "available", "2500.00", t["id"], branch_a["id"])


def test_t_eq_08_a(client, admin, branch_a, branch_b):
    """T-EQ-08-a (LIB-EQ-08): 200 with the new values; 422 three times"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    url = f"/api/v1/equipment-items/{it['id']}"
    r = ok(client.patch(url, headers=admin, json={"serial_no": "SN-NEW", "value": "1500.00", "branch_id": branch_b["id"]}))
    assert (r["serial_no"], r["value"], r["branch_id"]) == ("SN-NEW", "1500.00", branch_b["id"])
    for body in ({"status": "lost"}, {"asset_tag": "EQ-9999"}, {"type_id": etype(client, admin)["id"]}):
        assert client.patch(url, headers=admin, json=body).status_code == 422


def test_t_eq_08_c(client, admin, librarian, branch_a, branch_b):
    """T-EQ-08-c (LIB-EQ-08): 409 ITEM_NEEDED_FOR_RESERVATION; then 200"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    url = f"/api/v1/equipment-items/{it['id']}"
    err(client.patch(url, headers=admin, json={"branch_id": branch_b["id"]}), 409, "ITEM_NEEDED_FOR_RESERVATION")
    item(client, admin, t, branch_a)
    assert ok(client.patch(url, headers=admin, json={"branch_id": branch_b["id"]}))["branch_id"] == branch_b["id"]


def test_t_eq_09_a(client, admin, librarian, branch_a, branch_b):
    """T-EQ-09-a (LIB-EQ-09): Order by tag; q=sn-x → EQ-0003; branch_id B → EQ-0002; status=on_loan → EQ-0001"""
    t = etype(client, admin)
    item(client, admin, t, branch_a, tag="EQ-0003", serial_no="SN-XY")
    first = item(client, admin, t, branch_a, tag="EQ-0001")
    item(client, admin, t, branch_b, tag="EQ-0002")
    elend(client, librarian, member(client, librarian, branch_a)["id"], first["id"])
    tags = lambda **p: [x["asset_tag"] for x in items(get(client, librarian, "equipment-items", **p))]
    assert tags() == ["EQ-0001", "EQ-0002", "EQ-0003"]
    assert tags(q="sn-x") == ["EQ-0003"]
    assert tags(branch_id=branch_b["id"]) == ["EQ-0002"]
    assert tags(status="on_loan") == ["EQ-0001"]


def test_t_eq_10_a(client, admin, branch_a):
    """T-EQ-10-a (LIB-EQ-10): retired; 409 INVALID_ITEM_STATUS twice"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    assert ok(act(client, admin, f"equipment-items/{i1['id']}/retire"))["status"] == "retired"
    err(act(client, admin, f"equipment-items/{i1['id']}/retire"), 409, "INVALID_ITEM_STATUS")
    err(act(client, admin, f"equipment-items/{i2['id']}/repair-done"), 409, "INVALID_ITEM_STATUS")


def test_t_eq_10_c(client, admin, librarian, branch_a):
    """T-EQ-10-c (LIB-EQ-10): 409 ITEM_NEEDED_FOR_RESERVATION; item stays available"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    err(act(client, admin, f"equipment-items/{it['id']}/retire"), 409, "ITEM_NEEDED_FOR_RESERVATION")
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "available"


def test_t_eq_11_a(client, admin, librarian, branch_a):
    """T-EQ-11-a (LIB-EQ-11): 201; valid_until 2027-11-01"""
    t = etype(client, admin, training=True)
    m = member(client, librarian, branch_a)
    r = ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    assert (r["member_id"], r["type_id"], r["completed_on"], r["valid_until"]) == (m["id"], t["id"], "2026-11-02", "2027-11-01")


def test_t_eq_11_c(client, clock, admin, librarian, branch_a):
    """T-EQ-11-c (LIB-EQ-11): Mon 201; Tue 409 TRAINING_REQUIRED"""
    t = etype(client, admin, training=True)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    assert ok(train(client, librarian, m["id"], t["id"], "2025-11-03"), 201)["valid_until"] == "2026-11-02"
    ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"]))
    at(clock, TUE, 9, 0)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "TRAINING_REQUIRED")


def test_t_eq_12_a(client, clock, admin, librarian, branch_a):
    """T-EQ-12-a (LIB-EQ-12): 201 EquipmentLoanOut: open, due 14:20, not extended, not overdue, accrued 0.00, asset tag and type code; item on_loan"""
    t = etype(client, admin, code="CHG")
    it = item(client, admin, t, branch_a, tag="EQ-0042")
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    r = elend(client, librarian, m["id"], it["id"])
    assert (r["status"], r["member_id"], r["item_id"], r["branch_id"], r["asset_tag"], r["type_id"], r["type_code"]) == ("open", m["id"], it["id"], branch_a["id"], "EQ-0042", t["id"], "CHG")
    assert same(r["loaned_at"], TUE, 10, 20) and same(r["due_at"], TUE, 14, 20)
    assert (r["extended"], r["overdue"], r["accrued_late_fee"], r["reservation_id"], r["returned_at"], r["late_hours"]) == (False, False, "0.00", None, None, None)
    assert r["lent_by"] is not None
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "on_loan"


def test_t_eq_13_a(client, clock, admin, librarian, branch_a):
    """T-EQ-13-a (LIB-EQ-13): 409 MEMBER_PASSIVE; 409 MEMBERSHIP_EXPIRED"""
    it = item(client, admin, etype(client, admin), branch_a)
    p, m = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(try_lend(client, librarian, p["id"], it["id"]), 409, "MEMBER_PASSIVE")
    at(clock, "2027-11-02", 10, 0)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "MEMBERSHIP_EXPIRED")


def test_t_eq_13_c(client, admin, librarian, branch_a):
    """T-EQ-13-c (LIB-EQ-13): 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt '50.00'; 201"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(try_lend(client, librarian, m1["id"], i1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(try_lend(client, librarian, m2["id"], i2["id"]), 201)


def test_t_eq_13_e(client, admin, librarian, branch_a):
    """T-EQ-13-e (LIB-EQ-13): Next loan: 409 EQUIPMENT_LIMIT_REACHED with details.limit 2 and 3"""
    t = etype(client, admin, max_open=3)
    its = [item(client, admin, t, branch_a) for _ in range(7)]
    s, a = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    elend(client, librarian, s["id"], its[0]["id"]); elend(client, librarian, s["id"], its[1]["id"])
    assert err(try_lend(client, librarian, s["id"], its[2]["id"]), 409, "EQUIPMENT_LIMIT_REACHED")["details"]["limit"] == 2
    for it in its[3:6]:
        elend(client, librarian, a["id"], it["id"])
    assert err(try_lend(client, librarian, a["id"], its[6]["id"]), 409, "EQUIPMENT_LIMIT_REACHED")["details"]["limit"] == 3


def test_t_eq_13_g(client, admin, librarian, branch_a):
    """T-EQ-13-g (LIB-EQ-13): 409 ITEM_NOT_AVAILABLE each"""
    t = etype(client, admin)
    lent, broken, old = (item(client, admin, t, branch_a) for _ in range(3))
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    elend(client, librarian, m1["id"], lent["id"])
    ok(ret(client, librarian, elend(client, librarian, m1["id"], broken["id"])["id"], "damaged", "0.00"))
    ok(act(client, admin, f"equipment-items/{old['id']}/retire"))
    for it in (lent, broken, old):
        err(try_lend(client, librarian, m2["id"], it["id"]), 409, "ITEM_NOT_AVAILABLE")


def test_t_eq_14_a(client, clock, admin, librarian, branch_a):
    """T-EQ-14-a (LIB-EQ-14): 201; then 409 MEMBER_HAS_OVERDUE"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    c1, c2 = (add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"]) for _ in range(2))
    at(clock, TUE, 9, 0)
    elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 13, 15)
    lend(client, librarian, m["id"], c1["id"])
    at(clock, TUE, 13, 16)
    assert error_code(lend(client, librarian, m["id"], c2["id"], expect=409)) == "MEMBER_HAS_OVERDUE"


def test_t_eq_14_c(client, clock, admin, librarian, branch_a):
    """T-EQ-14-c (LIB-EQ-14): 409 MEMBER_HAS_OVERDUE"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    lend(client, librarian, m["id"], add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])["id"])
    at(clock, "2026-11-17", 10, 0)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "MEMBER_HAS_OVERDUE")


def test_t_eq_15_a(client, clock, admin, librarian, branch_a):
    """T-EQ-15-a (LIB-EQ-15): Due 14:20:30; due 20:00"""
    t = etype(client, admin, period=4)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20, 30)
    assert same(elend(client, librarian, m1["id"], i1["id"])["due_at"], TUE, 14, 20, 30)
    at(clock, TUE, 17, 30)
    assert same(elend(client, librarian, m2["id"], i2["id"])["due_at"], TUE, 20, 0)


def test_t_eq_15_c(client, clock, admin, librarian, branch_a):
    """T-EQ-15-c (LIB-EQ-15): Due Mon 2026-11-09 17:00"""
    it = item(client, admin, etype(client, admin, unit="working_days", period=1), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, FRI, 19, 0)
    assert same(elend(client, librarian, m["id"], it["id"])["due_at"], "2026-11-09", 17, 0)


def test_t_eq_17_a(client, clock, admin, librarian, branch_a):
    """T-EQ-17-a (LIB-EQ-17): Order L1, L2; member_id M2 → L2; overdue=true → L1; status=returned → L2"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 0)
    l2 = elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 9, 0)
    l1 = elend(client, librarian, m1["id"], i1["id"])
    at(clock, TUE, 14, 0)
    ok(ret(client, librarian, l2["id"]))
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "equipment-loans", **p))]
    assert ids() == [l1["id"], l2["id"]]
    assert ids(member_id=m2["id"]) == [l2["id"]]
    assert ids(overdue="true") == [l1["id"]]
    assert ids(status="returned") == [l2["id"]]


def test_t_eq_18_a(client, clock, admin, librarian, branch_a):
    """T-EQ-18-a (LIB-EQ-18): 201 with reservation_id; reservation collected with this loan_id"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    at(clock, TUE, 9, 50)
    loan = elend(client, librarian, m["id"], it["id"])
    assert loan["reservation_id"] == res["id"]
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["loan_id"]) == ("collected", loan["id"])


def test_t_eq_19_a(client, clock, admin, librarian, branch_a):
    """T-EQ-19-a (LIB-EQ-19): 200, due 18:20, extended true; then 409 EXTENSION_LIMIT_REACHED"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 13, 0)
    mh = member_headers(client, m)
    r = ok(act(client, mh, f"equipment-loans/{loan['id']}/extend"))
    assert same(r["due_at"], TUE, 18, 20) and r["extended"] is True
    err(act(client, mh, f"equipment-loans/{loan['id']}/extend"), 409, "EXTENSION_LIMIT_REACHED")


def test_t_eq_19_c(client, clock, admin, librarian, branch_a):
    """T-EQ-19-c (LIB-EQ-19): 200 (due 18:20); 409 LOAN_OVERDUE"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 14, 35, 0)
    assert same(ok(act(client, librarian, f"equipment-loans/{l1['id']}/extend"))["due_at"], TUE, 18, 20)
    at(clock, TUE, 14, 35, 1)
    err(act(client, librarian, f"equipment-loans/{l2['id']}/extend"), 409, "LOAN_OVERDUE")


def test_t_eq_19_e(client, clock, admin, librarian, branch_a):
    """T-EQ-19-e (LIB-EQ-19): Due Wed 2026-11-11 17:00; then 409 LOAN_NOT_OPEN"""
    it = item(client, admin, etype(client, admin, unit="working_days", period=3), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    assert same(loan["due_at"], FRI, 17, 0)
    at(clock, "2026-11-05", 10, 0)
    assert same(ok(act(client, librarian, f"equipment-loans/{loan['id']}/extend"))["due_at"], "2026-11-11", 17, 0)
    ok(ret(client, librarian, loan["id"]))
    err(act(client, librarian, f"equipment-loans/{loan['id']}/extend"), 409, "LOAN_NOT_OPEN")


def test_t_eq_20_a(client, clock, admin, librarian, branch_a):
    """T-EQ-20-a (LIB-EQ-20): 200: returned, returned_at 13:00, late_hours 0, received_by set; item available; no fee; then 409 LOAN_NOT_OPEN"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 13, 0)
    r = ok(ret(client, librarian, loan["id"]))
    assert (r["status"], r["late_hours"], r["return_condition"]) == ("returned", 0, "good")
    assert same(r["returned_at"], TUE, 13, 0) and r["received_by"] is not None
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "available"
    assert member_fees(client, librarian, m["id"])["total"] == 0
    err(ret(client, librarian, loan["id"]), 409, "LOAN_NOT_OPEN")


def test_t_eq_21_a(client, admin, librarian, branch_a):
    """T-EQ-21-a (LIB-EQ-21): Item in_repair; one equipment_damage_fee 300.00 with equipment_loan_id, loan_id null"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    assert ok(ret(client, librarian, loan["id"], "damaged", "300.00"))["return_condition"] == "damaged"
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "in_repair"
    fees = items(member_fees(client, librarian, m["id"]))
    assert [(f["kind"], f["amount"], f["equipment_loan_id"], f["loan_id"]) for f in fees] == [("equipment_damage_fee", "300.00", loan["id"], None)]


def test_t_eq_22_a(client, clock, admin, librarian, branch_a):
    """T-EQ-22-a (LIB-EQ-22): late_hours 0 (no fee) and 1"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 14, 35)
    assert ok(ret(client, librarian, l1["id"]))["late_hours"] == 0
    at(clock, TUE, 14, 36)
    assert ok(ret(client, librarian, l2["id"]))["late_hours"] == 1
    assert member_fees(client, librarian, m1["id"])["total"] == 0


def test_t_eq_22_c(client, clock, admin, librarian, branch_a):
    """T-EQ-22-c (LIB-EQ-22): late_hours 61 (nights and weekend count); fee 200.00 (cap)"""
    it = item(client, admin, etype(client, admin), branch_a, value="1000.00")
    m = member(client, librarian, branch_a)
    at(clock, FRI, 16, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, "2026-11-09", 9, 0)
    assert ok(ret(client, librarian, loan["id"]))["late_hours"] == 61
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "200.00")]


def test_t_eq_23_a(client, clock, admin, librarian, branch_a):
    """T-EQ-23-a (LIB-EQ-23): late_hours 30; equipment_late_fee 750.00"""
    it = item(client, admin, etype(client, admin, period=2, fee="25.00"), branch_a, value="30000.00")
    m = member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, WED, 17, 0)
    assert ok(ret(client, librarian, loan["id"]))["late_hours"] == 30
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "750.00")]


def test_t_eq_24_a(client, clock, admin, librarian, branch_a):
    """T-EQ-24-a (LIB-EQ-24): lost, returned_at null, late_hours 2; fees equipment_late_fee 10.00 and equipment_lost 1000.00; item lost"""
    it = item(client, admin, etype(client, admin), branch_a, value="1000.00")
    m = member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 15, 0)
    r = ok(act(client, librarian, f"equipment-loans/{loan['id']}/report-lost"))
    assert (r["status"], r["returned_at"], r["late_hours"]) == ("lost", None, 2)
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "10.00"), ("equipment_lost", "1000.00")]
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "lost"


def test_t_eq_25_a(client, admin, librarian, branch_a):
    """T-EQ-25-a (LIB-EQ-25): Fee paid 10.00, outstanding 20.00, balance 20.00; after waiving waived"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"], "damaged", "30.00"))
    pay(client, librarian, m["id"], "10.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    assert (fee["paid_amount"], fee["outstanding"], fee["status"]) == ("10.00", "20.00", "open")
    assert balance(client, librarian, m["id"])["outstanding_fees"] == "20.00"
    assert waive(client, admin, fee["id"])["status"] == "waived"


def test_t_eq_26_a(client, admin, librarian, branch_a):
    """T-EQ-26-a (LIB-EQ-26): 201: booked, own member_id, ends_at 14:00, loan_id and closed_at null"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    r = ok(try_reserve(client, member_headers(client, m), t["id"], branch_a["id"], ts(TUE, 10)), 201)
    assert (r["status"], r["member_id"], r["type_id"], r["branch_id"], r["loan_id"], r["closed_at"]) == ("booked", m["id"], t["id"], branch_a["id"], None, None)
    assert same(r["starts_at"], TUE, 10, 0) and same(r["ends_at"], TUE, 14, 0)


def test_t_eq_26_c(client, admin, librarian, branch_a):
    """T-EQ-26-c (LIB-EQ-26): 201 for that member; ends_at Fri 2026-11-06 17:00"""
    t = etype(client, admin, unit="working_days", period=3)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, t, branch_a, m, TUE, 10)
    assert r["member_id"] == m["id"] and same(r["ends_at"], FRI, 17, 0)


def test_t_eq_27_a(client, clock, admin, librarian, branch_a):
    """T-EQ-27-a (LIB-EQ-27): 409 ITEM_NEEDED_FOR_RESERVATION; then 201 (due 14:00, needed until 14:15)"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m1, TUE, 14, 30)
    at(clock, TUE, 10, 1)
    err(try_lend(client, librarian, m2["id"], it["id"]), 409, "ITEM_NEEDED_FOR_RESERVATION")
    at(clock, TUE, 10, 0)
    ok(try_lend(client, librarian, m2["id"], it["id"]), 201)


def test_t_eq_27_c(client, clock, admin, librarian, branch_a):
    """T-EQ-27-c (LIB-EQ-27): 409 NO_EQUIPMENT_AVAILABLE with details.next_free_at null (an overdue loan needs its item until returned)"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    elend(client, librarian, m1["id"], it["id"])
    at(clock, MON, 14, 0)
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m2["id"]), 409, "NO_EQUIPMENT_AVAILABLE")
    assert e["details"]["next_free_at"] is None


def test_t_eq_28_a(client, admin, librarian, branch_a):
    """T-EQ-28-a (LIB-EQ-28): 409 MEMBER_PASSIVE; 409 EQUIPMENT_NOT_ALLOWED_FOR_TYPE"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    p, g = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="guest")
    deactivate_member(client, librarian, p["id"])
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=p["id"]), 409, "MEMBER_PASSIVE")
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=g["id"]), 409, "EQUIPMENT_NOT_ALLOWED_FOR_TYPE")


def test_t_eq_28_c(client, admin, librarian, branch_a):
    """T-EQ-28-c (LIB-EQ-28): 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt '50.00'"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m, "50.00")
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"


def test_t_eq_28_e(client, admin, librarian, branch_a):
    """T-EQ-28-e (LIB-EQ-28): 409 DESK_CLOSED three times; Tue 19:30 201 with ends_at 20:00"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    for day, hh, mm in ((SAT, 10, 0), (TUE, 20, 0), (TUE, 7, 30)):
        err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(day, hh, mm), member_id=m["id"]), 409, "DESK_CLOSED")
    assert same(reserve(client, librarian, t, branch_a, m, TUE, 19, 30)["ends_at"], TUE, 20, 0)


def test_t_eq_28_g(client, admin, librarian, branch_a):
    """T-EQ-28-g (LIB-EQ-28): 201; 409 RESERVATION_TOO_FAR_AHEAD with details.latest_date 2026-11-16"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, "2026-11-16", 19, 30)
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2026-11-17", 8), member_id=m["id"]), 409, "RESERVATION_TOO_FAR_AHEAD")
    assert e["details"]["latest_date"] == "2026-11-16"


def test_t_eq_28_i(client, admin, librarian, branch_a):
    """T-EQ-28-i (LIB-EQ-28): 409 DUPLICATE_EQUIPMENT_RESERVATION; 201"""
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, TUE, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 13, 30), member_id=m["id"]), 409, "DUPLICATE_EQUIPMENT_RESERVATION")
    reserve(client, librarian, t, branch_a, m, TUE, 14)


def test_t_eq_29_a(client, clock, admin, librarian, branch_a):
    """T-EQ-29-a (LIB-EQ-29): 201: item EQ-0001, reservation_id set, due 13:45; reservation collected with loan_id, closed_at 09:45"""
    t = etype(client, admin)
    item(client, admin, t, branch_a, tag="EQ-0002"); item(client, admin, t, branch_a, tag="EQ-0001")
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    at(clock, TUE, 9, 45)
    loan = ok(try_lend(client, librarian, m["id"], reservation_id=res["id"]), 201)
    assert (loan["asset_tag"], loan["reservation_id"]) == ("EQ-0001", res["id"]) and same(loan["due_at"], TUE, 13, 45)
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["loan_id"]) == ("collected", loan["id"]) and same(r["closed_at"], TUE, 9, 45)


def test_t_eq_29_c(client, clock, admin, librarian, branch_a):
    """T-EQ-29-c (LIB-EQ-29): 409 RESERVATION_OF_OTHER_MEMBER; 409 RESERVATION_NOT_ACTIVE"""
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m1, TUE, 10)
    at(clock, TUE, 10, 0)
    err(try_lend(client, librarian, m2["id"], reservation_id=res["id"]), 409, "RESERVATION_OF_OTHER_MEMBER")
    ok(act(client, member_headers(client, m1), f"equipment-reservations/{res['id']}/cancel"))
    err(try_lend(client, librarian, m1["id"], reservation_id=res["id"]), 409, "RESERVATION_NOT_ACTIVE")


def test_t_eq_30_a(client, admin, librarian, branch_a):
    """T-EQ-30-a (LIB-EQ-30): 200 cancelled, member_request, closed_at set, no notification; then 409 RESERVATION_NOT_ACTIVE"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    mh = member_headers(client, m)
    r = ok(act(client, mh, f"equipment-reservations/{res['id']}/cancel"))
    assert (r["status"], r["cancel_reason"]) == ("cancelled", "member_request") and r["closed_at"] is not None
    assert notes(client, librarian, m["id"], "equipment_reservation_cancelled") == []
    err(act(client, mh, f"equipment-reservations/{res['id']}/cancel"), 409, "RESERVATION_NOT_ACTIVE")


def test_t_eq_31_a(client, clock, admin, librarian, branch_a):
    """T-EQ-31-a (LIB-EQ-31): expired_reservations 0, then 1; reservation expired with closed_at 10:30:01"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    res = reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    at(clock, TUE, 10, 30, 0)
    assert process(client, librarian)["expired_reservations"] == 0
    at(clock, TUE, 10, 30, 1)
    assert process(client, librarian)["expired_reservations"] == 1
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert r["status"] == "expired" and same(r["closed_at"], TUE, 10, 30, 1)


def test_t_eq_33_a(client, admin, librarian, branch_a):
    """T-EQ-33-a (LIB-EQ-33): Capacity 2; 24 slots 08:00…19:30; free 2 at 09:00, 1 at 09:30 and 13:30, 2 at 14:00"""
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    r = get(client, librarian, f"equipment-types/{t['id']}/availability", branch_id=branch_a["id"], date=TUE)
    assert (r["type_id"], r["branch_id"], r["date"], r["capacity"]) == (t["id"], branch_a["id"], TUE, 2)
    free = {s["start"]: s["free"] for s in r["slots"]}
    assert len(r["slots"]) == 24 and r["slots"][0]["start"] == "08:00" and r["slots"][-1]["start"] == "19:30"
    assert (free["09:00"], free["09:30"], free["13:30"], free["14:00"]) == (2, 1, 1, 2)


def test_t_eq_34_a(client, admin, librarian, branch_a):
    """T-EQ-34-a (LIB-EQ-34): Order R3, R2, R1; from=to=Wed → R1; status=cancelled → R2; member_id M1 → R3, R1"""
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = reserve(client, librarian, t, branch_a, m1, WED, 10)
    r2 = reserve(client, librarian, t, branch_a, m2, TUE, 12)
    r3 = reserve(client, librarian, t, branch_a, m1, TUE, 8)
    ok(act(client, librarian, f"equipment-reservations/{r2['id']}/cancel"))
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "equipment-reservations", **p))]
    assert ids() == [r3["id"], r2["id"], r1["id"]]
    assert ids(**{"from": WED, "to": WED}) == [r1["id"]]
    assert ids(status="cancelled") == [r2["id"]]
    assert ids(member_id=m1["id"]) == [r3["id"], r1["id"]]


def test_t_eq_35_a(client, admin, librarian, branch_a):
    """T-EQ-35-a (LIB-EQ-35): 409 MEMBER_HAS_OPEN_LOANS"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    elend(client, librarian, m["id"], it["id"])
    assert error_code(deactivate_member(client, librarian, m["id"], expect=409)) == "MEMBER_HAS_OPEN_LOANS"


def test_t_eq_37_a(client, clock, admin, librarian, branch_a):
    """T-EQ-37-a (LIB-EQ-37): equipment = {open_loans: 1, overdue_loans: 1, booked_reservations: 1}; borrowing.eligible false with MEMBER_HAS_OVERDUE"""
    t = etype(client, admin)
    i1, _ = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, WED, 10)
    at(clock, TUE, 9, 0)
    elend(client, librarian, m["id"], i1["id"])
    at(clock, TUE, 14, 0)
    s = get(client, librarian, f"members/{m['id']}/summary")
    assert s["equipment"] == {"open_loans": 1, "overdue_loans": 1, "booked_reservations": 1}
    assert s["borrowing"]["eligible"] is False and "MEMBER_HAS_OVERDUE" in s["borrowing"]["reasons"]


def test_t_eq_38_a(client, admin, librarian, branch_a):
    """T-EQ-38-a (LIB-EQ-38): One equipment_loan_created and one equipment_loan_returned notification with equipment_loan_id; messages contain EQ-0777"""
    it = item(client, admin, etype(client, admin), branch_a, tag="EQ-0777")
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    ok(ret(client, librarian, loan["id"]))
    for type_ in ("equipment_loan_created", "equipment_loan_returned"):
        rows = notes(client, librarian, m["id"], type_)
        assert len(rows) == 1 and rows[0]["equipment_loan_id"] == loan["id"] and "EQ-0777" in rows[0]["message"]


def test_t_eq_38_c(client, admin, librarian, branch_a):
    """T-EQ-38-c (LIB-EQ-38): One equipment_loan_lost and one fee_created notification"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    ok(act(client, librarian, f"equipment-loans/{loan['id']}/report-lost"))
    assert len(notes(client, librarian, m["id"], "equipment_loan_lost")) == 1
    assert len(notes(client, librarian, m["id"], "fee_created")) == 1


def test_t_eq_39_a(client, admin, librarian, branch_a):
    """T-EQ-39-a (LIB-EQ-39): One entry each for equipment_type_created, equipment_item_created, equipment_training_recorded, equipment_loan_created, equipment_loan_returned"""
    t = etype(client, admin, training=True)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"]))
    for event in ("equipment_type_created", "equipment_item_created", "equipment_training_recorded", "equipment_loan_created", "equipment_loan_returned"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event


def test_t_eq_40_a(client, clock, admin, librarian, branch_a, branch_b):
    """T-EQ-40-a (LIB-EQ-40): Branch A: AA {loans 2, late_returns 1, late_hours 2, damaged_returns 1, lost 0, reservations 1, expired_reservations 1, fees_created '50.00'}, BB all 0 and '0.00'; without branch AA loans 3"""
    aa, bb = etype(client, admin, code="AA"), etype(client, admin, code="BB")
    i1, i2, i3 = item(client, admin, aa, branch_a), item(client, admin, aa, branch_a), item(client, admin, aa, branch_b)
    m1, m2, m3, m4 = (member(client, librarian, branch_a) for _ in range(4))
    reserve(client, librarian, aa, branch_a, m4, WED, 10)
    at(clock, TUE, 9, 0)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    elend(client, librarian, m3["id"], i3["id"])
    at(clock, TUE, 12, 0)
    ok(ret(client, librarian, l2["id"], "damaged", "40.00"))
    at(clock, TUE, 15, 0)
    ok(ret(client, librarian, l1["id"]))
    at(clock, WED, 10, 31)
    process(client, librarian)
    p = {"from": MON, "to": WED}
    rows = items(get(client, librarian, "reports/equipment-usage", branch_id=branch_a["id"], **p))
    keys = ("type_code", "loans", "late_returns", "late_hours", "damaged_returns", "lost", "reservations", "expired_reservations", "fees_created")
    assert [tuple(r[k] for k in keys) for r in rows] == [("AA", 2, 1, 2, 1, 0, 1, 1, "50.00"), ("BB", 0, 0, 0, 0, 0, 0, 0, "0.00")]
    assert items(get(client, librarian, "reports/equipment-usage", **p))[0]["loans"] == 3


def test_t_eq_41_a(client, admin, librarian, branch_a):
    """T-EQ-41-a (LIB-EQ-41): The export has exactly the keys of 22.1 (no equipment data)"""
    it = item(client, admin, etype(client, admin), branch_a)
    elend(client, librarian, member(client, librarian, branch_a)["id"], it["id"])
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
