"""LMS Module 5: Loans and returns: feedback set.

Case table: ../cases/loans.md. Requirements: ../../requirements.md.
Written before the code exists; fails at ``import lms`` until then.
"""

from support import api


def test_t_loan_01_a(client, librarian, branch_a):
    """T-LOAN-01-a

    LIB-LOAN-01. Librarian lends an available copy by copy_id on 2026-11-02
    Expected: 201, LoanOut with status open, loan_date 2026-11-02, branch_id A, renewal_count 0, created_by = librarian; copy on_loan
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.lend(client, librarian, member["id"], copy["id"])
    me = api.get(client, "/api/v1/auth/me", librarian)
    assert loan["status"] == "open"
    assert loan["member_id"] == member["id"] and loan["copy_id"] == copy["id"]
    assert loan["branch_id"] == branch_a["id"]
    assert loan["loan_date"] == "2026-11-02"
    assert loan["renewal_count"] == 0
    assert loan["returned_on"] is None and loan["return_branch_id"] is None and loan["late_days"] is None
    assert loan["created_by"] == me["id"]
    assert api.get_copy(client, librarian, copy["id"])["status"] == "on_loan"


def test_t_loan_01_c(client, librarian, branch_a):
    """T-LOAN-01-c

    LIB-LOAN-01. Both copy_id and barcode
    Expected: 422 VALIDATION_ERROR
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    body = {"member_id": member["id"], "copy_id": copy["id"], "barcode": copy["barcode"]}
    r = api.post(client, "/api/v1/loans", librarian, body, expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_loan_01_e(client, librarian, branch_a):
    """T-LOAN-01-e

    LIB-LOAN-01. Unknown barcode NOPE-0001
    Expected: 404 NOT_FOUND, details {"field": "barcode", "value": "NOPE-0001"}
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.post(client, "/api/v1/loans", librarian,
                 {"member_id": member["id"], "barcode": "NOPE-0001"}, expect=404)
    assert api.error_code(r) == "NOT_FOUND"
    assert r["error"]["details"] == {"field": "barcode", "value": "NOPE-0001"}


def test_t_loan_01_g(client, librarian, branch_a):
    """T-LOAN-01-g

    LIB-LOAN-01, 9.2. A member calls POST /api/v1/loans for themselves
    Expected: 403 FORBIDDEN; copy stays available
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, api.member_headers(client, member), member["id"], copy["id"], expect=403)
    assert api.error_code(r) == "FORBIDDEN"
    assert api.get_copy(client, librarian, copy["id"])["status"] == "available"


def test_t_loan_02_a(client, clock, librarian, branch_a):
    """T-LOAN-02-a

    LIB-LOAN-02. Student loan due 2026-11-16, read on 2026-11-16
    Expected: is_overdue false
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-16")
    assert api.get_loan(client, librarian, loan["id"])["is_overdue"] is False


def test_t_loan_02_c(client, clock, librarian, branch_a):
    """T-LOAN-02-c

    LIB-LOAN-02. Loan returned late on 2026-11-20, read on 2026-11-23
    Expected: is_overdue false (only open loans are overdue)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-20")
    api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-23")
    assert api.get_loan(client, librarian, loan["id"])["is_overdue"] is False


def test_t_loan_03_a(client, clock, librarian, branch_a):
    """T-LOAN-03-a

    LIB-LOAN-03. Student, lent 2026-11-02
    Expected: due_date 2026-11-16 (requirement example)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="student")
    api.set_today(clock, "2026-11-02")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.lend(client, librarian, member["id"], copy["id"])
    # requirement example
    assert loan["loan_date"] == "2026-11-02"
    assert loan["due_date"] == "2026-11-16"


def test_t_loan_03_c(client, clock, librarian, branch_a):
    """T-LOAN-03-c

    LIB-LOAN-03. Staff, lent 2026-11-02
    Expected: due_date 2026-11-23 (2026-11-02 + 21 days = Monday 2026-11-23)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="staff")
    api.set_today(clock, "2026-11-02")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.lend(client, librarian, member["id"], copy["id"])
    # 2026-11-02 + 21 days = Monday 2026-11-23
    assert loan["loan_date"] == "2026-11-02"
    assert loan["due_date"] == "2026-11-23"


def test_t_loan_03_e(client, clock, librarian, branch_a):
    """T-LOAN-03-e

    LIB-LOAN-03. Student, lent 2027-10-15
    Expected: due_date 2027-11-01 (2027-10-15 + 14 = 2027-10-29 (Republic Day, Friday), 30-31 Oct weekend)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="student")
    api.set_today(clock, "2027-10-15")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    loan = api.lend(client, librarian, member["id"], copy["id"])
    # 2027-10-15 + 14 = 2027-10-29 (Republic Day, Friday), 30-31 Oct weekend
    assert loan["loan_date"] == "2027-10-15"
    assert loan["due_date"] == "2027-11-01"


def test_t_loan_04_a(client, librarian, branch_a):
    """T-LOAN-04-a

    LIB-LOAN-04. Student loan on 2026-11-02, then the member's type is changed to academic
    Expected: The open loan keeps loan_period_days 14, max_renewals 1, daily_fee "2.00", due_date 2026-11-16
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    assert (data["loan"]["loan_period_days"], data["loan"]["max_renewals"], data["loan"]["daily_fee"]) == (14, 1, "2.00")
    api.update_member(client, librarian, data["member"]["id"], membership_type="academic")
    loan = api.get_loan(client, librarian, data["loan"]["id"])
    assert (loan["loan_period_days"], loan["max_renewals"], loan["daily_fee"]) == (14, 1, "2.00")
    assert loan["due_date"] == "2026-11-16"


def test_t_loan_04_c(client, clock, librarian, branch_a):
    """T-LOAN-04-c

    LIB-LOAN-04, LIB-LOAN-10. Student loan (due 2026-11-16), type changed to academic, returned 2026-11-20
    Expected: Late fee uses the old daily fee: 4 days × 2.00 = "8.00"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.update_member(client, librarian, data["member"]["id"], membership_type="academic")
    api.set_today(clock, "2026-11-20")
    loan = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert loan["late_days"] == 4
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "8.00")]


def test_t_loan_05_a(client, clock, librarian, branch_a):
    """T-LOAN-05-a

    LIB-LOAN-05. Step 1: member passive and membership expired (clock 2027-11-02)
    Expected: 409 MEMBER_PASSIVE (step 1 before step 2)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.deactivate_member(client, librarian, member["id"])
    api.set_today(clock, "2027-11-02")  # valid_until 2027-11-01 (LIB-MEM-03)
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], copy["id"], expect=409)
    assert api.error_code(r) == "MEMBER_PASSIVE"


def test_t_loan_05_c(client, clock, librarian, branch_a):
    """T-LOAN-05-c

    LIB-LOAN-05. Step 3: overdue loan (due 2026-11-16, clock 2026-11-17) and total debt 52.00 (damage fee 50.00 + accrued 2.00)
    Expected: 409 MEMBER_HAS_OVERDUE (step 3 before step 4)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    second = api.new_loan(client, librarian, branch_id=branch_a["id"], member=data["member"])
    api.return_loan(client, librarian, second["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="50.00")
    api.set_today(clock, "2026-11-17")
    assert api.balance(client, librarian, data["member"]["id"])["total_debt"] == "52.00"
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, data["member"]["id"], copy["id"], expect=409)
    assert api.error_code(r) == "MEMBER_HAS_OVERDUE"


def test_t_loan_05_e(client, librarian, branch_a):
    """T-LOAN-05-e

    LIB-LOAN-05. Step 5: student with 5 open loans requests a copy that is on_loan to another member
    Expected: 409 LOAN_LIMIT_REACHED (step 5 before step 6)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    for _ in range(5):
        api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)
    other = api.new_loan(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], other["copy"]["id"], expect=409)
    assert api.error_code(r) == "LOAN_LIMIT_REACHED"


def test_t_loan_05_g(client, librarian, branch_a):
    """T-LOAN-05-g

    LIB-LOAN-05. Step 6: copy is on_hold for another member's ready reservation
    Expected: 409 COPY_ON_HOLD
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

    s3 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.lend(client, librarian, s3["id"], copy_id, expect=409)
    assert api.error_code(r) == "COPY_ON_HOLD"
    assert api.get_reservation(client, librarian, res["id"])["status"] == "ready"


def test_t_loan_05_i(client, librarian, branch_a):
    """T-LOAN-05-i

    LIB-LOAN-05. Step 6: copy is damaged (returned damaged before)
    Expected: 409 COPY_NOT_AVAILABLE with details.status "damaged"
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="10.00")
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    r = api.lend(client, librarian, member["id"], data["copy"]["id"], expect=409)
    assert api.error_code(r) == "COPY_NOT_AVAILABLE"
    assert r["error"]["details"]["status"] == "damaged"


def test_t_loan_05_k(client, clock, librarian, branch_a):
    """T-LOAN-05-k

    LIB-LOAN-05. Step 2: lending on valid_until itself (registered 2026-11-02, clock 2027-11-01)
    Expected: 201 (expired only when today > valid_until)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    assert member["valid_until"] == "2027-11-01"
    api.set_today(clock, "2027-11-01")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    api.lend(client, librarian, member["id"], copy["id"])


def test_t_loan_06_a(client, librarian, branch_a):
    """T-LOAN-06-a

    LIB-LOAN-06. Total debt 50.00 (one damage fee of 50.00)
    Expected: 409 MEMBER_BLOCKED_BY_DEBT
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="50.00")
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, data["member"]["id"], copy["id"], expect=409)
    assert api.error_code(r) == "MEMBER_BLOCKED_BY_DEBT"


def test_t_loan_06_c(client, clock, librarian, branch_a):
    """T-LOAN-06-c

    LIB-LOAN-06, LIB-FEE-06. Late fee 50.00 (student, 25 late days, returned 2026-12-21), then payment 0.01
    Expected: Before payment 409 MEMBER_BLOCKED_BY_DEBT; after it total_debt "49.99" and lending 201
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-12-21")  # LIB-E2E-01: 25 working days after 2026-11-16
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    _, copy = api.new_copy(client, librarian, branch_id=branch_a["id"])
    r = api.lend(client, librarian, data["member"]["id"], copy["id"], expect=409)
    assert api.error_code(r) == "MEMBER_BLOCKED_BY_DEBT"
    api.pay(client, librarian, data["member"]["id"], "0.01")
    assert api.balance(client, librarian, data["member"]["id"])["total_debt"] == "49.99"
    api.lend(client, librarian, data["member"]["id"], copy["id"])


def test_t_loan_07_a(client, clock, librarian, branch_a):
    """T-LOAN-07-a

    LIB-LOAN-07. Librarian renews an open student loan on 2026-11-10
    Expected: 200, renewal_count 1
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-10")
    renewed = api.renew(client, librarian, loan["id"])
    assert renewed["renewal_count"] == 1
    assert renewed["status"] == "open"


def test_t_loan_07_c(client, admin):
    """T-LOAN-07-c

    LIB-LOAN-07, LIB-IO-06. Check 2: imported passive member whose membership expired (valid_until 2026-08-31) with an open overdue loan (due 2026-10-15); renewed on 2026-11-02
    Expected: 409 MEMBER_PASSIVE (before MEMBERSHIP_EXPIRED and LOAN_OVERDUE)
    """
    # A passive member with an open loan cannot be reached through the API (LIB-MEM-10 refuses to
    # deactivate a member with open loans), so the state is imported (LIB-IO-01, LIB-IO-06).
    data = {
        "format_version": 1,
        "branches": [{"id": 1, "code": "AA", "name": "Branch A", "address": "", "is_active": True}],
        "authors": [{"id": 1, "name": "Author One"}],
        "publishers": [{"id": 1, "name": "Publisher One"}],
        "books": [{"id": 1, "isbn": "9780306406157", "title": "Book", "subtitle": None,
                   "author_ids": [1], "publisher_id": 1, "publication_year": 2020,
                   "language": "en", "classification": "005"}],
        "copies": [{"id": 1, "book_id": 1, "barcode": "C000001", "home_branch_id": 1,
                    "current_branch_id": 1, "price": "100.00", "status": "on_loan",
                    "acquired_on": "2020-01-01", "shelf_location": None}],
        "members": [{"id": 1, "full_name": "Passive Member", "email": "passive@example.edu.tr",
                     "phone": None, "membership_type": "student", "university_id": "P0000001",
                     "home_branch_id": 1, "status": "passive",
                     "membership_start": "2025-09-01", "valid_until": "2026-08-31"}],
        "loans": [{"id": 1, "copy_id": 1, "member_id": 1, "branch_id": 1,
                   "loan_date": "2026-10-01", "due_date": "2026-10-15", "renewal_count": 0,
                   "status": "open", "returned_on": None, "return_branch_id": None}],
    }
    api.post(client, "/api/v1/import", admin, data, expect=200)
    r = api.renew(client, admin, 1, expect=409)
    assert api.error_code(r) == "MEMBER_PASSIVE"


def test_t_loan_07_e(client, clock, librarian, branch_a):
    """T-LOAN-07-e

    LIB-LOAN-07. Check 3 alone: student lent 2027-10-25 (due 2027-11-08), renewed 2027-11-02 after valid_until 2027-11-01
    Expected: 409 MEMBERSHIP_EXPIRED (loan not overdue)
    """
    member = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.set_today(clock, "2027-10-25")
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"], member=member)["loan"]
    assert loan["due_date"] == "2027-11-08"
    api.set_today(clock, "2027-11-02")
    r = api.renew(client, librarian, loan["id"], expect=409)
    assert api.error_code(r) == "MEMBERSHIP_EXPIRED"


def test_t_loan_07_g(client, librarian, branch_a):
    """T-LOAN-07-g

    LIB-LOAN-07. Check 5: guest loan (0 renewals) and another member has a waiting reservation for the book
    Expected: 409 RENEWAL_LIMIT_REACHED (before BOOK_RESERVED)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], membership_type="guest")
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    api.reserve(client, librarian, book_id=data["book"]["id"], pickup_branch_id=branch_a["id"], member_id=other["id"])
    r = api.renew(client, librarian, data["loan"]["id"], expect=409)
    assert api.error_code(r) == "RENEWAL_LIMIT_REACHED"


def test_t_loan_07_i(client, librarian, branch_a):
    """T-LOAN-07-i

    LIB-LOAN-07. Check 6 with a ready reservation: book has copies C1 (lent to S1) and C2 (held for S2)
    Expected: S1's renewal 409 BOOK_RESERVED
    """
    s1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    s2 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    s3 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    book, c1 = api.new_copy(client, librarian, branch_id=branch_a["id"])
    c2 = api.add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    loan1 = api.lend(client, librarian, s1["id"], c1["id"])
    loan3 = api.lend(client, librarian, s3["id"], c2["id"])
    res = api.reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    api.return_loan(client, librarian, loan3["id"], branch_id=branch_a["id"])
    assert api.get_reservation(client, librarian, res["id"])["status"] == "ready"
    r = api.renew(client, librarian, loan1["id"], expect=409)
    assert api.error_code(r) == "BOOK_RESERVED"


def test_t_loan_07_k(client, librarian, branch_a):
    """T-LOAN-07-k

    LIB-LOAN-07, 9.2. The member renews their own loan
    Expected: 200, renewal_count 1
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    renewed = api.renew(client, api.member_headers(client, data["member"]), data["loan"]["id"])
    assert renewed["renewal_count"] == 1


def test_t_loan_07_m(client, clock, librarian, branch_a):
    """T-LOAN-07-m

    LIB-LOAN-07. Check 4 alone: student loan (due 2026-11-16) renewed on 2026-11-17
    Expected: 409 LOAN_OVERDUE
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-17")
    r = api.renew(client, librarian, loan["id"], expect=409)
    assert api.error_code(r) == "LOAN_OVERDUE"


def test_t_loan_08_a(client, clock, librarian, branch_a):
    """T-LOAN-08-a

    LIB-LOAN-08. Student loan due 2026-11-16 renewed on 2026-11-10
    Expected: due_date 2026-11-24, renewal_count 1 (requirement example)
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-10")
    renewed = api.renew(client, librarian, loan["id"])
    assert renewed["due_date"] == "2026-11-24"
    assert renewed["renewal_count"] == 1


def test_t_loan_08_c(client, clock, librarian, branch_a):
    """T-LOAN-08-c

    LIB-LOAN-08. Student lent 2026-05-14 (due 2026-06-01), renewed 2026-05-15
    Expected: due_date stays 2026-06-01, renewal_count 1 (requirement example: 2026-05-29 holiday)
    """
    api.set_today(clock, "2026-05-14")
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    assert loan["due_date"] == "2026-06-01"  # 2026-05-28 Kurban Bayrami, next working day 2026-06-01
    api.set_today(clock, "2026-05-15")
    renewed = api.renew(client, librarian, loan["id"])
    assert renewed["due_date"] == "2026-06-01"
    assert renewed["renewal_count"] == 1


def test_t_loan_09_a(client, clock, librarian, branch_a):
    """T-LOAN-09-a

    LIB-LOAN-09. Good return at branch A on 2026-11-10
    Expected: 200: status returned, returned_on 2026-11-10, return_branch_id A, condition_on_return good, late_days 0
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-10")
    closed = api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert closed["status"] == "returned"
    assert closed["returned_on"] == "2026-11-10"
    assert closed["return_branch_id"] == branch_a["id"]
    assert closed["condition_on_return"] == "good"
    assert closed["late_days"] == 0


def test_t_loan_09_c(client, admin, librarian, branch_a):
    """T-LOAN-09-c

    LIB-LOAN-09, LIB-BR-04. Business check 2: return at an inactive branch, damaged with damage_fee above the price
    Expected: 409 BRANCH_INACTIVE (before DAMAGE_FEE_EXCEEDS_PRICE); loan stays open
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"], price="120.00")["loan"]
    inactive = api.create_branch(client, admin, "CC")
    api.deactivate_branch(client, admin, inactive["id"])
    r = api.return_loan(client, librarian, loan["id"], branch_id=inactive["id"],
                        condition="damaged", damage_fee="130.00", expect=409)
    assert api.error_code(r) == "BRANCH_INACTIVE"
    assert api.get_loan(client, librarian, loan["id"])["status"] == "open"


def test_t_loan_09_e(client, librarian, branch_a, branch_b):
    """T-LOAN-09-e

    LIB-LOAN-09. Copy of branch A returned at branch B
    Expected: 200, return_branch_id B
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    closed = api.return_loan(client, librarian, loan["id"], branch_id=branch_b["id"])
    assert closed["return_branch_id"] == branch_b["id"]


def test_t_loan_09_g(client, librarian, branch_a):
    """T-LOAN-09-g

    LIB-LOAN-09, LIB-COM-28. Return of unknown loan id 999999 with a valid body
    Expected: 404 NOT_FOUND
    """
    r = api.return_loan(client, librarian, 999999, branch_id=branch_a["id"], expect=404)
    assert api.error_code(r) == "NOT_FOUND"


def test_t_loan_09_i(client, librarian, branch_a):
    """T-LOAN-09-i

    LIB-LOAN-09, LIB-COM-28. The member returns their own loan with condition "broken"
    Expected: 403 FORBIDDEN (role check before validation)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    r = api.return_loan(client, api.member_headers(client, data["member"]), data["loan"]["id"],
                        branch_id=branch_a["id"], condition="broken", expect=403)
    assert api.error_code(r) == "FORBIDDEN"


def test_t_loan_10_a(client, clock, librarian, branch_a):
    """T-LOAN-10-a

    LIB-LOAN-10. Student loan due 2026-11-16 returned 2026-11-20
    Expected: late_days 4; late fee "8.00" (requirement example)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-20")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 4  # requirement example
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "8.00")]


def test_t_loan_10_c(client, clock, librarian, branch_a):
    """T-LOAN-10-c

    LIB-LOAN-10. Student loan due 2026-11-16 returned 2026-11-17
    Expected: late_days 1; late fee "2.00" (first day after the due date)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.set_today(clock, "2026-11-17")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 1  # first day after the due date
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "2.00")]


def test_t_loan_10_e(client, clock, librarian, branch_a):
    """T-LOAN-10-e

    LIB-LOAN-10. Student lent 2026-10-13 (due 2026-10-27), returned 2026-10-30
    Expected: late_days 2 (28 Oct arife is a working day, 29 Oct holiday); late fee "4.00"
    """
    api.set_today(clock, "2026-10-13")
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    assert data["loan"]["due_date"] == "2026-10-27"
    api.set_today(clock, "2026-10-30")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 2
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "4.00")]


def test_t_loan_11_a(client, librarian, branch_a, branch_b):
    """T-LOAN-11-a

    LIB-LOAN-11, LIB-FEE-03. Copy (home A, price 120.00) returned damaged at branch B with damage_fee 40.00
    Expected: damage_fee fee "40.00"; copy damaged with current_branch_id B; condition_on_return damaged
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="120.00")
    closed = api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_b["id"],
                             condition="damaged", damage_fee="40.00")
    assert closed["condition_on_return"] == "damaged"
    copy = api.get_copy(client, librarian, data["copy"]["id"])
    assert copy["status"] == "damaged"
    assert copy["current_branch_id"] == branch_b["id"]
    fees = api.items(api.member_fees(client, librarian, data["member"]["id"]))
    assert [(f["kind"], f["amount"]) for f in fees] == [("damage_fee", "40.00")]


def test_t_loan_11_c(client, librarian, branch_a):
    """T-LOAN-11-c

    LIB-LOAN-11. condition damaged with damage_fee "0.00"
    Expected: 422 VALIDATION_ERROR
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    r = api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"],
                        condition="damaged", damage_fee="0.00", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"


def test_t_loan_11_e(client, librarian, branch_a):
    """T-LOAN-11-e

    LIB-LOAN-11. condition good with damage_fee "5.00"
    Expected: 422 VALIDATION_ERROR; loan stays open
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    r = api.return_loan(client, librarian, loan["id"], branch_id=branch_a["id"],
                        condition="good", damage_fee="5.00", expect=422)
    assert api.error_code(r) == "VALIDATION_ERROR"
    assert api.get_loan(client, librarian, loan["id"])["status"] == "open"


def test_t_loan_11_g(client, librarian, branch_a):
    """T-LOAN-11-g

    LIB-LOAN-11, LIB-RES-08. Only copy of a book returned damaged at A while another member waits (pickup A) (LIB-E2E-07)
    Expected: Reservation stays waiting; copy damaged (not released)
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="120.00")
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    res = api.reserve(client, librarian, book_id=data["book"]["id"], pickup_branch_id=branch_a["id"], member_id=other["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"],
                    condition="damaged", damage_fee="40.00")
    assert api.get_reservation(client, librarian, res["id"])["status"] == "waiting"
    assert api.get_copy(client, librarian, data["copy"]["id"])["status"] == "damaged"


def test_t_loan_12_a(client, librarian, branch_a):
    """T-LOAN-12-a

    LIB-LOAN-12, LIB-RES-08. Good return at the copy's home branch A, no reservation
    Expected: Copy available, current_branch_id A
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    copy = api.get_copy(client, librarian, data["copy"]["id"])
    assert copy["status"] == "available"
    assert copy["current_branch_id"] == branch_a["id"]


def test_t_loan_12_c(client, clock, librarian, branch_a):
    """T-LOAN-12-c

    LIB-LOAN-12, LIB-RES-08, LIB-RES-09. Good return at A on 2026-11-10 while another member waits with pickup A
    Expected: Reservation ready, hold_until 2026-11-13; copy on_hold
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"])
    other = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    res = api.reserve(client, librarian, book_id=data["book"]["id"], pickup_branch_id=branch_a["id"], member_id=other["id"])
    api.set_today(clock, "2026-11-10")
    api.return_loan(client, librarian, data["loan"]["id"], branch_id=branch_a["id"])
    res = api.get_reservation(client, librarian, res["id"])
    assert res["status"] == "ready"
    assert res["hold_until"] == "2026-11-13"  # 2026-11-10 + 3 working days
    assert api.get_copy(client, librarian, data["copy"]["id"])["status"] == "on_hold"


def test_t_loan_13_a(client, clock, librarian, branch_a):
    """T-LOAN-13-a

    LIB-LOAN-13. Student loan due 2026-11-16 reported lost on 2026-11-18 (LIB-E2E-04)
    Expected: 200: status lost, late_days 2; copy lost, current_branch_id null
    """
    data = api.new_loan(client, librarian, branch_id=branch_a["id"], price="180.00")
    api.set_today(clock, "2026-11-18")
    lost = api.report_lost(client, librarian, data["loan"]["id"])
    assert lost["status"] == "lost"
    assert lost["late_days"] == 2
    copy = api.get_copy(client, librarian, data["copy"]["id"])
    assert copy["status"] == "lost"
    assert copy["current_branch_id"] is None


def test_t_loan_13_c(client, clock, librarian, branch_a):
    """T-LOAN-13-c

    LIB-LOAN-13. Student loan due 2026-11-16 reported lost on 2026-11-05
    Expected: late_days 0
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.set_today(clock, "2026-11-05")
    assert api.report_lost(client, librarian, loan["id"])["late_days"] == 0


def test_t_loan_13_e(client, librarian, branch_a):
    """T-LOAN-13-e

    LIB-LOAN-13. Report lost twice
    Expected: Second call 409 LOAN_NOT_OPEN
    """
    loan = api.new_loan(client, librarian, branch_id=branch_a["id"])["loan"]
    api.report_lost(client, librarian, loan["id"])
    r = api.report_lost(client, librarian, loan["id"], expect=409)
    assert api.error_code(r) == "LOAN_NOT_OPEN"


def test_t_loan_14_a(client, librarian, branch_a):
    """T-LOAN-14-a

    LIB-LOAN-14. Three loans, GET /api/v1/loans
    Expected: Ordered by id descending; total 3
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    page = api.get(client, "/api/v1/loans", librarian)
    assert [x["id"] for x in page["items"]] == sorted(ids, reverse=True)
    assert page["total"] == 3


def test_t_loan_14_c(client, clock, librarian, branch_a):
    """T-LOAN-14-c

    LIB-LOAN-14. Filter overdue on 2026-11-10
    Expected: overdue=true → loan 3 (due 2026-11-09); overdue=false → loans 2, 1
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    api.set_today(clock, "2026-11-10")
    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"overdue": "true"}))] == [ids[2]]
    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"overdue": "false"}))] == [ids[1], ids[0]]


def test_t_loan_14_e(client, librarian, branch_a, branch_b):
    """T-LOAN-14-e

    LIB-LOAN-14. Filters book_id, copy_id, branch_id
    Expected: book_id/copy_id of loan 2 → loan 2; branch_id A → all three; branch_id B → none
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"book_id": l2["book"]["id"]}))] == [ids[1]]
    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"copy_id": l2["copy"]["id"]}))] == [ids[1]]
    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"branch_id": branch_a["id"]}))] == sorted(ids, reverse=True)
    assert [x["id"] for x in api.items(api.get(client, "/api/v1/loans", librarian, params={"branch_id": branch_b["id"]}))] == []


def test_t_loan_14_g(client, librarian, branch_a):
    """T-LOAN-14-g

    LIB-LOAN-14, 9.2, LIB-AUTH-25. A member calls GET /api/v1/loans, and reads another member's loans
    Expected: Both 403 FORBIDDEN
    """
    # m1: loan 1 (returned), loan 2 (open, due 2026-11-16); m2: loan 3 (open, guest, due 2026-11-09)
    m1 = api.register_member(client, librarian, home_branch_id=branch_a["id"])
    m2 = api.register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    l1 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l2 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m1)
    l3 = api.new_loan(client, librarian, branch_id=branch_a["id"], member=m2)
    api.return_loan(client, librarian, l1["loan"]["id"], branch_id=branch_a["id"])
    ids = [x["loan"]["id"] for x in (l1, l2, l3)]

    h1 = api.member_headers(client, m1)
    assert api.error_code(api.get(client, "/api/v1/loans", h1, expect=403)) == "FORBIDDEN"
    assert len(ids) == 3
    r = api.get(client, f"/api/v1/members/{m2['id']}/loans", h1, expect=403)
    assert api.error_code(r) == "FORBIDDEN"
