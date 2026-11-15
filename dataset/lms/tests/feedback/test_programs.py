"""Feedback tests: module 26 (Reading programs). Generated from cases/programs.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, deactivate_member, error_code, items, lend, member_fees, member_headers,
    register_member, report_lost, return_loan,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON = "2026-11-02"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); student loans are due 14 days later


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


def mh(client, m):
    return member_headers(client, m)


def try_program(client, headers, branch=None, **fields):
    _seq[0] += 1
    body = {"name": f"Okuma Programı {_seq[0]:03d}", "branch_id": branch["id"] if branch else None,
            "starts_on": MON, "ends_on": "2026-11-30", "goal_books": 2}
    body.update(fields)
    return post(client, headers, "programs", body)


def program(client, headers, branch=None, **fields):
    return ok(try_program(client, headers, branch, **fields), 201)


def published(client, lib, branch=None, **fields):
    p = program(client, lib, branch, **fields)
    return ok(post(client, lib, f"programs/{p['id']}/publish"))


def try_join(client, headers, p, member_id=None, public=None):
    body = {}
    if member_id is not None:
        body["member_id"] = member_id
    if public is not None:
        body["public"] = public
    return post(client, headers, f"programs/{p['id']}/join", body)


def joined(client, lib, branch, p, **kw):
    """A new member who joined ``p``: (participation, member, headers)."""
    m = member(client, lib, branch, **kw)
    h = mh(client, m)
    return ok(try_join(client, h, p), 201), m, h


def book_with_copy(client, lib, branch, book=None):
    b = book or create_book(client, lib, title="Okunan Kitap")
    return b, add_copy(client, lib, b["id"], home_branch_id=branch["id"])


def read(client, lib, m, branch, book=None):
    """``m`` borrows a copy at ``branch`` and returns it at once: (book, loan)."""
    b, cp = book_with_copy(client, lib, branch, book)
    loan = lend(client, lib, m["id"], cp["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"])
    return b, loan


def part(client, headers, participation):
    return [x for x in items(get(client, headers, f"members/{participation['member_id']}/programs")) if x["id"] == participation["id"]][0]


def entries(client, headers, participation, **params):
    return items(get(client, headers, f"participations/{participation['id']}/entries", **params))


def manual(client, lib, participation, book, note=""):
    return post(client, lib, f"participations/{participation['id']}/entries", {"book_id": book["id"], "note": note})


def board(client, headers, p):
    return items(get(client, headers, f"programs/{p['id']}/leaderboard"))


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def process(client, lib):
    return ok(post(client, lib, "programs/process"))


def test_t_rdp_01_a(client, librarian, branch_a):
    """T-RDP-01-a (LIB-RDP-01): 201 draft; audience all; description empty"""
    p = program(client, librarian, branch_a, name="Kasım Okuma Şenliği", goal_books=5, max_participants=50, reward_waiver="20.00")
    keys = ("name", "branch_id", "audience", "starts_on", "ends_on", "goal_books", "max_participants", "reward_waiver", "status", "description", "published_at")
    assert tuple(p[k] for k in keys) == ("Kasım Okuma Şenliği", branch_a["id"], "all", MON, "2026-11-30", 5, 50, "20.00", "draft", "", None)


def test_t_rdp_01_c(client, librarian):
    """T-RDP-01-c (LIB-RDP-01): 201 each"""
    program(client, librarian, ends_on="2026-11-15")
    program(client, librarian, ends_on="2027-03-02")


def test_t_rdp_03_a(client, librarian):
    """T-RDP-03-a (LIB-RDP-03): 200 published with published_at; INVALID_PROGRAM_STATUS; PROGRAM_ENDED"""
    p = program(client, librarian)
    out = ok(post(client, librarian, f"programs/{p['id']}/publish"))
    assert out["status"] == "published" and same(out["published_at"], MON, 9)
    err(post(client, librarian, f"programs/{p['id']}/publish"), 409, "INVALID_PROGRAM_STATUS")
    old = program(client, librarian, starts_on="2026-10-01", ends_on="2026-10-31")
    err(post(client, librarian, f"programs/{old['id']}/publish"), 409, "PROGRAM_ENDED")


def test_t_rdp_05_a(client, clock, librarian, branch_a):
    """T-RDP-05-a (LIB-RDP-05): {closed 1, participants_completed 1, participants_not_completed 1}; program closed with closed_at"""
    p = published(client, librarian, goal_books=1)
    pa, _, _ = joined(client, librarian, branch_a, p)
    joined(client, librarian, branch_a, p)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    at(clock, "2026-12-01")
    out = process(client, librarian)
    assert (out["closed"], out["participants_completed"], out["participants_not_completed"]) == (1, 1, 1)
    q = get(client, librarian, f"programs/{p['id']}")
    assert q["status"] == "closed" and same(q["closed_at"], "2026-12-01", 9)


def test_t_rdp_07_a(client, librarian, branch_a):
    """T-RDP-07-a (LIB-RDP-07): M: [P1, P3] with my_participation only on P3, P3 participants 1 and free_places 9; staff: [P1]; 404"""
    p1 = published(client, librarian)
    p2 = program(client, librarian)
    p3 = published(client, librarian, starts_on="2026-11-16", ends_on="2026-12-15", max_participants=10)
    part3, m, h = joined(client, librarian, branch_a, p3)
    rows = items(get(client, h, "programs"))
    assert [r["id"] for r in rows] == [p1["id"], p3["id"]]
    assert (rows[0]["my_participation"], rows[1]["my_participation"]["id"], rows[1]["participants"], rows[1]["free_places"]) == (None, part3["id"], 1, 9)
    assert [r["id"] for r in items(get(client, librarian, "programs", running="true"))] == [p1["id"]]
    assert client.get(f"/api/v1/programs/{p2['id']}", headers=h).status_code == 404


def test_t_rdp_09_a(client, librarian):
    """T-RDP-09-a (LIB-RDP-09): Drafts 'Kitap Kurdu (copy)' and 'Kitap Kurdu (copy 2)', 2027-01-04 – 2027-02-01, the same goal and featured book"""
    p = published(client, librarian, name="Kitap Kurdu", goal_books=4)
    b = create_book(client, librarian)
    ok(client.put(f"/api/v1/programs/{p['id']}/books", headers=librarian, json={"book_ids": [b["id"]]}))
    c1 = ok(post(client, librarian, f"programs/{p['id']}/copy", {"starts_on": "2027-01-04"}), 201)
    c2 = ok(post(client, librarian, f"programs/{p['id']}/copy", {"starts_on": "2027-01-04"}), 201)
    assert [(c["name"], c["status"], c["starts_on"], c["ends_on"], c["goal_books"]) for c in (c1, c2)] == [
        ("Kitap Kurdu (copy)", "draft", "2027-01-04", "2027-02-01", 4), ("Kitap Kurdu (copy 2)", "draft", "2027-01-04", "2027-02-01", 4)]
    assert [x["id"] for x in items(get(client, librarian, f"programs/{c1['id']}/books"))] == [b["id"]]


def test_t_rdp_11_a(client, clock, librarian, branch_a):
    """T-RDP-11-a (LIB-RDP-11): PROGRAM_NOT_OPEN; PROGRAM_ENDED; MEMBER_PASSIVE; PROGRAM_NOT_FOR_TYPE; ALREADY_JOINED"""
    h = mh(client, member(client, librarian, branch_a))
    err(try_join(client, h, program(client, librarian)), 409, "PROGRAM_NOT_OPEN")
    short = published(client, librarian, ends_on="2026-11-15")
    p = published(client, librarian, ends_on="2026-12-15")
    stu = published(client, librarian, audience="students")
    pm = member(client, librarian, branch_a)
    deactivate_member(client, librarian, pm["id"])
    err(try_join(client, mh(client, pm), p), 409, "MEMBER_PASSIVE")
    err(try_join(client, mh(client, member(client, librarian, branch_a, membership_type="academic")), stu), 409, "PROGRAM_NOT_FOR_TYPE")
    ok(try_join(client, h, p), 201)
    err(try_join(client, h, p), 409, "ALREADY_JOINED")
    at(clock, "2026-11-16")
    err(try_join(client, h, short), 409, "PROGRAM_ENDED")


def test_t_rdp_11_c(client, clock, librarian, branch_a):
    """T-RDP-11-c (LIB-RDP-11): 409 MEMBERSHIP_EXPIRED"""
    m = member(client, librarian, branch_a)
    p = published(client, librarian, starts_on="2027-10-15", ends_on="2027-12-01")
    at(clock, "2027-11-02")
    err(try_join(client, mh(client, m), p), 409, "MEMBERSHIP_EXPIRED")


def test_t_rdp_13_a(client, librarian, branch_a):
    """T-RDP-13-a (LIB-RDP-13): 200 left with member_request; 409 PARTICIPATION_NOT_ACTIVE; 201 with the same participation id, active and the entry kept"""
    p = published(client, librarian, goal_books=5)
    pa, m, h = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    out = ok(post(client, h, f"programs/{p['id']}/leave"))
    assert (out["status"], out["leave_reason"]) == ("left", "member_request")
    err(post(client, h, f"programs/{p['id']}/leave"), 409, "PARTICIPATION_NOT_ACTIVE")
    again = ok(try_join(client, h, p), 201)
    assert (again["id"], again["status"], again["books"], again["leave_reason"]) == (pa["id"], "active", 1, None)


def test_t_rdp_15_a(client, clock, librarian, branch_a):
    """T-RDP-15-a (LIB-RDP-15): [P2, P1] with program_name, goal_books, books; P1 rank 1, P2 rank null"""
    p1 = published(client, librarian, name="Birinci")
    pa, m, h = joined(client, librarian, branch_a, p1)
    read(client, librarian, m, branch_a)
    at(clock, MON, 10)
    p2 = published(client, librarian, name="İkinci")
    ok(try_join(client, h, p2), 201)
    rows = items(get(client, h, f"members/{m['id']}/programs"))
    assert [(r["program_id"], r["program_name"], r["goal_books"], r["books"], r["rank"]) for r in rows] == [(p2["id"], "İkinci", 2, 0, None), (p1["id"], "Birinci", 2, 1, 1)]


def test_t_rdp_17_a(client, clock, librarian, branch_a, branch_b):
    """T-RDP-17-a (LIB-RDP-17): Entries: X 10, the late book 5; nothing else (books 2, points 15)"""
    p = published(client, librarian, branch_a, goal_books=10)
    pa, m, _ = joined(client, librarian, branch_a, p)
    x, _ = read(client, librarian, m, branch_a)
    read(client, librarian, m, branch_a, book=x)
    _, late_cp = book_with_copy(client, librarian, branch_a)
    late = lend(client, librarian, m["id"], late_cp["id"])
    read(client, librarian, m, branch_b)
    _, lost_cp = book_with_copy(client, librarian, branch_a)
    report_lost(client, librarian, lend(client, librarian, m["id"], lost_cp["id"])["id"])
    _, after_cp = book_with_copy(client, librarian, branch_a)
    after = lend(client, librarian, m["id"], after_cp["id"])
    at(clock, "2026-11-17")
    return_loan(client, librarian, late["id"], branch_id=branch_a["id"])
    at(clock, "2026-12-01")
    return_loan(client, librarian, after["id"], branch_id=branch_a["id"])
    assert sorted(e["points"] for e in entries(client, librarian, pa)) == [5, 10]
    out = part(client, librarian, pa)
    assert (out["books"], out["points"]) == (2, 15)


def test_t_rdp_19_a(client, librarian, branch_a):
    """T-RDP-19-a (LIB-RDP-19): 201 manual 10 points; BOOK_ALREADY_COUNTED; MANUAL_ENTRY_LIMIT with details.limit 3; 422; PROGRAM_NOT_RUNNING; PARTICIPATION_NOT_ACTIVE"""
    p = published(client, librarian, goal_books=10)
    pa, _, h = joined(client, librarian, branch_a, p)
    x = create_book(client, librarian)
    e = ok(manual(client, librarian, pa, x, "Kendi kitabı"), 201)
    assert (e["source"], e["points"], e["book_id"], e["note"], e["on"]) == ("manual", 10, x["id"], "Kendi kitabı", MON)
    err(manual(client, librarian, pa, x), 409, "BOOK_ALREADY_COUNTED")
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert err(manual(client, librarian, pa, create_book(client, librarian)), 409, "MANUAL_ENTRY_LIMIT")["details"]["limit"] == 3
    assert manual(client, librarian, pa, {"id": 999999}).status_code == 422
    later = published(client, librarian, starts_on="2026-11-16", ends_on="2026-12-15")
    pl, _, _ = joined(client, librarian, branch_a, later)
    err(manual(client, librarian, pl, create_book(client, librarian)), 409, "PROGRAM_NOT_RUNNING")
    ok(post(client, h, f"programs/{p['id']}/leave"))
    err(manual(client, librarian, pa, create_book(client, librarian)), 409, "PARTICIPATION_NOT_ACTIVE")


def test_t_rdp_21_a(client, clock, admin, librarian, branch_a):
    """T-RDP-21-a (LIB-RDP-21): One event entry with event_id, 15 points; books 0"""
    p = published(client, librarian)
    pa, m, _ = joined(client, librarian, branch_a, p)
    u = ok(post(client, admin, "users", {"email": "rdp.staff@library.local", "full_name": "Etkinlik Görevlisi", "role": "librarian", "password": "Staff12345"}), 201)
    sid = ok(post(client, admin, "staff", {"user_id": u["id"], "home_branch_id": branch_a["id"], "employment": "full_time", "started_on": "2020-01-01"}), 201)["id"]
    ok(post(client, admin, "shifts", {"staff_id": sid, "branch_id": branch_a["id"], "date": "2026-11-04", "start_time": "08:00", "end_time": "18:00"}), 201)
    ev = ok(post(client, librarian, "events", {"title": "Söyleşi", "kind": "talk", "branch_id": branch_a["id"], "date": "2026-11-04", "start_time": "14:00", "end_time": "16:00", "capacity": 10, "staff_id": sid}), 201)
    ok(post(client, librarian, f"events/{ev['id']}/publish"))
    r = ok(post(client, librarian, f"events/{ev['id']}/registrations", {"member_id": m["id"]}), 201)
    at(clock, "2026-11-04", 13, 45)
    ok(post(client, librarian, f"event-registrations/{r['id']}/check-in"))
    es = entries(client, librarian, pa)
    assert [(e["source"], e["event_id"], e["points"], e["book_id"]) for e in es] == [("event", ev["id"], 15, None)]
    out = part(client, librarian, pa)
    assert (out["points"], out["books"]) == (15, 0)


def test_t_rdp_23_a(client, librarian, branch_a):
    """T-RDP-23-a (LIB-RDP-23): Points 15, 15, 10"""
    p = published(client, librarian, goal_books=10)
    f, g = create_book(client, librarian), create_book(client, librarian)
    ok(client.put(f"/api/v1/programs/{p['id']}/books", headers=librarian, json={"book_ids": [f["id"], g["id"]]}))
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a, book=f)
    ok(manual(client, librarian, pa, g), 201)
    read(client, librarian, m, branch_a)
    assert [e["points"] for e in entries(client, librarian, pa)] == [15, 15, 10]


def test_t_rdp_25_a(client, clock, librarian, branch_a):
    """T-RDP-25-a (LIB-RDP-25): One bonus, added with the 2026-11-17 entry"""
    p = published(client, librarian, goal_books=10)
    pa, m, _ = joined(client, librarian, branch_a, p)
    for day in ("2026-11-03", "2026-11-05", "2026-11-10"):
        at(clock, day)
        read(client, librarian, m, branch_a)
    assert [e for e in entries(client, librarian, pa) if e["source"] == "bonus"] == []
    for day in ("2026-11-17", "2026-11-24"):
        at(clock, day)
        read(client, librarian, m, branch_a)
    bonus = [e for e in entries(client, librarian, pa) if e["source"] == "bonus"]
    assert len(bonus) == 1 and bonus[0]["on"] == "2026-11-17"


def test_t_rdp_27_a(client, librarian, branch_a):
    """T-RDP-27-a (LIB-RDP-27): Member: [{1, Ayşe Y.}, {2, Anonymous}] without member_id; staff with member_id; 404"""
    p = published(client, librarian, goal_books=5)
    pa, a, _ = joined(client, librarian, branch_a, p, full_name="Ayşe Nur Yılmaz")
    m = member(client, librarian, branch_a)
    ok(try_join(client, mh(client, m), p, public=False), 201)
    read(client, librarian, a, branch_a); read(client, librarian, a, branch_a)
    read(client, librarian, m, branch_a)
    h = mh(client, member(client, librarian, branch_a))
    rows = board(client, h, p)
    assert [(r["rank"], r["name"], r["points"], r["books"]) for r in rows] == [(1, "Ayşe Y.", 20, 2), (2, "Anonymous", 10, 1)]
    assert all("member_id" not in r or r["member_id"] is None for r in rows)
    assert [r["member_id"] for r in board(client, librarian, p)] == [a["id"], m["id"]]
    d = program(client, librarian)
    assert client.get(f"/api/v1/programs/{d['id']}/leaderboard", headers=h).status_code == 404


def test_t_rdp_29_a(client, librarian, branch_a):
    """T-RDP-29-a (LIB-RDP-29): Still completed, level bronze, books 1"""
    p = published(client, librarian)
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    e = ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert part(client, librarian, pa)["status"] == "completed"
    assert client.delete(f"/api/v1/program-entries/{e['id']}", headers=librarian).status_code == 204
    out = part(client, librarian, pa)
    assert (out["status"], out["level"], out["books"]) == ("completed", "bronze", 1)


def test_t_rdp_31_a(client, librarian, branch_a):
    """T-RDP-31-a (LIB-RDP-31): none, bronze, bronze, silver, silver, gold"""
    p = published(client, librarian, goal_books=2)
    pa, m, _ = joined(client, librarian, branch_a, p)
    levels = []
    for _ in range(6):
        read(client, librarian, m, branch_a)
        levels.append(part(client, librarian, pa)["level"])
    assert levels == ["none", "bronze", "bronze", "silver", "silver", "gold"]


def test_t_rdp_33_a(client, librarian, branch_a):
    """T-RDP-33-a (LIB-RDP-33): reward_waived 0.00"""
    p = published(client, librarian, goal_books=1, reward_waiver="20.00")
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    out = part(client, librarian, pa)
    assert (out["status"], out["reward_waived"]) == ("completed", "0.00")


def test_t_rdp_35_a(client, clock, librarian, branch_a):
    """T-RDP-35-a (LIB-RDP-35): reminders 1; the active member gets one program_ending notification, the completed none"""
    p = published(client, librarian, goal_books=1)
    _, a, _ = joined(client, librarian, branch_a, p)
    _, b, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, b, branch_a)
    at(clock, "2026-11-27")
    assert process(client, librarian)["reminders"] == 1
    assert (len(notes(client, librarian, a["id"], "program_ending")), len(notes(client, librarian, b["id"], "program_ending"))) == (1, 0)


def test_t_rdp_37_a(client, librarian, branch_a):
    """T-RDP-37-a (LIB-RDP-37): 409 PARTICIPATION_NOT_ACTIVE; B completed with books 2"""
    p = published(client, librarian)
    _, a, ah = joined(client, librarian, branch_a, p)
    read(client, librarian, a, branch_a); read(client, librarian, a, branch_a)
    err(post(client, ah, f"programs/{p['id']}/leave"), 409, "PARTICIPATION_NOT_ACTIVE")
    pb, b, bh = joined(client, librarian, branch_a, p)
    read(client, librarian, b, branch_a)
    ok(post(client, bh, f"programs/{p['id']}/leave"))
    ok(try_join(client, bh, p), 201)
    read(client, librarian, b, branch_a)
    out = part(client, librarian, pb)
    assert (out["status"], out["books"]) == ("completed", 2)


def test_t_rdp_39_a(client, librarian, branch_a):
    """T-RDP-39-a (LIB-RDP-39): {active 1, completed_this_year 1, points_this_year 20}; zeros"""
    p1 = published(client, librarian, goal_books=1)
    p2 = published(client, librarian, goal_books=5)
    _, m, h = joined(client, librarian, branch_a, p1)
    ok(try_join(client, h, p2), 201)
    read(client, librarian, m, branch_a)
    assert get(client, librarian, f"members/{m['id']}/summary")["programs"] == {"active": 1, "completed_this_year": 1, "points_this_year": 20}
    other = member(client, librarian, branch_a)
    assert get(client, librarian, f"members/{other['id']}/summary")["programs"] == {"active": 0, "completed_this_year": 0, "points_this_year": 0}


def test_t_rdp_41_a(client, librarian, branch_a, branch_b):
    """T-RDP-41-a (LIB-RDP-41): Only the first counts (books 1)"""
    p = published(client, librarian, branch_a, goal_books=5)
    pa, m, _ = joined(client, librarian, branch_a, p)
    _, ca = book_with_copy(client, librarian, branch_a)
    _, cb = book_with_copy(client, librarian, branch_b)
    la, lb = lend(client, librarian, m["id"], ca["id"]), lend(client, librarian, m["id"], cb["id"])
    return_loan(client, librarian, la["id"], branch_id=branch_b["id"])
    return_loan(client, librarian, lb["id"], branch_id=branch_a["id"])
    assert [e["loan_id"] for e in entries(client, librarian, pa)] == [la["id"]]


def test_t_rdp_43_a(client, admin, librarian, branch_a):
    """T-RDP-43-a (LIB-RDP-43): One entry per event (2 for program_created and program_joined)"""
    p = program(client, librarian, goal_books=1)
    ok(client.patch(f"/api/v1/programs/{p['id']}", headers=librarian, json={"description": "Açıklama"}))
    ok(client.put(f"/api/v1/programs/{p['id']}/books", headers=librarian, json={"book_ids": []}))
    ok(post(client, librarian, f"programs/{p['id']}/publish"))
    pa, m, _ = joined(client, librarian, branch_a, p)
    _, _, bh = joined(client, librarian, branch_a, p)
    ok(post(client, bh, f"programs/{p['id']}/leave"))
    e = ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    other = program(client, librarian)
    ok(post(client, librarian, f"programs/{other['id']}/cancel"))
    ok(post(client, librarian, "programs/process"))
    counts = {"program_created": 2, "program_updated": 1, "program_books_set": 1, "program_published": 1, "program_joined": 2, "program_left": 1,
              "program_entry_added": 1, "program_completed": 1, "program_cancelled": 1, "programs_processed": 1}
    for name, n in counts.items():
        assert len(items(get(client, admin, "audit-log", event=name))) == n, name
    assert e["source"] == "manual"


def test_t_rdp_44_a(client, librarian, branch_a):
    """T-RDP-44-a (LIB-RDP-44): One row: {participants 3, completed 2, completion_rate 66.7, books_counted 3, points 30, rewards_waived 0.00}, top books X (2), Y (1)"""
    p = published(client, librarian, goal_books=1, reward_waiver="20.00")
    program(client, librarian)
    _, a, _ = joined(client, librarian, branch_a, p)
    _, b, _ = joined(client, librarian, branch_a, p)
    joined(client, librarian, branch_a, p)
    x, _ = read(client, librarian, a, branch_a)
    read(client, librarian, b, branch_a, book=x)
    y, _ = read(client, librarian, b, branch_a)
    rows = items(get(client, librarian, "reports/programs", **{"from": MON, "to": "2026-11-30"}))
    keys = ("program_id", "participants", "completed", "completion_rate", "books_counted", "points", "rewards_waived")
    assert [tuple(r[k] for k in keys) for r in rows] == [(p["id"], 3, 2, "66.7", 3, 30, "0.00")]
    assert [(t["book_id"], t["count"]) for t in rows[0]["top_books"]] == [(x["id"], 2), (y["id"], 1)]


def test_t_rdp_45_a(client, admin, librarian, branch_a):
    """T-RDP-45-a (LIB-RDP-45): The export has exactly the keys of 22.1"""
    _, m, _ = joined(client, librarian, branch_a, published(client, librarian))
    read(client, librarian, m, branch_a)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}


def test_t_rdp_47_a(client, librarian, branch_a):
    """T-RDP-47-a (LIB-RDP-47): status=active: A (rank 1), B (rank null) with full_name, public, reward_waived; status=left: C"""
    p = published(client, librarian, goal_books=5)
    pa, a, _ = joined(client, librarian, branch_a, p)
    pb, b, _ = joined(client, librarian, branch_a, p)
    pc, c, ch = joined(client, librarian, branch_a, p)
    read(client, librarian, a, branch_a); read(client, librarian, a, branch_a)
    ok(post(client, ch, f"programs/{p['id']}/leave"))
    rows = items(get(client, librarian, f"programs/{p['id']}/participants", status="active"))
    assert [(r["member_id"], r["rank"], r["full_name"], r["public"], r["reward_waived"]) for r in rows] == [(a["id"], 1, a["full_name"], True, "0.00"), (b["id"], None, b["full_name"], True, "0.00")]
    assert [r["member_id"] for r in items(get(client, librarian, f"programs/{p['id']}/participants", status="left"))] == [c["id"]]
