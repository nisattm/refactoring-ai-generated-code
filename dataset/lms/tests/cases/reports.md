# Test cases: module 10 (Reports)

Generated from one case list; 10 cases for 5 requirements (feedback 5, held-out 5, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-REP-01-a | LIB-REP-01 | Normal | November loans: `Zeta` 2, `Alfa` 2, `Beta` 1, `Delta` 0; range 2026-11-01 – 2026-11-30 | Alfa (rank 1), Zeta (2), Beta (3); Delta omitted; `limit=2` returns the first two | feedback |
| T-REP-01-b | LIB-REP-01 | Boundary | Ranges 365 days (2026-01-01 – 2027-01-01) and 366 days; `from` > `to`; `limit` 0 and 101; loans at A and B with `branch_id=B` | 200; `422`; `422`; `422`; only the loan at B counts | heldout |
| T-REP-01-c | LIB-REP-01 | Error | Member requests a report | `403 FORBIDDEN` | feedback |
| T-REP-02-a | LIB-REP-02 | Normal | On 2026-11-20: guest loan due 2026-11-09 (9 late days, 45.00) and student loan due 2026-11-16 (4 late days, 8.00); one returned loan | Two rows ordered by due date; `total_accrued` `"53.00"`; all documented fields | feedback |
| T-REP-02-b | LIB-REP-02 | Normal | Overdue loans at A and B; `branch_id=B`; `page_size=1` | Only the loan at B; `total_accrued` covers all matching rows, not only the page | heldout |
| T-REP-03-a | LIB-REP-03 | Normal | Activity in October and November 2026 (one member in October; in November 2 members, 3 loans, 2 returns with 4.00 fees, 1 payment 4.00, 1 waiver 4.00, 1 lost copy (100.00 + 25.00), 1 reservation that expires) | November: new_members 2, loans_created 3, loans_returned 2, loans_lost 1, reservations created 1 / fulfilled 0 / expired 1, fees_created 133.00, payments 4.00, waived 4.00; October: new_members 1, everything else 0 | feedback |
| T-REP-03-b | LIB-REP-03 | Error | On 2026-11-02: December 2026; `month=13`; `month=0` | `422 VALIDATION_ERROR` each | heldout |
| T-REP-04-a | LIB-REP-04 | Normal | A: 2 available, 1 damaged; B: 1 available; 1 copy in transfer; 1 lost copy | Rows (A, available, 2), (A, damaged, 1), (B, available, 1), (null, in_transfer, 1), (null, lost, 1) in this order | heldout |
| T-REP-05-a | LIB-REP-05 | Normal | `most-borrowed` with `format=csv` | `text/csv; charset=utf-8`; header `rank,book_id,title,isbn,loan_count`; one row per item | feedback |
| T-REP-05-b | LIB-REP-05 | Normal | Three overdue loans; `overdue` with `format=csv&page_size=1` | Header plus all three rows (no pagination) | heldout |
