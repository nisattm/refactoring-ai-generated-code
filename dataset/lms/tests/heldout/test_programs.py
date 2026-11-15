"""Heldout tests: module 26 (Reading programs). Generated from cases/programs.md."""
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


def test_t_rdp_01_b(client, admin, librarian, branch_a):
    """T-RDP-01-b (LIB-RDP-01): 422 five times; 409 CONFLICT with details.field name; 409 BRANCH_INACTIVE; 403"""
    for fields in (dict(ends_on="2026-11-14"), dict(ends_on="2027-03-03"), dict(goal_books=0), dict(reward_waiver="50.01"), dict(audience="everyone")):
        assert try_program(client, librarian, **fields).status_code == 422, fields
    program(client, librarian, name="Kış Okumaları")
    assert err(try_program(client, librarian, name="KIŞ OKUMALARI"), 409, "CONFLICT")["details"]["field"] == "name"
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_program(client, librarian, qq), 409, "BRANCH_INACTIVE")
    assert try_program(client, mh(client, member(client, librarian, branch_a))).status_code == 403


def test_t_rdp_02_a(client, librarian, branch_a):
    """T-RDP-02-a (LIB-RDP-02): 200; 200; 409 PROGRAM_PUBLISHED; 409 PARTICIPANTS_ABOVE_LIMIT with details.participants 2; 409 INVALID_PROGRAM_STATUS"""
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


def test_t_rdp_04_a(client, librarian, branch_a):
    """T-RDP-04-a (LIB-RDP-04): 200 cancelled; A left with program_cancelled and one program_cancelled notification; B completed; 409 INVALID_PROGRAM_STATUS"""
    p = published(client, librarian, goal_books=1)
    pa, a, _ = joined(client, librarian, branch_a, p)
    pb, b, _ = joined(client, librarian, branch_a, p)
    ok(manual(client, librarian, pb, create_book(client, librarian)), 201)
    assert ok(post(client, librarian, f"programs/{p['id']}/cancel"))["status"] == "cancelled"
    oa, ob = part(client, librarian, pa), part(client, librarian, pb)
    assert (oa["status"], oa["leave_reason"], ob["status"]) == ("left", "program_cancelled", "completed")
    assert (len(notes(client, librarian, a["id"], "program_cancelled")), len(notes(client, librarian, b["id"], "program_cancelled"))) == (1, 0)
    err(post(client, librarian, f"programs/{p['id']}/cancel"), 409, "INVALID_PROGRAM_STATUS")


def test_t_rdp_06_a(client, clock, librarian):
    """T-RDP-06-a (LIB-RDP-06): closed 0; then 1"""
    published(client, librarian)
    at(clock, "2026-11-30", 23, 59)
    assert process(client, librarian)["closed"] == 0
    at(clock, "2026-12-01", 0, 0)
    assert process(client, librarian)["closed"] == 1


def test_t_rdp_08_a(client, clock, librarian, branch_a):
    """T-RDP-08-a (LIB-RDP-08): 200; ordered Ayna, Zeki; 422; 409 INVALID_PROGRAM_STATUS"""
    p = published(client, librarian)
    z, a = create_book(client, librarian, title="Zeki"), create_book(client, librarian, title="Ayna")
    url = f"/api/v1/programs/{p['id']}/books"
    ok(client.put(url, headers=librarian, json={"book_ids": [z["id"], a["id"]]}))
    h = mh(client, member(client, librarian, branch_a))
    assert [b["id"] for b in items(ok(client.get(url, headers=h)))] == [a["id"], z["id"]]
    many = [create_book(client, librarian)["id"] for _ in range(31)]
    assert client.put(url, headers=librarian, json={"book_ids": many}).status_code == 422
    at(clock, "2026-12-01")
    process(client, librarian)
    err(client.put(url, headers=librarian, json={"book_ids": []}), 409, "INVALID_PROGRAM_STATUS")


def test_t_rdp_10_a(client, librarian, branch_a):
    """T-RDP-10-a (LIB-RDP-10): 201 active, joined_at, points 0, books 0, level none, public false; 422; 422; 201"""
    p = published(client, librarian)
    m = member(client, librarian, branch_a)
    out = ok(try_join(client, mh(client, m), p, public=False), 201)
    assert (out["member_id"], out["status"], out["points"], out["books"], out["level"], out["public"]) == (m["id"], "active", 0, 0, "none", False) and same(out["joined_at"], MON, 9)
    other = member(client, librarian, branch_a)
    assert try_join(client, mh(client, other), p, member_id=other["id"]).status_code == 422
    assert try_join(client, librarian, p).status_code == 422
    assert ok(try_join(client, librarian, p, member_id=other["id"]), 201)["member_id"] == other["id"]


def test_t_rdp_11_b(client, librarian, branch_a):
    """T-RDP-11-b (LIB-RDP-11): PROGRAM_FULL; MEMBER_BLOCKED_BY_DEBT with details.total_debt 50.00; PROGRAM_LIMIT_REACHED with details.limit 3"""
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


def test_t_rdp_12_a(client, clock, librarian, branch_a):
    """T-RDP-12-a (LIB-RDP-12): Only the 11-10 return counts (books 1)"""
    p = published(client, librarian, starts_on="2026-11-09", ends_on="2026-12-07")
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    at(clock, "2026-11-10")
    read(client, librarian, m, branch_a)
    assert part(client, librarian, pa)["books"] == 1


def test_t_rdp_14_a(client, librarian, branch_a):
    """T-RDP-14-a (LIB-RDP-14): 200; 403"""
    p = published(client, librarian)
    pa, _, h = joined(client, librarian, branch_a, p)
    url = f"/api/v1/participations/{pa['id']}"
    assert ok(client.patch(url, headers=h, json={"public": False}))["public"] is False
    assert client.patch(url, headers=mh(client, member(client, librarian, branch_a)), json={"public": True}).status_code == 403


def test_t_rdp_16_a(client, librarian, branch_a):
    """T-RDP-16-a (LIB-RDP-16): One loan entry with book_id, loan_id, 10 points, on 2026-11-02; participation points 10, books 1"""
    p = published(client, librarian)
    pa, m, _ = joined(client, librarian, branch_a, p)
    b, loan = read(client, librarian, m, branch_a)
    es = entries(client, librarian, pa)
    assert [(e["source"], e["book_id"], e["loan_id"], e["points"], e["on"]) for e in es] == [("loan", b["id"], loan["id"], 10, MON)]
    out = part(client, librarian, pa)
    assert (out["points"], out["books"]) == (10, 1)


def test_t_rdp_18_a(client, clock, librarian, branch_a):
    """T-RDP-18-a (LIB-RDP-18): The return counts (books 1)"""
    p = published(client, librarian)
    m = member(client, librarian, branch_a)
    _, cp = book_with_copy(client, librarian, branch_a)
    loan = lend(client, librarian, m["id"], cp["id"])
    at(clock, MON, 10)
    pa = ok(try_join(client, mh(client, m), p), 201)
    at(clock, MON, 11)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert part(client, librarian, pa)["books"] == 1


def test_t_rdp_20_a(client, librarian, branch_a):
    """T-RDP-20-a (LIB-RDP-20): 204 and points 10, books 1; 409 ENTRY_NOT_MANUAL"""
    p = published(client, librarian, goal_books=5)
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    e = ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert client.delete(f"/api/v1/program-entries/{e['id']}", headers=librarian).status_code == 204
    out = part(client, librarian, pa)
    assert (out["points"], out["books"]) == (10, 1)
    loan_entry = [x for x in entries(client, librarian, pa) if x["source"] == "loan"][0]
    err(client.delete(f"/api/v1/program-entries/{loan_entry['id']}", headers=librarian), 409, "ENTRY_NOT_MANUAL")


def test_t_rdp_22_a(client, clock, librarian, branch_a):
    """T-RDP-22-a (LIB-RDP-22): [loan, manual] with book_title; [manual]"""
    p = published(client, librarian, goal_books=5)
    pa, m, h = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    at(clock, MON, 10)
    ok(manual(client, librarian, pa, create_book(client, librarian, title="Ev Kitabı")), 201)
    rows = entries(client, h, pa)
    assert [(e["source"], e["book_title"]) for e in rows] == [("loan", "Okunan Kitap"), ("manual", "Ev Kitabı")]
    assert [e["source"] for e in entries(client, librarian, pa, source="manual")] == ["manual"]


def test_t_rdp_24_a(client, clock, librarian, branch_a):
    """T-RDP-24-a (LIB-RDP-24): A bonus entry of 10 points after the third week; points 40"""
    p = published(client, librarian, goal_books=10)
    pa, m, _ = joined(client, librarian, branch_a, p)
    for day in ("2026-11-03", "2026-11-10", "2026-11-17"):
        at(clock, day)
        read(client, librarian, m, branch_a)
    assert [(e["source"], e["points"]) for e in entries(client, librarian, pa) if e["source"] == "bonus"] == [("bonus", 10)]
    assert part(client, librarian, pa)["points"] == 40


def test_t_rdp_26_a(client, clock, librarian, branch_a):
    """T-RDP-26-a (LIB-RDP-26): Ranks A 1, B 2, C 3, D null"""
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


def test_t_rdp_28_a(client, clock, librarian, branch_a):
    """T-RDP-28-a (LIB-RDP-28): active; then completed with completed_at 10:00 and one program_completed notification with program_id; the third still counts (books 3)"""
    p = published(client, librarian)
    pa, m, _ = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    assert part(client, librarian, pa)["status"] == "active"
    at(clock, MON, 10)
    read(client, librarian, m, branch_a)
    out = part(client, librarian, pa)
    assert (out["status"], out["level"]) == ("completed", "bronze") and same(out["completed_at"], MON, 10)
    ns = notes(client, librarian, m["id"], "program_completed")
    assert len(ns) == 1 and ns[0]["program_id"] == p["id"]
    read(client, librarian, m, branch_a)
    assert part(client, librarian, pa)["books"] == 3


def test_t_rdp_30_a(client, librarian, branch_a):
    """T-RDP-30-a (LIB-RDP-30): Levels bronze, silver, gold; two program_level_reached notifications"""
    p = published(client, librarian, goal_books=1)
    pa, m, _ = joined(client, librarian, branch_a, p)
    levels = []
    for _ in range(3):
        read(client, librarian, m, branch_a)
        levels.append(part(client, librarian, pa)["level"])
    assert levels == ["bronze", "silver", "gold"]
    assert len(notes(client, librarian, m["id"], "program_level_reached")) == 2


def test_t_rdp_32_a(client, clock, librarian, branch_a):
    """T-RDP-32-a (LIB-RDP-32): 8.00 and 10.00 waived, 14.00 open; reward_waived 18.00"""
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
    assert part(client, librarian, pa)["reward_waived"] == "18.00"


def test_t_rdp_34_a(client, clock, librarian, branch_a):
    """T-RDP-34-a (LIB-RDP-34): RP-<id>-2 for A with name, level and books; RP-<id>-1 for B; 409 NOT_COMPLETED; 403"""
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


def test_t_rdp_36_a(client, clock, librarian, branch_a):
    """T-RDP-36-a (LIB-RDP-36): reminders 0, 1, 0, 0"""
    p = published(client, librarian)
    joined(client, librarian, branch_a, p)
    out = []
    for day in ("2026-11-26", "2026-11-27", "2026-11-27", "2026-11-28"):
        at(clock, day)
        out.append(process(client, librarian)["reminders"])
    assert out == [0, 1, 0, 0]


def test_t_rdp_38_a(client, librarian, branch_a):
    """T-RDP-38-a (LIB-RDP-38): left with member_deactivated"""
    pa, m, _ = joined(client, librarian, branch_a, published(client, librarian))
    deactivate_member(client, librarian, m["id"])
    out = part(client, librarian, pa)
    assert (out["status"], out["leave_reason"]) == ("left", "member_deactivated")


def test_t_rdp_40_a(client, admin, librarian):
    """T-RDP-40-a (LIB-RDP-40): 409 BRANCH_IN_USE; 200"""
    qq = create_branch(client, admin, "QQ")
    p = program(client, librarian, qq)
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"programs/{p['id']}/cancel"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))


def test_t_rdp_42_a(client, librarian, branch_a):
    """T-RDP-42-a (LIB-RDP-42): No notification"""
    p = published(client, librarian, goal_books=5)
    pa, m, h = joined(client, librarian, branch_a, p)
    read(client, librarian, m, branch_a)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    ok(post(client, h, f"programs/{p['id']}/leave"))
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0


def test_t_rdp_44_b(client, librarian, branch_a):
    """T-RDP-44-b (LIB-RDP-44): 422; 422; 403"""
    url = "/api/v1/reports/programs"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403


def test_t_rdp_46_a(client, clock, librarian, branch_a):
    """T-RDP-46-a (LIB-RDP-46): outstanding_fees 0.00; the fee listed as waived"""
    m = member(client, librarian, branch_a)
    loan = lend(client, librarian, m["id"], book_with_copy(client, librarian, branch_a)[1]["id"])
    at(clock, "2026-11-17")
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    p = published(client, librarian, starts_on="2026-11-17", ends_on="2026-12-16", goal_books=1, reward_waiver="5.00")
    pa = ok(try_join(client, mh(client, m), p), 201)
    ok(manual(client, librarian, pa, create_book(client, librarian)), 201)
    assert get(client, librarian, f"members/{m['id']}/balance")["outstanding_fees"] == "0.00"
    assert [(f["amount"], f["kind"]) for f in items(member_fees(client, librarian, m["id"], status="waived"))] == [("2.00", "late_fee")]
