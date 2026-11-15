"""Feedback tests: module 27 (Announcements and messages). Generated from cases/messaging.md."""
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


def test_t_msg_01_a(client, librarian):
    """T-MSG-01-a (LIB-MSG-01): 201 draft; all four types, normal, not pinned, publish_at now, no expiry, all branches"""
    a = ann(client, librarian, title="Kütüphane Haftası", body="Etkinlik programı yayında.")
    assert (a["title"], a["body"], a["status"], a["priority"], a["pinned"], a["branch_id"], a["expires_at"], a["published_at"]) == ("Kütüphane Haftası", "Etkinlik programı yayında.", "draft", "normal", False, None, None, None)
    assert set(a["audience"]) == ALL_TYPES and same(a["publish_at"], MON, 9)


def test_t_msg_01_c(client, librarian):
    """T-MSG-01-c (LIB-MSG-01): 201"""
    ann(client, librarian, publish_at=ts(MON), expires_at=ts("2027-01-31"))


def test_t_msg_02_a(client, librarian):
    """T-MSG-02-a (LIB-MSG-02): 200; 409 ANNOUNCEMENT_LIVE; 409 INVALID_ANNOUNCEMENT_STATUS with details.status withdrawn"""
    d = ann(client, librarian)
    assert ok(client.patch(f"/api/v1/announcements/{d['id']}", headers=librarian, json={"title": "Yeni"}))["title"] == "Yeni"
    a = live(client, librarian)
    err(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"publish_at": ts("2026-11-05")}), 409, "ANNOUNCEMENT_LIVE")
    ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    assert err(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"title": "X"}), 409, "INVALID_ANNOUNCEMENT_STATUS")["details"]["status"] == "withdrawn"


def test_t_msg_03_a(client, librarian):
    """T-MSG-03-a (LIB-MSG-03): 200 published with published_at now; INVALID_ANNOUNCEMENT_STATUS; ANNOUNCEMENT_EXPIRED"""
    a = ann(client, librarian)
    out = ok(publish(client, librarian, a))
    assert out["status"] == "published" and same(out["published_at"], MON, 9)
    err(publish(client, librarian, a), 409, "INVALID_ANNOUNCEMENT_STATUS")
    old = ann(client, librarian, publish_at=ts(MON, 8), expires_at=ts(MON, 8, 30))
    err(publish(client, librarian, old), 409, "ANNOUNCEMENT_EXPIRED")


def test_t_msg_05_a(client, librarian, branch_a):
    """T-MSG-05-a (LIB-MSG-05): 200 withdrawn with withdrawn_at; 404; 409 INVALID_ANNOUNCEMENT_STATUS"""
    a = live(client, librarian)
    out = ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    assert out["status"] == "withdrawn" and same(out["withdrawn_at"], MON, 9)
    assert client.get(f"/api/v1/announcements/{a['id']}", headers=mh(client, member(client, librarian, branch_a))).status_code == 404
    err(post(client, librarian, f"announcements/{a['id']}/withdraw"), 409, "INVALID_ANNOUNCEMENT_STATUS")


def test_t_msg_07_a(client, clock, librarian):
    """T-MSG-07-a (LIB-MSG-07): announcements_released 1, then 0"""
    for day in ("2026-11-03", "2026-11-04"):
        ok(publish(client, librarian, ann(client, librarian, publish_at=ts(day))))
    at(clock, "2026-11-03", 10)
    assert process(client, librarian)["announcements_released"] == 1
    assert process(client, librarian)["announcements_released"] == 0


def test_t_msg_09_a(client, clock, librarian, branch_a):
    """T-MSG-09-a (LIB-MSG-09): Feed [A2, A3, A1] with read only on A3; unread 2; the academic one 404"""
    a1 = live(client, librarian)
    at(clock, MON, 10)
    a2 = live(client, librarian, pinned=True, publish_at=ts(MON, 8))
    a3 = live(client, librarian)
    aca = live(client, librarian, audience=["academic"])
    h = mh(client, member(client, librarian, branch_a))
    get(client, h, f"announcements/{a3['id']}")
    out = feed(client, h)
    assert [(x["id"], x["read"]) for x in items(out)] == [(a2["id"], False), (a3["id"], True), (a1["id"], False)]
    assert out["unread"] == 2
    assert client.get(f"/api/v1/announcements/{aca['id']}", headers=h).status_code == 404


def test_t_msg_11_a(client, clock, librarian, branch_a):
    """T-MSG-11-a (LIB-MSG-11): 200 {announcement_id, read_at 09:00} both times; 404"""
    a = live(client, librarian)
    h = mh(client, member(client, librarian, branch_a))
    first = ok(post(client, h, f"announcements/{a['id']}/read"))
    at(clock, MON, 10)
    again = ok(post(client, h, f"announcements/{a['id']}/read"))
    assert first["announcement_id"] == a["id"] and same(first["read_at"], MON, 9) and same(again["read_at"], MON, 9)
    assert post(client, h, f"announcements/{ann(client, librarian)['id']}/read").status_code == 404


def test_t_msg_13_a(client, librarian, branch_a, branch_b):
    """T-MSG-13-a (LIB-MSG-13): In the feeds of the first two only"""
    a = live(client, librarian, branch_id=branch_a["id"], audience=["student", "academic"])
    people = [member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic"),
              member(client, librarian, branch_b), member(client, librarian, branch_a, membership_type="guest")]
    assert [[x["id"] for x in items(feed(client, mh(client, m)))] for m in people] == [[a["id"]], [a["id"]], [], []]


def test_t_msg_15_a(client, admin, librarian, branch_a):
    """T-MSG-15-a (LIB-MSG-15): MEMBER_PASSIVE; BRANCH_INACTIVE; THREAD_LIMIT_REACHED with details.limit 3; 201"""
    p = member(client, librarian, branch_a)
    ph = mh(client, p)
    deactivate_member(client, librarian, p["id"])
    err(try_thread(client, ph, branch_a), 409, "MEMBER_PASSIVE")
    h = mh(client, member(client, librarian, branch_a))
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_thread(client, h, qq), 409, "BRANCH_INACTIVE")
    ts_ = [thread(client, h, branch_a) for _ in range(3)]
    assert err(try_thread(client, h, branch_a), 409, "THREAD_LIMIT_REACHED")["details"]["limit"] == 3
    ok(step(client, h, ts_[0], "close"))
    thread(client, h, branch_a)


def test_t_msg_17_a(client, librarian, branch_a):
    """T-MSG-17-a (LIB-MSG-17): Member sees 2 messages (no internal note); afterwards unread 0; 404"""
    t, m, h = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t, "Not: kontrol et", internal=True), 201)
    ok(reply(client, librarian, t, "Pazar kapalıyız."), 201)
    out = read_thread(client, h, t)
    assert [(x["author"], x["body"]) for x in out["messages"]] == [("member", "Merhaba, bir sorum var."), ("staff", "Pazar kapalıyız.")]
    assert items(get(client, h, "threads"))[0]["unread"] == 0
    assert client.get(f"/api/v1/threads/{t['id']}", headers=mh(client, member(client, librarian, branch_a))).status_code == 404


def test_t_msg_19_a(client, clock, librarian, branch_a):
    """T-MSG-19-a (LIB-MSG-19): open (no notification); answered with first_reply_at 11:00 and one message_reply; open with due_at Wed 12:00"""
    t, m, h = asked(client, librarian, branch_a)
    at(clock, MON, 10)
    ok(reply(client, librarian, t, internal=True), 201)
    assert read_thread(client, librarian, t)["status"] == "open" and len(notes(client, librarian, m["id"], "message_reply")) == 0
    at(clock, MON, 11)
    ok(reply(client, librarian, t), 201)
    out = read_thread(client, librarian, t)
    assert out["status"] == "answered" and same(out["first_reply_at"], MON, 11) and out["due_at"] is None
    ns = notes(client, librarian, m["id"], "message_reply")
    assert len(ns) == 1 and ns[0]["thread_id"] == t["id"]
    at(clock, MON, 12)
    ok(reply(client, h, t), 201)
    out = read_thread(client, librarian, t)
    assert out["status"] == "open" and same(out["due_at"], "2026-11-04", 12)


def test_t_msg_21_a(client, librarian, branch_a):
    """T-MSG-21-a (LIB-MSG-21): member with member_no, full_name, membership_type; fee with kind, amount, status"""
    m = member(client, librarian, branch_a)
    cp = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    return_loan(client, librarian, lend(client, librarian, m["id"], cp["id"])["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    t = thread(client, mh(client, m), branch_a, category="fee", fee_id=fee["id"])
    out = read_thread(client, librarian, t)
    assert out["member"] == {"id": m["id"], "member_no": m["member_no"], "full_name": m["full_name"], "membership_type": "student"}
    assert (out["fee"]["id"], out["fee"]["kind"], out["fee"]["amount"], out["fee"]["status"]) == (fee["id"], "damage_fee", "10.00", "open")


def test_t_msg_23_a(client, clock, librarian, branch_a):
    """T-MSG-23-a (LIB-MSG-23): due_at Tue 16:00; not overdue, then overdue"""
    at(clock, "2026-11-06", 16)
    t, _, _ = asked(client, librarian, branch_a)
    assert same(t["due_at"], "2026-11-10", 16)
    at(clock, "2026-11-10", 16, 0, 0)
    assert get(client, librarian, "threads", overdue="true")["total"] == 0
    at(clock, "2026-11-10", 16, 0, 1)
    assert [r["id"] for r in items(get(client, librarian, "threads", overdue="true"))] == [t["id"]]


def test_t_msg_25_a(client, admin, librarian, branch_a):
    """T-MSG-25-a (LIB-MSG-25): assigned_to L2"""
    t, _, _ = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t, internal=True), 201)
    assert read_thread(client, librarian, t)["assigned_to"] is None
    u, uh = staff_user(client, admin)
    ok(reply(client, uh, t), 201)
    assert read_thread(client, librarian, t)["assigned_to"] == u["id"]


def test_t_msg_27_a(client, clock, librarian, branch_a):
    """T-MSG-27-a (LIB-MSG-27): 200 open with a new due_at; 409 THREAD_REOPEN_NOT_ALLOWED; 409 THREAD_NOT_CLOSED"""
    t1, _, h = asked(client, librarian, branch_a)
    t2 = thread(client, h, branch_a)
    ok(step(client, h, t1, "close")); ok(step(client, h, t2, "close"))
    at(clock, "2026-11-16", 9, 0, 0)
    out = ok(step(client, h, t1, "reopen"))
    assert (out["status"], out["close_reason"], out["closed_at"]) == ("open", None, None) and same(out["due_at"], "2026-11-18", 9)
    err(step(client, h, t1, "reopen"), 409, "THREAD_NOT_CLOSED")
    at(clock, "2026-11-16", 9, 0, 1)
    err(step(client, h, t2, "reopen"), 409, "THREAD_REOPEN_NOT_ALLOWED")


def test_t_msg_29_a(client, clock, librarian, branch_a):
    """T-MSG-29-a (LIB-MSG-29): threads_closed 0, then 1"""
    t, _, _ = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t), 201)
    at(clock, "2026-11-16", 9, 0, 0)
    assert process(client, librarian)["threads_closed"] == 0
    at(clock, "2026-11-16", 9, 0, 1)
    assert process(client, librarian)["threads_closed"] == 1


def test_t_msg_31_a(client, clock, librarian, branch_a):
    """T-MSG-31-a (LIB-MSG-31): overdue_by_hours 5"""
    t, _, _ = asked(client, librarian, branch_a)
    at(clock, "2026-11-04", 14, 59)
    rows = items(get(client, librarian, "threads", overdue="true"))
    assert [(r["id"], r["is_overdue"], r["overdue_by_hours"]) for r in rows] == [(t["id"], True, 5)]


def test_t_msg_33_a(client, librarian, branch_a):
    """T-MSG-33-a (LIB-MSG-33): {unread_announcements 1, open_threads 2, unread_replies 1}"""
    a1 = live(client, librarian)
    live(client, librarian)
    t, m, h = asked(client, librarian, branch_a)
    thread(client, h, branch_a)
    ok(post(client, h, f"announcements/{a1['id']}/read"))
    ok(reply(client, librarian, t), 201)
    ok(reply(client, librarian, t, internal=True), 201)
    assert get(client, librarian, f"members/{m['id']}/summary")["messages"] == {"unread_announcements": 1, "open_threads": 2, "unread_replies": 1}


def test_t_msg_35_a(client, librarian, branch_a):
    """T-MSG-35-a (LIB-MSG-35): Empty; then the announcement"""
    a = live(client, librarian, audience=["academic"])
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    assert feed(client, h)["total"] == 0
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "academic"}))
    assert [x["id"] for x in items(feed(client, h))] == [a["id"]]


def test_t_msg_37_a(client, librarian, branch_a):
    """T-MSG-37-a (LIB-MSG-37): No notification"""
    t, m, h = asked(client, librarian, branch_a)
    ok(step(client, h, t, "close"))
    ok(step(client, h, t, "reopen"))
    live(client, librarian)
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0


def test_t_msg_39_a(client, clock, librarian, branch_a):
    """T-MSG-39-a (LIB-MSG-39): threads 3, by_category loan 1, general 1, other 1; answered 2; average_first_reply_hours 1.5; overdue_now 1; closed 2; average_rating 4.5; announcements {published 2, important 1, reads 1}"""
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    cp = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, m["id"], cp["id"])
    t1 = thread(client, h, branch_a, category="loan", loan_id=loan["id"])
    t2 = thread(client, h, branch_a)
    h3 = mh(client, member(client, librarian, branch_a))
    thread(client, h3, branch_a, category="other")
    a = live(client, librarian, priority="important")
    live(client, librarian)
    ok(post(client, h, f"announcements/{a['id']}/read"))
    at(clock, MON, 10)
    ok(reply(client, librarian, t2), 201)
    at(clock, MON, 11)
    ok(reply(client, librarian, t1), 201)
    for t, r in ((t1, 4), (t2, 5)):
        ok(step(client, h, t, "close"))
        ok(step(client, h, t, "rate", {"rating": r}))
    at(clock, "2026-11-05")
    out = get(client, librarian, "reports/messaging", **{"from": MON, "to": "2026-11-08"})
    assert (out["threads"], out["by_category"]["loan"], out["by_category"]["general"], out["by_category"]["other"], out["answered"]) == (3, 1, 1, 1, 2)
    assert (out["average_first_reply_hours"], out["overdue_now"], out["closed"], out["average_rating"]) == ("1.5", 1, 2, "4.5")
    assert out["announcements"] == {"published": 2, "important": 1, "reads": 1}


def test_t_msg_41_a(client, librarian):
    """T-MSG-41-a (LIB-MSG-41): 409 INVALID_ANNOUNCEMENT_STATUS each"""
    a = live(client, librarian)
    ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    err(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"title": "X"}), 409, "INVALID_ANNOUNCEMENT_STATUS")
    err(publish(client, librarian, a), 409, "INVALID_ANNOUNCEMENT_STATUS")
    err(post(client, librarian, f"announcements/{a['id']}/withdraw"), 409, "INVALID_ANNOUNCEMENT_STATUS")


def test_t_msg_43_a(client, clock, librarian, branch_a):
    """T-MSG-43-a (LIB-MSG-43): Still published and in live=false; not in the feed; the new pinned one 200"""
    e = live(client, librarian, branch_id=branch_a["id"], pinned=True, expires_at=ts(MON, 10))
    live(client, librarian, branch_id=branch_a["id"], pinned=True)
    live(client, librarian, branch_id=branch_a["id"], pinned=True)
    at(clock, MON, 10)
    assert get(client, librarian, f"announcements/{e['id']}")["status"] == "published"
    assert e["id"] in [x["id"] for x in items(feed(client, librarian, live="false"))]
    assert e["id"] not in [x["id"] for x in items(feed(client, mh(client, member(client, librarian, branch_a))))]
    ok(publish(client, librarian, ann(client, librarian, branch_id=branch_a["id"], pinned=True)))


def test_t_msg_45_a(client, admin, librarian, branch_a):
    """T-MSG-45-a (LIB-MSG-45): assigned_to stays L1; the thread answered"""
    t, _, _ = asked(client, librarian, branch_a)
    u, uh = staff_user(client, admin)
    ok(step(client, librarian, t, "assign", {"user_id": me(client, librarian)}))
    ok(reply(client, uh, t), 201)
    out = read_thread(client, librarian, t)
    assert (out["assigned_to"], out["status"]) == (me(client, librarian), "answered")


def test_t_msg_47_a(client, librarian, branch_a):
    """T-MSG-47-a (LIB-MSG-47): read false again and unread 1"""
    a = live(client, librarian)
    h = mh(client, member(client, librarian, branch_a))
    ok(post(client, h, f"announcements/{a['id']}/read"))
    assert feed(client, h)["unread"] == 0
    ok(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"title": "Yeni başlık"}))
    out = feed(client, h)
    assert (items(out)[0]["read"], out["unread"]) == (False, 1)
