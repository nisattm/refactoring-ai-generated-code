"""Heldout tests: module 21 (Course reserves). Generated from cases/courses.md."""
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


def test_t_crs_01_b(client, librarian, branch_a):
    """T-CRS-01-b (LIB-CRS-01): 422 eight times; 403"""
    ins = academic(client, librarian, branch_a)
    bad = [dict(code="C301"), dict(term="2026-winter"), dict(starts_on="2026-11-02", ends_on="2026-11-07"),
           dict(starts_on="2026-11-02", ends_on="2027-05-01"), dict(starts_on="2026-09-01", ends_on="2026-11-01"),
           dict(enrollment_limit=0), dict(enrollment_limit=301), dict(instructor_id=999999)]
    for fields in bad:
        assert try_course(client, librarian, branch_a, ins, **fields).status_code == 422, fields
    assert try_course(client, member_headers(client, ins), branch_a, ins).status_code == 403


def test_t_crs_02_b(client, librarian, branch_a):
    """T-CRS-02-b (LIB-CRS-02): 409 CONFLICT with details.field code; 201"""
    ins = academic(client, librarian, branch_a)
    course(client, librarian, branch_a, ins, code="CENG301")
    assert err(try_course(client, librarian, branch_a, ins, code="ceng301"), 409, "CONFLICT")["details"]["field"] == "code"
    course(client, librarian, branch_a, ins, code="CENG301", term="2027-spring", starts_on="2027-02-15", ends_on="2027-06-10")


def test_t_crs_03_b(client, librarian, branch_a):
    """T-CRS-03-b (LIB-CRS-03): 409 INSTRUCTOR_NOT_ACADEMIC; 200"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    url = f"/api/v1/courses/{c['id']}"
    err(client.patch(url, headers=librarian, json={"instructor_id": member(client, librarian, branch_a)["id"]}), 409, "INSTRUCTOR_NOT_ACADEMIC")
    other = academic(client, librarian, branch_a)
    assert ok(client.patch(url, headers=librarian, json={"instructor_id": other["id"]}))["instructor_id"] == other["id"]


def test_t_crs_04_b(client, clock, librarian, branch_a):
    """T-CRS-04-b (LIB-CRS-04): 200; 409 COURSE_ENDED"""
    s1 = setup(client, librarian, branch_a, students=0, active=False, starts_on="2026-11-02", ends_on="2026-11-10")
    s2 = setup(client, librarian, branch_a, students=0, active=False, starts_on="2026-11-02", ends_on="2026-11-10")
    at(clock, "2026-11-10")
    ok(activate(client, librarian, s1.course["id"]))
    at(clock, "2026-11-11")
    err(activate(client, librarian, s2.course["id"]), 409, "COURSE_ENDED")


def test_t_crs_05_b(client, librarian, branch_a):
    """T-CRS-05-b (LIB-CRS-05): Student and instructor: 200 and the course listed; other student: 404 and an empty list"""
    s = setup(client, librarian, branch_a, active=False)
    other = member(client, librarian, branch_a)
    for m in (s.students[0], s.ins):
        mh = member_headers(client, m)
        assert get(client, mh, f"courses/{s.course['id']}")["id"] == s.course["id"]
        assert [r["id"] for r in items(get(client, mh, "courses"))] == [s.course["id"]]
    oh = member_headers(client, other)
    assert client.get(f"/api/v1/courses/{s.course['id']}", headers=oh).status_code == 404
    assert get(client, oh, "courses")["total"] == 0


def test_t_crs_06_a(client, librarian, branch_a):
    """T-CRS-06-a (LIB-CRS-06): 409 COURSE_HAS_OPEN_LOANS with details.loan_ids; 200 closed with released_copies 1 and the copy available; 409 INVALID_COURSE_STATUS"""
    s = setup(client, librarian, branch_a)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    url = f"courses/{s.course['id']}/close"
    assert err(post(client, librarian, url), 409, "COURSE_HAS_OPEN_LOANS")["details"]["loan_ids"] == [loan["id"]]
    ok(rreturn(client, librarian, loan["id"], branch_a))
    out = ok(post(client, librarian, url))
    assert (out["status"], out["released_copies"]) == ("closed", 1) and same(out["closed_at"], MON, 9)
    cp = copy_of(client, librarian, s.copies[0]["id"])
    assert (cp["status"], cp["reserve_item_id"]) == ("available", None)
    err(post(client, librarian, url), 409, "INVALID_COURSE_STATUS")


def test_t_crs_08_b(client, librarian, branch_a):
    """T-CRS-08-b (LIB-CRS-08): All skipped: NOT_FOUND, MEMBER_PASSIVE, ALREADY_ENROLLED"""
    s = setup(client, librarian, branch_a, active=False)
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    out = ok(post(client, librarian, f"courses/{s.course['id']}/enrollments", {"member_ids": [999999, p["id"], s.students[0]["id"]]}))
    assert out["enrolled"] == []
    assert [x["error_code"] for x in out["skipped"]] == ["NOT_FOUND", "MEMBER_PASSIVE", "ALREADY_ENROLLED"]


def test_t_crs_10_b(client, librarian, branch_a):
    """T-CRS-10-b (LIB-CRS-10): 409 MEMBER_HAS_RESERVE_LOANS"""
    s = setup(client, librarian, branch_a)
    rloan(client, librarian, s.students[0], s.copies[0])
    e = items(get(client, librarian, f"courses/{s.course['id']}/enrollments"))[0]
    err(post(client, librarian, f"enrollments/{e['id']}/drop"), 409, "MEMBER_HAS_RESERVE_LOANS")


def test_t_crs_12_b(client, librarian, branch_a):
    """T-CRS-12-b (LIB-CRS-12): 422; 409 BOOK_NOT_LENDABLE; 409 DUPLICATE_ITEM; 422; 409 INVALID_COURSE_STATUS"""
    s = setup(client, librarian, branch_a, students=0, active=False)
    cid = s.course["id"]
    assert try_item(client, librarian, cid, 999999).status_code == 422
    err(try_item(client, librarian, cid, book(client, librarian)[0]["id"]), 409, "BOOK_NOT_LENDABLE")
    err(try_item(client, librarian, cid, s.book["id"]), 409, "DUPLICATE_ITEM")
    b, _ = book(client, librarian, branch_a, 1)
    assert try_item(client, librarian, cid, b["id"], copies_wanted=6).status_code == 422
    ok(post(client, librarian, f"courses/{cid}/close"))
    err(try_item(client, librarian, cid, b["id"]), 409, "INVALID_COURSE_STATUS")


def test_t_crs_14_b(client, clock, librarian, branch_a):
    """T-CRS-14-b (LIB-CRS-14): Loan 1 due Mon 11:00 (unchanged); loan 2 due Tue 20:00"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    l1 = rloan(client, librarian, s.students[0], s.copies[0])
    ok(client.patch(f"/api/v1/reading-list-items/{s.item['id']}", headers=librarian, json={"loan_period": "1d"}))
    at(clock, MON, 9, 30)
    l2 = rloan(client, librarian, s.students[1], s.copies[1])
    assert same([x for x in items(get(client, librarian, "reserve-loans")) if x["id"] == l1["id"]][0]["due_at"], MON, 11)
    assert same(l2["due_at"], TUE, 20)


def test_t_crs_16_a(client, librarian, branch_a, branch_b):
    """T-CRS-16-a (LIB-CRS-16): 409 RESERVE_COPY_ON_LOAN with details.loan_ids; 200 removed with position null, I2 → 1, I3 → 2, the copy available; 409 ITEM_REMOVED"""
    s = setup(client, librarian, branch_a)
    i2 = item(client, librarian, s.course["id"], book(client, librarian, branch_b, 1)[0]["id"])
    i3 = item(client, librarian, s.course["id"], book(client, librarian, branch_b, 1)[0]["id"])
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    url = f"reading-list-items/{s.item['id']}/remove"
    assert err(post(client, librarian, url), 409, "RESERVE_COPY_ON_LOAN")["details"]["loan_ids"] == [loan["id"]]
    ok(rreturn(client, librarian, loan["id"], branch_a))
    out = ok(post(client, librarian, url))
    assert (out["status"], out["position"]) == ("removed", None)
    rows = items(get(client, librarian, f"courses/{s.course['id']}/reading-list"))
    assert [(x["id"], x["position"]) for x in rows] == [(i2["id"], 1), (i3["id"], 2)]
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "available"
    err(post(client, librarian, url), 409, "ITEM_REMOVED")


def test_t_crs_18_a(client, librarian, branch_a, branch_b):
    """T-CRS-18-a (LIB-CRS-18): 201, 200, 200; 403; 403, 403"""
    s = setup(client, librarian, branch_a, students=0, active=False)
    ih = member_headers(client, s.ins)
    b, _ = book(client, librarian, branch_b, 1)
    it = item(client, ih, s.course["id"], b["id"], kind="recommended")
    ok(client.patch(f"/api/v1/reading-list-items/{it['id']}", headers=ih, json={"note": "Ek okuma"}))
    ok(post(client, ih, f"reading-list-items/{it['id']}/remove"))
    b2, (c2,) = book(client, librarian, branch_a, 1)
    assert try_item(client, member_headers(client, academic(client, librarian, branch_a)), s.course["id"], b2["id"]).status_code == 403
    it2 = item(client, librarian, s.course["id"], b2["id"], kind="recommended")
    assert place(client, ih, it2["id"], c2["id"]).status_code == 403
    assert post(client, ih, f"courses/{s.course['id']}/enrollments", {"member_ids": [member(client, librarian, branch_a)["id"]]}).status_code == 403


def test_t_crs_19_b(client, librarian, branch_a, branch_b):
    """T-CRS-19-b (LIB-CRS-19): WRONG_BOOK; INVALID_COPY_STATUS with details.status on_loan; COPY_AT_OTHER_BRANCH; RESERVE_COPIES_COMPLETE; ITEM_REMOVED"""
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    b, (c1, c2) = book(client, librarian, branch_a, 2)
    far = add_copy(client, librarian, b["id"], home_branch_id=branch_b["id"])
    it = item(client, librarian, c["id"], b["id"], kind="recommended")
    _, (alien,) = book(client, librarian, branch_a, 1)
    err(place(client, librarian, it["id"], alien["id"]), 409, "WRONG_BOOK")
    lend(client, librarian, member(client, librarian, branch_a)["id"], c2["id"])
    assert err(place(client, librarian, it["id"], c2["id"]), 409, "INVALID_COPY_STATUS")["details"]["status"] == "on_loan"
    err(place(client, librarian, it["id"], far["id"]), 409, "COPY_AT_OTHER_BRANCH")
    ok(place(client, librarian, it["id"], c1["id"]), 201)
    other = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    err(place(client, librarian, it["id"], other["id"]), 409, "RESERVE_COPIES_COMPLETE")
    rm = item(client, librarian, c["id"], book(client, librarian, branch_b, 1)[0]["id"], kind="recommended")
    ok(post(client, librarian, f"reading-list-items/{rm['id']}/remove"))
    err(place(client, librarian, rm["id"], other["id"]), 409, "ITEM_REMOVED")


def test_t_crs_20_a(client, librarian, branch_a, branch_b):
    """T-CRS-20-a (LIB-CRS-20): 409 COPY_NOT_AVAILABLE with details.status on_reserve; 409 INVALID_COPY_STATUS twice; availability available 0, total 1"""
    s = setup(client, librarian, branch_a)
    cp = s.copies[0]
    r = post(client, librarian, "loans", {"member_id": member(client, librarian, branch_a)["id"], "copy_id": cp["id"]})
    assert err(r, 409, "COPY_NOT_AVAILABLE")["details"]["status"] == "on_reserve"
    err(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Eskidi artık"}), 409, "INVALID_COPY_STATUS")
    err(post(client, librarian, "transfers", {"copy_id": cp["id"], "to_branch_id": branch_b["id"]}), 409, "INVALID_COPY_STATUS")
    av = get(client, librarian, f"books/{s.book['id']}")["availability"]
    assert av == [{"branch_id": branch_a["id"], "available": 0, "total": 1}]


def test_t_crs_22_b(client, librarian, branch_a):
    """T-CRS-22-b (LIB-CRS-22): The copy stays available (not placed back); the item requested"""
    s = setup(client, librarian, branch_a, active=False)
    ok(post(client, librarian, f"copies/{s.copies[0]['id']}/unreserve"))
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "available"
    assert item_of(client, librarian, s.course["id"], s.item["id"])["status"] == "requested"


def test_t_crs_24_b(client, librarian, branch_a):
    """T-CRS-24-b (LIB-CRS-24): 422; 422; 404; 409 COPY_NOT_ON_RESERVE with details.status available; 403"""
    s = setup(client, librarian, branch_a)
    st, cp = s.students[0], s.copies[0]
    assert post(client, librarian, "reserve-loans", {"member_id": st["id"], "copy_id": cp["id"], "barcode": cp["barcode"]}).status_code == 422
    assert post(client, librarian, "reserve-loans", {"member_id": st["id"]}).status_code == 422
    assert post(client, librarian, "reserve-loans", {"member_id": st["id"], "barcode": "NOPE-0001"}).status_code == 404
    _, (free,) = book(client, librarian, branch_a, 1)
    assert err(rlend(client, librarian, st["id"], free["id"]), 409, "COPY_NOT_ON_RESERVE")["details"]["status"] == "available"
    assert rlend(client, member_headers(client, st), st["id"], cp["id"]).status_code == 403


def test_t_crs_24_d(client, librarian, branch_a):
    """T-CRS-24-d (LIB-CRS-24): MEMBER_PASSIVE; NOT_ENROLLED; NOT_ENROLLED; 201"""
    s = setup(client, librarian, branch_a, students=2)
    cp = s.copies[0]
    deactivate_member(client, librarian, s.students[0]["id"])
    err(rlend(client, librarian, s.students[0]["id"], cp["id"]), 409, "MEMBER_PASSIVE")
    err(rlend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"]), 409, "NOT_ENROLLED")
    e = [x for x in items(get(client, librarian, f"courses/{s.course['id']}/enrollments")) if x["member_id"] == s.students[1]["id"]][0]
    ok(post(client, librarian, f"enrollments/{e['id']}/drop"))
    err(rlend(client, librarian, s.students[1]["id"], cp["id"]), 409, "NOT_ENROLLED")
    rloan(client, librarian, s.ins, cp)


def test_t_crs_24_f(client, librarian, branch_a):
    """T-CRS-24-f (LIB-CRS-24): 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt '50.00'; 201"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    a, b = s.students
    debt(client, librarian, branch_a, a, "50.00")
    debt(client, librarian, branch_a, b, "49.99")
    assert err(rlend(client, librarian, a["id"], s.copies[0]["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    rloan(client, librarian, b, s.copies[0])


def test_t_crs_24_h(client, librarian, branch_a):
    """T-CRS-24-h (LIB-CRS-24): Three 201; RESERVE_LOAN_LIMIT_REACHED with details.limit 3"""
    s = setup(client, librarian, branch_a, students=0)
    copies = [s.copies[0]] + [more_item(client, librarian, branch_a, s.course["id"])[1][0] for _ in range(3)]
    for cp in copies[:3]:
        rloan(client, librarian, s.ins, cp)
    assert err(rlend(client, librarian, s.ins["id"], copies[3]["id"]), 409, "RESERVE_LOAN_LIMIT_REACHED")["details"]["limit"] == 3


def test_t_crs_26_b(client, clock, admin, librarian, branch_a, branch_b):
    """T-CRS-26-b (LIB-CRS-26): A: due Fri 2026-11-06 20:00; B: Mon 2026-11-09 20:00"""
    a = setup(client, librarian, branch_a, period="3d")
    b = setup(client, librarian, branch_b, period="3d")
    ok(post(client, admin, f"branches/{branch_b['id']}/closures", {"date": THU, "reason": "Sayım"}), 201)
    at(clock, TUE)
    assert same(rloan(client, librarian, a.students[0], a.copies[0])["due_at"], FRI, 20)
    assert same(rloan(client, librarian, b.students[0], b.copies[0])["due_at"], "2026-11-09", 20)


def test_t_crs_27_b(client, clock, librarian, branch_a):
    """T-CRS-27-b (LIB-CRS-27): RESERVE_IN_DEMAND; LOAN_OVERDUE; RESERVE_LOAN_NOT_OPEN"""
    one = setup(client, librarian, branch_a)
    two = setup(client, librarian, branch_a, copies=2)
    l1 = rloan(client, librarian, one.students[0], one.copies[0])
    l2 = rloan(client, librarian, two.students[0], two.copies[0])
    at(clock, MON, 10)
    err(post(client, librarian, f"reserve-loans/{l1['id']}/renew"), 409, "RESERVE_IN_DEMAND")
    at(clock, MON, 11, 1)
    err(post(client, librarian, f"reserve-loans/{l2['id']}/renew"), 409, "LOAN_OVERDUE")
    ok(rreturn(client, librarian, l1["id"], branch_a))
    err(post(client, librarian, f"reserve-loans/{l1['id']}/renew"), 409, "RESERVE_LOAN_NOT_OPEN")


def test_t_crs_28_a(client, clock, librarian, branch_a, branch_b):
    """T-CRS-28-a (LIB-CRS-28): 409 RESERVE_RETURN_WRONG_BRANCH with details.branch_id; 200 returned, late_minutes 0, no fee, copy still on_reserve; 409 RESERVE_LOAN_NOT_OPEN"""
    s = setup(client, librarian, branch_a)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    assert err(rreturn(client, librarian, loan["id"], branch_b), 409, "RESERVE_RETURN_WRONG_BRANCH")["details"]["branch_id"] == branch_a["id"]
    at(clock, MON, 10)
    out = ok(rreturn(client, librarian, loan["id"], branch_a))
    assert (out["status"], out["late_minutes"], out["fee_id"]) == ("returned", 0, None) and same(out["returned_at"], MON, 10)
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "on_reserve"
    err(rreturn(client, librarian, loan["id"], branch_a), 409, "RESERVE_LOAN_NOT_OPEN")


def test_t_crs_30_a(client, clock, librarian, branch_a):
    """T-CRS-30-a (LIB-CRS-30): 30.00 (cap); 5.00; accrued_late_fee 1.00 and is_overdue true"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    d = setup(client, librarian, branch_a, period="1d")
    l1 = rloan(client, librarian, s.students[0], s.copies[0])
    l2 = rloan(client, librarian, d.students[0], d.copies[0])
    l3 = rloan(client, librarian, s.students[1], s.copies[1])
    at(clock, MON, 12)
    open3 = [x for x in items(get(client, librarian, "reserve-loans")) if x["id"] == l3["id"]][0]
    assert (open3["accrued_late_fee"], open3["is_overdue"]) == ("1.00", True)
    at(clock, WED, 9)
    ok(rreturn(client, librarian, l2["id"], branch_a))
    at(clock, THU, 11)
    ok(rreturn(client, librarian, l1["id"], branch_a))
    assert fees_of(client, librarian, s.students[0]["id"]) == [("reserve_late_fee", "30.00")]
    assert fees_of(client, librarian, d.students[0]["id"]) == [("reserve_late_fee", "5.00")]


def test_t_crs_32_a(client, clock, librarian, branch_a):
    """T-CRS-32-a (LIB-CRS-32): [L2, L1]; [L1]; empty; own list [L1]; 403"""
    s = setup(client, librarian, branch_a, copies=2, students=2)
    other = setup(client, librarian, branch_a, students=0)
    a, b = s.students
    l1 = rloan(client, librarian, a, s.copies[0])
    at(clock, MON, 10)
    l2 = rloan(client, librarian, b, s.copies[1])
    at(clock, MON, 11, 30)
    assert [x["id"] for x in items(get(client, librarian, "reserve-loans"))] == [l2["id"], l1["id"]]
    assert [x["id"] for x in items(get(client, librarian, "reserve-loans", overdue="true"))] == [l1["id"]]
    assert get(client, librarian, "reserve-loans", course_id=other.course["id"])["total"] == 0
    ah = member_headers(client, a)
    assert [x["id"] for x in items(get(client, ah, f"members/{a['id']}/reserve-loans"))] == [l1["id"]]
    assert client.get(f"/api/v1/members/{b['id']}/reserve-loans", headers=ah).status_code == 403


def test_t_crs_34_a(client, clock, librarian, branch_a):
    """T-CRS-34-a (LIB-CRS-34): First {closed_courses 0, pending_courses 1}; then {closed_courses 1, released_copies 1, pending_courses 0} and the course closed"""
    s = setup(client, librarian, branch_a, starts_on="2026-11-02", ends_on="2026-11-20")
    at(clock, "2026-11-20", 10)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    at(clock, "2026-11-23", 10)
    first = ok(post(client, librarian, "course-reserves/process"))
    assert (first["closed_courses"], first["pending_courses"], first["overdue_notices"]) == (0, 1, 1)
    ok(rreturn(client, librarian, loan["id"], branch_a))
    second = ok(post(client, librarian, "course-reserves/process"))
    assert (second["closed_courses"], second["released_copies"], second["pending_courses"]) == (1, 1, 0)
    assert get(client, librarian, f"courses/{s.course['id']}")["status"] == "closed"
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "available"


def test_t_crs_36_a(client, clock, librarian, branch_a):
    """T-CRS-36-a (LIB-CRS-36): accrued_late_fees 3.00, total_debt 3.00"""
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 13, 30)
    b = balance(client, librarian, st["id"])
    assert (b["accrued_late_fees"], b["total_debt"], b["outstanding_fees"]) == ("3.00", "3.00", "0.00")


def test_t_crs_38_a(client, clock, librarian, branch_a):
    """T-CRS-38-a (LIB-CRS-38): Student {courses_enrolled 2, courses_teaching 0, open_reserve_loans 1, overdue_reserve_loans 1}; instructor courses_teaching 1"""
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    d = setup(client, librarian, branch_a, students=0, active=False)
    enroll(client, librarian, d.course["id"], st)
    rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 12)
    out = get(client, librarian, f"members/{st['id']}/summary")["course_reserves"]
    assert out == {"courses_enrolled": 2, "courses_teaching": 0, "open_reserve_loans": 1, "overdue_reserve_loans": 1}
    assert get(client, librarian, f"members/{s.ins['id']}/summary")["course_reserves"]["courses_teaching"] == 1


def test_t_crs_40_a(client, librarian, branch_a):
    """T-CRS-40-a (LIB-CRS-40): 409 MEMBER_HAS_ENROLLMENTS; 409 INSTRUCTOR_HAS_COURSES; 200"""
    s = setup(client, librarian, branch_a, active=False)
    url = "/api/v1/members/{}"
    err(client.patch(url.format(s.students[0]["id"]), headers=librarian, json={"membership_type": "academic"}), 409, "MEMBER_HAS_ENROLLMENTS")
    err(client.patch(url.format(s.ins["id"]), headers=librarian, json={"membership_type": "staff"}), 409, "INSTRUCTOR_HAS_COURSES")
    ok(post(client, librarian, f"courses/{s.course['id']}/close"))
    assert ok(client.patch(url.format(s.students[0]["id"]), headers=librarian, json={"membership_type": "academic"}))["membership_type"] == "academic"


def test_t_crs_42_a(client, librarian, branch_a):
    """T-CRS-42-a (LIB-CRS-42): 201 waiting; the copy stays on_reserve"""
    s = setup(client, librarian, branch_a)
    res = reserve(client, librarian, book_id=s.book["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    assert (res["status"], res["copy_id"]) == ("waiting", None)
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "on_reserve"


def test_t_crs_44_a(client, librarian, branch_a):
    """T-CRS-44-a (LIB-CRS-44): course_enrolled has course_id and the code in the message; no other notification"""
    s = setup(client, librarian, branch_a, students=0, code="CENG204")
    st = member(client, librarian, branch_a)
    enroll(client, librarian, s.course["id"], st)
    loan = rloan(client, librarian, st, s.copies[0])
    ok(rreturn(client, librarian, loan["id"], branch_a))
    ns = items(get(client, librarian, f"members/{st['id']}/notifications"))
    assert [n["type"] for n in ns] == ["course_enrolled"]
    assert ns[0]["course_id"] == s.course["id"] and "CENG204" in ns[0]["message"]


def test_t_crs_46_b(client, librarian, branch_a):
    """T-CRS-46-b (LIB-CRS-46): 422; 422; 403"""
    url = "/api/v1/reports/course-reserves"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": WED}).status_code == 403
