MODULE = "messaging"
TITLE = "module 27 (Announcements and messages)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- announcements
    dict(id="T-MSG-01-a", req="LIB-MSG-01", type="Normal", input="Librarian creates an announcement with only title and body", expected="201 `draft`; all four types, `normal`, not pinned, `publish_at` now, no expiry, all branches", code='''
def TEST(client, librarian):
    a = ann(client, librarian, title="Kütüphane Haftası", body="Etkinlik programı yayında.")
    assert (a["title"], a["body"], a["status"], a["priority"], a["pinned"], a["branch_id"], a["expires_at"], a["published_at"]) == ("Kütüphane Haftası", "Etkinlik programı yayında.", "draft", "normal", False, None, None, None)
    assert set(a["audience"]) == ALL_TYPES and same(a["publish_at"], MON, 9)
'''),
    dict(id="T-MSG-01-b", req="LIB-MSG-01", type="Error", input="Empty body; audience []; audience [kids]; a type twice; expiry before `publish_at`; expiry 91 days later; unknown branch; inactive branch; a member creates", expected="`422` seven times; `409 BRANCH_INACTIVE`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    bad = [dict(body=""), dict(audience=[]), dict(audience=["kids"]), dict(audience=["student", "student"]),
           dict(publish_at=ts(MON, 10), expires_at=ts(MON, 9)), dict(publish_at=ts(MON, 10), expires_at=ts("2027-02-01", 10)), dict(branch_id=999999)]
    for fields in bad:
        assert try_ann(client, librarian, **fields).status_code == 422, fields
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_ann(client, librarian, branch_id=qq["id"]), 409, "BRANCH_INACTIVE")
    assert try_ann(client, mh(client, member(client, librarian, branch_a))).status_code == 403
'''),
    dict(id="T-MSG-01-c", req="LIB-MSG-01", type="Boundary", input="Expiry exactly 90 days after `publish_at` (2026-11-02 09:00 → 2027-01-31 09:00)", expected="201", code='''
def TEST(client, librarian):
    ann(client, librarian, publish_at=ts(MON), expires_at=ts("2027-01-31"))
'''),
    dict(id="T-MSG-02-a", req="LIB-MSG-02", type="Error", input="Change a draft's title; a live announcement's `publish_at`; a withdrawn one's title", expected="200; `409 ANNOUNCEMENT_LIVE`; `409 INVALID_ANNOUNCEMENT_STATUS` with `details.status` `withdrawn`", code='''
def TEST(client, librarian):
    d = ann(client, librarian)
    assert ok(client.patch(f"/api/v1/announcements/{d['id']}", headers=librarian, json={"title": "Yeni"}))["title"] == "Yeni"
    a = live(client, librarian)
    err(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"publish_at": ts("2026-11-05")}), 409, "ANNOUNCEMENT_LIVE")
    ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    assert err(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"title": "X"}), 409, "INVALID_ANNOUNCEMENT_STATUS")["details"]["status"] == "withdrawn"
'''),
    dict(id="T-MSG-02-b", req="LIB-MSG-02", type="Normal", input="A live announcement read by a member; its body changed; its priority changed", expected="Stats `reads` 1, then 0 after the body change; the priority change keeps marks", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-MSG-03-a", req="LIB-MSG-03", type="Error", input="Publish a draft; publish again; publish one whose expiry (08:30) has passed", expected="200 `published` with `published_at` now; `INVALID_ANNOUNCEMENT_STATUS`; `ANNOUNCEMENT_EXPIRED`", code='''
def TEST(client, librarian):
    a = ann(client, librarian)
    out = ok(publish(client, librarian, a))
    assert out["status"] == "published" and same(out["published_at"], MON, 9)
    err(publish(client, librarian, a), 409, "INVALID_ANNOUNCEMENT_STATUS")
    old = ann(client, librarian, publish_at=ts(MON, 8), expires_at=ts(MON, 8, 30))
    err(publish(client, librarian, old), 409, "ANNOUNCEMENT_EXPIRED")
'''),
    dict(id="T-MSG-03-b", req="LIB-MSG-03", type="Boundary", input="Three live pinned announcements for branch A; a fourth pinned one for A", expected="`409 PIN_LIMIT_REACHED` with `details.limit` 3", code='''
def TEST(client, librarian, branch_a):
    for _ in range(3):
        live(client, librarian, branch_id=branch_a["id"], pinned=True)
    assert err(publish(client, librarian, ann(client, librarian, branch_id=branch_a["id"], pinned=True)), 409, "PIN_LIMIT_REACHED")["details"]["limit"] == 3
'''),
    dict(id="T-MSG-04-a", req="LIB-MSG-04", type="Normal", input="Announcement with `publish_at` 2026-11-03 09:00 published on Mon; a member's feed on Mon; process and feed on 2026-11-03 09:00", expected="Mon: `published_at` null and not in the feed; Tue: `published_at` 09:00 and in the feed", code='''
def TEST(client, clock, librarian, branch_a):
    a = ok(publish(client, librarian, ann(client, librarian, publish_at=ts("2026-11-03"))))
    assert (a["status"], a["published_at"]) == ("published", None)
    h = mh(client, member(client, librarian, branch_a))
    assert feed(client, h)["total"] == 0
    at(clock, "2026-11-03")
    process(client, librarian)
    assert same(get(client, librarian, f"announcements/{a['id']}")["published_at"], "2026-11-03", 9)
    assert [x["id"] for x in items(feed(client, h))] == [a["id"]]
'''),
    dict(id="T-MSG-05-a", req="LIB-MSG-05", type="Normal", input="A live announcement withdrawn; a member reads it; withdrawn again", expected="200 `withdrawn` with `withdrawn_at`; `404`; `409 INVALID_ANNOUNCEMENT_STATUS`", code='''
def TEST(client, librarian, branch_a):
    a = live(client, librarian)
    out = ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    assert out["status"] == "withdrawn" and same(out["withdrawn_at"], MON, 9)
    assert client.get(f"/api/v1/announcements/{a['id']}", headers=mh(client, member(client, librarian, branch_a))).status_code == 404
    err(post(client, librarian, f"announcements/{a['id']}/withdraw"), 409, "INVALID_ANNOUNCEMENT_STATUS")
'''),
    dict(id="T-MSG-06-a", req="LIB-MSG-06", type="Normal", input="Important announcement for students of A published now; a student of A, an academic of A, a student of B; a normal announcement", expected="One `announcement` notification with `announcement_id` for the student of A only; none for the normal one", code='''
def TEST(client, librarian, branch_a, branch_b):
    s, a, sb = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic"), member(client, librarian, branch_b)
    x = live(client, librarian, branch_id=branch_a["id"], audience=["student"], priority="important", title="Kapanış saati değişti")
    live(client, librarian, branch_id=branch_a["id"], audience=["student"])
    ns = notes(client, librarian, s["id"], "announcement")
    assert len(ns) == 1 and ns[0]["announcement_id"] == x["id"] and "Kapanış saati değişti" in ns[0]["message"]
    assert [len(notes(client, librarian, m["id"], "announcement")) for m in (a, sb)] == [0, 0]
'''),
    dict(id="T-MSG-07-a", req="LIB-MSG-07", type="Normal", input="Two scheduled announcements (Tue 09:00 and Wed 09:00); process on Tue 10:00 and again", expected="`announcements_released` 1, then 0", code='''
def TEST(client, clock, librarian):
    for day in ("2026-11-03", "2026-11-04"):
        ok(publish(client, librarian, ann(client, librarian, publish_at=ts(day))))
    at(clock, "2026-11-03", 10)
    assert process(client, librarian)["announcements_released"] == 1
    assert process(client, librarian)["announcements_released"] == 0
'''),
    dict(id="T-MSG-08-a", req="LIB-MSG-08", type="Boundary", input="Important announcement for students, `publish_at` 2026-11-03 09:00, published on Mon with an active student; process at 08:59 and 09:00", expected="No notification on Mon; `announcements_released` 0, then 1 with one notification", code='''
def TEST(client, clock, librarian, branch_a):
    s = member(client, librarian, branch_a)
    ok(publish(client, librarian, ann(client, librarian, audience=["student"], priority="important", publish_at=ts("2026-11-03"))))
    assert len(notes(client, librarian, s["id"], "announcement")) == 0
    at(clock, "2026-11-03", 8, 59)
    assert process(client, librarian)["announcements_released"] == 0
    at(clock, "2026-11-03", 9, 0)
    assert process(client, librarian)["announcements_released"] == 1
    assert len(notes(client, librarian, s["id"], "announcement")) == 1
'''),
    dict(id="T-MSG-09-a", req="LIB-MSG-09", type="Normal", input="Live A1 (09:00), pinned A2 (published 10:00 with `publish_at` 08:00), A3 (10:00); one for academics only; the member reads A3", expected="Feed [A2, A3, A1] with `read` only on A3; `unread` 2; the academic one `404`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-MSG-10-a", req="LIB-MSG-10", type="Normal", input="Draft D, live L, scheduled S (Wed), withdrawn W; staff list; `status=published`; `live=true`; `scheduled=true`", expected="[W, S, L, D]; [S, L]; [L]; [S]", code='''
def TEST(client, librarian):
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
'''),
    dict(id="T-MSG-11-a", req="LIB-MSG-11", type="Error", input="Member marks a live announcement read at 09:00 and again at 10:00; marks a draft", expected="200 `{announcement_id, read_at 09:00}` both times; `404`", code='''
def TEST(client, clock, librarian, branch_a):
    a = live(client, librarian)
    h = mh(client, member(client, librarian, branch_a))
    first = ok(post(client, h, f"announcements/{a['id']}/read"))
    at(clock, MON, 10)
    again = ok(post(client, h, f"announcements/{a['id']}/read"))
    assert first["announcement_id"] == a["id"] and same(first["read_at"], MON, 9) and same(again["read_at"], MON, 9)
    assert post(client, h, f"announcements/{ann(client, librarian)['id']}/read").status_code == 404
'''),
    dict(id="T-MSG-12-a", req="LIB-MSG-12", type="Normal", input="Announcement for students of A with 3 students of A (2 read it), a passive student and a student of B; an announcement for guests with no guests", expected="`{audience_size 3, reads 2, read_rate 66.7}`; `{0, 0, 0.0}`", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-MSG-13-a", req="LIB-MSG-13", type="Normal", input="Announcement for A and [student, academic]; a student and an academic of A, a student of B, a guest of A", expected="In the feeds of the first two only", code='''
def TEST(client, librarian, branch_a, branch_b):
    a = live(client, librarian, branch_id=branch_a["id"], audience=["student", "academic"])
    people = [member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic"),
              member(client, librarian, branch_b), member(client, librarian, branch_a, membership_type="guest")]
    assert [[x["id"] for x in items(feed(client, mh(client, m)))] for m in people] == [[a["id"]], [a["id"]], [], []]
'''),
    # ---------------------------------------------------------------- threads
    dict(id="T-MSG-14-a", req="LIB-MSG-14", type="Normal", input="A member writes to branch A about a general question", expected="201 `open` with `created_at`, one message by `member`; staff writing → `403`; an empty subject → `422`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    t = thread(client, h, branch_a, subject="Çalışma saatleri", body="Pazar açık mısınız?")
    assert (t["member_id"], t["branch_id"], t["subject"], t["category"], t["status"]) == (m["id"], branch_a["id"], "Çalışma saatleri", "general", "open") and same(t["created_at"], MON, 9)
    assert [(x["author"], x["body"]) for x in t["messages"]] == [("member", "Pazar açık mısınız?")]
    assert try_thread(client, librarian, branch_a).status_code == 403
    assert try_thread(client, h, branch_a, subject="").status_code == 422
'''),
    dict(id="T-MSG-15-a", req="LIB-MSG-15", type="Error", input="A passive member writes; a thread to an inactive branch; a member with 3 threads not closed writes a fourth; after closing one", expected="`MEMBER_PASSIVE`; `BRANCH_INACTIVE`; `THREAD_LIMIT_REACHED` with `details.limit` 3; 201", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-MSG-16-a", req="LIB-MSG-16", type="Normal", input="T1 (09:00) and T2 (10:00) of M, staff reply to T1 at 11:00; M lists; another member lists; staff list `status=answered`", expected="M: [T1, T2] with T1 `unread` 1; other member: empty; staff: [T1]", code='''
def TEST(client, clock, librarian, branch_a):
    t1, m, h = asked(client, librarian, branch_a)
    at(clock, MON, 10)
    t2 = thread(client, h, branch_a)
    at(clock, MON, 11)
    ok(reply(client, librarian, t1), 201)
    rows = items(get(client, h, "threads"))
    assert [(r["id"], r["unread"]) for r in rows] == [(t1["id"], 1), (t2["id"], 0)]
    assert get(client, mh(client, member(client, librarian, branch_a)), "threads")["total"] == 0
    assert [r["id"] for r in items(get(client, librarian, "threads", status="answered"))] == [t1["id"]]
'''),
    dict(id="T-MSG-17-a", req="LIB-MSG-17", type="Normal", input="Thread with an internal note and a staff reply; the member reads it; reads the list; another member reads it", expected="Member sees 2 messages (no internal note); afterwards `unread` 0; `404`", code='''
def TEST(client, librarian, branch_a):
    t, m, h = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t, "Not: kontrol et", internal=True), 201)
    ok(reply(client, librarian, t, "Pazar kapalıyız."), 201)
    out = read_thread(client, h, t)
    assert [(x["author"], x["body"]) for x in out["messages"]] == [("member", "Merhaba, bir sorum var."), ("staff", "Pazar kapalıyız.")]
    assert items(get(client, h, "threads"))[0]["unread"] == 0
    assert client.get(f"/api/v1/threads/{t['id']}", headers=mh(client, member(client, librarian, branch_a))).status_code == 404
'''),
    dict(id="T-MSG-18-a", req="LIB-MSG-18", type="Error", input="A member sends `internal` true; replies to a closed thread", expected="`422`; `409 THREAD_CLOSED`", code='''
def TEST(client, librarian, branch_a):
    t, _, h = asked(client, librarian, branch_a)
    assert reply(client, h, t, internal=True).status_code == 422
    ok(step(client, librarian, t, "close"))
    err(reply(client, h, t), 409, "THREAD_CLOSED")
'''),
    dict(id="T-MSG-19-a", req="LIB-MSG-19", type="Normal", input="Thread opened Mon 09:00; internal note 10:00; staff reply 11:00; member reply 12:00", expected="`open` (no notification); `answered` with `first_reply_at` 11:00 and one `message_reply`; `open` with `due_at` Wed 12:00", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-MSG-20-a", req="LIB-MSG-20", type="Error", input="Thread of category `loan` with another member's loan; with own loan; `loan_id` in category `general`; `fee_id` of another member", expected="`409 NOT_OWN_RECORD` with `details.field` `loan_id`; 201; `422`; `NOT_OWN_RECORD` with `fee_id`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-MSG-21-a", req="LIB-MSG-21", type="Normal", input="A member's thread about own fee of 10.00; staff read it", expected="`member` with `member_no`, `full_name`, `membership_type`; `fee` with kind, amount, status", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    cp = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    return_loan(client, librarian, lend(client, librarian, m["id"], cp["id"])["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    t = thread(client, mh(client, m), branch_a, category="fee", fee_id=fee["id"])
    out = read_thread(client, librarian, t)
    assert out["member"] == {"id": m["id"], "member_no": m["member_no"], "full_name": m["full_name"], "membership_type": "student"}
    assert (out["fee"]["id"], out["fee"]["kind"], out["fee"]["amount"], out["fee"]["status"]) == (fee["id"], "damage_fee", "10.00", "open")
'''),
    dict(id="T-MSG-22-a", req="LIB-MSG-22", type="Boundary", input="A thread's first message plus 9 member replies on Mon; an 11th; one more on Tue; staff reply many times", expected="`409 MESSAGE_LIMIT_REACHED` with `details.limit` 10 on the 11th; Tue 201; staff 201", code='''
def TEST(client, clock, librarian, branch_a):
    t, _, h = asked(client, librarian, branch_a)
    for _ in range(9):
        ok(reply(client, h, t), 201)
    assert err(reply(client, h, t), 409, "MESSAGE_LIMIT_REACHED")["details"]["limit"] == 10
    for _ in range(12):
        ok(reply(client, librarian, t), 201)
    at(clock, "2026-11-03")
    ok(reply(client, h, t), 201)
'''),
    # ---------------------------------------------------------------- response time, assignment, closing
    dict(id="T-MSG-23-a", req="LIB-MSG-23", type="Boundary", input="Thread opened Fri 2026-11-06 16:00; overdue list on Tue 2026-11-10 16:00 and 16:00:01", expected="`due_at` Tue 16:00; not overdue, then overdue", code='''
def TEST(client, clock, librarian, branch_a):
    at(clock, "2026-11-06", 16)
    t, _, _ = asked(client, librarian, branch_a)
    assert same(t["due_at"], "2026-11-10", 16)
    at(clock, "2026-11-10", 16, 0, 0)
    assert get(client, librarian, "threads", overdue="true")["total"] == 0
    at(clock, "2026-11-10", 16, 0, 1)
    assert [r["id"] for r in items(get(client, librarian, "threads", overdue="true"))] == [t["id"]]
'''),
    dict(id="T-MSG-24-a", req="LIB-MSG-24", type="Error", input="Assign to another librarian; filter `assigned_to=me` for both; assign to a member's user; remove; assign a closed thread", expected="200; listed only for the assignee; `422`; `assigned_to` null; `409 THREAD_CLOSED`", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-MSG-25-a", req="LIB-MSG-25", type="Normal", input="Unassigned thread: an internal note by librarian L1, a reply by L2", expected="`assigned_to` L2", code='''
def TEST(client, admin, librarian, branch_a):
    t, _, _ = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t, internal=True), 201)
    assert read_thread(client, librarian, t)["assigned_to"] is None
    u, uh = staff_user(client, admin)
    ok(reply(client, uh, t), 201)
    assert read_thread(client, librarian, t)["assigned_to"] == u["id"]
'''),
    dict(id="T-MSG-26-a", req="LIB-MSG-26", type="Normal", input="Member closes own thread; closes again; staff close another", expected="200 `closed` with `member_request` and `closed_at`; `409 THREAD_CLOSED`; `staff_request`", code='''
def TEST(client, librarian, branch_a):
    t, _, h = asked(client, librarian, branch_a)
    out = ok(step(client, h, t, "close"))
    assert (out["status"], out["close_reason"]) == ("closed", "member_request") and same(out["closed_at"], MON, 9)
    err(step(client, h, t, "close"), 409, "THREAD_CLOSED")
    t2 = thread(client, h, branch_a)
    assert ok(step(client, librarian, t2, "close"))["close_reason"] == "staff_request"
'''),
    dict(id="T-MSG-27-a", req="LIB-MSG-27", type="Boundary", input="Thread closed Mon 09:00: reopened on 2026-11-16 09:00; another closed Mon reopened on 2026-11-16 09:00:01; reopen an open thread", expected="200 `open` with a new `due_at`; `409 THREAD_REOPEN_NOT_ALLOWED`; `409 THREAD_NOT_CLOSED`", code='''
def TEST(client, clock, librarian, branch_a):
    t1, _, h = asked(client, librarian, branch_a)
    t2 = thread(client, h, branch_a)
    ok(step(client, h, t1, "close")); ok(step(client, h, t2, "close"))
    at(clock, "2026-11-16", 9, 0, 0)
    out = ok(step(client, h, t1, "reopen"))
    assert (out["status"], out["close_reason"], out["closed_at"]) == ("open", None, None) and same(out["due_at"], "2026-11-18", 9)
    err(step(client, h, t1, "reopen"), 409, "THREAD_NOT_CLOSED")
    at(clock, "2026-11-16", 9, 0, 1)
    err(step(client, h, t2, "reopen"), 409, "THREAD_REOPEN_NOT_ALLOWED")
'''),
    dict(id="T-MSG-28-a", req="LIB-MSG-28", type="Normal", input="An answered thread silent for 15 days, an open one and an answered one with a member reply on day 10; process on 2026-11-17", expected="`threads_closed` 1; the first `closed` with `inactive`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-MSG-29-a", req="LIB-MSG-29", type="Boundary", input="Staff reply on Mon 09:00; process on 2026-11-16 09:00 and 09:00:01", expected="`threads_closed` 0, then 1", code='''
def TEST(client, clock, librarian, branch_a):
    t, _, _ = asked(client, librarian, branch_a)
    ok(reply(client, librarian, t), 201)
    at(clock, "2026-11-16", 9, 0, 0)
    assert process(client, librarian)["threads_closed"] == 0
    at(clock, "2026-11-16", 9, 0, 1)
    assert process(client, librarian)["threads_closed"] == 1
'''),
    dict(id="T-MSG-30-a", req="LIB-MSG-30", type="Error", input="Rate an open thread; a closed thread without staff reply; a closed answered thread with 4; again; rating 6", expected="`THREAD_NOT_CLOSED`; `NOTHING_TO_RATE`; 200 `rating` 4; `ALREADY_RATED`; `422`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-MSG-31-a", req="LIB-MSG-31", type="Normal", input="Thread opened Mon 09:00 (due Wed 09:00); overdue list on Wed 14:59", expected="`overdue_by_hours` 5", code='''
def TEST(client, clock, librarian, branch_a):
    t, _, _ = asked(client, librarian, branch_a)
    at(clock, "2026-11-04", 14, 59)
    rows = items(get(client, librarian, "threads", overdue="true"))
    assert [(r["id"], r["is_overdue"], r["overdue_by_hours"]) for r in rows] == [(t["id"], True, 5)]
'''),
    # ---------------------------------------------------------------- effects
    dict(id="T-MSG-32-a", req="LIB-MSG-32", type="Normal", input="Member with an open thread is deactivated; tries to reopen it", expected="`closed` with `member_deactivated`; `409`", code='''
def TEST(client, librarian, branch_a):
    t, m, h = asked(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    out = read_thread(client, librarian, t)
    assert (out["status"], out["close_reason"]) == ("closed", "member_deactivated")
    assert step(client, h, t, "reopen").status_code == 409
'''),
    dict(id="T-MSG-33-a", req="LIB-MSG-33", type="Normal", input="Member with 2 live announcements (1 read), 2 open threads and one unread staff reply plus an internal note", expected="`{unread_announcements 1, open_threads 2, unread_replies 1}`", code='''
def TEST(client, librarian, branch_a):
    a1 = live(client, librarian)
    live(client, librarian)
    t, m, h = asked(client, librarian, branch_a)
    thread(client, h, branch_a)
    ok(post(client, h, f"announcements/{a1['id']}/read"))
    ok(reply(client, librarian, t), 201)
    ok(reply(client, librarian, t, internal=True), 201)
    assert get(client, librarian, f"members/{m['id']}/summary")["messages"] == {"unread_announcements": 1, "open_threads": 2, "unread_replies": 1}
'''),
    dict(id="T-MSG-34-a", req="LIB-MSG-34", type="Error", input="Branch QQ (no copies, no members) with a member's open thread; after closing it, with a live announcement for QQ; after withdrawing it", expected="`BRANCH_IN_USE` twice; then 200", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-MSG-35-a", req="LIB-MSG-35", type="Normal", input="Announcement for academics; a student reads the feed; becomes academic; reads again", expected="Empty; then the announcement", code='''
def TEST(client, librarian, branch_a):
    a = live(client, librarian, audience=["academic"])
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    assert feed(client, h)["total"] == 0
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "academic"}))
    assert [x["id"] for x in items(feed(client, h))] == [a["id"]]
'''),
    dict(id="T-MSG-36-a", req="LIB-MSG-36", type="Normal", input="Thread assigned to librarian U; U's user is deactivated", expected="`assigned_to` null", code='''
def TEST(client, admin, librarian, branch_a):
    t, _, _ = asked(client, librarian, branch_a)
    u, _ = staff_user(client, admin)
    ok(step(client, librarian, t, "assign", {"user_id": u["id"]}))
    ok(client.patch(f"/api/v1/users/{u['id']}", headers=admin, json={"is_active": False}))
    assert read_thread(client, librarian, t)["assigned_to"] is None
'''),
    dict(id="T-MSG-37-a", req="LIB-MSG-37", type="Normal", input="A member writes, closes, reopens and rates a thread; a normal announcement is published for them", expected="No notification", code='''
def TEST(client, librarian, branch_a):
    t, m, h = asked(client, librarian, branch_a)
    ok(step(client, h, t, "close"))
    ok(step(client, h, t, "reopen"))
    live(client, librarian)
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0
'''),
    dict(id="T-MSG-38-a", req="LIB-MSG-38", type="Normal", input="Announcement created, changed, published, withdrawn; thread created, message added, assigned, closed, reopened, closed again, rated; process; audit log", expected="One entry per event (2 for `thread_closed`, at least 2 for `thread_message_added`)", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-MSG-39-a", req="LIB-MSG-39", type="Normal", input="Threads: T1 loan (replied after 2 hours, closed, rated 4), T2 general (replied after 1 hour, rated 5), T3 other (no reply, overdue on Thu); an important and a normal announcement with 1 read; report 2026-11-02 – 2026-11-08 on Thu", expected="`threads` 3, `by_category` loan 1, general 1, other 1; `answered` 2; `average_first_reply_hours` 1.5; `overdue_now` 1; `closed` 2; `average_rating` 4.5; announcements `{published 2, important 1, reads 1}`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-MSG-39-b", req="LIB-MSG-39", type="Error", input="`from` > `to`; 367 days; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/messaging"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403
'''),
    dict(id="T-MSG-40-a", req="LIB-MSG-40", type="Normal", input="An announcement and a thread exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, librarian, branch_a):
    live(client, librarian)
    asked(client, librarian, branch_a)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
    dict(id="T-MSG-41-a", req="LIB-MSG-41", type="Error", input="A withdrawn announcement: changed, published, withdrawn", expected="`409 INVALID_ANNOUNCEMENT_STATUS` each", code='''
def TEST(client, librarian):
    a = live(client, librarian)
    ok(post(client, librarian, f"announcements/{a['id']}/withdraw"))
    err(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"title": "X"}), 409, "INVALID_ANNOUNCEMENT_STATUS")
    err(publish(client, librarian, a), 409, "INVALID_ANNOUNCEMENT_STATUS")
    err(post(client, librarian, f"announcements/{a['id']}/withdraw"), 409, "INVALID_ANNOUNCEMENT_STATUS")
'''),
    dict(id="T-MSG-42-a", req="LIB-MSG-42", type="Normal", input="Process with nothing to do", expected="200 `{announcements_released 0, threads_closed 0}`", code='''
def TEST(client, librarian):
    out = process(client, librarian)
    assert (out["announcements_released"], out["threads_closed"]) == (0, 0)
'''),
    dict(id="T-MSG-43-a", req="LIB-MSG-43", type="Normal", input="Announcement expiring Mon 10:00, pinned for A, with 2 other pinned for A; at 10:00 staff list `live=false` and a member's feed; another pinned one for A published", expected="Still `published` and in `live=false`; not in the feed; the new pinned one 200", code='''
def TEST(client, clock, librarian, branch_a):
    e = live(client, librarian, branch_id=branch_a["id"], pinned=True, expires_at=ts(MON, 10))
    live(client, librarian, branch_id=branch_a["id"], pinned=True)
    live(client, librarian, branch_id=branch_a["id"], pinned=True)
    at(clock, MON, 10)
    assert get(client, librarian, f"announcements/{e['id']}")["status"] == "published"
    assert e["id"] in [x["id"] for x in items(feed(client, librarian, live="false"))]
    assert e["id"] not in [x["id"] for x in items(feed(client, mh(client, member(client, librarian, branch_a))))]
    ok(publish(client, librarian, ann(client, librarian, branch_id=branch_a["id"], pinned=True)))
'''),
    dict(id="T-MSG-44-a", req="LIB-MSG-44", type="Normal", input="Branch A has 3 live pinned announcements; a pinned one for all branches; a pinned one for B", expected="200 both", code='''
def TEST(client, librarian, branch_a, branch_b):
    for _ in range(3):
        live(client, librarian, branch_id=branch_a["id"], pinned=True)
    live(client, librarian, pinned=True)
    live(client, librarian, branch_id=branch_b["id"], pinned=True)
'''),
    dict(id="T-MSG-45-a", req="LIB-MSG-45", type="Normal", input="Thread assigned to L1; librarian L2 replies", expected="`assigned_to` stays L1; the thread `answered`", code='''
def TEST(client, admin, librarian, branch_a):
    t, _, _ = asked(client, librarian, branch_a)
    u, uh = staff_user(client, admin)
    ok(step(client, librarian, t, "assign", {"user_id": me(client, librarian)}))
    ok(reply(client, uh, t), 201)
    out = read_thread(client, librarian, t)
    assert (out["assigned_to"], out["status"]) == (me(client, librarian), "answered")
'''),
    dict(id="T-MSG-46-a", req="LIB-MSG-46", type="Normal", input="Pinned announcement published Mon 09:00; three normal ones published later on Mon", expected="The pinned one first in the member's feed", code='''
def TEST(client, clock, librarian, branch_a):
    p = live(client, librarian, pinned=True)
    for hh in (10, 11, 12):
        at(clock, MON, hh)
        live(client, librarian)
    assert items(feed(client, mh(client, member(client, librarian, branch_a))))[0]["id"] == p["id"]
'''),
    dict(id="T-MSG-47-a", req="LIB-MSG-47", type="Normal", input="A member reads a live announcement; its title is changed", expected="`read` false again and `unread` 1", code='''
def TEST(client, librarian, branch_a):
    a = live(client, librarian)
    h = mh(client, member(client, librarian, branch_a))
    ok(post(client, h, f"announcements/{a['id']}/read"))
    assert feed(client, h)["unread"] == 0
    ok(client.patch(f"/api/v1/announcements/{a['id']}", headers=librarian, json={"title": "Yeni başlık"}))
    out = feed(client, h)
    assert (items(out)[0]["read"], out["unread"]) == (False, 1)
'''),
]
