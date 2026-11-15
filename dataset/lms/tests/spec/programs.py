MODULE = "programs"
TITLE = "module 26 (Reading programs)"

HEADER = '''
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
    """The participation as listed by LIB-RDP-15 (matched by ``program_id``: one participation per member and program)."""
    rows = items(get(client, headers, f"members/{participation['member_id']}/programs"))
    return [x for x in rows if x["program_id"] == participation["program_id"]][0]


def row(client, lib, participation):
    """The participation in the staff participants list (LIB-RDP-47), which shows `reward_waived`."""
    rows = items(get(client, lib, f"programs/{participation['program_id']}/participants"))
    return [x for x in rows if x["member_id"] == participation["member_id"]][0]


def book_ids(rows):
    """Book ids of a featured-books list (LIB-RDP-08 names no field; ``book_id`` as in LIB-RDP-44, else ``id``)."""
    return [r["book_id"] if "book_id" in r else r["id"] for r in rows]


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
'''


CASES = [
    # ---------------------------------------------------------------- programs
    dict(id="T-RDP-01-a", req="LIB-RDP-01", type="Normal", input="Librarian creates a program for branch A, 2026-11-02 – 2026-11-30, goal 5, max 50, reward 20.00, without description and audience", expected="201 `draft`; `audience` `all`; `description` empty", code='''
def TEST(client, librarian, branch_a):
    p = program(client, librarian, branch_a, name="Kasım Okuma Şenliği", goal_books=5, max_participants=50, reward_waiver="20.00")
    keys = ("name", "branch_id", "audience", "starts_on", "ends_on", "goal_books", "max_participants", "reward_waiver", "status", "description", "published_at")
    assert tuple(p[k] for k in keys) == ("Kasım Okuma Şenliği", branch_a["id"], "all", MON, "2026-11-30", 5, 50, "20.00", "draft", "", None)
'''),
    dict(id="T-RDP-01-b", req="LIB-RDP-01", type="Error", input="12 and 121 days long; goal 0; reward 50.01; audience `everyone`; a duplicate name (other case); an inactive branch; a member creates", expected="`422` five times; `409 CONFLICT` with `details.field` `name`; `409 BRANCH_INACTIVE`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    for fields in (dict(ends_on="2026-11-14"), dict(ends_on="2027-03-03"), dict(goal_books=0), dict(reward_waiver="50.01"), dict(audience="everyone")):
        assert try_program(client, librarian, **fields).status_code == 422, fields
    program(client, librarian, name="Kış Okumaları")
    assert err(try_program(client, librarian, name="KIŞ OKUMALARI"), 409, "CONFLICT")["details"]["field"] == "name"
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_program(client, librarian, qq), 409, "BRANCH_INACTIVE")
    assert try_program(client, mh(client, member(client, librarian, branch_a))).status_code == 403
'''),
    dict(id="T-RDP-01-c", req="LIB-RDP-01", type="Boundary", input="Programs 13 days (2026-11-02 – 2026-11-15) and 120 days (– 2027-03-02) long", expected="201 each", code='''
def TEST(client, librarian):
    program(client, librarian, ends_on="2026-11-15")
    program(client, librarian, ends_on="2027-03-02")
'''),
    dict(id="T-RDP-02-a", req="LIB-RDP-02", type="Error", input="Draft: change goal; published with 2 participants: description; goal; `max_participants` 1; a cancelled program changed", expected="200; 200; `409 PROGRAM_PUBLISHED`; `409 PARTICIPANTS_ABOVE_LIMIT` with `details.participants` 2; `409 INVALID_PROGRAM_STATUS`", code='''
def TEST(client, librarian, branch_a):
    p = program(client, librarian)
    url = f"/api/v1/programs/{p['id']}"
    assert ok(client.patch(url, headers=librarian, json={"goal_books": 3}))["goal_books"] == 3
    ok(post(client, librarian, f"programs/{p['id']}/publish"))
    joined(client, librarian, branch_a, p); joined(client, librarian, branch_a, p)
    assert ok(client.patch(url, headers=librarian, json={"description": "Herkese açık"}))["description"] == "Herkese açık"
    err(client.patch(url, headers=librarian, json={"goal_books": 4}), 409, "PROGRAM_PUBLISHED")
    assert err(client.patch(url, headers=librarian, json={"max_participants": 1}), 409, "PARTICIPANTS_ABOVE_LIMIT")["details"]["participants"] == 2
    ok(post(client, librarian, f"programs/{p['id']}/cancel"))
    assert err(client.patch(url, headers=librarian, json={"description": "X"}), 409, "INVALID_PROGRAM_STATUS")["details"]["status"] == "cancelled"
'''),
    dict(id="T-RDP-03-a", req="LIB-RDP-03", type="Error", input="Publish a draft; publish again; publish a draft that ended on 2026-10-31", expected="200 `published` with `published_at`; `INVALID_PROGRAM_STATUS`; `PROGRAM_ENDED`", code='''
def TEST(client, librarian):
    p = program(client, librarian)
    out = ok(post(client, librarian, f"programs/{p['id']}/publish"))
    assert out["status"] == "published" and same(out["published_at"], MON, 9)
    err(post(client, librarian, f"programs/{p['id']}/publish"), 409, "INVALID_PROGRAM_STATUS")
    old = program(client, librarian, starts_on="2026-10-01", ends_on="2026-10-31")
    err(post(client, librarian, f"programs/{old['id']}/publish"), 409, "PROGRAM_ENDED")
'''),
    dict(id="T-RDP-04-a", req="LIB-RDP-04", type="Normal", input="Published program (goal 1) with an active participant A and a completed participant B is cancelled; cancelled again", expected="200 `cancelled`; A `left` and one `program_cancelled` notification; B `completed`; `409 INVALID_PROGRAM_STATUS`", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=1)
    pa, a, _ = joined(client, librarian, branch_a, p)
    pb, b, _ = joined(client, librarian, branch_a, p)
    ok(manual(client, librarian, pb, create_book(client, librarian)), 201)
    assert ok(post(client, librarian, f"programs/{p['id']}/cancel"))["status"] == "cancelled"
    oa, ob = part(client, librarian, pa), part(client, librarian, pb)
    assert (oa["status"], ob["status"]) == ("left", "completed")
    assert (len(notes(client, librarian, a["id"], "program_cancelled")), len(notes(client, librarian, b["id"], "program_cancelled"))) == (1, 0)
    err(post(client, librarian, f"programs/{p['id']}/cancel"), 409, "INVALID_PROGRAM_STATUS")
'''),
    dict(id="T-RDP-05-a", req="LIB-RDP-05", type="Normal", input="Program (goal 1) ending 2026-11-30 with one completed and one active participant; process on 2026-12-01", expected="`{closed 1, participants_completed 1, participants_not_completed 1}`; program `closed` with `closed_at`", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian, goal_books=1)
    pa, _, _ = joined(client, librarian, branch_a, p)
    joined(client, librarian, branch_a, p)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    at(clock, "2026-12-01")
    out = process(client, librarian)
    assert (out["closed"], out["participants_completed"], out["participants_not_completed"]) == (1, 1, 1)
    q = get(client, librarian, f"programs/{p['id']}")
    assert q["status"] == "closed" and same(q["closed_at"], "2026-12-01", 9)
'''),
    dict(id="T-RDP-06-a", req="LIB-RDP-06", type="Boundary", input="Program 2026-11-02 – 2026-11-30; process on 2026-11-30 and on 2026-12-01", expected="`closed` 0; then 1", code='''
def TEST(client, clock, librarian):
    published(client, librarian)
    at(clock, "2026-11-30", 23, 59)
    assert process(client, librarian)["closed"] == 0
    at(clock, "2026-12-01", 0, 0)
    assert process(client, librarian)["closed"] == 1
'''),
    dict(id="T-RDP-07-a", req="LIB-RDP-07", type="Normal", input="Programs P1 (published, starts Mon), P2 (draft), P3 (published, starts 2026-11-16) with max 10 and one participant M; M lists; staff list `running=true`; M reads P2", expected="M: [P1, P3] with `my_participation` only on P3, P3 `participants` 1 and `free_places` 9; staff: [P1]; `404`", code='''
def TEST(client, librarian, branch_a):
    p1 = published(client, librarian)
    p2 = program(client, librarian)
    p3 = published(client, librarian, starts_on="2026-11-16", ends_on="2026-12-15", max_participants=10)
    part3, m, h = joined(client, librarian, branch_a, p3)
    rows = items(get(client, h, "programs"))
    assert [r["id"] for r in rows] == [p1["id"], p3["id"]]
    assert (rows[0]["my_participation"], rows[1]["my_participation"]["id"], rows[1]["participants"], rows[1]["free_places"]) == (None, part3["id"], 1, 9)
    assert [r["id"] for r in items(get(client, librarian, "programs", running="true"))] == [p1["id"]]
    assert client.get(f"/api/v1/programs/{p2['id']}", headers=h).status_code == 404
'''),
    dict(id="T-RDP-08-a", req="LIB-RDP-08", type="Error", input="Featured books set to [Zeki, Ayna]; read by a member; 31 books; set on a closed program", expected="200; ordered Ayna, Zeki; `422`; `409 INVALID_PROGRAM_STATUS`", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian)
    z, a = create_book(client, librarian, title="Zeki"), create_book(client, librarian, title="Ayna")
    url = f"/api/v1/programs/{p['id']}/books"
    ok(client.put(url, headers=librarian, json={"book_ids": [z["id"], a["id"]]}))
    h = mh(client, member(client, librarian, branch_a))
    assert book_ids(items(ok(client.get(url, headers=h)))) == [a["id"], z["id"]]
    many = [create_book(client, librarian)["id"] for _ in range(31)]
    assert client.put(url, headers=librarian, json={"book_ids": many}).status_code == 422
    at(clock, "2026-12-01")
    process(client, librarian)
    err(client.put(url, headers=librarian, json={"book_ids": []}), 409, "INVALID_PROGRAM_STATUS")
'''),
    dict(id="T-RDP-09-a", req="LIB-RDP-09", type="Normal", input="Program \"Kitap Kurdu\" 2026-11-02 – 2026-11-30 with a featured book copied twice with `starts_on` 2027-01-04", expected="Drafts \"Kitap Kurdu (copy)\" and \"Kitap Kurdu (copy 2)\", 2027-01-04 – 2027-02-01, the same goal and featured book", code='''
def TEST(client, librarian):
    p = published(client, librarian, name="Kitap Kurdu", goal_books=4)
    b = create_book(client, librarian)
    ok(client.put(f"/api/v1/programs/{p['id']}/books", headers=librarian, json={"book_ids": [b["id"]]}))
    c1 = ok(post(client, librarian, f"programs/{p['id']}/copy", {"starts_on": "2027-01-04"}), 201)
    c2 = ok(post(client, librarian, f"programs/{p['id']}/copy", {"starts_on": "2027-01-04"}), 201)
    assert [(c["name"], c["status"], c["starts_on"], c["ends_on"], c["goal_books"]) for c in (c1, c2)] == [
        ("Kitap Kurdu (copy)", "draft", "2027-01-04", "2027-02-01", 4), ("Kitap Kurdu (copy 2)", "draft", "2027-01-04", "2027-02-01", 4)]
    assert book_ids(items(get(client, librarian, f"programs/{c1['id']}/books"))) == [b["id"]]
'''),
    # ---------------------------------------------------------------- joining
    dict(id="T-RDP-10-a", req="LIB-RDP-10", type="Normal", input="A student joins with `public` false; a member sends `member_id`; staff omit it; staff join a member", expected="201 `active`, `joined_at`, `points` 0, `books` 0, `level` `none`, `public` false; `422`; `422`; 201", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian)
    m = member(client, librarian, branch_a)
    out = ok(try_join(client, mh(client, m), p, public=False), 201)
    assert (out["member_id"], out["status"], out["points"], out["books"], out["level"], out["public"]) == (m["id"], "active", 0, 0, "none", False) and same(out["joined_at"], MON, 9)
    other = member(client, librarian, branch_a)
    assert try_join(client, mh(client, other), p, member_id=other["id"]).status_code == 422
    assert try_join(client, librarian, p).status_code == 422
    assert ok(try_join(client, librarian, p, member_id=other["id"]), 201)["member_id"] == other["id"]
'''),
    dict(id="T-RDP-11-a", req="LIB-RDP-11", type="Error", input="Join a draft; a program that ended yesterday; a passive member; an academic joins a `students` program; join twice", expected="`PROGRAM_NOT_OPEN`; `PROGRAM_ENDED`; `MEMBER_PASSIVE`; `PROGRAM_NOT_FOR_TYPE`; `ALREADY_JOINED`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-RDP-11-b", req="LIB-RDP-11", type="Boundary", input="Program with max 1 and one participant; a member with debt 50.00; a member already in 3 active programs joins a fourth", expected="`PROGRAM_FULL`; `MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` 50.00; `PROGRAM_LIMIT_REACHED` with `details.limit` 3", code='''
def TEST(client, librarian, branch_a):
    full = published(client, librarian, max_participants=1)
    joined(client, librarian, branch_a, full)
    err(try_join(client, mh(client, member(client, librarian, branch_a)), full), 409, "PROGRAM_FULL")
    d = member(client, librarian, branch_a)
    _, cp = book_with_copy(client, librarian, branch_a)
    return_loan(client, librarian, lend(client, librarian, d["id"], cp["id"])["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="50.00")
    open_p = published(client, librarian)
    assert err(try_join(client, mh(client, d), open_p), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    h = mh(client, member(client, librarian, branch_a))
    for _ in range(3):
        ok(try_join(client, h, published(client, librarian)), 201)
    assert err(try_join(client, h, open_p), 409, "PROGRAM_LIMIT_REACHED")["details"]["limit"] == 3
'''),
    dict(id="T-RDP-11-c", req="LIB-RDP-11", type="Boundary", input="Student registered 2026-11-02 (valid until 2027-11-01); program 2027-10-15 – 2027-12-01; joins on 2027-11-02", expected="`409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, librarian, branch_a):
    m = member(client, librarian, branch_a)
    p = published(client, librarian, starts_on="2027-10-15", ends_on="2027-12-01")
    at(clock, "2027-11-02")
    err(try_join(client, mh(client, m), p), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-RDP-12-a", req="LIB-RDP-12", type="Normal", input="Program from 2026-11-09; M joins on Mon 11-02; returns a book on 11-02 and another on 11-10", expected="Only the 11-10 return counts (`books` 1)", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian, starts_on="2026-11-09", ends_on="2026-12-07")
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    at(clock, "2026-11-10")
    read(client, librarian, m, branch_a)
    assert part(client, librarian, pa)["books"] == 1
'''),
    dict(id="T-RDP-13-a", req="LIB-RDP-13", type="Normal", input="M with one entry leaves; leaves again; joins again", expected="200 `left` with `member_request`; `409 PARTICIPATION_NOT_ACTIVE`; 201 with the same participation id, `active` and the entry kept", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=5)
    pa, m, h = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    out = ok(post(client, h, f"programs/{p['id']}/leave"))
    assert (out["status"], out["leave_reason"]) == ("left", "member_request")
    err(post(client, h, f"programs/{p['id']}/leave"), 409, "PARTICIPATION_NOT_ACTIVE")
    again = ok(try_join(client, h, p), 201)
    assert (again["id"], again["status"], again["books"], again["leave_reason"]) == (pa["id"], "active", 1, None)
'''),
    dict(id="T-RDP-14-a", req="LIB-RDP-14", type="Error", input="M sets own participation `public` false; another member changes it", expected="200; `403`", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian)
    pa, _, h = joined(client, librarian, branch_a, p)
    url = f"/api/v1/participations/{pa['id']}"
    assert ok(client.patch(url, headers=h, json={"public": False}))["public"] is False
    assert client.patch(url, headers=mh(client, member(client, librarian, branch_a)), json={"public": True}).status_code == 403
'''),
    dict(id="T-RDP-15-a", req="LIB-RDP-15", type="Normal", input="M joins P1 (one book read) and later P2; M lists own programs", expected="[P2, P1] with `program_name`, `goal_books`, `books`; P1 `rank` 1, P2 `rank` null", code='''
def TEST(client, clock, librarian, branch_a):
    p1 = published(client, librarian, name="Birinci")
    pa, m, h = joined(client, librarian, branch_a, p1)
    read(client, librarian, m, branch_a)
    at(clock, MON, 10)
    p2 = published(client, librarian, name="İkinci")
    ok(try_join(client, h, p2), 201)
    rows = items(get(client, h, f"members/{m['id']}/programs"))
    assert [(r["program_id"], r["program_name"], r["goal_books"], r["books"], r["rank"]) for r in rows] == [(p2["id"], "İkinci", 2, 0, None), (p1["id"], "Birinci", 2, 1, 1)]
'''),
    # ---------------------------------------------------------------- entries
    dict(id="T-RDP-16-a", req="LIB-RDP-16", type="Normal", input="Participant returns a book on time on Mon", expected="One `loan` entry with `book_id`, `loan_id`, 10 points, `on` 2026-11-02; participation `points` 10, `books` 1", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian)
    pa, m, _ = joined(client, librarian, branch_a, p)
    b, loan = read(client, librarian, m, branch_a)
    es = entries(client, librarian, pa)
    assert [(e["source"], e["book_id"], e["loan_id"], e["points"], e["on"]) for e in es] == [("loan", b["id"], loan["id"], 10, MON)]
    out = part(client, librarian, pa)
    assert (out["points"], out["books"]) == (10, 1)
'''),
    dict(id="T-RDP-17-a", req="LIB-RDP-17", type="Normal", input="Program at A, goal 10: book X returned on time; X again; a loan from A returned 1 day late on 2026-11-17; a loan from B; a lost loan; a loan returned on 2026-12-01", expected="Entries: X 10, the late book 5; nothing else (`books` 2, `points` 15)", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    p = published(client, librarian, branch_a, goal_books=10)
    pa, m, _ = joined(client, librarian, branch_a, p)
    x, _ = read(client, librarian, m, branch_a)
    read(client, librarian, m, branch_a, book=x)
    _, late_cp = book_with_copy(client, librarian, branch_a)
    late = lend(client, librarian, m["id"], late_cp["id"])
    read(client, librarian, m, branch_b)
    _, after_cp = book_with_copy(client, librarian, branch_a)
    after = lend(client, librarian, m["id"], after_cp["id"])
    _, lost_cp = book_with_copy(client, librarian, branch_a)
    report_lost(client, librarian, lend(client, librarian, m["id"], lost_cp["id"])["id"])
    at(clock, "2026-11-17")
    return_loan(client, librarian, late["id"], branch_id=branch_a["id"])
    at(clock, "2026-12-01")
    return_loan(client, librarian, after["id"], branch_id=branch_a["id"])
    assert sorted(e["points"] for e in entries(client, librarian, pa)) == [5, 10]
    out = part(client, librarian, pa)
    assert (out["books"], out["points"]) == (2, 15)
'''),
    dict(id="T-RDP-18-a", req="LIB-RDP-18", type="Normal", input="M borrows a book on Mon 09:00, joins at 10:00 and returns the book at 11:00", expected="The return counts (`books` 1)", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian)
    m = member(client, librarian, branch_a)
    _, cp = book_with_copy(client, librarian, branch_a)
    loan = lend(client, librarian, m["id"], cp["id"])
    at(clock, MON, 10)
    pa = ok(try_join(client, mh(client, m), p), 201)
    at(clock, MON, 11)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert part(client, librarian, pa)["books"] == 1
'''),
    dict(id="T-RDP-19-a", req="LIB-RDP-19", type="Error", input="Manual entry of book X; X again; 3 manual entries then a fourth; an unknown book; a manual entry in a program starting 2026-11-16; for a participation that left", expected="201 `manual` 10 points; `BOOK_ALREADY_COUNTED`; `MANUAL_ENTRY_LIMIT` with `details.limit` 3; `422`; `PROGRAM_NOT_RUNNING`; `PARTICIPATION_NOT_ACTIVE`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-RDP-20-a", req="LIB-RDP-20", type="Error", input="Participation (goal 5) with a loan entry and a manual entry: remove the manual one; remove the loan one", expected="204 and `points` 10, `books` 1; `409 ENTRY_NOT_MANUAL`", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=5)
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    e = ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert client.delete(f"/api/v1/program-entries/{e['id']}", headers=librarian).status_code == 204
    out = part(client, librarian, pa)
    assert (out["points"], out["books"]) == (10, 1)
    loan_entry = [x for x in entries(client, librarian, pa) if x["source"] == "loan"][0]
    err(client.delete(f"/api/v1/program-entries/{loan_entry['id']}", headers=librarian), 409, "ENTRY_NOT_MANUAL")
'''),
    dict(id="T-RDP-21-a", req="LIB-RDP-21", type="Normal", input="Participant registered for an event on Wed 14:00 at A; checked in at 13:45; checked in elsewhere again not possible", expected="One `event` entry with `event_id`, 15 points; `books` 0", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-RDP-22-a", req="LIB-RDP-22", type="Normal", input="Entries: a loan (Mon 09:00) and a manual one (10:00); list; `source=manual`", expected="[loan, manual] with `book_title`; [manual]", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian, goal_books=5)
    pa, m, h = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    at(clock, MON, 10)
    ok(manual(client, librarian, pa, create_book(client, librarian, title="Ev Kitabı")), 201)
    rows = entries(client, h, pa)
    assert [(e["source"], e["book_title"]) for e in rows] == [("loan", "Okunan Kitap"), ("manual", "Ev Kitabı")]
    assert [e["source"] for e in entries(client, librarian, pa, source="manual")] == ["manual"]
'''),
    dict(id="T-RDP-23-a", req="LIB-RDP-23", type="Normal", input="Featured book F: returned on time; another featured book G added manually; a non-featured book returned on time", expected="Points 15, 15, 10", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=10)
    f, g = create_book(client, librarian), create_book(client, librarian)
    ok(client.put(f"/api/v1/programs/{p['id']}/books", headers=librarian, json={"book_ids": [f["id"], g["id"]]}))
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a, book=f)
    ok(manual(client, librarian, pa, g), 201)
    read(client, librarian, m, branch_a)
    assert [e["points"] for e in entries(client, librarian, pa)] == [15, 15, 10]
'''),
    dict(id="T-RDP-24-a", req="LIB-RDP-24", type="Normal", input="Book entries on 2026-11-03, 2026-11-10 and 2026-11-17 (goal 10)", expected="A `bonus` entry of 10 points after the third week; `points` 40", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian, goal_books=10)
    pa, m, _ = joined(client, librarian, branch_a, p)
    for day in ("2026-11-03", "2026-11-10", "2026-11-17"):
        at(clock, day)
        read(client, librarian, m, branch_a)
    assert [(e["source"], e["points"]) for e in entries(client, librarian, pa) if e["source"] == "bonus"] == [("bonus", 10)]
    assert part(client, librarian, pa)["points"] == 40
'''),
    dict(id="T-RDP-25-a", req="LIB-RDP-25", type="Boundary", input="Book entries on 2026-11-03, 2026-11-05, 2026-11-10 (no bonus yet), 2026-11-17 and 2026-11-24", expected="One bonus, added with the 2026-11-17 entry", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- ranking, completion, rewards
    dict(id="T-RDP-26-a", req="LIB-RDP-26", type="Normal", input="Goal 2: A 20 points (completed at 09:00), B 20 points (2 books at 10:00, completed later), C 10 points, D 0 points", expected="Ranks A 1, B 2, C 3, D null", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian)
    pa, a, _ = joined(client, librarian, branch_a, p)
    pb, b, _ = joined(client, librarian, branch_a, p)
    pc, c, _ = joined(client, librarian, branch_a, p)
    pd, _, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, a, branch_a); read(client, librarian, a, branch_a)
    at(clock, MON, 10)
    read(client, librarian, b, branch_a); read(client, librarian, b, branch_a)
    read(client, librarian, c, branch_a)
    rows = items(get(client, librarian, f"programs/{p['id']}/participants"))
    assert {r["member_id"]: r["rank"] for r in rows} == {a["id"]: 1, b["id"]: 2, c["id"]: 3, pd["member_id"]: None}
'''),
    dict(id="T-RDP-27-a", req="LIB-RDP-27", type="Normal", input="Participants \"Ayşe Nur Yılmaz\" (20 points) and a non-public one (10 points); a member and staff read the leaderboard; a member reads a draft's", expected="Member: [{1, Ayşe Y.}, {2, Anonymous}] without `member_id`; staff with `member_id`; `404`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-RDP-28-a", req="LIB-RDP-28", type="Normal", input="Goal 2: first book; second book at 10:00; a third book", expected="`active`; then `completed` with `completed_at` 10:00 and one `program_completed` notification with `program_id`; the third still counts (`books` 3)", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian)
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    assert part(client, librarian, pa)["status"] == "active"
    at(clock, MON, 10)
    read(client, librarian, m, branch_a)
    out = part(client, librarian, pa)
    assert (out["status"], out["level"]) == ("completed", "bronze")
    assert same(get(client, librarian, f"participations/{pa['id']}/certificate")["completed_at"], MON, 10)
    ns = notes(client, librarian, m["id"], "program_completed")
    assert len(ns) == 1 and ns[0]["program_id"] == p["id"]
    read(client, librarian, m, branch_a)
    assert part(client, librarian, pa)["books"] == 3
'''),
    dict(id="T-RDP-29-a", req="LIB-RDP-29", type="Normal", input="Goal 2 completed with a loan and a manual entry; the manual entry removed", expected="Still `completed`, `level` `bronze`, `books` 1", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian)
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    e = ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert part(client, librarian, pa)["status"] == "completed"
    assert client.delete(f"/api/v1/program-entries/{e['id']}", headers=librarian).status_code == 204
    out = part(client, librarian, pa)
    assert (out["status"], out["level"], out["books"]) == ("completed", "bronze", 1)
'''),
    dict(id="T-RDP-30-a", req="LIB-RDP-30", type="Normal", input="Goal 1: books 1, 2 and 3", expected="Levels bronze, silver, gold; two `program_level_reached` notifications", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=1)
    pa, m, _ = joined(client, librarian, branch_a, p)
    levels = []
    for _ in range(3):
        read(client, librarian, m, branch_a)
        levels.append(part(client, librarian, pa)["level"])
    assert levels == ["bronze", "silver", "gold"]
    assert len(notes(client, librarian, m["id"], "program_level_reached")) == 2
'''),
    dict(id="T-RDP-31-a", req="LIB-RDP-31", type="Boundary", input="Goal 2: books 1, 2, 3, 4, 5, 6", expected="none, bronze, bronze, silver, silver, gold", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=2)
    pa, m, _ = joined(client, librarian, branch_a, p)
    levels = []
    for _ in range(6):
        read(client, librarian, m, branch_a)
        levels.append(part(client, librarian, pa)["level"])
    assert levels == ["none", "bronze", "bronze", "silver", "silver", "gold"]
'''),
    dict(id="T-RDP-32-a", req="LIB-RDP-32", type="Normal", input="Student with open late fees 8.00 (11-20), 14.00 and 10.00 (both 11-25, in this order); joins a program with goal 1 and reward 20.00 on 11-25 and completes", expected="8.00 and 10.00 `waived`, 14.00 `open`; `reward_waived` 18.00", code='''
def TEST(client, clock, librarian, branch_a):
    m = member(client, librarian, branch_a)
    c1, c2 = book_with_copy(client, librarian, branch_a)[1], book_with_copy(client, librarian, branch_a)[1]
    l1, l2 = lend(client, librarian, m["id"], c1["id"]), lend(client, librarian, m["id"], c2["id"])
    at(clock, "2026-11-04")
    l3 = lend(client, librarian, m["id"], book_with_copy(client, librarian, branch_a)[1]["id"])
    at(clock, "2026-11-20")
    return_loan(client, librarian, l1["id"], branch_id=branch_a["id"])
    at(clock, "2026-11-25")
    return_loan(client, librarian, l2["id"], branch_id=branch_a["id"])
    return_loan(client, librarian, l3["id"], branch_id=branch_a["id"])
    assert [(f["amount"], f["status"]) for f in items(member_fees(client, librarian, m["id"]))] == [("8.00", "open"), ("14.00", "open"), ("10.00", "open")]
    p = published(client, librarian, starts_on="2026-11-25", ends_on="2026-12-24", goal_books=1, reward_waiver="20.00")
    pa = ok(try_join(client, mh(client, m), p), 201)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert [(f["amount"], f["status"]) for f in items(member_fees(client, librarian, m["id"]))] == [("8.00", "waived"), ("14.00", "open"), ("10.00", "waived")]
    assert row(client, librarian, pa)["reward_waived"] == "18.00"
'''),
    dict(id="T-RDP-33-a", req="LIB-RDP-33", type="Normal", input="Program with reward 20.00 completed by a member without fees", expected="`reward_waived` 0.00", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=1, reward_waiver="20.00")
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    out = row(client, librarian, pa)
    assert (out["status"], out["reward_waived"]) == ("completed", "0.00")
'''),
    dict(id="T-RDP-34-a", req="LIB-RDP-34", type="Error", input="Goal 1: B completes at 09:00, A at 10:00; certificates; an active participant's certificate; another member reads A's", expected="`RP-<id>-2` for A with name, level and books; `RP-<id>-1` for B; `409 NOT_COMPLETED`; `403`", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian, goal_books=1, name="Sertifikalı")
    pa, a, ah = joined(client, librarian, branch_a, p, full_name="Ali Can Demir")
    pb, b, _ = joined(client, librarian, branch_a, p)
    pc, _, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, b, branch_a)
    at(clock, MON, 10)
    read(client, librarian, a, branch_a)
    ca = get(client, ah, f"participations/{pa['id']}/certificate")
    assert (ca["certificate_no"], ca["member_name"], ca["program_name"], ca["level"], ca["books"]) == (f"RP-{p['id']}-2", "Ali Can Demir", "Sertifikalı", "bronze", 1)
    assert get(client, librarian, f"participations/{pb['id']}/certificate")["certificate_no"] == f"RP-{p['id']}-1"
    err(client.get(f"/api/v1/participations/{pc['id']}/certificate", headers=librarian), 409, "NOT_COMPLETED")
    assert client.get(f"/api/v1/participations/{pa['id']}/certificate", headers=mh(client, b)).status_code == 403
'''),
    dict(id="T-RDP-35-a", req="LIB-RDP-35", type="Normal", input="Program ending 2026-11-30 with one active and one completed participant (goal 1); process on 2026-11-27", expected="`reminders` 1; the active member gets one `program_ending` notification, the completed none", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian, goal_books=1)
    _, a, _ = joined(client, librarian, branch_a, p)
    _, b, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, b, branch_a)
    at(clock, "2026-11-27")
    assert process(client, librarian)["reminders"] == 1
    assert (len(notes(client, librarian, a["id"], "program_ending")), len(notes(client, librarian, b["id"], "program_ending"))) == (1, 0)
'''),
    dict(id="T-RDP-36-a", req="LIB-RDP-36", type="Boundary", input="Program ending 2026-11-30 with an active participant; process on 2026-11-26, 2026-11-27, again 2026-11-27 and 2026-11-28", expected="`reminders` 0, 1, 0, 0", code='''
def TEST(client, clock, librarian, branch_a):
    p = published(client, librarian)
    joined(client, librarian, branch_a, p)
    out = []
    for day in ("2026-11-26", "2026-11-27", "2026-11-27", "2026-11-28"):
        at(clock, day)
        out.append(process(client, librarian)["reminders"])
    assert out == [0, 1, 0, 0]
'''),
    dict(id="T-RDP-37-a", req="LIB-RDP-37", type="Normal", input="Goal 2: A completes and tries to leave; B reads one book, leaves, joins again and reads one more", expected="`409 PARTICIPATION_NOT_ACTIVE`; B `completed` with `books` 2", code='''
def TEST(client, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- effects
    dict(id="T-RDP-38-a", req="LIB-RDP-38", type="Normal", input="A member with an active participation is deactivated", expected="The participation `left`", code='''
def TEST(client, librarian, branch_a):
    pa, m, _ = joined(client, librarian, branch_a, published(client, librarian))
    deactivate_member(client, librarian, m["id"])
    assert part(client, librarian, pa)["status"] == "left"
'''),
    dict(id="T-RDP-39-a", req="LIB-RDP-39", type="Normal", input="Member in two programs, completed one (goal 1, 10 points) and active in the other (10 points from the same book); a member without programs", expected="`{active 1, completed_this_year 1, points_this_year 20}`; zeros", code='''
def TEST(client, librarian, branch_a):
    p1 = published(client, librarian, goal_books=1)
    p2 = published(client, librarian, goal_books=5)
    _, m, h = joined(client, librarian, branch_a, p1)
    ok(try_join(client, h, p2), 201)
    read(client, librarian, m, branch_a)
    assert get(client, librarian, f"members/{m['id']}/summary")["programs"] == {"active": 1, "completed_this_year": 1, "points_this_year": 20}
    other = member(client, librarian, branch_a)
    assert get(client, librarian, f"members/{other['id']}/summary")["programs"] == {"active": 0, "completed_this_year": 0, "points_this_year": 0}
'''),
    dict(id="T-RDP-40-a", req="LIB-RDP-40", type="Error", input="Branch QQ (no copies, no members) with a draft program is deactivated; after the program is cancelled", expected="`409 BRANCH_IN_USE`; 200", code='''
def TEST(client, admin, librarian):
    qq = create_branch(client, admin, "QQ")
    p = program(client, librarian, qq)
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"programs/{p['id']}/cancel"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))
'''),
    dict(id="T-RDP-41-a", req="LIB-RDP-41", type="Normal", input="Program at A; a loan made at A returned at B; a loan made at B returned at A", expected="Only the first counts (`books` 1)", code='''
def TEST(client, librarian, branch_a, branch_b):
    p = published(client, librarian, branch_a, goal_books=5)
    pa, m, _ = joined(client, librarian, branch_a, p)
    _, ca = book_with_copy(client, librarian, branch_a)
    _, cb = book_with_copy(client, librarian, branch_b)
    la, lb = lend(client, librarian, m["id"], ca["id"]), lend(client, librarian, m["id"], cb["id"])
    return_loan(client, librarian, la["id"], branch_id=branch_b["id"])
    return_loan(client, librarian, lb["id"], branch_id=branch_a["id"])
    assert [e["loan_id"] for e in entries(client, librarian, pa)] == [la["id"]]
'''),
    dict(id="T-RDP-42-a", req="LIB-RDP-42", type="Normal", input="A member joins (goal 5), gets an entry, a manual entry and leaves", expected="No `program_*` notification (the loan itself notifies `loan_created` and `loan_returned`)", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=5)
    pa, m, h = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    ok(post(client, h, f"programs/{p['id']}/leave"))
    types = [n["type"] for n in items(get(client, librarian, f"members/{m['id']}/notifications"))]
    assert [t for t in types if t.startswith("program_")] == []
'''),
    dict(id="T-RDP-43-a", req="LIB-RDP-43", type="Normal", input="Program created, changed, books set, published; members join (one leaves); manual entry added and removed; completion; another program cancelled; process; audit log", expected="One entry per event (2 for `program_created` and `program_joined`)", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-RDP-44-a", req="LIB-RDP-44", type="Normal", input="Program (goal 1, reward 20.00): A reads book X and completes; B reads X too and Y (goal reached); C nothing; a draft program; report for November", expected="One row: `{participants 3, completed 2, completion_rate 66.7, books_counted 3, points 30, rewards_waived 0.00}`, top books X (2), Y (1)", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-RDP-44-b", req="LIB-RDP-44", type="Error", input="`from` > `to`; 367 days; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/programs"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403
'''),
    dict(id="T-RDP-45-a", req="LIB-RDP-45", type="Normal", input="A program with a participant and an entry; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, librarian, branch_a):
    _, m, _ = joined(client, librarian, branch_a, published(client, librarian))
    read(client, librarian, m, branch_a)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
    dict(id="T-RDP-46-a", req="LIB-RDP-46", type="Normal", input="A late fee of 2.00 waived by a program reward; the member's balance and fee list `status=waived`", expected="`outstanding_fees` 0.00; the fee listed as `waived`", code='''
def TEST(client, clock, librarian, branch_a):
    m = member(client, librarian, branch_a)
    loan = lend(client, librarian, m["id"], book_with_copy(client, librarian, branch_a)[1]["id"])
    at(clock, "2026-11-17")
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    p = published(client, librarian, starts_on="2026-11-17", ends_on="2026-12-16", goal_books=1, reward_waiver="5.00")
    pa = ok(try_join(client, mh(client, m), p), 201)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert get(client, librarian, f"members/{m['id']}/balance")["outstanding_fees"] == "0.00"
    assert [(f["amount"], f["kind"]) for f in items(member_fees(client, librarian, m["id"], status="waived"))] == [("2.00", "late_fee")]
'''),
    dict(id="T-RDP-47-a", req="LIB-RDP-47", type="Normal", input="Participants: A 20 points, B 0 points, C left; list; `status=left`", expected="`status=active`: A (rank 1), B (rank null) with `full_name`, `public`, `reward_waived`; `status=left`: C", code='''
def TEST(client, librarian, branch_a):
    p = published(client, librarian, goal_books=5)
    pa, a, _ = joined(client, librarian, branch_a, p)
    pb, b, _ = joined(client, librarian, branch_a, p)
    pc, c, ch = joined(client, librarian, branch_a, p)
    read(client, librarian, a, branch_a); read(client, librarian, a, branch_a)
    ok(post(client, ch, f"programs/{p['id']}/leave"))
    rows = items(get(client, librarian, f"programs/{p['id']}/participants", status="active"))
    assert [(r["member_id"], r["rank"], r["full_name"], r["public"], r["reward_waived"]) for r in rows] == [(a["id"], 1, a["full_name"], True, "0.00"), (b["id"], None, b["full_name"], True, "0.00")]
    assert [r["member_id"] for r in items(get(client, librarian, f"programs/{p['id']}/participants", status="left"))] == [c["id"]]
'''),
]
