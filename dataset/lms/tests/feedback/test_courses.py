"""Feedback tests: module 21 (Course reserves). Generated from cases/courses.md."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from support.api import (
    add_copy, balance, create_book, create_branch, deactivate_member, error_code, items, lend, member_fees,
    member_headers, register_member, reserve, return_loan,
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


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def academic(client, lib, branch):
    return member(client, lib, branch, membership_type="academic")


def try_course(client, headers, branch, instructor, **fields):
    _seq[0] += 1
    body = {"code": f"CS{_seq[0]:03d}", "title": f"Course {_seq[0]}", "term": "2026-fall", "instructor_id": instructor["id"],
            "branch_id": branch["id"], "starts_on": "2026-10-01", "ends_on": "2027-01-15"}
    body.update(fields)
    return post(client, headers, "courses", body)


def course(client, headers, branch, instructor, **fields):
    return ok(try_course(client, headers, branch, instructor, **fields), 201)


def book(client, lib, branch=None, copies=0, price="100.00", title="Book"):
    b = create_book(client, lib, title=title)
    cps = [add_copy(client, lib, b["id"], home_branch_id=branch["id"], price=price) for _ in range(copies)]
    return b, cps


def try_item(client, headers, course_id, book_id, **fields):
    return post(client, headers, f"courses/{course_id}/reading-list", {"book_id": book_id, **fields})


def item(client, headers, course_id, book_id, **fields):
    return ok(try_item(client, headers, course_id, book_id, **fields), 201)


def enroll(client, lib, course_id, *members):
    return ok(post(client, lib, f"courses/{course_id}/enrollments", {"member_ids": [m["id"] for m in members]}))


def activate(client, lib, course_id):
    return post(client, lib, f"courses/{course_id}/activate")


def place(client, lib, item_id, copy_id):
    return post(client, lib, f"reading-list-items/{item_id}/copies", {"copy_id": copy_id})


def setup(client, lib, branch, *, copies=1, wanted=None, period="2h", students=1, price="100.00", active=True, **course_fields):
    """An instructor, a course with one required item whose copies are on reserve, enrolled students."""
    ins = academic(client, lib, branch)
    c = course(client, lib, branch, ins, **course_fields)
    b, cps = book(client, lib, branch, copies, price, title="Reserve Book")
    it = item(client, lib, c["id"], b["id"], loan_period=period, copies_wanted=wanted or max(copies, 1))
    ss = [member(client, lib, branch) for _ in range(students)]
    if ss:
        enroll(client, lib, c["id"], *ss)
    if active:
        ok(activate(client, lib, c["id"]))
    return SimpleNamespace(course=c, ins=ins, book=b, copies=cps, item=it, students=ss)


def more_item(client, lib, branch, course_id, copies=1, **fields):
    b, cps = book(client, lib, branch, copies)
    return item(client, lib, course_id, b["id"], copies_wanted=max(copies, 1), **fields), cps


def rlend(client, headers, member_id, copy_id):
    return post(client, headers, "reserve-loans", {"member_id": member_id, "copy_id": copy_id})


def rloan(client, lib, member_, copy):
    return ok(rlend(client, lib, member_["id"], copy["id"]), 201)


def rreturn(client, lib, loan_id, branch):
    return post(client, lib, f"reserve-loans/{loan_id}/return", {"branch_id": branch["id"]})


def copy_of(client, lib, copy_id):
    return get(client, lib, f"copies/{copy_id}")


def item_of(client, lib, course_id, item_id, **params):
    return [x for x in items(get(client, lib, f"courses/{course_id}/reading-list", **params)) if x["id"] == item_id][0]


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def fees_of(client, lib, member_id):
    return [(f["kind"], f["amount"]) for f in items(member_fees(client, lib, member_id))]


def debt(client, lib, branch, member_, amount="50.00"):
    _, (copy,) = book(client, lib, branch, 1)
    loan = lend(client, lib, member_["id"], copy["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=amount)


def test_t_crs_01_a(client, librarian, branch_a):
    """T-CRS-01-a (LIB-CRS-01): 201 draft; code CENG301; limit 100"""
    ins = academic(client, librarian, branch_a)
    c = course(client, librarian, branch_a, ins, code="ceng301", title="Veri Yapıları")
    assert (c["code"], c["title"], c["term"], c["status"], c["enrollment_limit"], c["instructor_id"]) == ("CENG301", "Veri Yapıları", "2026-fall", "draft", 100, ins["id"])
    assert (c["starts_on"], c["ends_on"], c["activated_at"], c["closed_at"]) == ("2026-10-01", "2027-01-15", None, None)


def test_t_crs_01_c(client, librarian, branch_a):
    """T-CRS-01-c (LIB-CRS-01): 201 each"""
    ins = academic(client, librarian, branch_a)
    course(client, librarian, branch_a, ins, starts_on=MON, ends_on="2026-11-08")
    course(client, librarian, branch_a, ins, starts_on=MON, ends_on="2027-04-30")
    course(client, librarian, branch_a, ins, starts_on="2026-10-01", ends_on=MON)


def test_t_crs_02_a(client, admin, librarian, branch_a):
    """T-CRS-02-a (LIB-CRS-02): BRANCH_INACTIVE; INSTRUCTOR_NOT_ACADEMIC twice"""
    ins = academic(client, librarian, branch_a)
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_course(client, librarian, qq, ins), 409, "BRANCH_INACTIVE")
    err(try_course(client, librarian, branch_a, member(client, librarian, branch_a)), 409, "INSTRUCTOR_NOT_ACADEMIC")
    p = academic(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(try_course(client, librarian, branch_a, p), 409, "INSTRUCTOR_NOT_ACADEMIC")


def test_t_crs_03_a(client, librarian, branch_a):
    """T-CRS-03-a (LIB-CRS-03): 200; 422; 409 ENROLLMENT_LIMIT_BELOW_ENROLLED with details.enrolled 2; 409 INVALID_COURSE_STATUS"""
    s = setup(client, librarian, branch_a, students=2, active=False)
    url = f"/api/v1/courses/{s.course['id']}"
    out = ok(client.patch(url, headers=librarian, json={"title": "Algoritmalar", "enrollment_limit": 50}))
    assert (out["title"], out["enrollment_limit"]) == ("Algoritmalar", 50)
    assert client.patch(url, headers=librarian, json={"code": "ABC123"}).status_code == 422
    assert err(client.patch(url, headers=librarian, json={"enrollment_limit": 1}), 409, "ENROLLMENT_LIMIT_BELOW_ENROLLED")["details"]["enrolled"] == 2
    ok(post(client, librarian, f"courses/{s.course['id']}/close"))
    assert err(client.patch(url, headers=librarian, json={"title": "X"}), 409, "INVALID_COURSE_STATUS")["details"]["status"] == "closed"


def test_t_crs_04_a(client, librarian, branch_a):
    """T-CRS-04-a (LIB-CRS-04): 409 COURSE_READING_LIST_EMPTY; 200 active with activated_at, one course_activated notification; 409 INVALID_COURSE_STATUS with details.status active"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    st = member(client, librarian, branch_a)
    enroll(client, librarian, c["id"], st)
    err(activate(client, librarian, c["id"]), 409, "COURSE_READING_LIST_EMPTY")
    b, _ = book(client, librarian, branch_a, 1)
    item(client, librarian, c["id"], b["id"])
    out = ok(activate(client, librarian, c["id"]))
    assert out["status"] == "active" and same(out["activated_at"], MON, 9)
    assert len(notes(client, librarian, st["id"], "course_activated")) == 1
    assert err(activate(client, librarian, c["id"]), 409, "INVALID_COURSE_STATUS")["details"]["status"] == "active"


def test_t_crs_05_a(client, librarian, branch_a):
    """T-CRS-05-a (LIB-CRS-05): Order CENG301, MATH101, CENG101; counts {enrolled 2, items 2, copies_on_reserve 1}; q gives CENG301 and CENG101"""
    ins = academic(client, librarian, branch_a)
    m = course(client, librarian, branch_a, ins, code="MATH101")
    s = setup(client, librarian, branch_a, students=2, active=False, code="CENG301")
    item(client, librarian, s.course["id"], book(client, librarian, branch_a, 1)[0]["id"], kind="recommended")
    sp = course(client, librarian, branch_a, ins, code="CENG101", term="2027-spring", starts_on="2027-02-15", ends_on="2027-06-10")
    rows = items(get(client, librarian, "courses"))
    assert [r["id"] for r in rows] == [s.course["id"], m["id"], sp["id"]]
    row = rows[0]
    assert (row["enrolled"], row["items"], row["copies_on_reserve"]) == (2, 2, 1)
    assert [r["id"] for r in items(get(client, librarian, "courses", q="ceng"))] == [s.course["id"], sp["id"]]


def test_t_crs_07_a(client, clock, librarian, branch_a):
    """T-CRS-07-a (LIB-CRS-07): COURSE_NOT_RUNNING; Mon COURSE_NOT_RUNNING, Tue 201; Mon 201, Tue COURSE_NOT_RUNNING"""
    d = setup(client, librarian, branch_a, active=False)
    err(rlend(client, librarian, d.students[0]["id"], d.copies[0]["id"]), 409, "COURSE_NOT_RUNNING")
    later = setup(client, librarian, branch_a, students=2, starts_on=TUE, ends_on="2026-12-31")
    ended = setup(client, librarian, branch_a, students=2, starts_on="2026-10-01", ends_on=MON)
    err(rlend(client, librarian, later.students[0]["id"], later.copies[0]["id"]), 409, "COURSE_NOT_RUNNING")
    l1 = rloan(client, librarian, ended.students[0], ended.copies[0])
    ok(rreturn(client, librarian, l1["id"], branch_a))
    at(clock, TUE)
    rloan(client, librarian, later.students[0], later.copies[0])
    err(rlend(client, librarian, ended.students[1]["id"], ended.copies[0]["id"]), 409, "COURSE_NOT_RUNNING")


def test_t_crs_08_a(client, librarian, branch_a):
    """T-CRS-08-a (LIB-CRS-08): enrolled [S1]; skipped A NOT_A_STUDENT, S2 ENROLLMENT_FULL; S1 gets one course_enrolled notification"""
    s = setup(client, librarian, branch_a, active=False, enrollment_limit=2)
    a, s1, s2 = academic(client, librarian, branch_a), member(client, librarian, branch_a), member(client, librarian, branch_a)
    out = enroll(client, librarian, s.course["id"], a, s1, s2)
    assert out == {"enrolled": [s1["id"]], "skipped": [{"member_id": a["id"], "error_code": "NOT_A_STUDENT"}, {"member_id": s2["id"], "error_code": "ENROLLMENT_FULL"}]}
    assert len(notes(client, librarian, s1["id"], "course_enrolled")) == 1


def test_t_crs_08_c(client, clock, librarian, branch_a):
    """T-CRS-08-c (LIB-CRS-08): Enrolled; skipped MEMBERSHIP_EXPIRED"""
    st = member(client, librarian, branch_a)
    ins = academic(client, librarian, branch_a)
    c1 = course(client, librarian, branch_a, ins, term="2027-fall", starts_on="2027-10-01", ends_on="2028-01-15")
    c2 = course(client, librarian, branch_a, ins, term="2027-fall", starts_on="2027-10-01", ends_on="2028-01-15")
    at(clock, "2027-11-01")
    assert enroll(client, librarian, c1["id"], st)["enrolled"] == [st["id"]]
    at(clock, "2027-11-02")
    assert enroll(client, librarian, c2["id"], st)["skipped"] == [{"member_id": st["id"], "error_code": "MEMBERSHIP_EXPIRED"}]


def test_t_crs_09_a(client, librarian, branch_a):
    """T-CRS-09-a (LIB-CRS-09): 422; 422; 409 INVALID_COURSE_STATUS"""
    s = setup(client, librarian, branch_a, students=0, active=False)
    s1 = member(client, librarian, branch_a)
    url = f"courses/{s.course['id']}/enrollments"
    assert post(client, librarian, url, {"member_ids": [s1["id"], s1["id"]]}).status_code == 422
    assert post(client, librarian, url, {"member_ids": []}).status_code == 422
    ok(post(client, librarian, f"courses/{s.course['id']}/close"))
    err(post(client, librarian, url, {"member_ids": [s1["id"]]}), 409, "INVALID_COURSE_STATUS")


def test_t_crs_10_a(client, librarian, branch_a):
    """T-CRS-10-a (LIB-CRS-10): 200 dropped with staff_request; 409 ENROLLMENT_NOT_ACTIVE; a new enrollment"""
    s = setup(client, librarian, branch_a, active=False)
    st = s.students[0]
    e = items(get(client, librarian, f"courses/{s.course['id']}/enrollments"))[0]
    out = ok(post(client, librarian, f"enrollments/{e['id']}/drop"))
    assert (out["status"], out["drop_reason"]) == ("dropped", "staff_request") and same(out["dropped_at"], MON, 9)
    err(post(client, librarian, f"enrollments/{e['id']}/drop"), 409, "ENROLLMENT_NOT_ACTIVE")
    enroll(client, librarian, s.course["id"], st)
    rows = items(get(client, librarian, f"courses/{s.course['id']}/enrollments"))
    assert [(r["member_id"], r["status"]) for r in rows] == [(st["id"], "dropped"), (st["id"], "enrolled")] and rows[1]["id"] != e["id"]


def test_t_crs_11_a(client, librarian, branch_a):
    """T-CRS-11-a (LIB-CRS-11): Rows with member_no and full_name; instructor 200; student 403; roles student and instructor"""
    s = setup(client, librarian, branch_a, students=2, active=False)
    url = f"/api/v1/courses/{s.course['id']}/enrollments"
    rows = items(ok(client.get(url, headers=librarian)))
    assert [(r["member_id"], r["member_no"], r["full_name"]) for r in rows] == [(m["id"], m["member_no"], m["full_name"]) for m in s.students]
    assert ok(client.get(url, headers=member_headers(client, s.ins)))["total"] == 2
    assert client.get(url, headers=member_headers(client, s.students[0])).status_code == 403
    for m, role in ((s.students[0], "student"), (s.ins, "instructor")):
        rows = items(get(client, member_headers(client, m), f"members/{m['id']}/courses"))
        assert [(r["id"], r["role"]) for r in rows] == [(s.course["id"], role)]


def test_t_crs_12_a(client, librarian, branch_a, branch_b):
    """T-CRS-12-a (LIB-CRS-12): 201: positions 1 and 2, status requested, required, 2h, copies_wanted 1, note empty"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    b1, _ = book(client, librarian, branch_b, 1)
    b2, _ = book(client, librarian, branch_b, 1)
    i1, i2 = item(client, librarian, c["id"], b1["id"]), item(client, librarian, c["id"], b2["id"])
    keys = ("position", "status", "kind", "loan_period", "copies_wanted", "note", "book_id")
    assert [tuple(i[k] for k in keys) for i in (i1, i2)] == [(1, "requested", "required", "2h", 1, "", b1["id"]), (2, "requested", "required", "2h", 1, "", b2["id"])]


def test_t_crs_12_c(client, librarian, branch_a, branch_b):
    """T-CRS-12-c (LIB-CRS-12): 409 READING_LIST_FULL; then 201"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    first = None
    for _ in range(40):
        it = item(client, librarian, c["id"], book(client, librarian, branch_b, 1)[0]["id"], kind="recommended")
        first = first or it
    extra, _ = book(client, librarian, branch_b, 1)
    err(try_item(client, librarian, c["id"], extra["id"]), 409, "READING_LIST_FULL")
    ok(post(client, librarian, f"reading-list-items/{first['id']}/remove"))
    assert item(client, librarian, c["id"], extra["id"])["position"] == 40


def test_t_crs_13_a(client, librarian, branch_a, branch_b):
    """T-CRS-13-a (LIB-CRS-13): The first two copies (by id) on_reserve and the item on_reserve with 2 copies; the recommended item requested with 0"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    b, cps = book(client, librarian, branch_a, 3)
    add_copy(client, librarian, b["id"], home_branch_id=branch_b["id"])
    it = item(client, librarian, c["id"], b["id"], copies_wanted=2)
    assert (it["status"], it["copies_on_reserve"]) == ("on_reserve", 2)
    assert [copy_of(client, librarian, x["id"])["status"] for x in cps] == ["on_reserve", "on_reserve", "available"]
    assert copy_of(client, librarian, cps[0]["id"])["reserve_item_id"] == it["id"]
    b2, cps2 = book(client, librarian, branch_a, 1)
    rec = item(client, librarian, c["id"], b2["id"], kind="recommended")
    assert (rec["status"], rec["copies_on_reserve"]) == ("requested", 0)
    assert copy_of(client, librarian, cps2[0]["id"])["status"] == "available"


def test_t_crs_14_a(client, librarian, branch_a):
    """T-CRS-14-a (LIB-CRS-14): 409 COPIES_WANTED_BELOW_RESERVE with details.on_reserve 2; 200; 409 ITEM_REMOVED"""
    s = setup(client, librarian, branch_a, copies=2, active=False)
    url = f"/api/v1/reading-list-items/{s.item['id']}"
    assert err(client.patch(url, headers=librarian, json={"copies_wanted": 1}), 409, "COPIES_WANTED_BELOW_RESERVE")["details"]["on_reserve"] == 2
    assert ok(client.patch(url, headers=librarian, json={"note": "Bölüm 3"}))["note"] == "Bölüm 3"
    ok(post(client, librarian, f"reading-list-items/{s.item['id']}/remove"))
    err(client.patch(url, headers=librarian, json={"note": "X"}), 409, "ITEM_REMOVED")


def test_t_crs_15_a(client, librarian, branch_a, branch_b):
    """T-CRS-15-a (LIB-CRS-15): 200 positions I3 1, I1 2, I2 3; 422; 422"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    i1, i2, i3 = (item(client, librarian, c["id"], book(client, librarian, branch_b, 1)[0]["id"]) for _ in range(3))
    url = f"/api/v1/courses/{c['id']}/reading-list/order"
    out = ok(client.put(url, headers=librarian, json={"item_ids": [i3["id"], i1["id"], i2["id"]]}))
    assert [(x["id"], x["position"]) for x in items(out)] == [(i3["id"], 1), (i1["id"], 2), (i2["id"], 3)]
    assert client.put(url, headers=librarian, json={"item_ids": [i3["id"], i1["id"]]}).status_code == 422
    assert client.put(url, headers=librarian, json={"item_ids": [i1["id"], i1["id"], i2["id"]]}).status_code == 422


def test_t_crs_17_a(client, clock, librarian, branch_a, branch_b):
    """T-CRS-17-a (LIB-CRS-17): copies_on_reserve 2, available_now 0, next_due_at 11:00, book_title; removed item only with include_removed, after the others"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    gone = item(client, librarian, s.course["id"], book(client, librarian, branch_b, 1)[0]["id"])
    ok(post(client, librarian, f"reading-list-items/{gone['id']}/remove"))
    rloan(client, librarian, s.students[0], s.copies[0])
    it = item_of(client, librarian, s.course["id"], s.item["id"])
    assert (it["available_now"], it["next_due_at"]) == (1, None)
    at(clock, MON, 9, 30)
    rloan(client, librarian, s.students[1], s.copies[1])
    it = item_of(client, librarian, s.course["id"], s.item["id"])
    assert (it["book_title"], it["copies_on_reserve"], it["available_now"]) == ("Reserve Book", 2, 0) and same(it["next_due_at"], MON, 11)
    assert [x["id"] for x in items(get(client, librarian, f"courses/{s.course['id']}/reading-list"))] == [s.item["id"]]
    assert [x["id"] for x in items(get(client, librarian, f"courses/{s.course['id']}/reading-list", include_removed="true"))] == [s.item["id"], gone["id"]]


def test_t_crs_19_a(client, librarian, branch_a):
    """T-CRS-19-a (LIB-CRS-19): 201 {copy_id, barcode, item_id, course_id, on_loan false}; copy on_reserve; item on_reserve"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    b, (cp,) = book(client, librarian, branch_a, 1)
    it = item(client, librarian, c["id"], b["id"], kind="recommended")
    out = ok(place(client, librarian, it["id"], cp["id"]), 201)
    keys = ("copy_id", "barcode", "item_id", "course_id", "on_loan")
    assert tuple(out[k] for k in keys) == (cp["id"], cp["barcode"], it["id"], c["id"], False)
    assert copy_of(client, librarian, cp["id"])["status"] == "on_reserve"
    assert item_of(client, librarian, c["id"], it["id"])["status"] == "on_reserve"


def test_t_crs_19_c(client, librarian, branch_a):
    """T-CRS-19-c (LIB-CRS-19): One reserve_item_available notification with course_id"""
    s = setup(client, librarian, branch_a)
    b, (c1, c2) = book(client, librarian, branch_a, 2)
    it = item(client, librarian, s.course["id"], b["id"], kind="recommended", copies_wanted=2)
    ok(place(client, librarian, it["id"], c1["id"]), 201)
    ok(place(client, librarian, it["id"], c2["id"]), 201)
    ns = notes(client, librarian, s.students[0]["id"], "reserve_item_available")
    assert len(ns) == 1 and ns[0]["course_id"] == s.course["id"]


def test_t_crs_21_a(client, librarian, branch_a):
    """T-CRS-21-a (LIB-CRS-21): 409 RESERVE_COPY_ON_LOAN; 200: copy available, reserve_item_id null, item requested; 409 INVALID_COPY_STATUS"""
    s = setup(client, librarian, branch_a)
    cp = s.copies[0]
    loan = rloan(client, librarian, s.students[0], cp)
    assert err(post(client, librarian, f"copies/{cp['id']}/unreserve"), 409, "RESERVE_COPY_ON_LOAN")["details"]["loan_ids"] == [loan["id"]]
    ok(rreturn(client, librarian, loan["id"], branch_a))
    out = ok(post(client, librarian, f"copies/{cp['id']}/unreserve"))
    assert (out["status"], out["reserve_item_id"]) == ("available", None)
    assert item_of(client, librarian, s.course["id"], s.item["id"])["status"] == "requested"
    err(post(client, librarian, f"copies/{cp['id']}/unreserve"), 409, "INVALID_COPY_STATUS")


def test_t_crs_22_a(client, librarian, branch_a):
    """T-CRS-22-a (LIB-CRS-22): C on_reserve for K1's item (reserve_course_id K1); K2's item still requested"""
    b, (cp,) = book(client, librarian, branch_a, 1)
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    ins = academic(client, librarian, branch_a)
    k1, k2 = course(client, librarian, branch_a, ins), course(client, librarian, branch_a, ins)
    i1, i2 = item(client, librarian, k1["id"], b["id"]), item(client, librarian, k2["id"], b["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    out = copy_of(client, librarian, cp["id"])
    assert (out["status"], out["reserve_item_id"], out["reserve_course_id"]) == ("on_reserve", i1["id"], k1["id"])
    assert item_of(client, librarian, k2["id"], i2["id"])["status"] == "requested"


def test_t_crs_23_a(client, librarian, branch_a):
    """T-CRS-23-a (LIB-CRS-23): After adding: C1 on reserve, 1 of 2. Reservation 201 waiting. After the return: C2 on_reserve, item 2 copies, reservation still waiting"""
    b, (c1, c2) = book(client, librarian, branch_a, 2)
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], c2["id"])
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    it = item(client, librarian, c["id"], b["id"], copies_wanted=2)
    assert (it["status"], it["copies_on_reserve"]) == ("on_reserve", 1)
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    assert res["status"] == "waiting"
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert copy_of(client, librarian, c2["id"])["status"] == "on_reserve"
    assert item_of(client, librarian, c["id"], it["id"])["copies_on_reserve"] == 2
    assert get(client, librarian, f"reservations/{res['id']}")["status"] == "waiting"


def test_t_crs_24_a(client, librarian, branch_a):
    """T-CRS-24-a (LIB-CRS-24): 201 open, due 11:00, renewed false, book_title, course_code, is_overdue false; by barcode 201"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    assert (loan["status"], loan["renewed"], loan["book_title"], loan["course_code"], loan["is_overdue"], loan["item_id"]) == ("open", False, "Reserve Book", s.course["code"], False, s.item["id"])
    assert same(loan["lent_at"], MON, 9) and same(loan["due_at"], MON, 11)
    ok(post(client, librarian, "reserve-loans", {"member_id": s.students[1]["id"], "barcode": s.copies[1]["barcode"]}), 201)


def test_t_crs_24_c(client, clock, librarian, branch_a):
    """T-CRS-24-c (LIB-CRS-24): RESERVE_DESK_CLOSED; 201; 201; RESERVE_DESK_CLOSED; RESERVE_DESK_CLOSED"""
    s = setup(client, librarian, branch_a, copies=3, students=2)
    a, b = s.students
    at(clock, MON, 7, 59)
    err(rlend(client, librarian, a["id"], s.copies[0]["id"]), 409, "RESERVE_DESK_CLOSED")
    at(clock, MON, 8, 0)
    rloan(client, librarian, a, s.copies[0])
    at(clock, MON, 19, 59)
    rloan(client, librarian, b, s.copies[1])
    at(clock, MON, 20, 0)
    err(rlend(client, librarian, a["id"], s.copies[2]["id"]), 409, "RESERVE_DESK_CLOSED")
    at(clock, SAT, 10)
    err(rlend(client, librarian, a["id"], s.copies[2]["id"]), 409, "RESERVE_DESK_CLOSED")


def test_t_crs_24_e(client, clock, librarian, branch_a):
    """T-CRS-24-e (LIB-CRS-24): 201; 409 MEMBER_HAS_OVERDUE"""
    s = setup(client, librarian, branch_a)
    it2, cps2 = more_item(client, librarian, branch_a, s.course["id"], copies=2)
    rloan(client, librarian, s.students[0], s.copies[0])
    at(clock, MON, 11, 0)
    rloan(client, librarian, s.students[0], cps2[0])
    at(clock, MON, 11, 1, 1)
    it3, cps3 = more_item(client, librarian, branch_a, s.course["id"])
    err(rlend(client, librarian, s.students[0]["id"], cps3[0]["id"]), 409, "MEMBER_HAS_OVERDUE")


def test_t_crs_24_g(client, librarian, branch_a):
    """T-CRS-24-g (LIB-CRS-24): ALREADY_BORROWED; J 201, K RESERVE_LOAN_LIMIT_REACHED with details.limit 2; COPY_ON_RESERVE_LOAN with details.due_at"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    a, b = s.students
    _, cj = more_item(client, librarian, branch_a, s.course["id"])
    _, ck = more_item(client, librarian, branch_a, s.course["id"])
    l1 = rloan(client, librarian, a, s.copies[0])
    err(rlend(client, librarian, a["id"], s.copies[1]["id"]), 409, "ALREADY_BORROWED")
    rloan(client, librarian, a, cj[0])
    assert err(rlend(client, librarian, a["id"], ck[0]["id"]), 409, "RESERVE_LOAN_LIMIT_REACHED")["details"]["limit"] == 2
    d = err(rlend(client, librarian, b["id"], s.copies[0]["id"]), 409, "COPY_ON_RESERVE_LOAN")["details"]["due_at"]
    assert datetime.fromisoformat(d) == datetime.fromisoformat(l1["due_at"])


def test_t_crs_24_i(client, clock, librarian, branch_a):
    """T-CRS-24-i (LIB-CRS-24): 201; 409 MEMBERSHIP_EXPIRED"""
    st = member(client, librarian, branch_a)
    at(clock, "2027-10-04")
    s = setup(client, librarian, branch_a, students=0, term="2027-fall", starts_on="2027-10-01", ends_on="2028-01-15")
    enroll(client, librarian, s.course["id"], st)
    at(clock, "2027-11-01")
    loan = rloan(client, librarian, st, s.copies[0])
    ok(rreturn(client, librarian, loan["id"], branch_a))
    at(clock, "2027-11-02")
    err(rlend(client, librarian, st["id"], s.copies[0]["id"]), 409, "MEMBERSHIP_EXPIRED")


def test_t_crs_25_a(client, clock, admin, librarian, branch_a):
    """T-CRS-25-a (LIB-CRS-25): Due 18:00; the 1d loan stays due Tue 18:00"""
    ok(client.put(f"/api/v1/branches/{branch_a['id']}/hours", headers=admin, json={"opens_at": "08:00", "closes_at": "18:00", "min_staff": 1}))
    s = setup(client, librarian, branch_a)
    d = setup(client, librarian, branch_a, period="1d")
    day = rloan(client, librarian, d.students[0], d.copies[0])
    assert same(day["due_at"], TUE, 18)
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": TUE, "reason": "Sayım"}), 201)
    assert same(items(get(client, librarian, "reserve-loans", member_id=d.students[0]["id"]))[0]["due_at"], TUE, 18)
    at(clock, MON, 17)
    assert same(rloan(client, librarian, s.students[0], s.copies[0])["due_at"], MON, 18)


def test_t_crs_26_a(client, clock, librarian, branch_a):
    """T-CRS-26-a (LIB-CRS-26): Due 12:15; 20:00; Mon 2026-11-09 20:00"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    d = setup(client, librarian, branch_a, period="1d")
    at(clock, MON, 10, 15)
    assert same(rloan(client, librarian, s.students[0], s.copies[0])["due_at"], MON, 12, 15)
    at(clock, MON, 19)
    assert same(rloan(client, librarian, s.students[1], s.copies[1])["due_at"], MON, 20)
    at(clock, FRI, 15)
    assert same(rloan(client, librarian, d.students[0], d.copies[0])["due_at"], "2026-11-09", 20)


def test_t_crs_27_a(client, clock, librarian, branch_a):
    """T-CRS-27-a (LIB-CRS-27): 200 due 12:00, renewed true; 409 RENEWAL_LIMIT_REACHED"""
    s = setup(client, librarian, branch_a, copies=2)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    at(clock, MON, 10)
    mh = member_headers(client, s.students[0])
    out = ok(post(client, mh, f"reserve-loans/{loan['id']}/renew"))
    assert out["renewed"] is True and same(out["due_at"], MON, 12)
    err(post(client, mh, f"reserve-loans/{loan['id']}/renew"), 409, "RENEWAL_LIMIT_REACHED")


def test_t_crs_29_a(client, clock, librarian, branch_a):
    """T-CRS-29-a (LIB-CRS-29): late_minutes 5, 6, 120, 121; fees none, 1.00, 2.00, 3.00 (reserve_late_fee with reserve_loan_id)"""
    s = setup(client, librarian, branch_a, copies=4, students=4)
    loans = [rloan(client, librarian, st, cp) for st, cp in zip(s.students, s.copies)]
    result = []
    for loan, (hh, mm) in zip(loans, ((11, 5), (11, 6), (13, 0), (13, 1))):
        at(clock, MON, hh, mm)
        out = ok(rreturn(client, librarian, loan["id"], branch_a))
        result.append(out["late_minutes"])
    assert result == [5, 6, 120, 121]
    got = []
    for st, loan in zip(s.students, loans):
        fs = items(member_fees(client, librarian, st["id"]))
        assert all(f["reserve_loan_id"] == loan["id"] and f["kind"] == "reserve_late_fee" for f in fs)
        got.append([f["amount"] for f in fs])
    assert got == [[], ["1.00"], ["2.00"], ["3.00"]]


def test_t_crs_31_a(client, clock, librarian, branch_a):
    """T-CRS-31-a (LIB-CRS-31): Loan lost with late_minutes 60; fees reserve_late_fee 1.00 and reserve_lost 80.00; copy lost with branch and item null; item requested; 409 RESERVE_LOAN_NOT_OPEN"""
    s = setup(client, librarian, branch_a, price="80.00")
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    at(clock, MON, 12)
    out = ok(post(client, librarian, f"reserve-loans/{loan['id']}/report-lost"))
    assert (out["status"], out["late_minutes"]) == ("lost", 60)
    assert sorted(fees_of(client, librarian, s.students[0]["id"])) == [("reserve_late_fee", "1.00"), ("reserve_lost", "80.00")]
    cp = copy_of(client, librarian, s.copies[0]["id"])
    assert (cp["status"], cp["current_branch_id"], cp["reserve_item_id"]) == ("lost", None, None)
    assert item_of(client, librarian, s.course["id"], s.item["id"])["status"] == "requested"
    err(post(client, librarian, f"reserve-loans/{loan['id']}/report-lost"), 409, "RESERVE_LOAN_NOT_OPEN")


def test_t_crs_33_a(client, clock, librarian, branch_a):
    """T-CRS-33-a (LIB-CRS-33): overdue_notices 0, 1, 0; one reserve_overdue notification"""
    s = setup(client, librarian, branch_a)
    rloan(client, librarian, s.students[0], s.copies[0])
    counts = []
    for t in ((11, 0, 0), (11, 0, 1), (11, 0, 2)):
        at(clock, MON, *t)
        counts.append(ok(post(client, librarian, "course-reserves/process"))["overdue_notices"])
    assert counts == [0, 1, 0]
    assert len(notes(client, librarian, s.students[0]["id"], "reserve_overdue")) == 1


def test_t_crs_35_a(client, clock, librarian, branch_a):
    """T-CRS-35-a (LIB-CRS-35): Listed; payment allocated, fee paid"""
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    loan = rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 12, 30)
    ok(rreturn(client, librarian, loan["id"], branch_a))
    fee = items(get(client, librarian, "fees", kind="reserve_late_fee"))
    assert [(f["member_id"], f["amount"]) for f in fee] == [(st["id"], "2.00")]
    ok(post(client, librarian, f"members/{st['id']}/payments", {"amount": "2.00", "method": "cash"}), 201)
    assert items(member_fees(client, librarian, st["id"]))[0]["status"] == "paid"


def test_t_crs_37_a(client, clock, librarian, branch_a):
    """T-CRS-37-a (LIB-CRS-37): 409 MEMBER_HAS_OVERDUE; borrowing.reasons contains MEMBER_HAS_OVERDUE"""
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 11, 30)
    _, (cp,) = book(client, librarian, branch_a, 1)
    err(post(client, librarian, "loans", {"member_id": st["id"], "copy_id": cp["id"]}), 409, "MEMBER_HAS_OVERDUE")
    assert "MEMBER_HAS_OVERDUE" in get(client, librarian, f"members/{st['id']}/summary")["borrowing"]["reasons"]


def test_t_crs_39_a(client, librarian, branch_a):
    """T-CRS-39-a (LIB-CRS-39): 409 MEMBER_HAS_OPEN_LOANS; 409 INSTRUCTOR_HAS_COURSES with details.course_ids; 200 and the enrollment dropped with member_deactivated"""
    s = setup(client, librarian, branch_a, students=2)
    a, b = s.students
    rloan(client, librarian, a, s.copies[0])
    err(post(client, librarian, f"members/{a['id']}/deactivate"), 409, "MEMBER_HAS_OPEN_LOANS")
    assert err(post(client, librarian, f"members/{s.ins['id']}/deactivate"), 409, "INSTRUCTOR_HAS_COURSES")["details"]["course_ids"] == [s.course["id"]]
    deactivate_member(client, librarian, b["id"])
    e = [x for x in items(get(client, librarian, f"courses/{s.course['id']}/enrollments")) if x["member_id"] == b["id"]][0]
    assert (e["status"], e["drop_reason"]) == ("dropped", "member_deactivated")


def test_t_crs_41_a(client, admin, librarian, branch_a):
    """T-CRS-41-a (LIB-CRS-41): 409 BRANCH_IN_USE; 200"""
    qq = create_branch(client, admin, "QQ")
    c = course(client, librarian, qq, academic(client, librarian, branch_a))
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"courses/{c['id']}/close"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))


def test_t_crs_43_a(client, librarian, branch_a):
    """T-CRS-43-a (LIB-CRS-43): Only the reserved copy, with reserve_item_id and reserve_course_id; the other has both null"""
    s = setup(client, librarian, branch_a)
    free = add_copy(client, librarian, s.book["id"], home_branch_id=branch_a["id"])
    rows = items(get(client, librarian, f"books/{s.book['id']}/copies", status="on_reserve"))
    assert [(r["id"], r["reserve_item_id"], r["reserve_course_id"]) for r in rows] == [(s.copies[0]["id"], s.item["id"], s.course["id"])]
    other = copy_of(client, librarian, free["id"])
    assert (other["reserve_item_id"], other["reserve_course_id"]) == (None, None)


def test_t_crs_45_a(client, clock, librarian, admin, branch_a):
    """T-CRS-45-a (LIB-CRS-45): One entry of each event"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    ok(client.patch(f"/api/v1/courses/{c['id']}", headers=librarian, json={"title": "Yeni"}))
    b, (c1, c2) = book(client, librarian, branch_a, 2)
    it = item(client, librarian, c["id"], b["id"], kind="recommended", copies_wanted=2)
    ok(client.patch(f"/api/v1/reading-list-items/{it['id']}", headers=librarian, json={"note": "Not"}))
    ok(place(client, librarian, it["id"], c1["id"]), 201)
    ok(place(client, librarian, it["id"], c2["id"]), 201)
    st = member(client, librarian, branch_a)
    enroll(client, librarian, c["id"], st)
    ok(activate(client, librarian, c["id"]))
    loan = rloan(client, librarian, st, c1)
    ok(post(client, librarian, f"reserve-loans/{loan['id']}/renew"))
    ok(rreturn(client, librarian, loan["id"], branch_a))
    ok(post(client, librarian, f"copies/{c1['id']}/unreserve"))
    ok(post(client, librarian, f"reading-list-items/{it['id']}/remove"))
    e = items(get(client, librarian, f"courses/{c['id']}/enrollments"))[0]
    ok(post(client, librarian, f"enrollments/{e['id']}/drop"))
    ok(post(client, librarian, f"courses/{c['id']}/close"))
    ok(post(client, librarian, "course-reserves/process"))
    names = ("course_created", "course_updated", "course_activated", "course_enrollment_created", "course_enrollment_dropped", "reading_list_item_added",
             "reading_list_item_updated", "reading_list_item_removed", "reserve_loan_created", "reserve_loan_renewed", "reserve_loan_returned", "course_closed",
             "course_reserves_processed")
    for name in names:
        assert len(items(get(client, admin, "audit-log", event=name))) == 1, name
    assert len(items(get(client, admin, "audit-log", event="reserve_copy_placed"))) == 2
    assert len(items(get(client, admin, "audit-log", event="reserve_copy_removed"))) >= 1


def test_t_crs_46_a(client, clock, librarian, branch_a, branch_b):
    """T-CRS-46-a (LIB-CRS-46): Only K: {status active, enrolled 2, items 2, items_unfilled 1, loans 2, borrowers 2, late_returns 1, fees_charged 1.00}"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    item(client, librarian, s.course["id"], book(client, librarian, branch_b, 1)[0]["id"], kind="recommended")
    setup(client, librarian, branch_a, students=0, active=False)
    a, b = s.students
    la, lb = rloan(client, librarian, a, s.copies[0]), rloan(client, librarian, b, s.copies[1])
    at(clock, MON, 10)
    ok(rreturn(client, librarian, lb["id"], branch_a))
    at(clock, MON, 11, 10)
    ok(rreturn(client, librarian, la["id"], branch_a))
    rows = items(get(client, librarian, "reports/course-reserves", **{"from": MON, "to": "2026-11-08"}))
    keys = ("course_id", "status", "enrolled", "items", "items_unfilled", "loans", "borrowers", "late_returns", "fees_charged")
    assert [tuple(r[k] for k in keys) for r in rows] == [(s.course["id"], "active", 2, 2, 1, 2, 2, 1, "1.00")]


def test_t_crs_47_a(client, admin, librarian, branch_a):
    """T-CRS-47-a (LIB-CRS-47): The export has exactly the keys of 22.1"""
    s = setup(client, librarian, branch_a)
    rloan(client, librarian, s.students[0], s.copies[0])
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
