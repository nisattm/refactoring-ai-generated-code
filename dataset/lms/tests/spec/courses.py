MODULE = "courses"
TITLE = "module 21 (Course reserves)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- courses
    dict(id="T-CRS-01-a", req="LIB-CRS-01", type="Normal", input="Librarian creates course `ceng301` for term 2026-fall without `enrollment_limit`", expected="201 `draft`; code `CENG301`; limit 100", code='''
def TEST(client, librarian, branch_a):
    ins = academic(client, librarian, branch_a)
    c = course(client, librarian, branch_a, ins, code="ceng301", title="Veri Yapıları")
    assert (c["code"], c["title"], c["term"], c["status"], c["enrollment_limit"], c["instructor_id"]) == ("CENG301", "Veri Yapıları", "2026-fall", "draft", 100, ins["id"])
    assert (c["starts_on"], c["ends_on"], c["activated_at"], c["closed_at"]) == ("2026-10-01", "2027-01-15", None, None)
'''),
    dict(id="T-CRS-01-b", req="LIB-CRS-01", type="Error", input="Code `C301`; term `2026-winter`; 5 and 180 days long; ends yesterday; limit 0 and 301; unknown instructor; member creates", expected="`422` eight times; `403`", code='''
def TEST(client, librarian, branch_a):
    ins = academic(client, librarian, branch_a)
    bad = [dict(code="C301"), dict(term="2026-winter"), dict(starts_on="2026-11-02", ends_on="2026-11-07"),
           dict(starts_on="2026-11-02", ends_on="2027-05-01"), dict(starts_on="2026-09-01", ends_on="2026-11-01"),
           dict(enrollment_limit=0), dict(enrollment_limit=301), dict(instructor_id=999999)]
    for fields in bad:
        assert try_course(client, librarian, branch_a, ins, **fields).status_code == 422, fields
    assert try_course(client, member_headers(client, ins), branch_a, ins).status_code == 403
'''),
    dict(id="T-CRS-01-c", req="LIB-CRS-01", type="Boundary", input="Courses 6 days long (2026-11-02 – 2026-11-08) and 179 days long; ending today", expected="201 each", code='''
def TEST(client, librarian, branch_a):
    ins = academic(client, librarian, branch_a)
    course(client, librarian, branch_a, ins, starts_on=MON, ends_on="2026-11-08")
    course(client, librarian, branch_a, ins, starts_on=MON, ends_on="2027-04-30")
    course(client, librarian, branch_a, ins, starts_on="2026-10-01", ends_on=MON)
'''),
    dict(id="T-CRS-02-a", req="LIB-CRS-02", type="Error", input="Inactive branch; a student as instructor; a passive academic", expected="`BRANCH_INACTIVE`; `INSTRUCTOR_NOT_ACADEMIC` twice", code='''
def TEST(client, admin, librarian, branch_a):
    ins = academic(client, librarian, branch_a)
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_course(client, librarian, qq, ins), 409, "BRANCH_INACTIVE")
    err(try_course(client, librarian, branch_a, member(client, librarian, branch_a)), 409, "INSTRUCTOR_NOT_ACADEMIC")
    p = academic(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(try_course(client, librarian, branch_a, p), 409, "INSTRUCTOR_NOT_ACADEMIC")
'''),
    dict(id="T-CRS-02-b", req="LIB-CRS-02", type="Error", input="Course CENG301 2026-fall exists; another CENG301 2026-fall; CENG301 2027-spring", expected="`409 CONFLICT` with `details.field` `code`; 201", code='''
def TEST(client, librarian, branch_a):
    ins = academic(client, librarian, branch_a)
    course(client, librarian, branch_a, ins, code="CENG301")
    assert err(try_course(client, librarian, branch_a, ins, code="ceng301"), 409, "CONFLICT")["details"]["field"] == "code"
    course(client, librarian, branch_a, ins, code="CENG301", term="2027-spring", starts_on="2027-02-15", ends_on="2027-06-10")
'''),
    dict(id="T-CRS-03-a", req="LIB-CRS-03", type="Error", input="PATCH title and limit; PATCH `code`; limit 1 with 2 enrolled; PATCH a closed course", expected="200; `422`; `409 ENROLLMENT_LIMIT_BELOW_ENROLLED` with `details.enrolled` 2; `409 INVALID_COURSE_STATUS`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=2, active=False)
    url = f"/api/v1/courses/{s.course['id']}"
    out = ok(client.patch(url, headers=librarian, json={"title": "Algoritmalar", "enrollment_limit": 50}))
    assert (out["title"], out["enrollment_limit"]) == ("Algoritmalar", 50)
    assert client.patch(url, headers=librarian, json={"code": "ABC123"}).status_code == 422
    assert err(client.patch(url, headers=librarian, json={"enrollment_limit": 1}), 409, "ENROLLMENT_LIMIT_BELOW_ENROLLED")["details"]["enrolled"] == 2
    ok(post(client, librarian, f"courses/{s.course['id']}/close"))
    assert err(client.patch(url, headers=librarian, json={"title": "X"}), 409, "INVALID_COURSE_STATUS")["details"]["status"] == "closed"
'''),
    dict(id="T-CRS-03-b", req="LIB-CRS-03", type="Error", input="Instructor changed to a student; to another academic", expected="`409 INSTRUCTOR_NOT_ACADEMIC`; 200", code='''
def TEST(client, librarian, branch_a):
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    url = f"/api/v1/courses/{c['id']}"
    err(client.patch(url, headers=librarian, json={"instructor_id": member(client, librarian, branch_a)["id"]}), 409, "INSTRUCTOR_NOT_ACADEMIC")
    other = academic(client, librarian, branch_a)
    assert ok(client.patch(url, headers=librarian, json={"instructor_id": other["id"]}))["instructor_id"] == other["id"]
'''),
    dict(id="T-CRS-04-a", req="LIB-CRS-04", type="Normal", input="Activate without items; add an item and activate (one student enrolled); activate again", expected="`409 COURSE_READING_LIST_EMPTY`; 200 `active` with `activated_at`, one `course_activated` notification; `409 INVALID_COURSE_STATUS` with `details.status` `active`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-CRS-04-b", req="LIB-CRS-04", type="Boundary", input="Draft course ending 2026-11-10 with an item; activated on 2026-11-10 (another one) and on 2026-11-11", expected="200; `409 COURSE_ENDED`", code='''
def TEST(client, clock, librarian, branch_a):
    s1 = setup(client, librarian, branch_a, students=0, active=False, starts_on="2026-11-02", ends_on="2026-11-10")
    s2 = setup(client, librarian, branch_a, students=0, active=False, starts_on="2026-11-02", ends_on="2026-11-10")
    at(clock, "2026-11-10")
    ok(activate(client, librarian, s1.course["id"]))
    at(clock, "2026-11-11")
    err(activate(client, librarian, s2.course["id"]), 409, "COURSE_ENDED")
'''),
    dict(id="T-CRS-05-a", req="LIB-CRS-05", type="Normal", input="Courses MATH101 2026-fall, CENG301 2026-fall, CENG101 2027-spring; CENG301 has 2 students, 2 items, 1 copy on reserve; list; `q=ceng`", expected="Order CENG301, MATH101, CENG101; counts `{enrolled 2, items 2, copies_on_reserve 1}`; `q` gives CENG301 and CENG101", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-CRS-05-b", req="LIB-CRS-05", type="Error", input="Enrolled student, the instructor and another student read the course and the list", expected="Student and instructor: 200 and the course listed; other student: `404` and an empty list", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, active=False)
    other = member(client, librarian, branch_a)
    for m in (s.students[0], s.ins):
        mh = member_headers(client, m)
        assert get(client, mh, f"courses/{s.course['id']}")["id"] == s.course["id"]
        assert [r["id"] for r in items(get(client, mh, "courses"))] == [s.course["id"]]
    oh = member_headers(client, other)
    assert client.get(f"/api/v1/courses/{s.course['id']}", headers=oh).status_code == 404
    assert get(client, oh, "courses")["total"] == 0
'''),
    dict(id="T-CRS-06-a", req="LIB-CRS-06", type="Normal", input="Active course with an open reserve loan is closed; after the return closed again; closed a third time", expected="`409 COURSE_HAS_OPEN_LOANS` with `details.loan_ids`; 200 `closed` with `released_copies` 1 and the copy `available`; `409 INVALID_COURSE_STATUS`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-CRS-07-a", req="LIB-CRS-07", type="Boundary", input="Reserve loans from a draft course; an active course starting 2026-11-03 (on Mon and on Tue); an active course that ended 2026-11-02 (on Mon and on Tue)", expected="`COURSE_NOT_RUNNING`; Mon `COURSE_NOT_RUNNING`, Tue 201; Mon 201, Tue `COURSE_NOT_RUNNING`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- enrollment
    dict(id="T-CRS-08-a", req="LIB-CRS-08", type="Normal", input="Limit 2, one student enrolled; enroll [academic A, student S1, student S2]", expected="`enrolled` [S1]; skipped A `NOT_A_STUDENT`, S2 `ENROLLMENT_FULL`; S1 gets one `course_enrolled` notification", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, active=False, enrollment_limit=2)
    a, s1, s2 = academic(client, librarian, branch_a), member(client, librarian, branch_a), member(client, librarian, branch_a)
    out = enroll(client, librarian, s.course["id"], a, s1, s2)
    assert out == {"enrolled": [s1["id"]], "skipped": [{"member_id": a["id"], "error_code": "NOT_A_STUDENT"}, {"member_id": s2["id"], "error_code": "ENROLLMENT_FULL"}]}
    assert len(notes(client, librarian, s1["id"], "course_enrolled")) == 1
'''),
    dict(id="T-CRS-08-b", req="LIB-CRS-08", type="Error", input="Enroll [unknown 999999, passive student, already enrolled student]", expected="All skipped: `NOT_FOUND`, `MEMBER_PASSIVE`, `ALREADY_ENROLLED`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, active=False)
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    out = ok(post(client, librarian, f"courses/{s.course['id']}/enrollments", {"member_ids": [999999, p["id"], s.students[0]["id"]]}))
    assert out["enrolled"] == []
    assert [x["error_code"] for x in out["skipped"]] == ["NOT_FOUND", "MEMBER_PASSIVE", "ALREADY_ENROLLED"]
'''),
    dict(id="T-CRS-08-c", req="LIB-CRS-08", type="Boundary", input="Student registered 2026-11-02 (valid until 2027-11-01) enrolled on 2027-11-01 in one course and on 2027-11-02 in another", expected="Enrolled; skipped `MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, librarian, branch_a):
    st = member(client, librarian, branch_a)
    ins = academic(client, librarian, branch_a)
    c1 = course(client, librarian, branch_a, ins, term="2027-fall", starts_on="2027-10-01", ends_on="2028-01-15")
    c2 = course(client, librarian, branch_a, ins, term="2027-fall", starts_on="2027-10-01", ends_on="2028-01-15")
    at(clock, "2027-11-01")
    assert enroll(client, librarian, c1["id"], st)["enrolled"] == [st["id"]]
    at(clock, "2027-11-02")
    assert enroll(client, librarian, c2["id"], st)["skipped"] == [{"member_id": st["id"], "error_code": "MEMBERSHIP_EXPIRED"}]
'''),
    dict(id="T-CRS-09-a", req="LIB-CRS-09", type="Error", input="`member_ids` [S1, S1]; `member_ids` []; enroll into a closed course", expected="`422`; `422`; `409 INVALID_COURSE_STATUS`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=0, active=False)
    s1 = member(client, librarian, branch_a)
    url = f"courses/{s.course['id']}/enrollments"
    assert post(client, librarian, url, {"member_ids": [s1["id"], s1["id"]]}).status_code == 422
    assert post(client, librarian, url, {"member_ids": []}).status_code == 422
    ok(post(client, librarian, f"courses/{s.course['id']}/close"))
    err(post(client, librarian, url, {"member_ids": [s1["id"]]}), 409, "INVALID_COURSE_STATUS")
'''),
    dict(id="T-CRS-10-a", req="LIB-CRS-10", type="Normal", input="Drop an enrollment; drop it again; enroll the member again", expected="200 `dropped` with `staff_request`; `409 ENROLLMENT_NOT_ACTIVE`; a new enrollment", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, active=False)
    st = s.students[0]
    e = items(get(client, librarian, f"courses/{s.course['id']}/enrollments"))[0]
    out = ok(post(client, librarian, f"enrollments/{e['id']}/drop"))
    assert (out["status"], out["drop_reason"]) == ("dropped", "staff_request") and same(out["dropped_at"], MON, 9)
    err(post(client, librarian, f"enrollments/{e['id']}/drop"), 409, "ENROLLMENT_NOT_ACTIVE")
    enroll(client, librarian, s.course["id"], st)
    rows = items(get(client, librarian, f"courses/{s.course['id']}/enrollments"))
    assert [(r["member_id"], r["status"]) for r in rows] == [(st["id"], "dropped"), (st["id"], "enrolled")] and rows[1]["id"] != e["id"]
'''),
    dict(id="T-CRS-10-b", req="LIB-CRS-10", type="Error", input="Drop a student with an open reserve loan of the course", expected="`409 MEMBER_HAS_RESERVE_LOANS`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    rloan(client, librarian, s.students[0], s.copies[0])
    e = items(get(client, librarian, f"courses/{s.course['id']}/enrollments"))[0]
    err(post(client, librarian, f"enrollments/{e['id']}/drop"), 409, "MEMBER_HAS_RESERVE_LOANS")
'''),
    dict(id="T-CRS-11-a", req="LIB-CRS-11", type="Normal", input="Enrollments read by the librarian, the instructor and another student; courses of the student and of the instructor", expected="Rows with `member_no` and `full_name`; instructor 200; student `403`; roles `student` and `instructor`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=2, active=False)
    url = f"/api/v1/courses/{s.course['id']}/enrollments"
    rows = items(ok(client.get(url, headers=librarian)))
    assert [(r["member_id"], r["member_no"], r["full_name"]) for r in rows] == [(m["id"], m["member_no"], m["full_name"]) for m in s.students]
    assert ok(client.get(url, headers=member_headers(client, s.ins)))["total"] == 2
    assert client.get(url, headers=member_headers(client, s.students[0])).status_code == 403
    for m, role in ((s.students[0], "student"), (s.ins, "instructor")):
        rows = items(get(client, member_headers(client, m), f"members/{m['id']}/courses"))
        assert [(r["id"], r["role"]) for r in rows] == [(s.course["id"], role)]
'''),
    # ---------------------------------------------------------------- reading list
    dict(id="T-CRS-12-a", req="LIB-CRS-12", type="Normal", input="Two items added with only `book_id` (copies only at another branch)", expected="201: positions 1 and 2, status `requested`, `required`, `2h`, `copies_wanted` 1, `note` empty", code='''
def TEST(client, librarian, branch_a, branch_b):
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    b1, _ = book(client, librarian, branch_b, 1)
    b2, _ = book(client, librarian, branch_b, 1)
    i1, i2 = item(client, librarian, c["id"], b1["id"]), item(client, librarian, c["id"], b2["id"])
    keys = ("position", "status", "kind", "loan_period", "copies_wanted", "note", "book_id")
    assert [tuple(i[k] for k in keys) for i in (i1, i2)] == [(1, "requested", "required", "2h", 1, "", b1["id"]), (2, "requested", "required", "2h", 1, "", b2["id"])]
'''),
    dict(id="T-CRS-12-b", req="LIB-CRS-12", type="Error", input="Unknown book; book without copies; a book already on the list; `copies_wanted` 6; item for a closed course", expected="`422`; `409 BOOK_NOT_LENDABLE`; `409 DUPLICATE_ITEM`; `422`; `409 INVALID_COURSE_STATUS`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=0, active=False)
    cid = s.course["id"]
    assert try_item(client, librarian, cid, 999999).status_code == 422
    err(try_item(client, librarian, cid, book(client, librarian)[0]["id"]), 409, "BOOK_NOT_LENDABLE")
    err(try_item(client, librarian, cid, s.book["id"]), 409, "DUPLICATE_ITEM")
    b, _ = book(client, librarian, branch_a, 1)
    assert try_item(client, librarian, cid, b["id"], copies_wanted=6).status_code == 422
    ok(post(client, librarian, f"courses/{cid}/close"))
    err(try_item(client, librarian, cid, b["id"]), 409, "INVALID_COURSE_STATUS")
'''),
    dict(id="T-CRS-12-c", req="LIB-CRS-12", type="Boundary", input="Course with 40 items; a 41st; one removed, then the 41st again", expected="`409 READING_LIST_FULL`; then 201", code='''
def TEST(client, librarian, branch_a, branch_b):
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    first = None
    for _ in range(40):
        it = item(client, librarian, c["id"], book(client, librarian, branch_b, 1)[0]["id"], kind="recommended")
        first = first or it
    extra, _ = book(client, librarian, branch_b, 1)
    err(try_item(client, librarian, c["id"], extra["id"]), 409, "READING_LIST_FULL")
    ok(post(client, librarian, f"reading-list-items/{first['id']}/remove"))
    assert item(client, librarian, c["id"], extra["id"])["position"] == 40
'''),
    dict(id="T-CRS-13-a", req="LIB-CRS-13", type="Normal", input="Book with 3 available copies at the course's branch and 1 at another; `required` item with `copies_wanted` 2; a `recommended` item of a second such book", expected="The first two copies (by id) `on_reserve` and the item `on_reserve` with 2 copies; the recommended item `requested` with 0", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-CRS-14-a", req="LIB-CRS-14", type="Error", input="Item with 2 copies on reserve: `copies_wanted` 1; `note` changed; a removed item changed", expected="`409 COPIES_WANTED_BELOW_RESERVE` with `details.on_reserve` 2; 200; `409 ITEM_REMOVED`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, copies=2, active=False)
    url = f"/api/v1/reading-list-items/{s.item['id']}"
    assert err(client.patch(url, headers=librarian, json={"copies_wanted": 1}), 409, "COPIES_WANTED_BELOW_RESERVE")["details"]["on_reserve"] == 2
    assert ok(client.patch(url, headers=librarian, json={"note": "Bölüm 3"}))["note"] == "Bölüm 3"
    ok(post(client, librarian, f"reading-list-items/{s.item['id']}/remove"))
    err(client.patch(url, headers=librarian, json={"note": "X"}), 409, "ITEM_REMOVED")
'''),
    dict(id="T-CRS-14-b", req="LIB-CRS-14", type="Normal", input="`2h` item with 2 copies: loan 1 at 09:00; `loan_period` changed to `1d`; loan 2 at 09:30", expected="Loan 1 due Mon 11:00 (unchanged); loan 2 due Tue 20:00", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a, copies=2, students=2)
    l1 = rloan(client, librarian, s.students[0], s.copies[0])
    ok(client.patch(f"/api/v1/reading-list-items/{s.item['id']}", headers=librarian, json={"loan_period": "1d"}))
    at(clock, MON, 9, 30)
    l2 = rloan(client, librarian, s.students[1], s.copies[1])
    assert same([x for x in items(get(client, librarian, "reserve-loans")) if x["id"] == l1["id"]][0]["due_at"], MON, 11)
    assert same(l2["due_at"], TUE, 20)
'''),
    dict(id="T-CRS-15-a", req="LIB-CRS-15", type="Error", input="Items I1, I2, I3: order [I3, I1, I2]; order missing I2; order with I1 twice", expected="200 positions I3 1, I1 2, I2 3; `422`; `422`", code='''
def TEST(client, librarian, branch_a, branch_b):
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    i1, i2, i3 = (item(client, librarian, c["id"], book(client, librarian, branch_b, 1)[0]["id"]) for _ in range(3))
    url = f"/api/v1/courses/{c['id']}/reading-list/order"
    out = ok(client.put(url, headers=librarian, json={"item_ids": [i3["id"], i1["id"], i2["id"]]}))
    assert [(x["id"], x["position"]) for x in items(out)] == [(i3["id"], 1), (i1["id"], 2), (i2["id"], 3)]
    assert client.put(url, headers=librarian, json={"item_ids": [i3["id"], i1["id"]]}).status_code == 422
    assert client.put(url, headers=librarian, json={"item_ids": [i1["id"], i1["id"], i2["id"]]}).status_code == 422
'''),
    dict(id="T-CRS-16-a", req="LIB-CRS-16", type="Normal", input="Items I1 (1 copy on reserve, on loan), I2, I3: remove I1; after the return remove I1; remove again", expected="`409 RESERVE_COPY_ON_LOAN` with `details.loan_ids`; 200 `removed` with position null, I2 → 1, I3 → 2, the copy `available`; `409 ITEM_REMOVED`", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-CRS-17-a", req="LIB-CRS-17", type="Normal", input="Item with 2 copies on reserve: both lent at 09:00 and 09:30 (`2h`); a removed item; list; `include_removed=true`", expected="`copies_on_reserve` 2, `available_now` 0, `next_due_at` 11:00, `book_title`; removed item only with `include_removed`, after the others", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-CRS-18-a", req="LIB-CRS-18", type="Error", input="The instructor adds, changes and removes an item; another academic adds one; the instructor places a copy and enrolls a student", expected="201, 200, 200; `403`; `403`, `403`", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    # ---------------------------------------------------------------- copies on reserve
    dict(id="T-CRS-19-a", req="LIB-CRS-19", type="Normal", input="Recommended item of a book with an available copy at the course's branch; the copy is placed", expected="201 `{copy_id, barcode, item_id, course_id, on_loan false}`; copy `on_reserve`; item `on_reserve`", code='''
def TEST(client, librarian, branch_a):
    c = course(client, librarian, branch_a, academic(client, librarian, branch_a))
    b, (cp,) = book(client, librarian, branch_a, 1)
    it = item(client, librarian, c["id"], b["id"], kind="recommended")
    out = ok(place(client, librarian, it["id"], cp["id"]), 201)
    keys = ("copy_id", "barcode", "item_id", "course_id", "on_loan")
    assert tuple(out[k] for k in keys) == (cp["id"], cp["barcode"], it["id"], c["id"], False)
    assert copy_of(client, librarian, cp["id"])["status"] == "on_reserve"
    assert item_of(client, librarian, c["id"], it["id"])["status"] == "on_reserve"
'''),
    dict(id="T-CRS-19-b", req="LIB-CRS-19", type="Error", input="Copy of another book; a copy on loan; a copy at another branch; a copy when `copies_wanted` is reached; a removed item", expected="`WRONG_BOOK`; `INVALID_COPY_STATUS` with `details.status` `on_loan`; `COPY_AT_OTHER_BRANCH`; `RESERVE_COPIES_COMPLETE`; `ITEM_REMOVED`", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-CRS-19-c", req="LIB-CRS-19", type="Normal", input="Active course with an enrolled student and a recommended item (`copies_wanted` 2) without copies; two copies placed one after the other", expected="One `reserve_item_available` notification with `course_id`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    b, (c1, c2) = book(client, librarian, branch_a, 2)
    it = item(client, librarian, s.course["id"], b["id"], kind="recommended", copies_wanted=2)
    ok(place(client, librarian, it["id"], c1["id"]), 201)
    ok(place(client, librarian, it["id"], c2["id"]), 201)
    ns = notes(client, librarian, s.students[0]["id"], "reserve_item_available")
    assert len(ns) == 1 and ns[0]["course_id"] == s.course["id"]
'''),
    dict(id="T-CRS-20-a", req="LIB-CRS-20", type="Error", input="Only copy of a book is on reserve: normal loan; withdrawal; relocation to another branch; book availability", expected="`409 COPY_NOT_AVAILABLE` with `details.status` `on_reserve`; `409 INVALID_COPY_STATUS` twice; availability `available` 0, `total` 1", code='''
def TEST(client, librarian, branch_a, branch_b):
    s = setup(client, librarian, branch_a)
    cp = s.copies[0]
    r = post(client, librarian, "loans", {"member_id": member(client, librarian, branch_a)["id"], "copy_id": cp["id"]})
    assert err(r, 409, "COPY_NOT_AVAILABLE")["details"]["status"] == "on_reserve"
    err(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Eskidi artık"}), 409, "INVALID_COPY_STATUS")
    err(post(client, librarian, "transfers", {"copy_id": cp["id"], "to_branch_id": branch_b["id"]}), 409, "INVALID_COPY_STATUS")
    av = get(client, librarian, f"books/{s.book['id']}")["availability"]
    assert av == [{"branch_id": branch_a["id"], "available": 0, "total": 1}]
'''),
    dict(id="T-CRS-21-a", req="LIB-CRS-21", type="Normal", input="Copy on loan as reserve: unreserve; after the return unreserve; an available copy unreserved", expected="`409 RESERVE_COPY_ON_LOAN`; 200: copy `available`, `reserve_item_id` null, item `requested`; `409 INVALID_COPY_STATUS`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    cp = s.copies[0]
    loan = rloan(client, librarian, s.students[0], cp)
    assert err(post(client, librarian, f"copies/{cp['id']}/unreserve"), 409, "RESERVE_COPY_ON_LOAN")["details"]["loan_ids"] == [loan["id"]]
    ok(rreturn(client, librarian, loan["id"], branch_a))
    out = ok(post(client, librarian, f"copies/{cp['id']}/unreserve"))
    assert (out["status"], out["reserve_item_id"]) == ("available", None)
    assert item_of(client, librarian, s.course["id"], s.item["id"])["status"] == "requested"
    err(post(client, librarian, f"copies/{cp['id']}/unreserve"), 409, "INVALID_COPY_STATUS")
'''),
    dict(id="T-CRS-22-a", req="LIB-CRS-22", type="Normal", input="Copy C of book X on loan; courses K1 then K2 at the branch each add a `required` item for X; C returned in good condition at the branch", expected="C `on_reserve` for K1's item (`reserve_course_id` K1); K2's item still `requested`", code='''
def TEST(client, librarian, branch_a):
    b, (cp,) = book(client, librarian, branch_a, 1)
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    ins = academic(client, librarian, branch_a)
    k1, k2 = course(client, librarian, branch_a, ins), course(client, librarian, branch_a, ins)
    i1, i2 = item(client, librarian, k1["id"], b["id"]), item(client, librarian, k2["id"], b["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    out = copy_of(client, librarian, cp["id"])
    assert (out["status"], out["reserve_item_id"], out["reserve_course_id"]) == ("on_reserve", i1["id"], k1["id"])
    assert item_of(client, librarian, k2["id"], i2["id"])["status"] == "requested"
'''),
    dict(id="T-CRS-22-b", req="LIB-CRS-22", type="Normal", input="Required item with its only copy on reserve; the copy is taken off reserve", expected="The copy stays `available` (not placed back); the item `requested`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, active=False)
    ok(post(client, librarian, f"copies/{s.copies[0]['id']}/unreserve"))
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "available"
    assert item_of(client, librarian, s.course["id"], s.item["id"])["status"] == "requested"
'''),
    dict(id="T-CRS-23-a", req="LIB-CRS-23", type="Normal", input="Copies C1 (available) and C2 (on loan) of book X at branch A; required item, `copies_wanted` 2; a member reserves X for pickup at A; C2 returned at A", expected="After adding: C1 on reserve, 1 of 2. Reservation 201 `waiting`. After the return: C2 `on_reserve`, item 2 copies, reservation still `waiting`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- reserve loans
    dict(id="T-CRS-24-a", req="LIB-CRS-24", type="Normal", input="Enrolled student borrows a `2h` reserve copy on Mon 09:00; another copy by barcode", expected="201 `open`, due 11:00, `renewed` false, `book_title`, `course_code`, `is_overdue` false; by barcode 201", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, copies=2, students=2)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    assert (loan["status"], loan["renewed"], loan["book_title"], loan["course_code"], loan["is_overdue"], loan["item_id"]) == ("open", False, "Reserve Book", s.course["code"], False, s.item["id"])
    assert same(loan["lent_at"], MON, 9) and same(loan["due_at"], MON, 11)
    ok(post(client, librarian, "reserve-loans", {"member_id": s.students[1]["id"], "barcode": s.copies[1]["barcode"]}), 201)
'''),
    dict(id="T-CRS-24-b", req="LIB-CRS-24", type="Error", input="Both `copy_id` and `barcode`; neither; unknown barcode; an `available` copy; a member lends", expected="`422`; `422`; `404`; `409 COPY_NOT_ON_RESERVE` with `details.status` `available`; `403`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    st, cp = s.students[0], s.copies[0]
    assert post(client, librarian, "reserve-loans", {"member_id": st["id"], "copy_id": cp["id"], "barcode": cp["barcode"]}).status_code == 422
    assert post(client, librarian, "reserve-loans", {"member_id": st["id"]}).status_code == 422
    assert post(client, librarian, "reserve-loans", {"member_id": st["id"], "barcode": "NOPE-0001"}).status_code == 404
    _, (free,) = book(client, librarian, branch_a, 1)
    assert err(rlend(client, librarian, st["id"], free["id"]), 409, "COPY_NOT_ON_RESERVE")["details"]["status"] == "available"
    assert rlend(client, member_headers(client, st), st["id"], cp["id"]).status_code == 403
'''),
    dict(id="T-CRS-24-c", req="LIB-CRS-24", type="Boundary", input="Lending on Mon 07:59, 08:00, 19:59, 20:00 and on Saturday 10:00", expected="`RESERVE_DESK_CLOSED`; 201; 201; `RESERVE_DESK_CLOSED`; `RESERVE_DESK_CLOSED`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-CRS-24-d", req="LIB-CRS-24", type="Error", input="Passive enrolled student; a student not enrolled; a dropped student; the instructor", expected="`MEMBER_PASSIVE`; `NOT_ENROLLED`; `NOT_ENROLLED`; 201", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=2)
    cp = s.copies[0]
    deactivate_member(client, librarian, s.students[0]["id"])
    err(rlend(client, librarian, s.students[0]["id"], cp["id"]), 409, "MEMBER_PASSIVE")
    err(rlend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"]), 409, "NOT_ENROLLED")
    e = [x for x in items(get(client, librarian, f"courses/{s.course['id']}/enrollments")) if x["member_id"] == s.students[1]["id"]][0]
    ok(post(client, librarian, f"enrollments/{e['id']}/drop"))
    err(rlend(client, librarian, s.students[1]["id"], cp["id"]), 409, "NOT_ENROLLED")
    rloan(client, librarian, s.ins, cp)
'''),
    dict(id="T-CRS-24-e", req="LIB-CRS-24", type="Boundary", input="Student with a `2h` reserve loan due 11:00 borrows from a second item at 11:00 and from a third at 11:00:01", expected="201; `409 MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    it2, cps2 = more_item(client, librarian, branch_a, s.course["id"], copies=2)
    rloan(client, librarian, s.students[0], s.copies[0])
    at(clock, MON, 11, 0)
    rloan(client, librarian, s.students[0], cps2[0])
    at(clock, MON, 11, 1, 1)
    it3, cps3 = more_item(client, librarian, branch_a, s.course["id"])
    err(rlend(client, librarian, s.students[0]["id"], cps3[0]["id"]), 409, "MEMBER_HAS_OVERDUE")
'''),
    dict(id="T-CRS-24-f", req="LIB-CRS-24", type="Boundary", input="Enrolled students with debt 50.00 and 49.99", expected="`409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` \"50.00\"; 201", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, copies=2, students=2)
    a, b = s.students
    debt(client, librarian, branch_a, a, "50.00")
    debt(client, librarian, branch_a, b, "49.99")
    assert err(rlend(client, librarian, a["id"], s.copies[0]["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    rloan(client, librarian, b, s.copies[0])
'''),
    dict(id="T-CRS-24-g", req="LIB-CRS-24", type="Boundary", input="Student borrows copy 1 of item I (2 copies) and then copy 2; borrows from items J and K; another student borrows I's copy 1", expected="`ALREADY_BORROWED`; J 201, K `RESERVE_LOAN_LIMIT_REACHED` with `details.limit` 2; `COPY_ON_RESERVE_LOAN` with `details.due_at`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-CRS-24-h", req="LIB-CRS-24", type="Boundary", input="The instructor borrows from 3 items and then a fourth", expected="Three 201; `RESERVE_LOAN_LIMIT_REACHED` with `details.limit` 3", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=0)
    copies = [s.copies[0]] + [more_item(client, librarian, branch_a, s.course["id"])[1][0] for _ in range(3)]
    for cp in copies[:3]:
        rloan(client, librarian, s.ins, cp)
    assert err(rlend(client, librarian, s.ins["id"], copies[3]["id"]), 409, "RESERVE_LOAN_LIMIT_REACHED")["details"]["limit"] == 3
'''),
    dict(id="T-CRS-24-i", req="LIB-CRS-24", type="Boundary", input="Student registered 2026-11-02 (valid until 2027-11-01), enrolled in a 2027-fall course; borrows on Mon 2027-11-01 and on Tue 2027-11-02", expected="201; `409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, librarian, branch_a):
    st = member(client, librarian, branch_a)
    at(clock, "2027-10-04")
    s = setup(client, librarian, branch_a, students=0, term="2027-fall", starts_on="2027-10-01", ends_on="2028-01-15")
    enroll(client, librarian, s.course["id"], st)
    at(clock, "2027-11-01")
    loan = rloan(client, librarian, st, s.copies[0])
    ok(rreturn(client, librarian, loan["id"], branch_a))
    at(clock, "2027-11-02")
    err(rlend(client, librarian, st["id"], s.copies[0]["id"]), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-CRS-25-a", req="LIB-CRS-25", type="Normal", input="Branch hours set to 08:00–18:00; `2h` loan at 17:00; a closure added afterwards for Tue does not move a `1d` loan made on Mon", expected="Due 18:00; the `1d` loan stays due Tue 18:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(client.put(f"/api/v1/branches/{branch_a['id']}/hours", headers=admin, json={"opens_at": "08:00", "closes_at": "18:00", "min_staff": 1}))
    s = setup(client, librarian, branch_a)
    d = setup(client, librarian, branch_a, period="1d")
    day = rloan(client, librarian, d.students[0], d.copies[0])
    assert same(day["due_at"], TUE, 18)
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": TUE, "reason": "Sayım"}), 201)
    assert same(items(get(client, librarian, "reserve-loans", member_id=d.students[0]["id"]))[0]["due_at"], TUE, 18)
    at(clock, MON, 17)
    assert same(rloan(client, librarian, s.students[0], s.copies[0])["due_at"], MON, 18)
'''),
    dict(id="T-CRS-26-a", req="LIB-CRS-26", type="Boundary", input="`2h` loans on Mon 10:15 and 19:00; `1d` loan on Fri 2026-11-06 15:00", expected="Due 12:15; 20:00; Mon 2026-11-09 20:00", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a, copies=2, students=2)
    d = setup(client, librarian, branch_a, period="1d")
    at(clock, MON, 10, 15)
    assert same(rloan(client, librarian, s.students[0], s.copies[0])["due_at"], MON, 12, 15)
    at(clock, MON, 19)
    assert same(rloan(client, librarian, s.students[1], s.copies[1])["due_at"], MON, 20)
    at(clock, FRI, 15)
    assert same(rloan(client, librarian, d.students[0], d.copies[0])["due_at"], "2026-11-09", 20)
'''),
    dict(id="T-CRS-26-b", req="LIB-CRS-26", type="Normal", input="`3d` loans on Tue 2026-11-03: one at branch A, one at branch B with a closure on Thu 2026-11-05", expected="A: due Fri 2026-11-06 20:00; B: Mon 2026-11-09 20:00", code='''
def TEST(client, clock, admin, librarian, branch_a, branch_b):
    a = setup(client, librarian, branch_a, period="3d")
    b = setup(client, librarian, branch_b, period="3d")
    ok(post(client, admin, f"branches/{branch_b['id']}/closures", {"date": THU, "reason": "Sayım"}), 201)
    at(clock, TUE)
    assert same(rloan(client, librarian, a.students[0], a.copies[0])["due_at"], FRI, 20)
    assert same(rloan(client, librarian, b.students[0], b.copies[0])["due_at"], "2026-11-09", 20)
'''),
    dict(id="T-CRS-27-a", req="LIB-CRS-27", type="Normal", input="Item with 2 copies: loan at 09:00; the member renews at 10:00; renews again", expected="200 due 12:00, `renewed` true; `409 RENEWAL_LIMIT_REACHED`", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a, copies=2)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    at(clock, MON, 10)
    mh = member_headers(client, s.students[0])
    out = ok(post(client, mh, f"reserve-loans/{loan['id']}/renew"))
    assert out["renewed"] is True and same(out["due_at"], MON, 12)
    err(post(client, mh, f"reserve-loans/{loan['id']}/renew"), 409, "RENEWAL_LIMIT_REACHED")
'''),
    dict(id="T-CRS-27-b", req="LIB-CRS-27", type="Error", input="Item with one copy: renew at 10:00; item with 2 copies: renew at 11:01 (due 11:00); renew a returned loan", expected="`RESERVE_IN_DEMAND`; `LOAN_OVERDUE`; `RESERVE_LOAN_NOT_OPEN`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-CRS-28-a", req="LIB-CRS-28", type="Normal", input="Return at another branch; at the course's branch at 10:00; return again", expected="`409 RESERVE_RETURN_WRONG_BRANCH` with `details.branch_id`; 200 `returned`, `late_minutes` 0, no fee, copy still `on_reserve`; `409 RESERVE_LOAN_NOT_OPEN`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    s = setup(client, librarian, branch_a)
    loan = rloan(client, librarian, s.students[0], s.copies[0])
    assert err(rreturn(client, librarian, loan["id"], branch_b), 409, "RESERVE_RETURN_WRONG_BRANCH")["details"]["branch_id"] == branch_a["id"]
    at(clock, MON, 10)
    out = ok(rreturn(client, librarian, loan["id"], branch_a))
    assert (out["status"], out["late_minutes"], out["fee_id"]) == ("returned", 0, None) and same(out["returned_at"], MON, 10)
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "on_reserve"
    err(rreturn(client, librarian, loan["id"], branch_a), 409, "RESERVE_LOAN_NOT_OPEN")
'''),
    dict(id="T-CRS-29-a", req="LIB-CRS-29", type="Boundary", input="Four `2h` loans due 11:00 returned at 11:05, 11:06, 13:00 and 13:01", expected="`late_minutes` 5, 6, 120, 121; fees none, 1.00, 2.00, 3.00 (`reserve_late_fee` with `reserve_loan_id`)", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-CRS-30-a", req="LIB-CRS-30", type="Boundary", input="`2h` loan (due Mon 11:00) returned Thu 11:00; `1d` loan (due Tue 20:00) returned Wed 09:00; accrued fee of a `2h` loan at 12:00", expected="30.00 (cap); 5.00; `accrued_late_fee` 1.00 and `is_overdue` true", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-CRS-31-a", req="LIB-CRS-31", type="Normal", input="`2h` reserve loan (copy price 80.00) reported lost at 12:00; reported again", expected="Loan `lost` with `late_minutes` 60; fees `reserve_late_fee` 1.00 and `reserve_lost` 80.00; copy `lost` with branch and item null; item `requested`; `409 RESERVE_LOAN_NOT_OPEN`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-CRS-32-a", req="LIB-CRS-32", type="Normal", input="Loans L1 (09:00) and L2 (10:00) of two students; at 11:30 list all, `overdue=true`, `course_id` of another course; a student reads own and the other's loans", expected="[L2, L1]; [L1]; empty; own list [L1]; `403`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-CRS-33-a", req="LIB-CRS-33", type="Boundary", input="`2h` loan due 11:00; process at 11:00, 11:00:01 and again", expected="`overdue_notices` 0, 1, 0; one `reserve_overdue` notification", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    rloan(client, librarian, s.students[0], s.copies[0])
    counts = []
    for t in ((11, 0, 0), (11, 0, 1), (11, 0, 2)):
        at(clock, MON, *t)
        counts.append(ok(post(client, librarian, "course-reserves/process"))["overdue_notices"])
    assert counts == [0, 1, 0]
    assert len(notes(client, librarian, s.students[0]["id"], "reserve_overdue")) == 1
'''),
    dict(id="T-CRS-34-a", req="LIB-CRS-34", type="Normal", input="Course ending Fri 2026-11-20 with one open reserve loan; process Mon 2026-11-23; after the return process again", expected="First `{closed_courses 0, pending_courses 1}`; then `{closed_courses 1, released_copies 1, pending_courses 0}` and the course `closed`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- effects
    dict(id="T-CRS-35-a", req="LIB-CRS-35", type="Normal", input="A `reserve_late_fee` of 2.00; fee list `kind=reserve_late_fee`; payment of 2.00", expected="Listed; payment allocated, fee `paid`", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    loan = rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 12, 30)
    ok(rreturn(client, librarian, loan["id"], branch_a))
    fee = items(get(client, librarian, "fees", kind="reserve_late_fee"))
    assert [(f["member_id"], f["amount"]) for f in fee] == [(st["id"], "2.00")]
    ok(post(client, librarian, f"members/{st['id']}/payments", {"amount": "2.00", "method": "cash"}), 201)
    assert items(member_fees(client, librarian, st["id"]))[0]["status"] == "paid"
'''),
    dict(id="T-CRS-36-a", req="LIB-CRS-36", type="Normal", input="Open `2h` reserve loan due 11:00; balance at 13:30", expected="`accrued_late_fees` 3.00, `total_debt` 3.00", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 13, 30)
    b = balance(client, librarian, st["id"])
    assert (b["accrued_late_fees"], b["total_debt"], b["outstanding_fees"]) == ("3.00", "3.00", "0.00")
'''),
    dict(id="T-CRS-37-a", req="LIB-CRS-37", type="Normal", input="Student with an overdue reserve loan borrows a normal book; the summary", expected="`409 MEMBER_HAS_OVERDUE`; `borrowing.reasons` contains `MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 11, 30)
    _, (cp,) = book(client, librarian, branch_a, 1)
    err(post(client, librarian, "loans", {"member_id": st["id"], "copy_id": cp["id"]}), 409, "MEMBER_HAS_OVERDUE")
    assert "MEMBER_HAS_OVERDUE" in get(client, librarian, f"members/{st['id']}/summary")["borrowing"]["reasons"]
'''),
    dict(id="T-CRS-38-a", req="LIB-CRS-38", type="Normal", input="Student enrolled in an active and a draft course and with one overdue reserve loan; the instructor's summary", expected="Student `{courses_enrolled 2, courses_teaching 0, open_reserve_loans 1, overdue_reserve_loans 1}`; instructor `courses_teaching` 1", code='''
def TEST(client, clock, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    st = s.students[0]
    d = setup(client, librarian, branch_a, students=0, active=False)
    enroll(client, librarian, d.course["id"], st)
    rloan(client, librarian, st, s.copies[0])
    at(clock, MON, 12)
    out = get(client, librarian, f"members/{st['id']}/summary")["course_reserves"]
    assert out == {"courses_enrolled": 2, "courses_teaching": 0, "open_reserve_loans": 1, "overdue_reserve_loans": 1}
    assert get(client, librarian, f"members/{s.ins['id']}/summary")["course_reserves"]["courses_teaching"] == 1
'''),
    dict(id="T-CRS-39-a", req="LIB-CRS-39", type="Error", input="Deactivate a student with an open reserve loan; the instructor of an active course; an enrolled student without loans", expected="`409 MEMBER_HAS_OPEN_LOANS`; `409 INSTRUCTOR_HAS_COURSES` with `details.course_ids`; 200 and the enrollment `dropped` with `member_deactivated`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=2)
    a, b = s.students
    rloan(client, librarian, a, s.copies[0])
    err(post(client, librarian, f"members/{a['id']}/deactivate"), 409, "MEMBER_HAS_OPEN_LOANS")
    assert err(post(client, librarian, f"members/{s.ins['id']}/deactivate"), 409, "INSTRUCTOR_HAS_COURSES")["details"]["course_ids"] == [s.course["id"]]
    deactivate_member(client, librarian, b["id"])
    e = [x for x in items(get(client, librarian, f"courses/{s.course['id']}/enrollments")) if x["member_id"] == b["id"]][0]
    assert (e["status"], e["drop_reason"]) == ("dropped", "member_deactivated")
'''),
    dict(id="T-CRS-40-a", req="LIB-CRS-40", type="Error", input="Enrolled student changed to `academic`; the instructor changed to `staff`; a student of a closed course changed to `academic`", expected="`409 MEMBER_HAS_ENROLLMENTS`; `409 INSTRUCTOR_HAS_COURSES`; 200", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, active=False)
    url = "/api/v1/members/{}"
    err(client.patch(url.format(s.students[0]["id"]), headers=librarian, json={"membership_type": "academic"}), 409, "MEMBER_HAS_ENROLLMENTS")
    err(client.patch(url.format(s.ins["id"]), headers=librarian, json={"membership_type": "staff"}), 409, "INSTRUCTOR_HAS_COURSES")
    ok(post(client, librarian, f"courses/{s.course['id']}/close"))
    assert ok(client.patch(url.format(s.students[0]["id"]), headers=librarian, json={"membership_type": "academic"}))["membership_type"] == "academic"
'''),
    dict(id="T-CRS-41-a", req="LIB-CRS-41", type="Error", input="Branch QQ with only a draft course (no copies, no members) is deactivated; after the course is closed", expected="`409 BRANCH_IN_USE`; 200", code='''
def TEST(client, admin, librarian, branch_a):
    qq = create_branch(client, admin, "QQ")
    c = course(client, librarian, qq, academic(client, librarian, branch_a))
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"courses/{c['id']}/close"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))
'''),
    dict(id="T-CRS-42-a", req="LIB-CRS-42", type="Normal", input="The only copy of a book at branch A is on reserve; a member reserves the book for pickup at A", expected="201 `waiting`; the copy stays `on_reserve`", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    res = reserve(client, librarian, book_id=s.book["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    assert (res["status"], res["copy_id"]) == ("waiting", None)
    assert copy_of(client, librarian, s.copies[0]["id"])["status"] == "on_reserve"
'''),
    dict(id="T-CRS-43-a", req="LIB-CRS-43", type="Normal", input="Book with one copy on reserve and one available; copies with `status=on_reserve`", expected="Only the reserved copy, with `reserve_item_id` and `reserve_course_id`; the other has both null", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    free = add_copy(client, librarian, s.book["id"], home_branch_id=branch_a["id"])
    rows = items(get(client, librarian, f"books/{s.book['id']}/copies", status="on_reserve"))
    assert [(r["id"], r["reserve_item_id"], r["reserve_course_id"]) for r in rows] == [(s.copies[0]["id"], s.item["id"], s.course["id"])]
    other = copy_of(client, librarian, free["id"])
    assert (other["reserve_item_id"], other["reserve_course_id"]) == (None, None)
'''),
    dict(id="T-CRS-44-a", req="LIB-CRS-44", type="Normal", input="Student enrolled in course CENG204 (one notification); borrows and returns a reserve copy in time", expected="`course_enrolled` has `course_id` and the code in the message; no other notification", code='''
def TEST(client, librarian, branch_a):
    s = setup(client, librarian, branch_a, students=0, code="CENG204")
    st = member(client, librarian, branch_a)
    enroll(client, librarian, s.course["id"], st)
    loan = rloan(client, librarian, st, s.copies[0])
    ok(rreturn(client, librarian, loan["id"], branch_a))
    ns = items(get(client, librarian, f"members/{st['id']}/notifications"))
    assert [n["type"] for n in ns] == ["course_enrolled"]
    assert ns[0]["course_id"] == s.course["id"] and "CENG204" in ns[0]["message"]
'''),
    dict(id="T-CRS-45-a", req="LIB-CRS-45", type="Normal", input="Course created, changed, activated; enrollment created and dropped; recommended item added, changed; copy placed, lent, renewed, returned, taken off; item removed; course closed; process; audit log", expected="One entry of each event", code='''
def TEST(client, clock, librarian, admin, branch_a):
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
'''),
    dict(id="T-CRS-46-a", req="LIB-CRS-46", type="Normal", input="Course K (2 students, one item filled and one `recommended` unfilled): A returns 10 minutes late, B in time; a draft course; report 2026-11-02 – 2026-11-08", expected="Only K: `{status active, enrolled 2, items 2, items_unfilled 1, loans 2, borrowers 2, late_returns 1, fees_charged 1.00}`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-CRS-46-b", req="LIB-CRS-46", type="Error", input="`from` > `to`; 367 days; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/course-reserves"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": WED}).status_code == 403
'''),
    dict(id="T-CRS-47-a", req="LIB-CRS-47", type="Normal", input="A course with a reserve loan exists; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, librarian, branch_a):
    s = setup(client, librarian, branch_a)
    rloan(client, librarian, s.students[0], s.copies[0])
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
]
