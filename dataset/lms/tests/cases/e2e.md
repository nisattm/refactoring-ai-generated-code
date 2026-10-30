# Test cases: end-to-end scenarios (section 21)

Generated from one case list; 11 cases for 11 requirements (feedback 6, held-out 5, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-E2E-01 | LIB-E2E-01 | Scenario | Late return and borrowing block (section 21) | Overdue blocks; 25 late days = 50.00 blocks; paying 0.01 allows lending | feedback |
| T-E2E-02 | LIB-E2E-02 | Scenario | Reservation at another branch (section 21) | BOOK_RESERVED on renewal; in transit 20 Nov; not received 23 Nov; ready 24 Nov until 27 Nov; fulfilled on 27 Nov | held-out |
| T-E2E-03 | LIB-E2E-03 | Scenario | Hold expires and passes on (section 21) | S1 ready until 3 Nov; on 4 Nov S1 expired, S2 ready until 9 Nov; C1 on hold; lending to S1 COPY_ON_HOLD | feedback |
| T-E2E-04 | LIB-E2E-04 | Scenario | Lost book (section 21) | Fees 4.00, 180.00, 25.00; debt 209.00; 209.01 rejected; 209.00 pays all in order; copy withdrawn | held-out |
| T-E2E-05 | LIB-E2E-05 | Scenario | Renewal limits by type (section 21) | Guest: RENEWAL_LIMIT_REACHED; academic: 2 Dec → 21 Dec → 31 Dec; third renewal RENEWAL_LIMIT_REACHED | feedback |
| T-E2E-06 | LIB-E2E-06 | Scenario | Type change keeps open loan terms (section 21) | Old loan due 16 Nov at 2.00; new loan on 3 Nov due 3 Dec at 1.00 | held-out |
| T-E2E-07 | LIB-E2E-07 | Scenario | Damaged return and repair (section 21) | 130.00 rejected (DAMAGE_FEE_EXCEEDS_PRICE); 40.00 accepted, copy damaged, reservation waiting; repair → ready until 11 Nov | feedback |
| T-E2E-08 | LIB-E2E-08 | Scenario | Waiver by admin only (section 21): late fee 8.00 from a 4-day late return | Librarian 403; admin waives; outstanding fees 8.00 → 0.00 | held-out |
| T-E2E-09 | LIB-E2E-09 | Scenario | Purchasing to shelf (section 21) | total 286.50; partially received with 2 copies at 95.50; over-receiving rejected with nothing created; then received | feedback |
| T-E2E-10 | LIB-E2E-10 | Scenario | Login lockout (section 21) | Fifth wrong 401; correct password 403 ACCOUNT_LOCKED; after 15 minutes 200 | held-out |
| T-E2E-11 | LIB-E2E-11 | Scenario | Import, export, search (section 21) on an empty database | Export equals the imported records; `q=istanbul` finds `İstanbul Hatırası`; imported member login 401 | feedback |
