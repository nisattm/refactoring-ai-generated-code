"""LMS Module 5: Loans and returns: held-out set.

Case table: ../cases/loans.md. Requirements: ../../requirements.md.
Written before the code exists; fails at ``import lms`` until then.
"""

from support import api


def test_t_loan_01_b(client, librarian, branch_a):
    """T-LOAN-01-b

    LIB-LOAN-01. Lend by barcode instead of copy_id
    Expected: 201; the loan refers to the copy with that barcode
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.post(client, "/api/v1/loans", librarian,
                    {"member_id": member["id"], "barcode": copy["barcode"]}, expect=201)
    assert loan["copy_id"] == copy["id"]
    assert api.get_copy(client, librarian, copy["id"])["status"] == "on_loan"


def test_t_loan_01_d(client, librarian, branch_a):
    """T-LOAN-01-d

    LIB-LOAN-01. Neither copy_id nor barcode
    Expected: 422 VALIDATION_ERROR; copy stays available
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.post(client, "/api/v1/loans", librarian, {"member_id": member["id"]}, expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.get_copy(client, librarian, copy["id"])["status"] == "available"


def test_t_loan_01_f(client, librarian, branch_a):
    """T-LOAN-01-f

    LIB-LOAN-01, LIB-COM-29. Unknown copy_id 999999
    Expected: 404 NOT_FOUND, details {"field": "copy_id", "id": 999999}
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], 999999, expect=404)
    assert api.error_code(r) == "NOT_FOUND"
    assert r["error"]["details"] == {"field": "copy_id", "id": 999999}


def test_t_loan_02_b(client, clock, librarian, branch_a):
    """T-LOAN-02-b

    LIB-LOAN-02. Same loan read on 2026-11-17
    Expected: is_overdue true
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-17")
    assert api.get_loan(client, librarian, loan["id"])["is_overdue"] is True


def test_t_loan_03_b(client, clock, librarian, branch_a):
    """T-LOAN-03-b

    LIB-LOAN-03. Academic, lent 2026-12-02
    Expected: due_date 2027-01-04 (requirement example: 2027-01-01 holiday, 2-3 Jan weekend)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="academic")
    api.set_today(clock, "2026-12-02")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.lend(client, librarian, member["id"], copy["id"])
    # requirement example: 2027-01-01 holiday, 2-3 Jan weekend
    assert loan["loan_date"] == "2026-12-02"
    assert loan["due_date"] == "2027-01-04"


def test_t_loan_03_d(client, clock, librarian, branch_a):
    """T-LOAN-03-d

    LIB-LOAN-03. Guest, lent 2026-11-02
    Expected: due_date 2026-11-09 (2026-11-02 + 7 days = Monday 2026-11-09)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    api.set_today(clock, "2026-11-02")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.lend(client, librarian, member["id"], copy["id"])
    # 2026-11-02 + 7 days = Monday 2026-11-09
    assert loan["loan_date"] == "2026-11-02"
    assert loan["due_date"] == "2026-11-09"


def test_t_loan_04_b(client, clock, librarian, branch_a):
    """T-LOAN-04-b

    LIB-LOAN-04. After the change to academic, a new loan on 2026-11-03
    Expected: New loan: loan_period_days 30, max_renewals 2, daily_fee "1.00", due_date 2026-12-03
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.update_member(client, librarian, data["member"]["id"], membership_type="academic")
    api.set_today(clock, "2026-11-03")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.lend(client, librarian, data["member"]["id"], copy["id"])
    assert (loan["loan_period_days"], loan["max_renewals"], loan["daily_fee"]) == (30, 2, "1.00")
    assert loan["due_date"] == "2026-12-03"  # 2026-11-03 + 30 days, a Thursday


def test_t_loan_04_d(client, clock, librarian, branch_a):
    """T-LOAN-04-d

    LIB-LOAN-04, LIB-LOAN-07. Student loan, type changed to academic (2 renewals), renewed twice
    Expected: First renewal 200; second 409 RENEWAL_LIMIT_REACHED (the loan keeps max_renewals 1)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.update_member(client, librarian, data["member"]["id"], membership_type="academic")
    api.set_today(clock, "2026-11-10")
    api.renew(client, librarian, data["loan"]["id"])
    r = api.renew(client, librarian, data["loan"]["id"], expect=409)
    assert api.error_code(r) == "RENEWAL_LIMIT_REACHED"


def test_t_loan_05_b(client, clock, librarian, branch_a):
    """T-LOAN-05-b

    LIB-LOAN-05. Step 2: membership expired (clock 2027-11-02) and the member has an overdue loan
    Expected: 409 MEMBERSHIP_EXPIRED (step 2 before step 3)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2027-11-02")  # valid_until 2027-11-01; loan due 2026-11-16 is overdue
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, data["member"]["id"], copy["id"], expect=409)
    assert api.error_code(r) == "MEMBERSHIP_EXPIRED"


def test_t_loan_05_d(client, librarian, branch_a):
    """T-LOAN-05-d

    LIB-LOAN-05. Step 4: total debt 50.00 and loan limit reached (student with 2 open loans changed to guest, limit 2)
    Expected: 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt "50.00" (step 4 before step 5)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    loans = [api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)["loan"] for _ in range(3)]
    api.return_loan(client, librarian, loans[2]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="50.00")
    api.update_member(client, librarian, member["id"], membership_type="guest", phone="+905551112233")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], copy["id"], expect=409)
    assert api.error_code(r) == "MEMBER_BLOCKED_BY_DEBT"
    assert r["error"]["details"]["total_debt"] == "50.00"


def test_t_loan_05_f(client, librarian, branch_a):
    """T-LOAN-05-f

    LIB-LOAN-05. Step 6: copy is on_loan to another member
    Expected: 409 COPY_NOT_AVAILABLE with details.status "on_loan"
    """
    other = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], other["copy"]["id"], expect=409)
    assert api.error_code(r) == "COPY_NOT_AVAILABLE"
    assert r["error"]["details"]["status"] == "on_loan"


def test_t_loan_05_h(client, librarian, branch_a):
    """T-LOAN-05-h

    LIB-LOAN-05, LIB-RES-10. Step 6: copy is on_hold for this member's ready reservation
    Expected: 201; the reservation becomes fulfilled
    """
    # Copy C1 (only copy of the book) on loan to S1; S2 reserves with pickup A; C1 returned at A
    # -> S2's reservation becomes ready and C1 on_hold (LIB-RES-08 b, LIB-RES-09).
    first = api.new_loan(client, librarian, branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    res = api.reserve(client, librarian, book_id=first["book"]["id"], pickup_branch_id=branch_a["id"],
                      member_id=s2["id"])
    api.return_loan(client, librarian, first["loan"]["id"], branch_id=branch_a["id"])
    copy_id = first["copy"]["id"]
    assert api.get_copy(client, librarian, copy_id)["status"] == "on_hold"

    loan = api.lend(client, librarian, s2["id"], copy_id)
    assert loan["copy_id"] == copy_id
    assert api.get_reservation(client, librarian, res["id"])["status"] == "fulfilled"


def test_t_loan_05_j(client, librarian, branch_a):
    """T-LOAN-05-j

    LIB-LOAN-05. Step 5: student with 4 open loans requests a 5th (limit 5)
    Expected: 201; a 6th request then returns 409 LOAN_LIMIT_REACHED
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    for _ in range(4):
        api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)  # 5th: allowed
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], copy["id"], expect=409)
    assert api.error_code(r) == "LOAN_LIMIT_REACHED"


def test_t_loan_05_l(client, librarian, branch_a):
    """T-LOAN-05-l

    LIB-LOAN-05. Step 5 uses the current type: student with 2 open loans changed to guest (limit 2) requests a 3rd
    Expected: 409 LOAN_LIMIT_REACHED
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    for _ in range(2):
        api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.update_member(client, librarian, member["id"], membership_type="guest", phone="+905551112233")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], copy["id"], expect=409)
    assert api.error_code(r) == "LOAN_LIMIT_REACHED"


def test_t_loan_06_b(client, librarian, branch_a):
    """T-LOAN-06-b

    LIB-LOAN-06. Total debt 49.99 (one damage fee of 49.99)
    Expected: 201
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="49.99")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    api.lend(client, librarian, data["member"]["id"], copy["id"])


def test_t_loan_07_b(client, librarian, branch_a):
    """T-LOAN-07-b

    LIB-LOAN-07. Check 1: loan already returned and the member deactivated afterwards
    Expected: 409 LOAN_NOT_OPEN (before MEMBER_PASSIVE)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    api.deactivate_member(client, librarian, data["member"]["id"])
    r = api.renew(client, librarian, data["loan"]["id"], expect=409)
    assert api.error_code(r) == "LOAN_NOT_OPEN"


def test_t_loan_07_d(client, clock, librarian, branch_a):
    """T-LOAN-07-d

    LIB-LOAN-07. Check 3: membership expired (clock 2027-11-02) and the loan (due 2026-11-16) overdue
    Expected: 409 MEMBERSHIP_EXPIRED (before LOAN_OVERDUE)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2027-11-02")
    r = api.renew(client, librarian, loan["id"], expect=409)
    assert api.error_code(r) == "MEMBERSHIP_EXPIRED"


def test_t_loan_07_f(client, clock, librarian, branch_a):
    """T-LOAN-07-f

    LIB-LOAN-07. Check 4: guest loan (due 2026-11-09, 0 renewals) renewed on 2026-11-10
    Expected: 409 LOAN_OVERDUE (before RENEWAL_LIMIT_REACHED)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest")["loan"]
    api.set_today(clock, "2026-11-10")
    r = api.renew(client, librarian, loan["id"], expect=409)
    assert api.error_code(r) == "LOAN_OVERDUE"


def test_t_loan_07_h(client, clock, librarian, branch_a):
    """T-LOAN-07-h

    LIB-LOAN-07. Check 6: another member has a waiting reservation for the book (LIB-E2E-02, renew 2026-11-10)
    Expected: 409 BOOK_RESERVED
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.reserve(client, librarian, book_id=data["book"]["id"], pickup_branch_id=branch_a["id"], member_id=other["id"])
    api.set_today(clock, "2026-11-10")
    r = api.renew(client, librarian, data["loan"]["id"], expect=409)
    assert api.error_code(r) == "BOOK_RESERVED"


def test_t_loan_07_j(client, librarian, branch_a):
    """T-LOAN-07-j

    LIB-LOAN-07. Another member's reservation for the book was cancelled
    Expected: Renewal 200 (only active reservations block)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    res = api.reserve(client, librarian, book_id=data["book"]["id"], pickup_branch_id=branch_a["id"], member_id=other["id"])
    api.post(client, f"/api/v1/reservations/{res['id']}/cancel", librarian, None, expect=200)
    assert api.renew(client, librarian, data["loan"]["id"])["renewal_count"] == 1


def test_t_loan_07_l(client, librarian, branch_a):
    """T-LOAN-07-l

    LIB-LOAN-07, LIB-AUTH-25. A member renews another member's loan
    Expected: 403 FORBIDDEN; renewal_count stays 0
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.renew(client, api.member_headers(client, other), data["loan"]["id"], expect=403)
    assert api.error_code(r) == "FORBIDDEN"
    assert api.get_loan(client, librarian, data["loan"]["id"])["renewal_count"] == 0


def test_t_loan_08_b(client, clock, librarian, branch_a):
    """T-LOAN-08-b

    LIB-LOAN-08. Student loan due 2026-11-16 renewed on the due date
    Expected: 200, due_date 2026-11-30 (2026-11-16 + 14 days, a Monday)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-16")
    renewed = api.renew(client, librarian, loan["id"])
    assert renewed["due_date"] == "2026-11-30"


def test_t_loan_08_d(client, clock, librarian, branch_a):
    """T-LOAN-08-d

    LIB-LOAN-08. Academic lent 2026-11-02 (due 2026-12-02), renewed 2026-11-20 and 2026-12-01, third renewal 2026-12-10 (LIB-E2E-05)
    Expected: due_date 2026-12-21, then 2026-12-31; third renewal 409 RENEWAL_LIMIT_REACHED
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="academic")["loan"]
    assert loan["due_date"] == "2026-12-02"
    api.set_today(clock, "2026-11-20")
    assert api.renew(client, librarian, loan["id"])["due_date"] == "2026-12-21"  # 2026-12-20 is a Sunday
    api.set_today(clock, "2026-12-01")
    assert api.renew(client, librarian, loan["id"])["due_date"] == "2026-12-31"
    api.set_today(clock, "2026-12-10")
    r = api.renew(client, librarian, loan["id"], expect=409)
    assert api.error_code(r) == "RENEWAL_LIMIT_REACHED"


def test_t_loan_09_b(client, admin, librarian, branch_a):
    """T-LOAN-09-b

    LIB-LOAN-09. Business check 1: loan already returned; second return at an inactive branch
    Expected: 409 LOAN_NOT_OPEN (before BRANCH_INACTIVE)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    inactive = api.create_branch(client, admin, "C")
    api.deactivate_branch(client, admin, inactive["id"])
    r = api.return_loan(client, librarian, loan["id"], branch_id=inactive["id"], expect=409)
    assert api.error_code(r) == "LOAN_NOT_OPEN"


def test_t_loan_09_d(client, librarian, branch_a):
    """T-LOAN-09-d

    LIB-LOAN-09, LIB-LOAN-11. Business check 3: copy price 120.00, damaged with damage_fee 130.00 (LIB-E2E-07)
    Expected: 409 DAMAGE_FEE_EXCEEDS_PRICE; loan stays open, no fee
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="120.00")
    r = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                        condition="damaged", damage_fee="130.00", expect=409)
    assert api.error_code(r) == "DAMAGE_FEE_EXCEEDS_PRICE"
    assert api.get_loan(client, librarian, data["loan"]["id"])["status"] == "open"
    assert api.items(api.member_fees(client, librarian, data["member"]["id"])) == []


def test_t_loan_09_f(client, librarian, branch_a):
    """T-LOAN-09-f

    LIB-LOAN-09, LIB-COM-28. Returned loan, second return damaged without damage_fee
    Expected: 422 VALIDATION_ERROR (validation before the 409 business checks)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    r = api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_loan_09_h(client, librarian, branch_a):
    """T-LOAN-09-h

    LIB-LOAN-09, LIB-COM-28. Return of unknown loan id 999999 with condition "broken"
    Expected: 422 VALIDATION_ERROR (validation before existence)
    """
    r = api.return_loan(client, librarian, 999999, branch_id=branch_a["id"], condition="broken", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_loan_09_j(client, librarian, branch_a):
    """T-LOAN-09-j

    LIB-LOAN-09, LIB-COM-29. Return with unknown branch_id 999999
    Expected: 404 NOT_FOUND, details {"field": "branch_id", "id": 999999}
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    r = api.return_loan(client, librarian, loan["id"], branch_id=999999, expect=404)
    assert api.error_code(r) == "NOT_FOUND"
    assert r["error"]["details"] == {"field": "branch_id", "id": 999999}


def test_t_loan_10_b(client, clock, librarian, branch_a):
    """T-LOAN-10-b

    LIB-LOAN-10. Student loan due 2026-11-16 returned 2026-11-16
    Expected: late_days 0; no fee (returned on the due date)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-16")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 0  # returned on the due date
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert fees == []


def test_t_loan_10_d(client, clock, librarian, branch_a):
    """T-LOAN-10-d

    LIB-LOAN-10. Student loan due 2026-11-16 returned 2026-11-21
    Expected: late_days 4; late fee "8.00" (returned on a Saturday: 17-20 Nov count, 21 Nov does not)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-21")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 4  # returned on a Saturday: 17-20 Nov count, 21 Nov does not
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "8.00")]


def test_t_loan_11_b(client, librarian, branch_a):
    """T-LOAN-11-b

    LIB-LOAN-11. condition damaged without damage_fee
    Expected: 422 VALIDATION_ERROR; loan stays open
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    r = api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.get_loan(client, librarian, loan["id"])["status"] == "open"


def test_t_loan_11_d(client, librarian, branch_a):
    """T-LOAN-11-d

    LIB-LOAN-11. damage_fee equal to the price (120.00)
    Expected: 200; damage fee "120.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="120.00")
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="120.00")
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("damage_fee", "120.00")]


def test_t_loan_11_f(client, librarian, branch_a):
    """T-LOAN-11-f

    LIB-LOAN-11. damage_fee 120.01 for a copy priced 120.00
    Expected: 409 DAMAGE_FEE_EXCEEDS_PRICE
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"], price="120.00")["loan"]
    r = api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"],
                        condition="damaged", damage_fee="120.01", expect=409)
    assert api.error_code(r) == "DAMAGE_FEE_EXCEEDS_PRICE"


def test_t_loan_11_h(client, librarian, branch_a):
    """T-LOAN-11-h

    LIB-LOAN-11, LIB-COM-13. damage_fee "-5.00"
    Expected: 422 VALIDATION_ERROR
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    r = api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"],
                        condition="damaged", damage_fee="-5.00", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_loan_12_b(client, librarian, branch_a, branch_b):
    """T-LOAN-12-b

    LIB-LOAN-12, LIB-RES-08, LIB-BR-05. Good return of a branch-A copy at branch B, no reservation
    Expected: Return transfer starts: copy in_transfer, current_branch_id null
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_b["id"])
    copy = api.get_copy(client, librarian, data["copy"]["id"])
    assert copy["status"] == "in_transfer"
    assert copy["current_branch_id"] is None


def test_t_loan_13_b(client, librarian, branch_a):
    """T-LOAN-13-b

    LIB-LOAN-13. Report lost on a returned loan
    Expected: 409 LOAN_NOT_OPEN
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    r = api.report_lost(client, librarian, loan["id"], expect=409)
    assert api.error_code(r) == "LOAN_NOT_OPEN"


def test_t_loan_13_d(client, librarian, branch_a):
    """T-LOAN-13-d

    LIB-LOAN-13, 9.2. The member reports their own loan lost
    Expected: 403 FORBIDDEN; loan stays open
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    r = api.report_lost(client, api.member_headers(client, data["member"]), data["loan"]["id"], expect=403)
    assert api.error_code(r) == "FORBIDDEN"
    assert api.get_loan(client, librarian, data["loan"]["id"])["status"] == "open"


def test_t_loan_14_b(client, librarian, branch_a):
    """T-LOAN-14-b

    LIB-LOAN-14. Filters member_id and status
    Expected: member_id=m1 → loans 2, 1; status=returned → loan 1
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"member_id": m1["id"]}))] == [ids[1], ids[0]]
    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"status": "returned"}))] == [ids[0]]


def test_t_loan_14_d(client, librarian, branch_a):
    """T-LOAN-14-d

    LIB-LOAN-14. Filter due_before=2026-11-16
    Expected: Due dates ≤ 2026-11-16: loans 3, 2, 1 (all); due_before=2026-11-15 → loan 3
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"due_before": "2026-11-16"}))] == sorted(ids, reverse=True)
    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"due_before": "2026-11-15"}))] == [ids[2]]


def test_t_loan_14_f(client, librarian, branch_a):
    """T-LOAN-14-f

    LIB-LOAN-14. m1 reads GET /api/v1/members/{m1}/loans?status=open with their own token
    Expected: 200, loan 2 only
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    own = api.get(client, f"/api/v1/members/{m1['id']}/loans", api.member_headers(client, m1),
                  params={"status": "open"})
    assert [x["id"] for x in own["items"]] == [ids[1]]


def test_t_loan_14_h(client, librarian, branch_a):
    """T-LOAN-14-h

    LIB-LOAN-14, LIB-COM-18. page_size=2, pages 1 and 2
    Expected: Page 1: 2 items; page 2: 1 item; total 3 on both
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    p1 = api.get(client, "/api/v1/loans", librarian, params={"page_size": 2, "page": 1})
    p2 = api.get(client, "/api/v1/loans", librarian, params={"page_size": 2, "page": 2})
    assert [x["id"] for x in p1["items"] + p2["items"]] == sorted(ids, reverse=True)
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    assert p1["total"] == p2["total"] == 3
