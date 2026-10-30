"""LMS Module 7: Fines and payments: feedback set.

Case table: ../cases/fees.md. Requirements: ../../requirements.md.
Written before the code exists; fails at ``import lms`` until then.
"""

from support import api


def test_t_fee_01_a(client, librarian, branch_a):
    """T-FEE-01-a

    LIB-FEE-01, LIB-COM-13. Damaged return with damage_fee "40.5" (one decimal)
    Expected: FeeOut amounts are strings with two decimals: amount "40.50", paid_amount "0.00", outstanding "40.50"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="40.5")
    fee = api.items(api.member_fees(client, librarian, data["member"]["id"]))[0]
    assert (fee["amount"], fee["paid_amount"], fee["outstanding"]) == ("40.50", "0.00", "40.50")


def test_t_fee_01_c(client, librarian, branch_a):
    """T-FEE-01-c

    LIB-FEE-01, LIB-COM-13. damage_fee sent as the JSON number 40
    Expected: 422 VALIDATION_ERROR
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    body = {"branch_id": branch_a["id"], "condition": "damaged", "damage_fee": 40}
    r = api.post(client, f"/api/v1/loans/{data['loan']['id']}/return", librarian, body, expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_fee_02_a(client, clock, librarian, branch_a):
    """T-FEE-02-a

    LIB-FEE-02. Guest loan (5.00 TL/day, due 2026-11-09, copy price 100.00) returned 2026-12-14
    Expected: late_days 25; late fee "100.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest", price="100.00")
    assert data["loan"]["due_date"] == "2026-11-09"
    api.set_today(clock, "2026-12-14")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 25  # working days after 2026-11-09 up to 2026-12-14
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "100.00")]  # min(25 x 5.00, 100.00)


def test_t_fee_02_c(client, clock, librarian, branch_a):
    """T-FEE-02-c

    LIB-FEE-02. Guest loan (5.00 TL/day, due 2026-11-09, copy price 100.00) returned 2026-12-07
    Expected: late_days 20; late fee "100.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest", price="100.00")
    assert data["loan"]["due_date"] == "2026-11-09"
    api.set_today(clock, "2026-12-07")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 20  # working days after 2026-11-09 up to 2026-12-07
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "100.00")]  # min(20 x 5.00, 100.00)


def test_t_fee_02_e(client, clock, librarian, branch_a):
    """T-FEE-02-e

    LIB-FEE-02. Guest loan (5.00 TL/day, due 2026-11-09, copy price 10.00) returned 2026-12-14
    Expected: late_days 25; late fee "100.00" (cap does not depend on the copy price 10.00)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest", price="10.00")
    assert data["loan"]["due_date"] == "2026-11-09"
    api.set_today(clock, "2026-12-14")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 25  # working days after 2026-11-09 up to 2026-12-14
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "100.00")]  # min(25 x 5.00, 100.00)


def test_t_fee_02_g(client, clock, librarian, branch_a):
    """T-FEE-02-g

    LIB-FEE-02, 9.1. Loan returned 2026-11-20 (4 late days), read again on 2026-11-30
    Expected: accrued_late_fee stays "8.00" (final late fee of a closed loan)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-20")
    api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-30")
    assert api.get_loan(client, librarian, loan["id"])["accrued_late_fee"] == "8.00"


def test_t_fee_03_a(client, librarian, branch_a):
    """T-FEE-03-a

    LIB-FEE-03. Copy price 500.00 returned damaged with damage_fee 150.00
    Expected: One fee: kind damage_fee, amount "150.00" (not capped at 100.00), loan_id = the loan, status open
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="500.00")
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="150.00")
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert len(fees) == 1
    fee = fees[0]
    assert (fee["kind"], fee["amount"], fee["loan_id"], fee["status"]) == ("damage_fee", "150.00", data["loan"]["id"], "open")
    assert fee["created_on"] == "2026-11-02"


def test_t_fee_04_a(client, clock, librarian, branch_a):
    """T-FEE-04-a

    LIB-FEE-04. Student loan due 2026-11-16, copy price 180.00, reported lost 2026-11-18 (requirement example)
    Expected: Fees late_fee "4.00", lost_book "180.00", lost_processing "25.00", all with the loan's loan_id
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="180.00")
    api.set_today(clock, "2026-11-18")
    api.report_lost(client, librarian, data["loan"]["id"])
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert sorted((f["kind"], f["amount"]) for f in fees) == [
        ("late_fee", "4.00"), ("lost_book", "180.00"), ("lost_processing", "25.00")]
    assert {f["loan_id"] for f in fees} == {data["loan"]["id"]}


def test_t_fee_04_c(client, clock, librarian, branch_a):
    """T-FEE-04-c

    LIB-FEE-04, LIB-FEE-02. Guest loan (due 2026-11-09, price 60.00) reported lost 2026-12-14 (25 working days)
    Expected: late_fee "100.00" (cap), lost_book "60.00", lost_processing "25.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest", price="60.00")
    api.set_today(clock, "2026-12-14")
    api.report_lost(client, librarian, data["loan"]["id"])
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert sorted((f["kind"], f["amount"]) for f in fees) == [
        ("late_fee", "100.00"), ("lost_book", "60.00"), ("lost_processing", "25.00")]


def test_t_fee_05_a(client, librarian, branch_a):
    """T-FEE-05-a

    LIB-FEE-05. Damage fee 30.00; librarian records a cash payment of 10.00
    Expected: 201 with member_id, amount "10.00", method cash, received_by = librarian, allocations [{fee, "10.00"}]
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    fee = api.items(api.member_fees(client, librarian, data["member"]["id"]))[0]
    payment = api.pay(client, librarian, data["member"]["id"], "10.00")
    me = api.get(client, "/api/v1/auth/me", librarian)
    assert payment["member_id"] == data["member"]["id"]
    assert (payment["amount"], payment["method"], payment["received_by"]) == ("10.00", "cash", me["id"])
    assert payment["allocations"] == [{"fee_id": fee["id"], "amount": "10.00"}]


def test_t_fee_05_c(client, librarian, branch_a):
    """T-FEE-05-c

    LIB-FEE-05, LIB-COM-13. Payment amount "-1.00" (negative); member owes 30.00
    Expected: 422 VALIDATION_ERROR; no payment recorded
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    r = api.pay(client, librarian, data["member"]["id"], "-1.00", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.balance(client, librarian, data["member"]["id"])["outstanding_fees"] == "30.00"


def test_t_fee_05_e(client, librarian, branch_a):
    """T-FEE-05-e

    LIB-FEE-05, LIB-COM-13. Payment amount 10 (JSON number); member owes 30.00
    Expected: 422 VALIDATION_ERROR; no payment recorded
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    r = api.pay(client, librarian, data["member"]["id"], 10, expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.balance(client, librarian, data["member"]["id"])["outstanding_fees"] == "30.00"


def test_t_fee_05_g(client, librarian, branch_a):
    """T-FEE-05-g

    LIB-FEE-05, LIB-COM-13. Payment amount "1.001" (three decimals); member owes 30.00
    Expected: 422 VALIDATION_ERROR; no payment recorded
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    r = api.pay(client, librarian, data["member"]["id"], "1.001", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.balance(client, librarian, data["member"]["id"])["outstanding_fees"] == "30.00"


def test_t_fee_05_i(client, librarian, branch_a):
    """T-FEE-05-i

    LIB-FEE-05. Payment method "cheque"
    Expected: 422 VALIDATION_ERROR
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    r = api.pay(client, librarian, data["member"]["id"], "10.00", method="cheque", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_fee_05_k(client, librarian, branch_a):
    """T-FEE-05-k

    LIB-FEE-05. Payment by card, 30.00, equal to the outstanding amount
    Expected: 201, method card; fee paid
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="30.00")
    payment = api.pay(client, librarian, data["member"]["id"], "30.00", method="card")
    assert payment["method"] == "card"
    assert api.items(api.member_fees(client, librarian, data["member"]["id"]))[0]["status"] == "paid"


def test_t_fee_06_a(client, clock, librarian, branch_a):
    """T-FEE-06-a

    LIB-FEE-06. Fee A 6.00 (2026-11-02) and fee B 20.00 (2026-11-03); payment 10.00 (requirement example)
    Expected: A paid (paid 6.00); B open, paid_amount "4.00", outstanding "16.00"; allocations [A 6.00, B 4.00]
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    first = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    second = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.return_loan(client, librarian, first["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="6.00")
    api.set_today(clock, "2026-11-03")
    api.return_loan(client, librarian, second["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    fee_a, fee_b = api.items(api.member_fees(client, librarian, member["id"]))
    payment = api.pay(client, librarian, member["id"], "10.00")
    assert payment["allocations"] == [{"fee_id": fee_a["id"], "amount": "6.00"},
                                      {"fee_id": fee_b["id"], "amount": "4.00"}]
    fee_a, fee_b = api.items(api.member_fees(client, librarian, member["id"]))
    assert (fee_a["status"], fee_a["paid_amount"], fee_a["outstanding"]) == ("paid", "6.00", "0.00")
    assert (fee_b["status"], fee_b["paid_amount"], fee_b["outstanding"]) == ("open", "4.00", "16.00")


def test_t_fee_06_c(client, librarian, branch_a):
    """T-FEE-06-c

    LIB-FEE-06. Fee 6.00; payment 2.50 (partial)
    Expected: Fee stays open, paid_amount "2.50", outstanding "3.50"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="6.00")
    api.pay(client, librarian, data["member"]["id"], "2.50")
    fee = api.items(api.member_fees(client, librarian, data["member"]["id"]))[0]
    assert (fee["status"], fee["paid_amount"], fee["outstanding"]) == ("open", "2.50", "3.50")


def test_t_fee_07_a(client, admin, librarian, branch_a):
    """T-FEE-07-a

    LIB-FEE-07. Admin waives an open fee of 20.00 with reason "Library error"
    Expected: 200: status waived, waive_reason set, waived_by = admin, outstanding "0.00"; outstanding_fees "0.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    waived = api.waive(client, admin, fee["id"], reason="Library error")
    me = api.get(client, "/api/v1/auth/me", admin)
    assert waived["status"] == "waived"
    assert waived["waive_reason"] == "Library error"
    assert waived["waived_by"] == me["id"]
    assert waived["outstanding"] == "0.00"
    assert api.balance(client, librarian, member_id)["outstanding_fees"] == "0.00"


def test_t_fee_07_c(client, admin, librarian, branch_a):
    """T-FEE-07-c

    LIB-FEE-07. Admin waives a fee that is already paid
    Expected: 409 FEE_NOT_OPEN
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    api.pay(client, librarian, member_id, "20.00")
    r = api.waive(client, admin, fee["id"], expect=409)
    assert api.error_code(r) == "FEE_NOT_OPEN"


def test_t_fee_07_e(client, admin, librarian, branch_a):
    """T-FEE-07-e

    LIB-FEE-07. Reason of 4 characters "abcd"
    Expected: 422 VALIDATION_ERROR
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    r = api.waive(client, admin, fee["id"], reason="abcd", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_fee_07_g(client, admin, librarian, branch_a):
    """T-FEE-07-g

    LIB-FEE-07. Fee 20.00 with 5.00 already paid; admin waives it (LIB-E2E-08)
    Expected: paid_amount stays "5.00"; outstanding_fees drops from "15.00" to "0.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="20.00")
    member_id = data["member"]["id"]
    fee = api.items(api.member_fees(client, librarian, member_id))[0]

    api.pay(client, librarian, member_id, "5.00")
    assert api.balance(client, librarian, member_id)["outstanding_fees"] == "15.00"
    waived = api.waive(client, admin, fee["id"])
    assert waived["paid_amount"] == "5.00"
    assert api.balance(client, librarian, member_id)["outstanding_fees"] == "0.00"


def test_t_fee_08_a(client, clock, librarian, branch_a):
    """T-FEE-08-a

    LIB-FEE-08. GET /api/v1/fees without filters
    Expected: Ordered by created_on, then id: 5.00, 7.00, 9.00
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

    assert [f["amount"] for f in api.items(api.get(client, "/api/v1/fees", librarian, params=None))] == ["5.00", "7.00", "9.00"]


def test_t_fee_08_c(client, clock, librarian, branch_a):
    """T-FEE-08-c

    LIB-FEE-08. GET /api/v1/fees with member_id=m2, with loan_id=l2, with kind=late_fee
    Expected: 9.00; 7.00; empty
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

    assert [f["amount"] for f in api.items(api.get(client, "/api/v1/fees", librarian, params={"member_id": m2["id"]}))] == ["9.00"]
    assert [f["amount"] for f in api.items(api.get(client, "/api/v1/fees", librarian, params={"loan_id": l2["loan"]["id"]}))] == ["7.00"]
    assert [f["amount"] for f in api.items(api.get(client, "/api/v1/fees", librarian, params={"kind": "late_fee"}))] == []


def test_t_fee_08_e(client, clock, librarian, branch_a):
    """T-FEE-08-e

    LIB-FEE-08, LIB-COM-18. GET /api/v1/fees?page_size=2&page=2
    Expected: One item (9.00); total 3
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

    page = api.get(client, "/api/v1/fees", librarian, params={"page_size": 2, "page": 2})
    assert [f["amount"] for f in page["items"]] == ["9.00"]
    assert page["total"] == 3


def test_t_fee_09_a(client, clock, librarian, branch_a):
    """T-FEE-09-a

    LIB-FEE-09. Open damage fee 10.00 and an open loan due 2026-11-16, clock 2026-11-20 (accrued 8.00)
    Expected: total_debt "18.00"
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    other = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.return_loan(client, librarian, other["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    api.set_today(clock, "2026-11-20")
    assert api.balance(client, librarian, member["id"])["total_debt"] == "18.00"


def test_t_fee_09_c(client, clock, librarian, branch_a):
    """T-FEE-09-c

    LIB-FEE-09. Open damage fee 10.00 and an open loan that is not overdue (clock 2026-11-16)
    Expected: total_debt "10.00"
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    other = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    api.return_loan(client, librarian, other["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    api.set_today(clock, "2026-11-16")
    assert api.balance(client, librarian, member["id"])["total_debt"] == "10.00"


def test_t_fee_10_a(client, librarian, branch_a):
    """T-FEE-10-a

    LIB-FEE-10. Member without fees or loans
    Expected: 200, exactly {"outstanding_fees": "0.00", "accrued_late_fees": "0.00", "total_debt": "0.00", "blocked": false}
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    assert api.balance(client, librarian, member["id"]) == {
        "outstanding_fees": "0.00", "accrued_late_fees": "0.00", "total_debt": "0.00", "blocked": False}


def test_t_fee_10_c(client, librarian, branch_a):
    """T-FEE-10-c

    LIB-FEE-10. Open fee 50.00
    Expected: total_debt "50.00", blocked true
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="50.00")
    bal = api.balance(client, librarian, data["member"]["id"])
    assert (bal["total_debt"], bal["blocked"]) == ("50.00", True)


def test_t_fee_10_e(client, librarian, branch_a):
    """T-FEE-10-e

    LIB-FEE-10, 11.2, LIB-AUTH-25. Member reads own balance and another member's balance
    Expected: Own: 200; other: 403 FORBIDDEN
    """
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    h1 = api.member_headers(client, m1)
    assert api.balance(client, h1, m1["id"])["total_debt"] == "0.00"
    assert api.error_code(api.balance(client, h1, m2["id"], expect=403)) == "FORBIDDEN"


def test_t_fee_11_a(client, clock, librarian, branch_a):
    """T-FEE-11-a

    LIB-FEE-11. Three payments at 2026-11-02 10:00, 11:00 and 2026-11-03 09:00
    Expected: Ordered by paid_at, then id: p1, p2, p3; paid_at with offset +03:00
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="30.00")
    payments = []
    for day, hour, amount in (("2026-11-02", 10, "5.00"), ("2026-11-02", 11, "7.00"), ("2026-11-03", 9, "3.00")):
        api.set_today(clock, day, hour=hour)
        payments.append(api.pay(client, librarian, member["id"], amount))

    page = api.get(client, f"/api/v1/members/{member['id']}/payments", librarian)
    assert [p["id"] for p in page["items"]] == [p["id"] for p in payments]
    assert page["items"][0]["paid_at"].endswith("+03:00")


def test_t_fee_11_c(client, clock, librarian, branch_a):
    """T-FEE-11-c

    LIB-FEE-11, LIB-COM-18. page_size=2&page=2
    Expected: One item (p3); total 3
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    member = data["member"]
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="30.00")
    payments = []
    for day, hour, amount in (("2026-11-02", 10, "5.00"), ("2026-11-02", 11, "7.00"), ("2026-11-03", 9, "3.00")):
        api.set_today(clock, day, hour=hour)
        payments.append(api.pay(client, librarian, member["id"], amount))

    page = api.get(client, f"/api/v1/members/{member['id']}/payments", librarian, params={"page_size": 2, "page": 2})
    assert [p["id"] for p in page["items"]] == [payments[2]["id"]]
    assert page["total"] == 3
