"""LMS Module 8: Notifications: feedback set.

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


def test_t_not_01_a(client, librarian, branch_a):
    """T-NOT-01-a

    LIB-NOT-01. Member registered, then a copy is lent to them
    Expected: No notification after registration; after the loan exactly one loan_created with the loan's loan_id
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    assert notes(client, librarian, member["id"]) == []
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    got = notes(client, librarian, member["id"])
    assert [n["type"] for n in got] == ["loan_created"]
    assert got[0]["loan_id"] == data["loan"]["id"]
    assert got[0]["member_id"] == member["id"]


def test_t_not_01_c(client, clock, librarian, branch_a):
    """T-NOT-01-c

    LIB-NOT-01. Student loan due 2026-11-16 returned late on 2026-11-20 (one late fee)
    Expected: One loan_returned and one fee_created with the fee's fee_id
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-20")
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    fee = api.items(api.member_fees(client, librarian, data["member"]["id"]))[0]
    created = notes(client, librarian, data["member"]["id"], type="fee_created")
    assert [n["fee_id"] for n in created] == [fee["id"]]
    assert types(client, librarian, data["member"]["id"]).count("loan_returned") == 1


def test_t_not_01_e(client, admin, librarian, branch_a):
    """T-NOT-01-e

    LIB-NOT-01. Damage fee 20.00; payment 5.00; admin waives the fee
    Expected: One payment_received and one fee_waived (with fee_id)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    fee = api.items(api.member_fees(client, librarian, data["member"]["id"]))[0]
    api.pay(client, librarian, data["member"]["id"], "5.00")
    api.waive(client, admin, fee["id"])
    assert types(client, librarian, data["member"]["id"]).count("payment_received") == 1
    waived = notes(client, librarian, data["member"]["id"], type="fee_waived")
    assert [n["fee_id"] for n in waived] == [fee["id"]]


def test_t_not_01_g(client, librarian, branch_a, branch_b):
    """T-NOT-01-g

    LIB-NOT-01. S2 reserves K with pickup B; C1 returned at A (transfer to B)
    Expected: S2 gets one reservation_in_transit
    """
    # Book K: its only copy C1 is on loan to S1; S2 reserves K (pickup given below).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])

    api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_b["id"], member_id=s2["id"])
    api.return_loan(client, librarian, first["loan"]["id"], branch_id=branch_a["id"])
    assert types(client, librarian, s2["id"]) == ["reservation_in_transit"]


def test_t_not_01_i(client, librarian, branch_a):
    """T-NOT-01-i

    LIB-NOT-01. Waiting reservation cancelled by staff; another member cancels their own waiting reservation
    Expected: Staff cancel: one reservation_cancelled; member's own cancel: no notification
    """
    # Book K: its only copy C1 is on loan to S1; S2 reserves K (pickup given below).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])

    res = api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    api.post(client, f"/api/v1/reservations/{res['id']}/cancel", librarian, None, expect=200)
    assert types(client, librarian, s2["id"]) == ["reservation_cancelled"]
    s3 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    h3 = api.member_headers(client, s3)
    own = api.reserve(client, h3, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"])
    api.post(client, f"/api/v1/reservations/{own['id']}/cancel", h3, None, expect=200)
    assert types(client, librarian, s3["id"]) == []


def test_t_not_01_k(client, librarian, branch_a):
    """T-NOT-01-k

    LIB-NOT-01. Membership renewed
    Expected: One membership_renewed
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.post(client, f"/api/v1/members/{member['id']}/renew-membership", librarian, None, expect=200)
    assert types(client, librarian, member["id"]) == ["membership_renewed"]


def test_t_not_01_m(client, librarian, branch_a):
    """T-NOT-01-m

    LIB-NOT-01, LIB-TECH-08. A lending request that fails (409 COPY_NOT_AVAILABLE)
    Expected: No notification for the member
    """
    other = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.lend(client, librarian, member["id"], other["copy"]["id"], expect=409)
    assert notes(client, librarian, member["id"]) == []


def test_t_not_02_a(client, librarian, branch_a):
    """T-NOT-02-a

    LIB-NOT-02, LIB-COM-04. Book titled "Quiet Harbor Atlas" lent on 2026-11-02 (due 2026-11-16)
    Expected: loan_created message contains the title and "2026-11-16"
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    book = api.create_book(client, librarian, title="Quiet Harbor Atlas")
    copy = api.add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    api.lend(client, librarian, member["id"], copy["id"])
    message = notes(client, librarian, member["id"])[0]["message"]
    assert "Quiet Harbor Atlas" in message
    assert "2026-11-16" in message


def test_t_not_02_c(client, librarian, branch_a):
    """T-NOT-02-c

    LIB-NOT-02, LIB-COM-04. Reservation for "Distant Signal" ready on 2026-11-02 (hold_until 2026-11-05)
    Expected: reservation_ready message contains the title and "2026-11-05"
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    book = api.create_book(client, librarian, title="Distant Signal")
    copy = api.add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    loan = api.lend(client, librarian, member["id"], copy["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    message = notes(client, librarian, s2["id"])[0]["message"]
    assert "Distant Signal" in message
    assert "2026-11-05" in message


def test_t_not_02_e(client, librarian, branch_a):
    """T-NOT-02-e

    LIB-NOT-02, LIB-MEM-09. Membership (valid until 2027-11-01) renewed on 2026-11-02
    Expected: membership_renewed message contains the new valid_until "2028-10-31" (2027-11-01 + 365 days)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    renewed = api.post(client, f"/api/v1/members/{member['id']}/renew-membership", librarian, None, expect=200)
    assert renewed["valid_until"] == "2028-10-31"
    assert "2028-10-31" in notes(client, librarian, member["id"], type="membership_renewed")[0]["message"]


def test_t_not_03_a(client, clock, librarian, branch_a):
    """T-NOT-03-a

    LIB-NOT-03. Notifications created at 09:00, 10:00 and 11:00
    Expected: Ordered by created_at descending: loan_returned, loan_renewed, loan_created; created_at has offset +03:00
    """
    # member: loan_created (09:00), loan_renewed (10:00), loan_returned (11:00)
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.set_today(clock, "2026-11-02", hour=10)
    api.renew(client, librarian, data["loan"]["id"])
    api.set_today(clock, "2026-11-02", hour=11)
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    mh = api.member_headers(client, member)

    got = notes(client, mh, member["id"])
    assert [n["type"] for n in got] == ["loan_returned", "loan_renewed", "loan_created"]
    assert got[0]["created_at"].endswith("+03:00")


def test_t_not_03_c(client, clock, librarian, branch_a):
    """T-NOT-03-c

    LIB-NOT-03. Filter type=loan_created
    Expected: One item
    """
    # member: loan_created (09:00), loan_renewed (10:00), loan_returned (11:00)
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.set_today(clock, "2026-11-02", hour=10)
    api.renew(client, librarian, data["loan"]["id"])
    api.set_today(clock, "2026-11-02", hour=11)
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    mh = api.member_headers(client, member)

    assert types(client, mh, member["id"], type="loan_created") == ["loan_created"]


def test_t_not_03_e(client, clock, librarian, branch_a):
    """T-NOT-03-e

    LIB-NOT-03, LIB-COM-18. page_size=2, page 2
    Expected: One item (loan_created), total 3
    """
    # member: loan_created (09:00), loan_renewed (10:00), loan_returned (11:00)
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.set_today(clock, "2026-11-02", hour=10)
    api.renew(client, librarian, data["loan"]["id"])
    api.set_today(clock, "2026-11-02", hour=11)
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    mh = api.member_headers(client, member)

    page = api.get(client, f"/api/v1/members/{member['id']}/notifications", mh, params={"page_size": 2, "page": 2})
    assert [n["type"] for n in page["items"]] == ["loan_created"]
    assert page["total"] == 3


def test_t_not_03_g(client, librarian, branch_a):
    """T-NOT-03-g

    LIB-NOT-03. Two loans lent to the same member at the same time (09:00)
    Expected: Same created_at: ordered by id descending
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    got = notes(client, librarian, member["id"])
    assert got[0]["created_at"] == got[1]["created_at"]
    assert got[0]["id"] > got[1]["id"]


def test_t_not_04_a(client, clock, librarian, branch_a):
    """T-NOT-04-a

    LIB-NOT-04. Member marks own notification read at 2026-11-02 10:00
    Expected: 200 with the notification; read_at "2026-11-02T10:00:00+03:00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    mh = api.member_headers(client, member)
    note = notes(client, mh, member["id"])[0]

    api.set_today(clock, "2026-11-02", hour=10)
    read = api.post(client, f"/api/v1/notifications/{note['id']}/read", mh, None, expect=200)
    assert read["id"] == note["id"]
    assert read["read_at"] == "2026-11-02T10:00:00+03:00"


def test_t_not_04_c(client, librarian, branch_a):
    """T-NOT-04-c

    LIB-NOT-04. Member with 3 unread notifications calls read-all twice
    Expected: First {"updated": 3}, second {"updated": 0}; no unread left
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.renew(client, librarian, data["loan"]["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    mh = api.member_headers(client, member)
    path = f"/api/v1/members/{member['id']}/notifications/read-all"
    assert api.post(client, path, mh, None, expect=200) == {"updated": 3}
    assert api.post(client, path, mh, None, expect=200) == {"updated": 0}
    assert notes(client, mh, member["id"], unread="true") == []


def test_t_not_04_e(client, librarian, branch_a):
    """T-NOT-04-e

    LIB-NOT-04, LIB-AUTH-25. Another member marks the notification read
    Expected: 403 FORBIDDEN
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    mh = api.member_headers(client, member)
    note = notes(client, mh, member["id"])[0]

    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.post(client, f"/api/v1/notifications/{note['id']}/read", api.member_headers(client, other), None, expect=403)
    assert api.error_code(r) == "FORBIDDEN"


def test_t_not_04_g(client, librarian, branch_a):
    """T-NOT-04-g

    LIB-NOT-04, LIB-COM-28. Member marks unknown notification id 999999
    Expected: 404 NOT_FOUND
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.post(client, "/api/v1/notifications/999999/read", api.member_headers(client, member), None, expect=404)
    assert api.error_code(r) == "NOT_FOUND"


def test_t_not_05_a(client, clock, librarian, branch_a):
    """T-NOT-05-a

    LIB-NOT-05. Student loan due Monday 2026-11-16; reminders run on Friday 2026-11-13 (requirement example)
    Expected: {"due_reminders": 1, "overdue_notices": 0}; the member gets a due_reminder with the loan_id
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-13")
    assert run_reminders(client, librarian) == {"due_reminders": 1, "overdue_notices": 0}
    got = notes(client, librarian, data["member"]["id"], type="due_reminder")
    assert [n["loan_id"] for n in got] == [data["loan"]["id"]]


def test_t_not_05_c(client, clock, librarian, branch_a):
    """T-NOT-05-c

    LIB-NOT-05. Loan due 2026-11-16; reminders run on Thursday 2026-11-12 (next working day 2026-11-13)
    Expected: {"due_reminders": 0, "overdue_notices": 0}
    """
    api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-12")
    assert run_reminders(client, librarian) == {"due_reminders": 0, "overdue_notices": 0}


def test_t_not_05_e(client, clock, librarian, branch_a):
    """T-NOT-05-e

    LIB-NOT-05. Two loans due 2026-11-16, one already returned; one guest loan returned late; run on 2026-11-13
    Expected: Only the open loan: {"due_reminders": 1, "overdue_notices": 0}
    """
    open_loan = api.new_loan(client, librarian, branch_id=branch_a["id"])
    returned = api.new_loan(client, librarian, branch_id=branch_a["id"])
    guest = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest")
    api.return_loan(client, librarian, returned["loan"]["id"], branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-12")
    api.return_loan(client, librarian, guest["loan"]["id"], branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-13")
    assert run_reminders(client, librarian) == {"due_reminders": 1, "overdue_notices": 0}
    assert types(client, librarian, open_loan["member"]["id"], type="due_reminder") == ["due_reminder"]


def test_t_not_06_a(client, clock, librarian, branch_a):
    """T-NOT-06-a

    LIB-NOT-06. Reminders run twice on 2026-11-13 for a loan due 2026-11-16
    Expected: The member has exactly one due_reminder
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-13")
    run_reminders(client, librarian)
    run_reminders(client, librarian)
    assert types(client, librarian, data["member"]["id"], type="due_reminder") == ["due_reminder"]


def test_t_not_06_c(client, clock, librarian, branch_a):
    """T-NOT-06-c

    LIB-NOT-06. Loan due Monday 2026-11-16: reminders run on Friday 2026-11-13 and Saturday 2026-11-14
    Expected: One due_reminder (same due_date)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-13")
    run_reminders(client, librarian)
    api.set_today(clock, "2026-11-14")  # next working day after the 14th is also the 16th
    run_reminders(client, librarian)
    assert len(notes(client, librarian, data["member"]["id"], type="due_reminder")) == 1


def test_t_not_07_a(client, librarian, branch_a):
    """T-NOT-07-a

    LIB-NOT-07. Member with one unread notification marks it read
    Expected: {"unread": 1} before, {"unread": 0} after
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    mh = api.member_headers(client, member)
    note = notes(client, mh, member["id"])[0]

    path = f"/api/v1/members/{member['id']}/notifications/unread-count"
    assert api.get(client, path, mh) == {"unread": 1}
    api.post(client, f"/api/v1/notifications/{note['id']}/read", mh, None, expect=200)
    assert api.get(client, path, mh) == {"unread": 0}
