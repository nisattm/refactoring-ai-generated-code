# Test cases: Module 7: Fines and payments

Requirements: [`../../requirements.md`](../../requirements.md). Tests: [`../feedback/test_fees.py`](../feedback/test_fees.py), [`../heldout/test_fees.py`](../heldout/test_fees.py). Split rule and conventions: [`../README.md`](../README.md).

Dates are the clock's local date (`FixedClock`, start 2026-11-02 09:00 +03:00, a Monday). Expected dates and amounts come from the examples in the requirements or were computed with the working-day rules of section 3.2 and the default holiday list.

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-FEE-01-a | LIB-FEE-01, LIB-COM-13 | Normal | Damaged return with `damage_fee` "40.5" (one decimal) | `FeeOut` amounts are strings with two decimals: `amount` "40.50", `paid_amount` "0.00", `outstanding` "40.50" | feedback |
| T-FEE-01-b | LIB-FEE-01, LIB-COM-13 | Error | `damage_fee` "40.123" (three decimals) | `422 VALIDATION_ERROR`, no fee | held-out |
| T-FEE-01-c | LIB-FEE-01, LIB-COM-13 | Error | `damage_fee` sent as the JSON number 40 | `422 VALIDATION_ERROR` | feedback |
| T-FEE-02-a | LIB-FEE-02 | Boundary | Guest loan (5.00 TL/day, due 2026-11-09, copy price 100.00) returned 2026-12-14 | `late_days` 25; late fee "100.00" | feedback |
| T-FEE-02-b | LIB-FEE-02 | Normal | Open student loan due 2026-11-16, read on 2026-11-20 | `accrued_late_fee` "8.00" (4 working days × 2.00) | held-out |
| T-FEE-02-c | LIB-FEE-02 | Boundary | Guest loan (5.00 TL/day, due 2026-11-09, copy price 100.00) returned 2026-12-07 | `late_days` 20; late fee "100.00" | feedback |
| T-FEE-02-d | LIB-FEE-02 | Boundary | Guest loan (5.00 TL/day, due 2026-11-09, copy price 100.00) returned 2026-12-04 | `late_days` 19; late fee "95.00" | held-out |
| T-FEE-02-e | LIB-FEE-02 | Normal | Guest loan (5.00 TL/day, due 2026-11-09, copy price 10.00) returned 2026-12-14 | `late_days` 25; late fee "100.00" (cap does not depend on the copy price 10.00) | feedback |
| T-FEE-02-f | LIB-FEE-02 | Boundary | Open loan read on its due date 2026-11-16 | `accrued_late_fee` "0.00" | held-out |
| T-FEE-02-g | LIB-FEE-02, 9.1 | Normal | Loan returned 2026-11-20 (4 late days), read again on 2026-11-30 | `accrued_late_fee` stays "8.00" (final late fee of a closed loan) | feedback |
| T-FEE-02-h | LIB-FEE-02 | Boundary | Open guest loan read on 2026-12-14 (25 working days late) | `accrued_late_fee` "100.00" (cap also applies to accrued fees) | held-out |
| T-FEE-03-a | LIB-FEE-03 | Normal | Copy price 500.00 returned damaged with `damage_fee` 150.00 | One fee: `kind` damage_fee, `amount` "150.00" (not capped at 100.00), `loan_id` = the loan, `status` open | feedback |
| T-FEE-03-b | LIB-FEE-03, LIB-LOAN-10 | Normal | Student loan due 2026-11-16 returned damaged on 2026-11-20 with `damage_fee` 30.00 | Two fees: late_fee "8.00" and damage_fee "30.00" | held-out |
| T-FEE-04-a | LIB-FEE-04 | Normal | Student loan due 2026-11-16, copy price 180.00, reported lost 2026-11-18 (requirement example) | Fees late_fee "4.00", lost_book "180.00", lost_processing "25.00", all with the loan's `loan_id` | feedback |
| T-FEE-04-b | LIB-FEE-04 | Boundary | Loan reported lost before the due date (2026-11-05) | Only lost_book "100.00" and lost_processing "25.00" (no late fee) | held-out |
| T-FEE-04-c | LIB-FEE-04, LIB-FEE-02 | Boundary | Guest loan (due 2026-11-09, price 60.00) reported lost 2026-12-14 (25 working days) | late_fee "100.00" (cap), lost_book "60.00", lost_processing "25.00" | feedback |
| T-FEE-05-a | LIB-FEE-05 | Normal | Damage fee 30.00; librarian records a cash payment of 10.00 | `201` with `member_id`, `amount` "10.00", `method` cash, `received_by` = librarian, `allocations` [{fee, "10.00"}] | feedback |
| T-FEE-05-b | LIB-FEE-05, LIB-COM-13 | Boundary | Payment `amount` "0.00" (zero); member owes 30.00 | `422 VALIDATION_ERROR`; no payment recorded | held-out |
| T-FEE-05-c | LIB-FEE-05, LIB-COM-13 | Error | Payment `amount` "-1.00" (negative); member owes 30.00 | `422 VALIDATION_ERROR`; no payment recorded | feedback |
| T-FEE-05-d | LIB-FEE-05 | Boundary | Lost-book fees 209.00 (LIB-E2E-04); payment 209.01 | `409 PAYMENT_EXCEEDS_BALANCE`, `details.outstanding_fees` "209.00" | held-out |
| T-FEE-05-e | LIB-FEE-05, LIB-COM-13 | Error | Payment `amount` 10 (JSON number); member owes 30.00 | `422 VALIDATION_ERROR`; no payment recorded | feedback |
| T-FEE-05-f | LIB-FEE-05, LIB-FEE-06 | Boundary | Lost-book fees 209.00 (LIB-E2E-04); payment 209.00 | `201`; all three fees `paid`, `outstanding_fees` "0.00" | held-out |
| T-FEE-05-g | LIB-FEE-05, LIB-COM-13 | Error | Payment `amount` "1.001" (three decimals); member owes 30.00 | `422 VALIDATION_ERROR`; no payment recorded | feedback |
| T-FEE-05-h | LIB-FEE-05 | Error | Only an accrued late fee (open loan due 2026-11-16, clock 2026-11-20, accrued 8.00); payment 1.00 | `409 PAYMENT_EXCEEDS_BALANCE`, `details.outstanding_fees` "0.00" | held-out |
| T-FEE-05-i | LIB-FEE-05 | Error | Payment `method` "cheque" | `422 VALIDATION_ERROR` | feedback |
| T-FEE-05-j | LIB-FEE-05, 11.2 | Error | The member records a payment for themselves | `403 FORBIDDEN` | held-out |
| T-FEE-05-k | LIB-FEE-05 | Normal | Payment by card, 30.00, equal to the outstanding amount | `201`, `method` card; fee `paid` | feedback |
| T-FEE-06-a | LIB-FEE-06 | Normal | Fee A 6.00 (2026-11-02) and fee B 20.00 (2026-11-03); payment 10.00 (requirement example) | A `paid` (paid 6.00); B `open`, `paid_amount` "4.00", `outstanding` "16.00"; allocations [A 6.00, B 4.00] | feedback |
| T-FEE-06-b | LIB-FEE-06 | Normal | Two fees on the same day: 5.00 (lower id) then 7.00; payment 6.00 | First fee `paid`; second `paid_amount` "1.00", `outstanding` "6.00" | held-out |
| T-FEE-06-c | LIB-FEE-06 | Boundary | Fee 6.00; payment 2.50 (partial) | Fee stays `open`, `paid_amount` "2.50", `outstanding` "3.50" | feedback |
| T-FEE-06-d | LIB-FEE-06 | Normal | Fee 6.00 paid in two payments 2.50 and 3.50 | After the second payment the fee is `paid`, `outstanding` "0.00" | held-out |
| T-FEE-07-a | LIB-FEE-07 | Normal | Admin waives an open fee of 20.00 with reason "Library error" | `200`: `status` waived, `waive_reason` set, `waived_by` = admin, `outstanding` "0.00"; `outstanding_fees` "0.00" | feedback |
| T-FEE-07-b | LIB-FEE-07 | Error | A librarian waives a fee (LIB-E2E-08) | `403 FORBIDDEN`; fee stays `open` | held-out |
| T-FEE-07-c | LIB-FEE-07 | Error | Admin waives a fee that is already `paid` | `409 FEE_NOT_OPEN` | feedback |
| T-FEE-07-d | LIB-FEE-07 | Error | Admin waives the same fee twice | Second call `409 FEE_NOT_OPEN` | held-out |
| T-FEE-07-e | LIB-FEE-07 | Boundary | Reason of 4 characters "abcd" | `422 VALIDATION_ERROR` | feedback |
| T-FEE-07-f | LIB-FEE-07 | Boundary | Reason of 5 characters "abcde" | `200`, `status` waived | held-out |
| T-FEE-07-g | LIB-FEE-07 | Normal | Fee 20.00 with 5.00 already paid; admin waives it (LIB-E2E-08) | `paid_amount` stays "5.00"; `outstanding_fees` drops from "15.00" to "0.00" | feedback |
| T-FEE-07-h | LIB-FEE-07 | Boundary | Reason of 501 characters (500 is accepted) | 501: `422 VALIDATION_ERROR`; 500: `200` | held-out |
| T-FEE-08-a | LIB-FEE-08 | Normal | `GET /api/v1/fees` without filters | Ordered by `created_on`, then `id`: 5.00, 7.00, 9.00 | feedback |
| T-FEE-08-b | LIB-FEE-08 | Normal | m1's fees with `status=open` and with `status=paid` | open → 7.00; paid → 5.00 | held-out |
| T-FEE-08-c | LIB-FEE-08 | Normal | `GET /api/v1/fees` with `member_id`=m2, with `loan_id`=l2, with `kind=late_fee` | 9.00; 7.00; empty | feedback |
| T-FEE-08-d | LIB-FEE-08, 11.2, LIB-AUTH-25 | Normal | m1 reads own fees; m1 reads m2's fees; m1 calls `GET /api/v1/fees` | Own: `200` with 5.00, 7.00; m2's: `403 FORBIDDEN`; all fees: `403 FORBIDDEN` | held-out |
| T-FEE-08-e | LIB-FEE-08, LIB-COM-18 | Normal | `GET /api/v1/fees?page_size=2&page=2` | One item (9.00); `total` 3 | feedback |
| T-FEE-09-a | LIB-FEE-09 | Normal | Open damage fee 10.00 and an open loan due 2026-11-16, clock 2026-11-20 (accrued 8.00) | `total_debt` "18.00" | feedback |
| T-FEE-09-b | LIB-FEE-09 | Normal | Fees 10.00 (paid), 20.00 (waived), 5.00 (open) | `total_debt` "5.00" (only `open` fees count) | held-out |
| T-FEE-09-c | LIB-FEE-09 | Boundary | Open damage fee 10.00 and an open loan that is not overdue (clock 2026-11-16) | `total_debt` "10.00" | feedback |
| T-FEE-10-a | LIB-FEE-10 | Normal | Member without fees or loans | `200`, exactly `{"outstanding_fees": "0.00", "accrued_late_fees": "0.00", "total_debt": "0.00", "blocked": false}` | feedback |
| T-FEE-10-b | LIB-FEE-10 | Boundary | Open fee 49.99 | `total_debt` "49.99", `blocked` false | held-out |
| T-FEE-10-c | LIB-FEE-10 | Boundary | Open fee 50.00 | `total_debt` "50.00", `blocked` true | feedback |
| T-FEE-10-d | LIB-FEE-10 | Normal | Open loan due 2026-11-16, clock 2026-11-20; open fee 10.00 | `outstanding_fees` "10.00", `accrued_late_fees` "8.00", `total_debt` "18.00", `blocked` false | held-out |
| T-FEE-10-e | LIB-FEE-10, 11.2, LIB-AUTH-25 | Normal | Member reads own balance and another member's balance | Own: `200`; other: `403 FORBIDDEN` | feedback |
| T-FEE-11-a | LIB-FEE-11 | Normal | Three payments at 2026-11-02 10:00, 11:00 and 2026-11-03 09:00 | Ordered by `paid_at`, then `id`: p1, p2, p3; `paid_at` with offset +03:00 | feedback |
| T-FEE-11-b | LIB-FEE-11, 11.2, LIB-AUTH-25 | Normal | The member reads own payments; another member reads them | Own: `200` with the 3 payments; other: `403 FORBIDDEN` | held-out |
| T-FEE-11-c | LIB-FEE-11, LIB-COM-18 | Normal | `page_size=2&page=2` | One item (p3); `total` 3 | feedback |
