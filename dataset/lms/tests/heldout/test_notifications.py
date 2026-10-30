"""LMS Module 8: Notifications: held-out set.

Case table: ../cases/notifications.md. Requirements: ../../requirements.md.
Written before the code exists; fails at ``import lms`` until then.
"""

from support import api


def notes(client, headers, member_id, **params):
    """Notifications of a member, in list order (LIB-NOT-03)."""
    page = api.get(client, f"/api/v1/members/{member_id}/notifications", headers, params=params or None)
    return page["items"]


def types(client, headers, member_id, **params):
    return [n["type"] for n in notes(client, headers, member_id, **params)]


def run_reminders(client, headers):
    return api.post(client, "/api/v1/notifications/run-reminders", headers, None, expect=200)


def test_t_not_01_b(client, librarian, branch_a):
    """T-NOT-01-b

    LIB-NOT-01. Loan renewed, then returned on time
    Expected: Types (newest first): loan_returned, loan_renewed, loan_created
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.renew(client, librarian, data["loan"]["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert types(client, librarian, data["member"]["id"]) == ["loan_returned", "loan_renewed", "loan_created"]


def test_t_not_01_d(client, clock, librarian, branch_a):
    """T-NOT-01-d

    LIB-NOT-01. Loan reported lost on 2026-11-18 (three fees, LIB-E2E-04)
    Expected: One loan_lost and three fee_created (one per fee)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="180.00")
    api.set_today(clock, "2026-11-18")
    api.report_lost(client, librarian, data["loan"]["id"])
    got = types(client, librarian, data["member"]["id"])
    assert got.count("loan_lost") == 1
    assert got.count("fee_created") == 3


def test_t_not_01_f(client, librarian, branch_a):
    """T-NOT-01-f

    LIB-NOT-01. S2 reserves K with pickup A; C1 returned at A
    Expected: S2 gets one reservation_ready with the reservation_id; S2 has no other notification
    """
    # Book K: its only copy C1 is on loan to S1; S2 reserves K (pickup given below).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])

    res = api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    api.return_loan(client, librarian, first["loan"]["id"], branch_id=branch_a["id"])
    got = notes(client, librarian, s2["id"])
    assert [n["type"] for n in got] == ["reservation_ready"]
    assert got[0]["reservation_id"] == res["id"]


def test_t_not_01_h(client, clock, librarian, branch_a):
    """T-NOT-01-h

    LIB-NOT-01. S2's reservation ready on 2026-11-02 (hold_until 2026-11-05); process-expired on 2026-11-06
    Expected: S2 has reservation_expired (newest) and reservation_ready
    """
    # Book K: its only copy C1 is on loan to S1; S2 reserves K (pickup given below).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])

    api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    api.return_loan(client, librarian, first["loan"]["id"], branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-06")
    api.post(client, "/api/v1/reservations/process-expired", librarian, None, expect=200)
    assert types(client, librarian, s2["id"]) == ["reservation_expired", "reservation_ready"]


def test_t_not_01_j(client, librarian, branch_a):
    """T-NOT-01-j

    LIB-NOT-01. Member with a waiting reservation (no loans) is deactivated
    Expected: Notifications member_deactivated and reservation_cancelled (reason member_deactivated), one each
    """
    # Book K: its only copy C1 is on loan to S1; S2 reserves K (pickup given below).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])

    api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    api.deactivate_member(client, librarian, s2["id"])
    assert sorted(types(client, librarian, s2["id"])) == ["member_deactivated", "reservation_cancelled"]


def test_t_not_01_l(client, librarian, branch_a):
    """T-NOT-01-l

    LIB-NOT-01. Events without a notification: member updated, reservation created, member activated after deactivation
    Expected: Only member_deactivated is created
    """
    # Book K: its only copy C1 is on loan to S1; S2 reserves K (pickup given below).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])

    api.update_member(client, librarian, s2["id"], full_name="Renamed Member")
    res = api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    assert types(client, librarian, s2["id"]) == []
    api.post(client, f"/api/v1/reservations/{res['id']}/cancel", api.member_headers(client, s2), None, expect=200)
    api.deactivate_member(client, librarian, s2["id"])
    api.post(client, f"/api/v1/members/{s2['id']}/activate", librarian, None, expect=200)
    assert types(client, librarian, s2["id"]) == ["member_deactivated"]


def test_t_not_01_n(client, librarian, branch_a):
    """T-NOT-01-n

    LIB-NOT-01. S2's reservation ready, then S2 borrows the held copy (reservation fulfilled)
    Expected: S2 has loan_created and reservation_ready only (fulfilment creates none)
    """
    # Book K: its only copy C1 is on loan to S1; S2 reserves K (pickup given below).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])

    api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    api.return_loan(client, librarian, first["loan"]["id"], branch_id=branch_a["id"])
    api.lend(client, librarian, s2["id"], first["copy"]["id"])
    assert sorted(types(client, librarian, s2["id"])) == ["loan_created", "reservation_ready"]


def test_t_not_02_b(client, clock, librarian, branch_a):
    """T-NOT-02-b

    LIB-NOT-02, LIB-COM-13. Late fee of 8.00 created at return on 2026-11-20
    Expected: fee_created message contains "8.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-20")
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert "8.00" in notes(client, librarian, data["member"]["id"], type="fee_created")[0]["message"]


def test_t_not_02_d(client, librarian, branch_a):
    """T-NOT-02-d

    LIB-NOT-02, LIB-COM-13. Payment of 12.50
    Expected: payment_received message contains "12.50"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="30.00")
    api.pay(client, librarian, data["member"]["id"], "12.50")
    assert "12.50" in notes(client, librarian, data["member"]["id"], type="payment_received")[0]["message"]


def test_t_not_03_b(client, clock, librarian, branch_a):
    """T-NOT-03-b

    LIB-NOT-03. The member marks loan_renewed read; filters unread=true and unread=false
    Expected: unread=true → loan_returned, loan_created; unread=false → loan_renewed
    """
    # member: loan_created (09:00), loan_renewed (10:00), loan_returned (11:00)
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.set_today(clock, "2026-11-02", hour=10)
    api.renew(client, librarian, data["loan"]["id"])
    api.set_today(clock, "2026-11-02", hour=11)
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    mh = api.member_headers(client, member)

    renewed = notes(client, mh, member["id"], type="loan_renewed")[0]
    api.post(client, f"/api/v1/notifications/{renewed['id']}/read", mh, None, expect=200)
    assert types(client, mh, member["id"], unread="true") == ["loan_returned", "loan_created"]
    assert types(client, mh, member["id"], unread="false") == ["loan_renewed"]


def test_t_not_03_d(client, clock, librarian, branch_a):
    """T-NOT-03-d

    LIB-NOT-03, 14.2. Librarian reads GET /api/v1/notifications with member_id; a member calls the same endpoint
    Expected: Librarian: the member's 3 notifications; member: 403 FORBIDDEN
    """
    # member: loan_created (09:00), loan_renewed (10:00), loan_returned (11:00)
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.set_today(clock, "2026-11-02", hour=10)
    api.renew(client, librarian, data["loan"]["id"])
    api.set_today(clock, "2026-11-02", hour=11)
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    mh = api.member_headers(client, member)

    other = api.new_loan(client, librarian, branch_id=branch_a["id"])  # one more notification for another member
    page = api.get(client, "/api/v1/notifications", librarian, params={"member_id": member["id"]})
    assert [n["type"] for n in page["items"]] == ["loan_returned", "loan_renewed", "loan_created"]
    assert page["total"] == 3
    everything = api.get(client, "/api/v1/notifications", librarian)
    assert everything["total"] == 4
    assert other["member"]["id"] in {n["member_id"] for n in everything["items"]}
    assert api.error_code(api.get(client, "/api/v1/notifications", mh, expect=403)) == "FORBIDDEN"


def test_t_not_03_f(client, clock, librarian, branch_a):
    """T-NOT-03-f

    LIB-NOT-03, LIB-AUTH-25. Another member reads this member's notifications
    Expected: 403 FORBIDDEN
    """
    # member: loan_created (09:00), loan_renewed (10:00), loan_returned (11:00)
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.set_today(clock, "2026-11-02", hour=10)
    api.renew(client, librarian, data["loan"]["id"])
    api.set_today(clock, "2026-11-02", hour=11)
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    mh = api.member_headers(client, member)

    assert len(notes(client, mh, member["id"])) == 3  # own list: allowed
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.get(client, f"/api/v1/members/{member['id']}/notifications", api.member_headers(client, other), expect=403)
    assert api.error_code(r) == "FORBIDDEN"


def test_t_not_04_b(client, clock, librarian, branch_a):
    """T-NOT-04-b

    LIB-NOT-04. Marked read at 10:00, marked again at 11:00
    Expected: Second call 200; read_at stays "2026-11-02T10:00:00+03:00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    mh = api.member_headers(client, member)
    note = notes(client, mh, member["id"])[0]

    api.set_today(clock, "2026-11-02", hour=10)
    api.post(client, f"/api/v1/notifications/{note['id']}/read", mh, None, expect=200)
    api.set_today(clock, "2026-11-02", hour=11)
    again = api.post(client, f"/api/v1/notifications/{note['id']}/read", mh, None, expect=200)
    assert again["read_at"] == "2026-11-02T10:00:00+03:00"


def test_t_not_04_d(client, librarian, branch_a):
    """T-NOT-04-d

    LIB-NOT-04. The librarian marks a member's notification read
    Expected: 403 FORBIDDEN; read_at stays null
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    mh = api.member_headers(client, member)
    note = notes(client, mh, member["id"])[0]

    r = api.post(client, f"/api/v1/notifications/{note['id']}/read", librarian, None, expect=403)
    assert api.error_code(r) == "FORBIDDEN"
    assert notes(client, mh, member["id"])[0]["read_at"] is None


def test_t_not_04_f(client, librarian, branch_a):
    """T-NOT-04-f

    LIB-NOT-04. read-all for the member called by the librarian and by another member
    Expected: Both 403 FORBIDDEN; the notification stays unread
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    mh = api.member_headers(client, member)
    note = notes(client, mh, member["id"])[0]

    path = f"/api/v1/members/{member['id']}/notifications/read-all"
    assert api.error_code(api.post(client, path, librarian, None, expect=403)) == "FORBIDDEN"
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    assert api.error_code(api.post(client, path, api.member_headers(client, other), None, expect=403)) == "FORBIDDEN"
    assert [n["read_at"] for n in notes(client, mh, member["id"]) if n["id"] == note["id"]] == [None]


def test_t_not_05_b(client, clock, librarian, branch_a):
    """T-NOT-05-b

    LIB-NOT-05. Guest loan due 2026-11-09; reminders run on 2026-11-10
    Expected: {"due_reminders": 0, "overdue_notices": 1}; the member gets an overdue_notice
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest")
    api.set_today(clock, "2026-11-10")
    assert run_reminders(client, librarian) == {"due_reminders": 0, "overdue_notices": 1}
    assert types(client, librarian, data["member"]["id"], type="overdue_notice") == ["overdue_notice"]


def test_t_not_05_d(client, clock, librarian, branch_a):
    """T-NOT-05-d

    LIB-NOT-05. Student lent 2026-10-16 (due Friday 2026-10-30); reminders run on 2026-10-28 (29 Oct is a holiday)
    Expected: due_reminders 1 (next working day after 2026-10-28 is 2026-10-30)
    """
    api.set_today(clock, "2026-10-16")
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    assert data["loan"]["due_date"] == "2026-10-30"
    api.set_today(clock, "2026-10-28")
    assert run_reminders(client, librarian)["due_reminders"] == 1


def test_t_not_05_f(client, librarian, branch_a):
    """T-NOT-05-f

    LIB-NOT-05, 14.2. A member runs the reminders
    Expected: 403 FORBIDDEN
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.post(client, "/api/v1/notifications/run-reminders", api.member_headers(client, member), None, expect=403)
    assert api.error_code(r) == "FORBIDDEN"


def test_t_not_06_b(client, clock, librarian, branch_a):
    """T-NOT-06-b

    LIB-NOT-06. Overdue guest loan (due 2026-11-09): reminders run twice on 2026-11-10 and once on 2026-11-11
    Expected: Two overdue_notice in total (one per day)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest")
    api.set_today(clock, "2026-11-10")
    run_reminders(client, librarian)
    run_reminders(client, librarian)
    assert len(notes(client, librarian, data["member"]["id"], type="overdue_notice")) == 1
    api.set_today(clock, "2026-11-11")
    run_reminders(client, librarian)
    assert len(notes(client, librarian, data["member"]["id"], type="overdue_notice")) == 2


def test_t_not_06_d(client, clock, librarian, branch_a):
    """T-NOT-06-d

    LIB-NOT-06. Reminder on 2026-11-13 (due 2026-11-16); loan renewed on 2026-11-13 (due 2026-11-27); reminders run on 2026-11-26
    Expected: Two due_reminder (the new due date allows a new one)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-13")
    run_reminders(client, librarian)
    assert api.renew(client, librarian, data["loan"]["id"])["due_date"] == "2026-11-27"
    api.set_today(clock, "2026-11-26")
    run_reminders(client, librarian)
    assert len(notes(client, librarian, data["member"]["id"], type="due_reminder")) == 2


def test_t_not_07_b(client, librarian, branch_a):
    """T-NOT-07-b

    LIB-NOT-07, 14.2, LIB-AUTH-25. The librarian and another member read the unread count
    Expected: Librarian: {"unread": 1}; other member: 403 FORBIDDEN
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    mh = api.member_headers(client, member)
    note = notes(client, mh, member["id"])[0]

    path = f"/api/v1/members/{member['id']}/notifications/unread-count"
    assert note["read_at"] is None
    assert api.get(client, path, librarian) == {"unread": 1}
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    assert api.error_code(api.get(client, path, api.member_headers(client, other), expect=403)) == "FORBIDDEN"
