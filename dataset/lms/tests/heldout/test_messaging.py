"""Heldout tests: module 27 (Announcements and messages). Generated from cases/messaging.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, deactivate_member, error_code, items, lend, member_fees, member_headers,
    register_member, return_loan, session,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON = "2026-11-02"
ALL_TYPES = {"student", "academic", "staff", "guest"}
# the clock starts on Monday 2026-11-02 09:00 (conftest.py)


def at(clock, day, hh=9, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    clock.set(datetime(y, m, d, hh, mm, ss, tzinfo=TR))


def ts(day, hh=9, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, hh, mm, ss, tzinfo=TR).isoformat()


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


def me(client, headers):
    return get(client, headers, "auth/me")["id"]


def staff_user(client, admin):
    _seq[0] += 1
    email = f"msgstaff{_seq[0]}@library.local"
    u = ok(post(client, admin, "users", {"email": email, "full_name": f"Görevli {_seq[0]}", "role": "librarian", "password": "Staff12345"}), 201)
    return u, session(client, email, "Staff12345")


def try_ann(client, headers, **fields):
    _seq[0] += 1
    body = {"title": f"Duyuru {_seq[0]:03d}", "body": "Kütüphane duyurusu."}
    body.update(fields)
    return post(client, headers, "announcements", body)


def ann(client, headers, **fields):
    return ok(try_ann(client, headers, **fields), 201)


def publish(client, headers, a):
    return post(client, headers, f"announcements/{a['id']}/publish")


def live(client, lib, **fields):
    return ok(publish(client, lib, ann(client, lib, **fields)))


def feed(client, headers, **params):
    return get(client, headers, "announcements", **params)


def try_thread(client, headers, branch, **fields):
    _seq[0] += 1
    body = {"branch_id": branch["id"], "subject": f"Soru {_seq[0]:03d}", "body": "Merhaba, bir sorum var."}
    body.update(fields)
    return post(client, headers, "threads", body)


def thread(client, headers, branch, **fields):
    return ok(try_thread(client, headers, branch, **fields), 201)


def asked(client, lib, branch, **fields):
    """A thread of a new member: (thread, member, headers)."""
    m = member(client, lib, branch)
    h = mh(client, m)
    return thread(client, h, branch, **fields), m, h


def reply(client, headers, t, body="Yanıt", internal=None):
    payload = {"body": body}
    if internal is not None:
        payload["internal"] = internal
    return post(client, headers, f"threads/{t['id']}/messages", payload)


def step(client, headers, t, name, body=None):
    return post(client, headers, f"threads/{t['id']}/{name}", body)


def read_thread(client, headers, t):
    return get(client, headers, f"threads/{t['id']}")


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def process(client, lib):
    return ok(post(client, lib, "messaging/process"))


def test_t_msg_01_b(client, admin, librarian, branch_a):
    """T-MSG-01-b (LIB-MSG-01): 422 seven times; 409 BRANCH_INACTIVE; 403"""
    bad = [dict(body=""), dict(audience=[]), dict(audience=["kids"]), dict(audience=["student", "student"]),
           dict(publish_at=ts(MON, 10), expires_at=ts(MON, 9)), dict(publish_at=ts(MON, 10), expires_at=ts("2027-02-01", 10)), dict(branch_id=999999)]
    for fields in bad:
        assert try_ann(client, librarian, **fields).status_code == 422, fields
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_ann(client, librarian, branch_id=qq["id"]), 409, "BRANCH_INACTIVE")
    assert try_ann(client, mh(client, member(client, librarian, branch_a))).status_code == 403


def test_t_msg_02_b(client, librarian, branch_a):
    """T-MSG-02-b (LIB-MSG-02): Stats reads 1, then 0 after the body change; the priority change keeps marks"""
    a = live(client, librarian)
    h = mh(client, member(client, librarian, branch_a))
    ok(post(client, h, f"announcements/{a['id']}/read"))
    url = f"/api/v1/announcements/{a['id']}"
    assert get(client, librarian, f"announcements/{a['id']}/stats")["reads"] == 1
    ok(client.patch(url, headers=librarian, json={"body": "Güncellendi."}))
    assert get(client, librarian, f"announcements/{a['id']}/stats")["reads"] == 0
    ok(post(client, h, f"announcements/{a['id']}/read"))
    ok(client.patch(url, headers=librarian, json={"priority": "important"}))
    assert get(client, librarian, f"announcements/{a['id']}/stats")["reads"] == 1


def test_t_msg_03_b(client, librarian, branch_a):
    """T-MSG-03-b (LIB-MSG-03): 409 PIN_LIMIT_REACHED with details.limit 3"""
    for _ in range(3):
        live(client, librarian, branch_id=branch_a["id"], pinned=True)
    assert err(publish(client, librarian, ann(client, librarian, branch_id=branch_a["id"], pinned=True)), 409, "PIN_LIMIT_REACHED")["details"]["limit"] == 3


def test_t_msg_04_a(client, clock, librarian, branch_a):
    """T-MSG-04-a (LIB-MSG-04): Mon: published_at null and not in the feed; Tue: published_at 09:00 and in the feed"""
    a = ok(publish(client, librarian, ann(client, librarian, publish_at=ts("2026-11-03"))))
    assert (a["status"], a["published_at"]) == ("published", None)
    h = mh(client, member(client, librarian, branch_a))
    assert feed(client, h)["total"] == 0
    at(clock, "2026-11-03")
    process(client, librarian)
    assert same(get(client, librarian, f"announcements/{a['id']}")["published_at"], "2026-11-03", 9)
    assert [x["id"] for x in items(feed(client, h))] == [a["id"]]


def test_t_msg_06_a(client, librarian, branch_a, branch_b):
    """T-MSG-06-a (LIB-MSG-06): One announcement notification with announcement_id for the student of A only; none for the normal one"""
    s, a, sb = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic"), member(client, librarian, branch_b)
    x = live(client, librarian, branch_id=branch_a["id"], audience=["student"], priority="important", title="Kapanış saati değişti")
    live(client, librarian, branch_id=branch_a["id"], audience=["student"])
    ns = notes(client, librarian, s["id"], "announcement")
    assert len(ns) == 1 and ns[0]["announcement_id"] == x["id"] and "Kapanış saati değişti" in ns[0]["message"]
    assert [len(notes(client, librarian, m["id"], "announcement")) for m in (a, sb)] == [0, 0]


def test_t_msg_08_a(client, clock, librarian, branch_a):
    """T-MSG-08-a (LIB-MSG-08): No notification on Mon; announcements_released 0, then 1 with one notification"""
    s = member(client, librarian, branch_a)
    ok(publish(client, librarian, ann(client, librarian, audience=["student"], priority="important", publish_at=ts("2026-11-03"))))
    assert len(notes(client, librarian, s["id"], "announcement")) == 0
    at(clock, "2026-11-03", 8, 59)
    assert process(client, librarian)["announcements_released"] == 0
    at(clock, "2026-11-03", 9, 0)
    assert process(client, librarian)["announcements_released"] == 1
    assert len(notes(client, librarian, s["id"], "announcement")) == 1


def test_t_msg_10_a(client, librarian):
    """T-MSG-10-a (LIB-MSG-10): [W, S, L, D]; [S, L]; [L]; [S]"""
    d = ann(client, librarian)
    l = live(client, librarian)
    s = ok(publish(client, librarian, ann(client, librarian, publish_at=ts("2026-11-04"))))
    w = live(client, librarian)
    ok(post(client, librarian, f"announcements/{w['id']}/withdraw"))
    ids = lambda **p: [x["id"] for x in items(feed(client, librarian, **p))]
    assert ids() == [w["id"], s["id"], l["id"], d["id"]]
    assert ids(status="published") == [s["id"], l["id"]]
    assert ids(live="true") == [l["id"]]
    assert ids(scheduled="true") == [s["id"]]


def test_t_msg_12_a(client, librarian, branch_a, branch_b):
    """T-MSG-12-a (LIB-MSG-12): {audience_size 3, reads 2, read_rate 66.7}; {0, 0, 0.0}"""
    ms = [member(client, librarian, branch_a) for _ in range(3)]
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    member(client, librarian, branch_b)
    a = live(client, librarian, branch_id=branch_a["id"], audience=["student"])
    for m in ms[:2]:
        ok(post(client, mh(client, m), f"announcements/{a['id']}/read"))
    assert get(client, librarian, f"announcements/{a['id']}/stats") == {"audience_size": 3, "reads": 2, "read_rate": "66.7"}
    g = live(client, librarian, audience=["guest"])
    assert get(client, librarian, f"announcements/{g['id']}/stats") == {"audience_size": 0, "reads": 0, "read_rate": "0.0"}


def test_t_msg_14_a(client, librarian, branch_a):
    """T-MSG-14-a (LIB-MSG-14): 201 open with created_at, one message by member; staff writing → 403; an empty subject → 422"""
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    t = thread(client, h, branch_a, subject="Çalışma saatleri", body="Pazar açık mısınız?")
    assert (t["member_id"], t["branch_id"], t["subject"], t["category"], t["status"]) == (m["id"], branch_a["id"], "Çalışma saatleri", "general", "open") and same(t["created_at"], MON, 9)
    assert [(x["author"], x["body"]) for x in t["messages"]] == [("member", "Pazar açık mısınız?")]
    assert try_thread(client, librarian, branch_a).status_code == 403
    assert try_thread(client, h, branch_a, subject="").status_code == 422


def test_t_msg_16_a(client, clock, librarian, branch_a):
    """T-MSG-16-a (LIB-MSG-16): M: [T1, T2] with T1 unread 1; other member: empty; staff: [T1]"""
    t1, m, h = asked(client, librarian, branch_a)
    at(clock, MON, 10)
    t2 = thread(client, h, branch_a)
    at(clock, MON, 11)
    ok(reply(client, librarian, t1), 201)
    rows = items(get(client, h, "threads"))
    assert [(r["id"], r["unread"]) for r in rows] == [(t1["id"], 1), (t2["id"], 0)]
    assert get(client, mh(client, member(client, librarian, branch_a)), "threads")["total"] == 0
    assert [r["id"] for r in items(get(client, librarian, "threads", status="answered"))] == [t1["id"]]


def test_t_msg_18_a(client, librarian, branch_a):
    """T-MSG-18-a (LIB-MSG-18): 422; 409 THREAD_CLOSED"""
    t, _, h = asked(client, librarian, branch_a)
    assert reply(client, h, t, internal=True).status_code == 422
    ok(step(client, librarian, t, "close"))
    err(reply(client, h, t), 409, "THREAD_CLOSED")


def test_t_msg_20_a(client, librarian, branch_a):
    """T-MSG-20-a (LIB-MSG-20): 409 NOT_OWN_RECORD with details.field loan_id; 201; 422; NOT_OWN_RECORD with fee_id"""
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    h = mh(client, m)
    cp1, cp2 = (add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"]) for _ in range(2))
    own, foreign = lend(client, librarian, m["id"], cp1["id"]), lend(client, librarian, other["id"], cp2["id"])
    assert err(try_thread(client, h, branch_a, category="loan", loan_id=foreign["id"]), 409, "NOT_OWN_RECORD")["details"]["field"] == "loan_id"
    assert thread(client, h, branch_a, category="loan", loan_id=own["id"])["loan_id"] == own["id"]
    assert try_thread(client, h, branch_a, category="general", loan_id=own["id"]).status_code == 422
    return_loan(client, librarian, foreign["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    fee = items(member_fees(client, librarian, other["id"]))[0]
    assert err(try_thread(client, h, branch_a, category="fee", fee_id=fee["id"]), 409, "NOT_OWN_RECORD")["details"]["field"] == "fee_id"


def test_t_msg_22_a(client, clock, librarian, branch_a):
    """T-MSG-22-a (LIB-MSG-22): 409 MESSAGE_LIMIT_REACHED with details.limit 10 on the 11th; Tue 201; staff 201"""
    t, _, h = asked(client, librarian, branch_a)
    for _ in range(9):
        ok(reply(client, h, t), 201)
    assert err(reply(client, h, t), 409, "MESSAGE_LIMIT_REACHED")["details"]["limit"] == 10
    for _ in range(12):
        ok(reply(client, librarian, t), 201)
    at(clock, "2026-11-03")
    ok(reply(client, h, t), 201)


def test_t_msg_24_a(client, admin, librarian, branch_a):
    """T-MSG-24-a (LIB-MSG-24): 200; listed only for the assignee; 422; assigned_to null; 409 THREAD_CLOSED"""
    t, m, _ = asked(client, librarian, branch_a)
    u, uh = staff_user(client, admin)
    assert ok(step(client, librarian, t, "assign", {"user_id": u["id"]}))["assigned_to"] == u["id"]
    assert [r["id"] for r in items(get(client, uh, "threads", assigned_to="me"))] == [t["id"]]
    assert get(client, librarian, "threads", assigned_to="me")["total"] == 0
    member_user = get(client, mh(client, m), "auth/me")["id"]
    assert step(client, librarian, t, "assign", {"user_id": member_user}).status_code == 422
    assert ok(step(client, librarian, t, "assign", {"user_id": None}))["assigned_to"] is None
    ok(step(client, librarian, t, "close"))
    err(step(client, librarian, t, "assign", {"user_id": u["id"]}), 409, "THREAD_CLOSED")


def test_t_msg_26_a(client, librarian, branch_a):
    """T-MSG-26-a (LIB-MSG-26): 200 closed with member_request and closed_at; 409 THREAD_CLOSED; staff_request"""
    t, _, h = asked(client, librarian, branch_a)
    out = ok(step(client, h, t, "close"))
    assert (out["status"], out["close_reason"]) == ("closed", "member_request") and same(out["closed_at"], MON, 9)
    err(step(client, h, t, "close"), 409, "THREAD_CLOSED")
    t2 = thread(client, h, branch_a)
    assert ok(step(client, librarian, t2, "close"))["close_reason"] == "staff_request"


def test_t_msg_28_a(client, clock, librarian, branch_a):
    """T-MSG-28-a (LIB-MSG-28): threads_closed 1; the first closed with inactive"""
    t1, _, _ = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t1), 201)
    asked(client, librarian, branch_a)
    t3, _, h3 = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t3), 201)
    at(clock, "2026-11-12")
    ok(reply(client, h3, t3), 201)
    ok(reply(client, librarian, t3), 201)
    at(clock, "2026-11-17")
    assert process(client, librarian)["threads_closed"] == 1
    out = read_thread(client, librarian, t1)
    assert (out["status"], out["close_reason"]) == ("closed", "inactive")


def test_t_msg_30_a(client, librarian, branch_a):
    """T-MSG-30-a (LIB-MSG-30): THREAD_NOT_CLOSED; NOTHING_TO_RATE; 200 rating 4; ALREADY_RATED; 422"""
    t, _, h = asked(client, librarian, branch_a)
    err(step(client, h, t, "rate", {"rating": 4}), 409, "THREAD_NOT_CLOSED")
    lone = thread(client, h, branch_a)
    ok(step(client, h, lone, "close"))
    err(step(client, h, lone, "rate", {"rating": 4}), 409, "NOTHING_TO_RATE")
    ok(reply(client, librarian, t), 201)
    ok(step(client, h, t, "close"))
    assert step(client, h, t, "rate", {"rating": 6}).status_code == 422
    assert ok(step(client, h, t, "rate", {"rating": 4}))["rating"] == 4
    err(step(client, h, t, "rate", {"rating": 5}), 409, "ALREADY_RATED")


def test_t_msg_32_a(client, librarian, branch_a):
    """T-MSG-32-a (LIB-MSG-32): closed with member_deactivated; 409"""
    t, m, h = asked(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    out = read_thread(client, librarian, t)
    assert (out["status"], out["close_reason"]) == ("closed", "member_deactivated")
    assert step(client, h, t, "reopen").status_code == 409


def test_t_msg_34_a(client, admin, librarian, branch_a):
    """T-MSG-34-a (LIB-MSG-34): BRANCH_IN_USE twice; then 200"""
    qq = create_branch(client, admin, "QQ")
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    t = thread(client, h, qq)
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(step(client, h, t, "close"))
    a = live(client, librarian, branch_id=qq["id"])
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))


def test_t_msg_36_a(client, admin, librarian, branch_a):
    """T-MSG-36-a (LIB-MSG-36): assigned_to null"""
    t, _, _ = asked(client, librarian, branch_a)
    u, _ = staff_user(client, admin)
    ok(step(client, librarian, t, "assign", {"user_id": u["id"]}))
    ok(client.patch(f"/api/v1/users/{u['id']}", headers=admin, json={"is_active": False}))
    assert read_thread(client, librarian, t)["assigned_to"] is None


def test_t_msg_38_a(client, admin, librarian, branch_a):
    """T-MSG-38-a (LIB-MSG-38): One entry per event (2 for thread_closed, at least 2 for thread_message_added)"""
    a = ann(client, librarian)
    ok(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"title": "Değişti"}))
    ok(publish(client, librarian, a))
    ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    t, _, h = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t), 201)
    ok(reply(client, librarian, t, internal=True), 201)
    ok(step(client, librarian, t, "assign", {"user_id": me(client, librarian)}))
    ok(step(client, h, t, "close"))
    ok(step(client, h, t, "reopen"))
    ok(step(client, h, t, "close"))
    ok(step(client, h, t, "rate", {"rating": 5}))
    process(client, librarian)
    counts = {"announcement_created": 1, "announcement_updated": 1, "announcement_published": 1, "announcement_withdrawn": 1, "thread_created": 1,
              "thread_message_added": 2, "thread_assigned": 1, "thread_closed": 2, "thread_reopened": 1, "thread_rated": 1, "messaging_processed": 1}
    for name, n in counts.items():
        got = len(items(get(client, admin, "audit-log", event=name)))
        assert (got >= n if name == "thread_message_added" else got == n), name


def test_t_msg_39_b(client, librarian, branch_a):
    """T-MSG-39-b (LIB-MSG-39): 422; 422; 403"""
    url = "/api/v1/reports/messaging"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403


def test_t_msg_40_a(client, admin, librarian, branch_a):
    """T-MSG-40-a (LIB-MSG-40): The export has exactly the keys of 22.1"""
    live(client, librarian)
    asked(client, librarian, branch_a)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}


def test_t_msg_42_a(client, librarian):
    """T-MSG-42-a (LIB-MSG-42): 200 {announcements_released 0, threads_closed 0}"""
    out = process(client, librarian)
    assert (out["announcements_released"], out["threads_closed"]) == (0, 0)


def test_t_msg_44_a(client, librarian, branch_a, branch_b):
    """T-MSG-44-a (LIB-MSG-44): 200 both"""
    for _ in range(3):
        live(client, librarian, branch_id=branch_a["id"], pinned=True)
    live(client, librarian, pinned=True)
    live(client, librarian, branch_id=branch_b["id"], pinned=True)


def test_t_msg_46_a(client, clock, librarian, branch_a):
    """T-MSG-46-a (LIB-MSG-46): The pinned one first in the member's feed"""
    p = live(client, librarian, pinned=True)
    for hh in (10, 11, 12):
        at(clock, MON, hh)
        live(client, librarian)
    assert items(feed(client, mh(client, member(client, librarian, branch_a))))[0]["id"] == p["id"]
