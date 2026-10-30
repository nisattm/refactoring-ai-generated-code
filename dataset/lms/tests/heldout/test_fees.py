"""LMS Module 7: Fines and payments: held-out set.

Case table: ../cases/fees.md. Requirements: ../../requirements.md.
Written before the code exists; fails at ``import lms`` until then.
"""

from support import api


def test_t_fee_01_b(client, librarian, branch_a):
    """T-FEE-01-b

    LIB-FEE-01, LIB-COM-13. damage_fee "40.123" (three decimals)
    Expected: 422 VALIDATION_ERROR, no fee
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    r = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                        condition="damaged", damage_fee="40.123", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.items(api.member_fees(client, librarian, data["member"]["id"])) == []


def test_t_fee_02_b(client, clock, librarian, branch_a):
    """T-FEE-02-b

    LIB-FEE-02. Open student loan due 2026-11-16, read on 2026-11-20
    Expected: accrued_late_fee "8.00" (4 working days × 2.00)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-20")
    assert api.get_loan(client, librarian, loan["id"])["accrued_late_fee"] == "8.00"


def test_t_fee_02_d(client, clock, librarian, branch_a):
    """T-FEE-02-d

    LIB-FEE-02. Guest loan (5.00 TL/day, due 2026-11-09, copy price 100.00) returned 2026-12-04
    Expected: late_days 19; late fee "95.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest", price="100.00")
    assert data["loan"]["due_date"] == "2026-11-09"
    api.set_today(clock, "2026-12-04")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 19  # working days after 2026-11-09 up to 2026-12-04
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "95.00")]  # min(19 x 5.00, 100.00)


def test_t_fee_02_f(client, clock, librarian, branch_a):
    """T-FEE-02-f

    LIB-FEE-02. Open loan read on its due date 2026-11-16
    Expected: accrued_late_fee "0.00"
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-16")
    assert api.get_loan(client, librarian, loan["id"])["accrued_late_fee"] == "0.00"


def test_t_fee_02_h(client, clock, librarian, branch_a):
    """T-FEE-02-h

    LIB-FEE-02. Open guest loan read on 2026-12-14 (25 working days late)
    Expected: accrued_late_fee "100.00" (cap also applies to accrued fees)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest")["loan"]
    api.set_today(clock, "2026-12-14")
    assert api.get_loan(client, librarian, loan["id"])["accrued_late_fee"] == "100.00"


def test_t_fee_03_b(client, clock, librarian, branch_a):
    """T-FEE-03-b

    LIB-FEE-03, LIB-LOAN-10. Student loan due 2026-11-16 returned damaged on 2026-11-20 with damage_fee 30.00
    Expected: Two fees: late_fee "8.00" and damage_fee "30.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-20")
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert sorted((f["kind"], f["amount"]) for f in fees) == [("damage_fee", "30.00"), ("late_fee", "8.00")]


def test_t_fee_04_b(client, clock, librarian, branch_a):
    """T-FEE-04-b

    LIB-FEE-04. Loan reported lost before the due date (2026-11-05)
    Expected: Only lost_book "100.00" and lost_processing "25.00" (no late fee)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-05")
    api.report_lost(client, librarian, data["loan"]["id"])
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert sorted((f["kind"], f["amount"]) for f in fees) == [("lost_book", "100.00"), ("lost_processing", "25.00")]


def test_t_fee_05_b(client, librarian, branch_a):
    """T-FEE-05-b

    LIB-FEE-05, LIB-COM-13. Payment amount "0.00" (zero); member owes 30.00
    Expected: 422 VALIDATION_ERROR; no payment recorded
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    r = api.pay(client, librarian, data["member"]["id"], "0.00", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.balance(client, librarian, data["member"]["id"])["outstanding_fees"] == "30.00"


def test_t_fee_05_d(client, clock, librarian, branch_a):
    """T-FEE-05-d

    LIB-FEE-05. Lost-book fees 209.00 (LIB-E2E-04); payment 209.01
    Expected: 409 PAYMENT_EXCEEDS_BALANCE, details.outstanding_fees "209.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="180.00")
    api.set_today(clock, "2026-11-18")
    api.report_lost(client, librarian, data["loan"]["id"])
    r = api.pay(client, librarian, data["member"]["id"], "209.01", expect=409)
    assert api.error_code(r) == "PAYMENT_EXCEEDS_BALANCE"
    assert r["error"]["details"]["outstanding_fees"] == "209.00"


def test_t_fee_05_f(client, clock, librarian, branch_a):
    """T-FEE-05-f

    LIB-FEE-05, LIB-FEE-06. Lost-book fees 209.00 (LIB-E2E-04); payment 209.00
    Expected: 201; all three fees paid, outstanding_fees "0.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="180.00")
    api.set_today(clock, "2026-11-18")
    api.report_lost(client, librarian, data["loan"]["id"])
    api.pay(client, librarian, data["member"]["id"], "209.00")
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [f["status"] for f in fees] == ["paid", "paid", "paid"]
    assert api.balance(client, librarian, data["member"]["id"])["outstanding_fees"] == "0.00"


def test_t_fee_05_h(client, clock, librarian, branch_a):
    """T-FEE-05-h

    LIB-FEE-05. Only an accrued late fee (open loan due 2026-11-16, clock 2026-11-20, accrued 8.00); payment 1.00
    Expected: 409 PAYMENT_EXCEEDS_BALANCE, details.outstanding_fees "0.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-20")
    r = api.pay(client, librarian, data["member"]["id"], "1.00", expect=409)
    assert api.error_code(r) == "PAYMENT_EXCEEDS_BALANCE"
    assert r["error"]["details"]["outstanding_fees"] == "0.00"


def test_t_fee_05_j(client, librarian, branch_a):
    """T-FEE-05-j

    LIB-FEE-05, 11.2. The member records a payment for themselves
    Expected: 403 FORBIDDEN
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    r = api.pay(client, api.member_headers(client, data["member"]), data["member"]["id"], "10.00", expect=403)
    assert api.error_code(r) == "FORBIDDEN"


def test_t_fee_06_b(client, librarian, branch_a):
    """T-FEE-06-b

    LIB-FEE-06. Two fees on the same day: 5.00 (lower id) then 7.00; payment 6.00
    Expected: First fee paid; second paid_amount "1.00", outstanding "6.00"
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    first = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    second = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.return_loan(client, librarian, first["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="5.00")
    api.return_loan(client, librarian, second["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="7.00")
    api.pay(client, librarian, member["id"], "6.00")
    f1, f2 = sorted(api.items(api.member_fees(client, librarian, member["id"])), key=lambda f: f["id"])
    assert (f1["amount"], f1["status"]) == ("5.00", "paid")
    assert (f2["amount"], f2["status"], f2["paid_amount"], f2["outstanding"]) == ("7.00", "open", "1.00", "6.00")


def test_t_fee_06_d(client, librarian, branch_a):
    """T-FEE-06-d

    LIB-FEE-06. Fee 6.00 paid in two payments 2.50 and 3.50
    Expected: After the second payment the fee is paid, outstanding "0.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="6.00")
    api.pay(client, librarian, data["member"]["id"], "2.50")
    api.pay(client, librarian, data["member"]["id"], "3.50")
    fee = api.items(api.member_fees(client, librarian, data["member"]["id"]))[0]
    assert (fee["status"], fee["paid_amount"], fee["outstanding"]) == ("paid", "6.00", "0.00")


def test_t_fee_07_b(client, librarian, branch_a):
    """T-FEE-07-b

    LIB-FEE-07. A librarian waives a fee (LIB-E2E-08)
    Expected: 403 FORBIDDEN; fee stays open
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    r = api.waive(client, librarian, fee["id"], expect=403)
    assert api.error_code(r) == "FORBIDDEN"
    assert api.items(api.member_fees(client, librarian, member_id))[0]["status"] == "open"


def test_t_fee_07_d(client, admin, librarian, branch_a):
    """T-FEE-07-d

    LIB-FEE-07. Admin waives the same fee twice
    Expected: Second call 409 FEE_NOT_OPEN
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    api.waive(client, admin, fee["id"])
    r = api.waive(client, admin, fee["id"], expect=409)
    assert api.error_code(r) == "FEE_NOT_OPEN"


def test_t_fee_07_f(client, admin, librarian, branch_a):
    """T-FEE-07-f

    LIB-FEE-07. Reason of 5 characters "abcde"
    Expected: 200, status waived
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    assert api.waive(client, admin, fee["id"], reason="abcde")["status"] == "waived"


def test_t_fee_07_h(client, admin, librarian, branch_a):
    """T-FEE-07-h

    LIB-FEE-07. Reason of 501 characters (500 is accepted)
    Expected: 501: 422 VALIDATION_ERROR; 500: 200
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    r = api.waive(client, admin, fee["id"], reason="x" * 501, expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.waive(client, admin, fee["id"], reason="x" * 500)["status"] == "waived"


def test_t_fee_08_b(client, clock, librarian, branch_a):
    """T-FEE-08-b

    LIB-FEE-08. m1's fees with status=open and with status=paid
    Expected: open → 7.00; paid → 5.00
    """
    # m1: damage fee 5.00 (2026-11-02, loan l1), damage fee 7.00 (2026-11-03, loan l2, then paid);
    # m2: damage fee 9.00 (2026-11-03)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="5.00")
    api.set_today(clock, "2026-11-03")
    api.return_loan(client, librarian, l2["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="7.00")
    api.return_loan(client, librarian, l3["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="9.00")
    api.pay(client, librarian, m1["id"], "5.00")  # pays the oldest fee (5.00)

    path = f"/api/v1/members/{m1['id']}/fees"
    assert [f["amount"] for f in api.items(api.get(client, path, librarian, params={"status": "open"}))] == ["7.00"]
    assert [f["amount"] for f in api.items(api.get(client, path, librarian, params={"status": "paid"}))] == ["5.00"]


def test_t_fee_08_d(client, clock, librarian, branch_a):
    """T-FEE-08-d

    LIB-FEE-08, 11.2, LIB-AUTH-25. m1 reads own fees; m1 reads m2's fees; m1 calls GET /api/v1/fees
    Expected: Own: 200 with 5.00, 7.00; m2's: 403 FORBIDDEN; all fees: 403 FORBIDDEN
    """
    # m1: damage fee 5.00 (2026-11-02, loan l1), damage fee 7.00 (2026-11-03, loan l2, then paid);
    # m2: damage fee 9.00 (2026-11-03)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="5.00")
    api.set_today(clock, "2026-11-03")
    api.return_loan(client, librarian, l2["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="7.00")
    api.return_loan(client, librarian, l3["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="9.00")
    api.pay(client, librarian, m1["id"], "5.00")  # pays the oldest fee (5.00)

    h1 = api.member_headers(client, m1)
    own = api.get(client, f"/api/v1/members/{m1['id']}/fees", h1)
    assert [f["amount"] for f in own["items"]] == ["5.00", "7.00"]
    assert api.error_code(api.get(client, f"/api/v1/members/{m2['id']}/fees", h1, expect=403)) == "FORBIDDEN"
    assert api.error_code(api.get(client, "/api/v1/fees", h1, expect=403)) == "FORBIDDEN"


def test_t_fee_09_b(client, admin, librarian, branch_a):
    """T-FEE-09-b

    LIB-FEE-09. Fees 10.00 (paid), 20.00 (waived), 5.00 (open)
    Expected: total_debt "5.00" (only open fees count)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    loans = [api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)["loan"] for _ in range(3)]
    for loan, fee in zip(loans, ("10.00", "20.00", "5.00"), strict=True):
        api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee=fee)
    fees = api.items(api.member_fees(client, librarian, member["id"]))
    api.pay(client, librarian, member["id"], "10.00")  # oldest first: the 10.00 fee
    api.waive(client, admin, fees[1]["id"])
    assert api.balance(client, librarian, member["id"])["total_debt"] == "5.00"


def test_t_fee_10_b(client, librarian, branch_a):
    """T-FEE-10-b

    LIB-FEE-10. Open fee 49.99
    Expected: total_debt "49.99", blocked false
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="49.99")
    bal = api.balance(client, librarian, data["member"]["id"])
    assert (bal["total_debt"], bal["blocked"]) == ("49.99", False)


def test_t_fee_10_d(client, clock, librarian, branch_a):
    """T-FEE-10-d

    LIB-FEE-10. Open loan due 2026-11-16, clock 2026-11-20; open fee 10.00
    Expected: outstanding_fees "10.00", accrued_late_fees "8.00", total_debt "18.00", blocked false
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    other = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.return_loan(client, librarian, other["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    api.set_today(clock, "2026-11-20")
    assert api.balance(client, librarian, member["id"]) == {
        "outstanding_fees": "10.00", "accrued_late_fees": "8.00", "total_debt": "18.00", "blocked": False}


def test_t_fee_11_b(client, clock, librarian, branch_a):
    """T-FEE-11-b

    LIB-FEE-11, 11.2, LIB-AUTH-25. The member reads own payments; another member reads them
    Expected: Own: 200 with the 3 payments; other: 403 FORBIDDEN
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="30.00")
    payments = []
    for day, hour, amount in (("2026-11-02", 10, "5.00"), ("2026-11-02", 11, "7.00"), ("2026-11-03", 9, "3.00")):
        api.set_today(clock, day, hour=hour)
        payments.append(api.pay(client, librarian, member["id"], amount))

    own = api.get(client, f"/api/v1/members/{member['id']}/payments", api.member_headers(client, member))
    assert [p["id"] for p in own["items"]] == [p["id"] for p in payments]
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.get(client, f"/api/v1/members/{member['id']}/payments", api.member_headers(client, other), expect=403)
    assert api.error_code(r) == "FORBIDDEN"
