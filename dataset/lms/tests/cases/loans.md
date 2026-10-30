# Test cases: Module 5: Loans and returns

Requirements: [`../../requirements.md`](../../requirements.md). Tests: [`../feedback/test_loans.py`](../feedback/test_loans.py), [`../heldout/test_loans.py`](../heldout/test_loans.py). Split rule and conventions: [`../README.md`](../README.md).

Dates are the clock's local date (`FixedClock`, start 2026-11-02 09:00 +03:00, a Monday). Expected dates and amounts come from the examples in the requirements or were computed with the working-day rules of section 3.2 and the default holiday list.

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-LOAN-01-a | LIB-LOAN-01 | Normal | Librarian lends an available copy by `copy_id` on 2026-11-02 | `201`, `LoanOut` with `status` open, `loan_date` 2026-11-02, `branch_id` A, `renewal_count` 0, `created_by` = librarian; copy `on_loan` | feedback |
| T-LOAN-01-b | LIB-LOAN-01 | Normal | Lend by `barcode` instead of `copy_id` | `201`; the loan refers to the copy with that barcode | held-out |
| T-LOAN-01-c | LIB-LOAN-01 | Error | Both `copy_id` and `barcode` | `422 VALIDATION_ERROR` | feedback |
| T-LOAN-01-d | LIB-LOAN-01 | Error | Neither `copy_id` nor `barcode` | `422 VALIDATION_ERROR`; copy stays `available` | held-out |
| T-LOAN-01-e | LIB-LOAN-01 | Error | Unknown `barcode` `NOPE-0001` | `404 NOT_FOUND`, `details` `{"field": "barcode", "value": "NOPE-0001"}` | feedback |
| T-LOAN-01-f | LIB-LOAN-01, LIB-COM-29 | Error | Unknown `copy_id` 999999 | `404 NOT_FOUND`, `details` `{"field": "copy_id", "id": 999999}` | held-out |
| T-LOAN-01-g | LIB-LOAN-01, 9.2 | Error | A member calls `POST /api/v1/loans` for themselves | `403 FORBIDDEN`; copy stays `available` | feedback |
| T-LOAN-02-a | LIB-LOAN-02 | Boundary | Student loan due 2026-11-16, read on 2026-11-16 | `is_overdue` false | feedback |
| T-LOAN-02-b | LIB-LOAN-02 | Boundary | Same loan read on 2026-11-17 | `is_overdue` true | held-out |
| T-LOAN-02-c | LIB-LOAN-02 | Normal | Loan returned late on 2026-11-20, read on 2026-11-23 | `is_overdue` false (only open loans are overdue) | feedback |
| T-LOAN-03-a | LIB-LOAN-03 | Normal | Student, lent 2026-11-02 | `due_date` 2026-11-16 (requirement example) | feedback |
| T-LOAN-03-b | LIB-LOAN-03 | Boundary | Academic, lent 2026-12-02 | `due_date` 2027-01-04 (requirement example: 2027-01-01 holiday, 2-3 Jan weekend) | held-out |
| T-LOAN-03-c | LIB-LOAN-03 | Normal | Staff, lent 2026-11-02 | `due_date` 2026-11-23 (2026-11-02 + 21 days = Monday 2026-11-23) | feedback |
| T-LOAN-03-d | LIB-LOAN-03 | Normal | Guest, lent 2026-11-02 | `due_date` 2026-11-09 (2026-11-02 + 7 days = Monday 2026-11-09) | held-out |
| T-LOAN-03-e | LIB-LOAN-03 | Boundary | Student, lent 2027-10-15 | `due_date` 2027-11-01 (2027-10-15 + 14 = 2027-10-29 (Republic Day, Friday), 30-31 Oct weekend) | feedback |
| T-LOAN-04-a | LIB-LOAN-04 | Normal | Student loan on 2026-11-02, then the member's type is changed to academic | The open loan keeps `loan_period_days` 14, `max_renewals` 1, `daily_fee` "2.00", `due_date` 2026-11-16 | feedback |
| T-LOAN-04-b | LIB-LOAN-04 | Normal | After the change to academic, a new loan on 2026-11-03 | New loan: `loan_period_days` 30, `max_renewals` 2, `daily_fee` "1.00", `due_date` 2026-12-03 | held-out |
| T-LOAN-04-c | LIB-LOAN-04, LIB-LOAN-10 | Normal | Student loan (due 2026-11-16), type changed to academic, returned 2026-11-20 | Late fee uses the old daily fee: 4 days × 2.00 = "8.00" | feedback |
| T-LOAN-04-d | LIB-LOAN-04, LIB-LOAN-07 | Normal | Student loan, type changed to academic (2 renewals), renewed twice | First renewal `200`; second `409 RENEWAL_LIMIT_REACHED` (the loan keeps `max_renewals` 1) | held-out |
| T-LOAN-05-a | LIB-LOAN-05 | Error | Step 1: member `passive` and membership expired (clock 2027-11-02) | `409 MEMBER_PASSIVE` (step 1 before step 2) | feedback |
| T-LOAN-05-b | LIB-LOAN-05 | Error | Step 2: membership expired (clock 2027-11-02) and the member has an overdue loan | `409 MEMBERSHIP_EXPIRED` (step 2 before step 3) | held-out |
| T-LOAN-05-c | LIB-LOAN-05 | Error | Step 3: overdue loan (due 2026-11-16, clock 2026-11-17) and total debt 52.00 (damage fee 50.00 + accrued 2.00) | `409 MEMBER_HAS_OVERDUE` (step 3 before step 4) | feedback |
| T-LOAN-05-d | LIB-LOAN-05 | Error | Step 4: total debt 50.00 and loan limit reached (student with 2 open loans changed to guest, limit 2) | `409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` "50.00" (step 4 before step 5) | held-out |
| T-LOAN-05-e | LIB-LOAN-05 | Error | Step 5: student with 5 open loans requests a copy that is `on_loan` to another member | `409 LOAN_LIMIT_REACHED` (step 5 before step 6) | feedback |
| T-LOAN-05-f | LIB-LOAN-05 | Error | Step 6: copy is `on_loan` to another member | `409 COPY_NOT_AVAILABLE` with `details.status` "on_loan" | held-out |
| T-LOAN-05-g | LIB-LOAN-05 | Error | Step 6: copy is `on_hold` for another member's `ready` reservation | `409 COPY_ON_HOLD` | feedback |
| T-LOAN-05-h | LIB-LOAN-05, LIB-RES-10 | Normal | Step 6: copy is `on_hold` for this member's `ready` reservation | `201`; the reservation becomes `fulfilled` | held-out |
| T-LOAN-05-i | LIB-LOAN-05 | Error | Step 6: copy is `damaged` (returned damaged before) | `409 COPY_NOT_AVAILABLE` with `details.status` "damaged" | feedback |
| T-LOAN-05-j | LIB-LOAN-05 | Boundary | Step 5: student with 4 open loans requests a 5th (limit 5) | `201`; a 6th request then returns `409 LOAN_LIMIT_REACHED` | held-out |
| T-LOAN-05-k | LIB-LOAN-05 | Boundary | Step 2: lending on `valid_until` itself (registered 2026-11-02, clock 2027-11-01) | `201` (expired only when today > `valid_until`) | feedback |
| T-LOAN-05-l | LIB-LOAN-05 | Boundary | Step 5 uses the current type: student with 2 open loans changed to guest (limit 2) requests a 3rd | `409 LOAN_LIMIT_REACHED` | held-out |
| T-LOAN-06-a | LIB-LOAN-06 | Boundary | Total debt 50.00 (one damage fee of 50.00) | `409 MEMBER_BLOCKED_BY_DEBT` | feedback |
| T-LOAN-06-b | LIB-LOAN-06 | Boundary | Total debt 49.99 (one damage fee of 49.99) | `201` | held-out |
| T-LOAN-06-c | LIB-LOAN-06, LIB-FEE-06 | Boundary | Late fee 50.00 (student, 25 late days, returned 2026-12-21), then payment 0.01 | Before payment `409 MEMBER_BLOCKED_BY_DEBT`; after it `total_debt` "49.99" and lending `201` | feedback |
| T-LOAN-07-a | LIB-LOAN-07 | Normal | Librarian renews an open student loan on 2026-11-10 | `200`, `renewal_count` 1 | feedback |
| T-LOAN-07-b | LIB-LOAN-07 | Error | Check 1: loan already returned and the member deactivated afterwards | `409 LOAN_NOT_OPEN` (before `MEMBER_PASSIVE`) | held-out |
| T-LOAN-07-c | LIB-LOAN-07, LIB-IO-06 | Error | Check 2: imported `passive` member whose membership expired (`valid_until` 2026-08-31) with an open overdue loan (due 2026-10-15); renewed on 2026-11-02 | `409 MEMBER_PASSIVE` (before `MEMBERSHIP_EXPIRED` and `LOAN_OVERDUE`) | feedback |
| T-LOAN-07-d | LIB-LOAN-07 | Error | Check 3: membership expired (clock 2027-11-02) and the loan (due 2026-11-16) overdue | `409 MEMBERSHIP_EXPIRED` (before `LOAN_OVERDUE`) | held-out |
| T-LOAN-07-e | LIB-LOAN-07 | Error | Check 3 alone: student lent 2027-10-25 (due 2027-11-08), renewed 2027-11-02 after `valid_until` 2027-11-01 | `409 MEMBERSHIP_EXPIRED` (loan not overdue) | feedback |
| T-LOAN-07-f | LIB-LOAN-07 | Error | Check 4: guest loan (due 2026-11-09, 0 renewals) renewed on 2026-11-10 | `409 LOAN_OVERDUE` (before `RENEWAL_LIMIT_REACHED`) | held-out |
| T-LOAN-07-g | LIB-LOAN-07 | Error | Check 5: guest loan (0 renewals) and another member has a `waiting` reservation for the book | `409 RENEWAL_LIMIT_REACHED` (before `BOOK_RESERVED`) | feedback |
| T-LOAN-07-h | LIB-LOAN-07 | Error | Check 6: another member has a `waiting` reservation for the book (LIB-E2E-02, renew 2026-11-10) | `409 BOOK_RESERVED` | held-out |
| T-LOAN-07-i | LIB-LOAN-07 | Error | Check 6 with a `ready` reservation: book has copies C1 (lent to S1) and C2 (held for S2) | S1's renewal `409 BOOK_RESERVED` | feedback |
| T-LOAN-07-j | LIB-LOAN-07 | Normal | Another member's reservation for the book was cancelled | Renewal `200` (only active reservations block) | held-out |
| T-LOAN-07-k | LIB-LOAN-07, 9.2 | Normal | The member renews their own loan | `200`, `renewal_count` 1 | feedback |
| T-LOAN-07-l | LIB-LOAN-07, LIB-AUTH-25 | Error | A member renews another member's loan | `403 FORBIDDEN`; `renewal_count` stays 0 | held-out |
| T-LOAN-07-m | LIB-LOAN-07 | Error | Check 4 alone: student loan (due 2026-11-16) renewed on 2026-11-17 | `409 LOAN_OVERDUE` | feedback |
| T-LOAN-08-a | LIB-LOAN-08 | Normal | Student loan due 2026-11-16 renewed on 2026-11-10 | `due_date` 2026-11-24, `renewal_count` 1 (requirement example) | feedback |
| T-LOAN-08-b | LIB-LOAN-08 | Boundary | Student loan due 2026-11-16 renewed on the due date | `200`, `due_date` 2026-11-30 (2026-11-16 + 14 days, a Monday) | held-out |
| T-LOAN-08-c | LIB-LOAN-08 | Boundary | Student lent 2026-05-14 (due 2026-06-01), renewed 2026-05-15 | `due_date` stays 2026-06-01, `renewal_count` 1 (requirement example: 2026-05-29 holiday) | feedback |
| T-LOAN-08-d | LIB-LOAN-08 | Normal | Academic lent 2026-11-02 (due 2026-12-02), renewed 2026-11-20 and 2026-12-01, third renewal 2026-12-10 (LIB-E2E-05) | `due_date` 2026-12-21, then 2026-12-31; third renewal `409 RENEWAL_LIMIT_REACHED` | held-out |
| T-LOAN-09-a | LIB-LOAN-09 | Normal | Good return at branch A on 2026-11-10 | `200`: `status` returned, `returned_on` 2026-11-10, `return_branch_id` A, `condition_on_return` good, `late_days` 0 | feedback |
| T-LOAN-09-b | LIB-LOAN-09 | Error | Business check 1: loan already returned; second return at an inactive branch | `409 LOAN_NOT_OPEN` (before `BRANCH_INACTIVE`) | held-out |
| T-LOAN-09-c | LIB-LOAN-09, LIB-BR-04 | Error | Business check 2: return at an inactive branch, damaged with `damage_fee` above the price | `409 BRANCH_INACTIVE` (before `DAMAGE_FEE_EXCEEDS_PRICE`); loan stays open | feedback |
| T-LOAN-09-d | LIB-LOAN-09, LIB-LOAN-11 | Error | Business check 3: copy price 120.00, damaged with `damage_fee` 130.00 (LIB-E2E-07) | `409 DAMAGE_FEE_EXCEEDS_PRICE`; loan stays open, no fee | held-out |
| T-LOAN-09-e | LIB-LOAN-09 | Normal | Copy of branch A returned at branch B | `200`, `return_branch_id` B | feedback |
| T-LOAN-09-f | LIB-LOAN-09, LIB-COM-28 | Error | Returned loan, second return `damaged` without `damage_fee` | `422 VALIDATION_ERROR` (validation before the `409` business checks) | held-out |
| T-LOAN-09-g | LIB-LOAN-09, LIB-COM-28 | Error | Return of unknown loan id 999999 with a valid body | `404 NOT_FOUND` | feedback |
| T-LOAN-09-h | LIB-LOAN-09, LIB-COM-28 | Error | Return of unknown loan id 999999 with `condition` "broken" | `422 VALIDATION_ERROR` (validation before existence) | held-out |
| T-LOAN-09-i | LIB-LOAN-09, LIB-COM-28 | Error | The member returns their own loan with `condition` "broken" | `403 FORBIDDEN` (role check before validation) | feedback |
| T-LOAN-09-j | LIB-LOAN-09, LIB-COM-29 | Error | Return with unknown `branch_id` 999999 | `404 NOT_FOUND`, `details` `{"field": "branch_id", "id": 999999}` | held-out |
| T-LOAN-10-a | LIB-LOAN-10 | Normal | Student loan due 2026-11-16 returned 2026-11-20 | `late_days` 4; late fee "8.00" (requirement example) | feedback |
| T-LOAN-10-b | LIB-LOAN-10 | Boundary | Student loan due 2026-11-16 returned 2026-11-16 | `late_days` 0; no fee (returned on the due date) | held-out |
| T-LOAN-10-c | LIB-LOAN-10 | Boundary | Student loan due 2026-11-16 returned 2026-11-17 | `late_days` 1; late fee "2.00" (first day after the due date) | feedback |
| T-LOAN-10-d | LIB-LOAN-10 | Boundary | Student loan due 2026-11-16 returned 2026-11-21 | `late_days` 4; late fee "8.00" (returned on a Saturday: 17-20 Nov count, 21 Nov does not) | held-out |
| T-LOAN-10-e | LIB-LOAN-10 | Boundary | Student lent 2026-10-13 (due 2026-10-27), returned 2026-10-30 | `late_days` 2 (28 Oct arife is a working day, 29 Oct holiday); late fee "4.00" | feedback |
| T-LOAN-11-a | LIB-LOAN-11, LIB-FEE-03 | Normal | Copy (home A, price 120.00) returned damaged at branch B with `damage_fee` 40.00 | `damage_fee` fee "40.00"; copy `damaged` with `current_branch_id` B; `condition_on_return` damaged | feedback |
| T-LOAN-11-b | LIB-LOAN-11 | Error | `condition` damaged without `damage_fee` | `422 VALIDATION_ERROR`; loan stays open | held-out |
| T-LOAN-11-c | LIB-LOAN-11 | Boundary | `condition` damaged with `damage_fee` "0.00" | `422 VALIDATION_ERROR` | feedback |
| T-LOAN-11-d | LIB-LOAN-11 | Boundary | `damage_fee` equal to the price (120.00) | `200`; damage fee "120.00" | held-out |
| T-LOAN-11-e | LIB-LOAN-11 | Error | `condition` good with `damage_fee` "5.00" | `422 VALIDATION_ERROR`; loan stays open | feedback |
| T-LOAN-11-f | LIB-LOAN-11 | Boundary | `damage_fee` 120.01 for a copy priced 120.00 | `409 DAMAGE_FEE_EXCEEDS_PRICE` | held-out |
| T-LOAN-11-g | LIB-LOAN-11, LIB-RES-08 | Normal | Only copy of a book returned damaged at A while another member waits (pickup A) (LIB-E2E-07) | Reservation stays `waiting`; copy `damaged` (not released) | feedback |
| T-LOAN-11-h | LIB-LOAN-11, LIB-COM-13 | Error | `damage_fee` "-5.00" | `422 VALIDATION_ERROR` | held-out |
| T-LOAN-12-a | LIB-LOAN-12, LIB-RES-08 | Normal | Good return at the copy's home branch A, no reservation | Copy `available`, `current_branch_id` A | feedback |
| T-LOAN-12-b | LIB-LOAN-12, LIB-RES-08, LIB-BR-05 | Normal | Good return of a branch-A copy at branch B, no reservation | Return transfer starts: copy `in_transfer`, `current_branch_id` null | held-out |
| T-LOAN-12-c | LIB-LOAN-12, LIB-RES-08, LIB-RES-09 | Normal | Good return at A on 2026-11-10 while another member waits with pickup A | Reservation `ready`, `hold_until` 2026-11-13; copy `on_hold` | feedback |
| T-LOAN-13-a | LIB-LOAN-13 | Normal | Student loan due 2026-11-16 reported lost on 2026-11-18 (LIB-E2E-04) | `200`: `status` lost, `late_days` 2; copy `lost`, `current_branch_id` null | feedback |
| T-LOAN-13-b | LIB-LOAN-13 | Error | Report lost on a returned loan | `409 LOAN_NOT_OPEN` | held-out |
| T-LOAN-13-c | LIB-LOAN-13 | Boundary | Student loan due 2026-11-16 reported lost on 2026-11-05 | `late_days` 0 | feedback |
| T-LOAN-13-d | LIB-LOAN-13, 9.2 | Error | The member reports their own loan lost | `403 FORBIDDEN`; loan stays open | held-out |
| T-LOAN-13-e | LIB-LOAN-13 | Error | Report lost twice | Second call `409 LOAN_NOT_OPEN` | feedback |
| T-LOAN-14-a | LIB-LOAN-14 | Normal | Three loans, `GET /api/v1/loans` | Ordered by `id` descending; `total` 3 | feedback |
| T-LOAN-14-b | LIB-LOAN-14 | Normal | Filters `member_id` and `status` | `member_id`=m1 → loans 2, 1; `status=returned` → loan 1 | held-out |
| T-LOAN-14-c | LIB-LOAN-14 | Normal | Filter `overdue` on 2026-11-10 | `overdue=true` → loan 3 (due 2026-11-09); `overdue=false` → loans 2, 1 | feedback |
| T-LOAN-14-d | LIB-LOAN-14 | Boundary | Filter `due_before=2026-11-16` | Due dates ≤ 2026-11-16: loans 3, 2, 1 (all); `due_before=2026-11-15` → loan 3 | held-out |
| T-LOAN-14-e | LIB-LOAN-14 | Normal | Filters `book_id`, `copy_id`, `branch_id` | `book_id`/`copy_id` of loan 2 → loan 2; `branch_id` A → all three; `branch_id` B → none | feedback |
| T-LOAN-14-f | LIB-LOAN-14 | Normal | m1 reads `GET /api/v1/members/{m1}/loans?status=open` with their own token | `200`, loan 2 only | held-out |
| T-LOAN-14-g | LIB-LOAN-14, 9.2, LIB-AUTH-25 | Error | A member calls `GET /api/v1/loans`, and reads another member's loans | Both `403 FORBIDDEN` | feedback |
| T-LOAN-14-h | LIB-LOAN-14, LIB-COM-18 | Normal | `page_size=2`, pages 1 and 2 | Page 1: 2 items; page 2: 1 item; `total` 3 on both | held-out |
