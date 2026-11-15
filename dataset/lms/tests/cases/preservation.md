# Test cases: module 23 (Preservation)

Generated from one case list; 46 cases for 40 requirements (feedback 23, held-out 23, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-PRE-01-a | LIB-PRE-01 | Normal | Admin sets 5000.00 for branch A in 2026, then 6000.00 | 200 `{amount 5000.00, committed 0.00, spent 0.00, available 5000.00}`; then `amount` and `available` 6000.00 | feedback |
| T-PRE-01-b | LIB-PRE-01 | Error | Librarian sets a budget; unknown branch; year 1999; amount -1.00; a member reads it | `403`; `404`; `422`; `422`; `403` | held-out |
| T-PRE-02-a | LIB-PRE-02 | Normal | Budget 1000.00: jobs approved 100.00, sent 50.00, returned with actual 30.00 (estimated 40.00), lost 20.00, cancelled 70.00; budget of 2027 | `committed` 150.00, `spent` 50.00, `available` 800.00; 2027 `404` | held-out |
| T-PRE-03-a | LIB-PRE-03 | Boundary | Budget 1000.00 with 150.00 committed and 50.00 spent; set to 199.99; to 200.00 | `409 BUDGET_BELOW_USED` with `details.used` 200.00; 200 with `available` 0.00 | feedback |
| T-PRE-04-a | LIB-PRE-04 | Normal | Copy inspected `worn` with a note; a lost copy inspected; a member inspects | 201; copy `condition` `worn`; `409 INVALID_COPY_STATUS`; `403` | held-out |
| T-PRE-05-a | LIB-PRE-05 | Normal | Inspections `worn` on Mon and `fragile` on Tue; history | [fragile, worn]; copy `fragile` | feedback |
| T-PRE-06-a | LIB-PRE-06 | Error | A `fragile` copy lent; inspected `good` and lent | `409 COPY_FRAGILE`; 201 | held-out |
| T-PRE-07-a | LIB-PRE-07 | Normal | Only copy of a book on loan; another member reserves it at A; the copy is inspected `fragile` and returned in good condition | Copy `available`; the reservation stays `waiting` | feedback |
| T-PRE-08-a | LIB-PRE-08 | Normal | Librarian creates an in-house `repair` job of 25.00 for a damaged copy at A | 201 `requested`, `requested_at`, `branch_id` A, `priority` `normal`, `supplier_id` null | feedback |
| T-PRE-08-b | LIB-PRE-08 | Error | `supplier` without `supplier_id`; `in_house` with one; kind `gluing`; cost -0.01; unknown copy; a member creates a job | `422` five times; `403` | held-out |
| T-PRE-09-a | LIB-PRE-09 | Error | Job for a copy on loan; a second job for a copy with an open job; a job with an inactive supplier | `INVALID_COPY_STATUS` with `details.status` `on_loan`; `COPY_HAS_REPAIR_JOB` with `details.job_id`; `SUPPLIER_INACTIVE` | feedback |
| T-PRE-10-a | LIB-PRE-10 | Error | PATCH kind and cost of a requested job; PATCH after approval | 200; `409 INVALID_JOB_STATUS` with `details.status` `approved` | held-out |
| T-PRE-11-a | LIB-PRE-11 | Normal | Job for a copy returned damaged; job for an available copy | `loan_id` of that loan; null | feedback |
| T-PRE-12-a | LIB-PRE-12 | Error | Approve without a budget for 2026 (only 2027 set); with a budget; approve again | `409 NO_PRESERVATION_BUDGET`; 200 `approved` with `approved_at`; `409 INVALID_JOB_STATUS` | held-out |
| T-PRE-13-a | LIB-PRE-13 | Boundary | Librarian approves jobs of 500.00 and 500.01; admin approves the 500.01 job | 200; `403`; 200 | feedback |
| T-PRE-14-a | LIB-PRE-14 | Boundary | Branches A and B with budgets 1000.00 and 700.00 committed; A: normal jobs of 300.01 and 300.00; B: urgent jobs of 400.01 and 400.00 | A: `BUDGET_EXCEEDED` with `details.available` 300.00, then 200; B: `BUDGET_EXCEEDED`, then 200 | held-out |
| T-PRE-15-a | LIB-PRE-15 | Normal | Cancel a requested job of a damaged copy; cancel an approved job; cancel a sent job | 200 `cancelled` with `staff_request`, the copy stays `damaged`; 200; `409 INVALID_JOB_STATUS` | feedback |
| T-PRE-16-a | LIB-PRE-16 | Normal | Approved in-house `repair` job of a damaged copy returned at branch B (home A) is sent | 200 `sent`, `sent_at`, `due_back` 2026-11-09; the copy `in_repair` with current branch B | feedback |
| T-PRE-16-b | LIB-PRE-16 | Error | Send a requested job; an approved supplier job; an approved job whose available copy was lent meanwhile | `INVALID_JOB_STATUS`; `SHIPMENT_REQUIRED`; `INVALID_COPY_STATUS` with `details.status` `on_loan` | held-out |
| T-PRE-17-a | LIB-PRE-17 | Boundary | Sent on 2026-11-02: in-house rebinding; in-house conservation; urgent in-house repair; supplier repair; urgent supplier rebinding | `due_back` 2026-11-23; 2026-12-14; 2026-11-06; 2026-11-16; 2026-11-16 | feedback |
| T-PRE-18-a | LIB-PRE-18 | Normal | Copy with home branch A sent for repair at A; returned repaired | While in repair `current_branch_id` A; after the return `available` at A | held-out |
| T-PRE-19-a | LIB-PRE-19 | Normal | Two approved supplier jobs at branch AA shipped; a third shipped later | 201 code `SH-AA-1` with both jobs `sent` with `shipment_id`, copies `in_repair`; then `SH-AA-2` | feedback |
| T-PRE-19-b | LIB-PRE-19 | Error | Shipment of a good job with: a job of another supplier; an in-house job; a requested job; a job of branch B; empty list; the same job twice | `409 SHIPMENT_MISMATCH` with `details.job_id` four times (the good job stays `approved`); `422`; `422` | held-out |
| T-PRE-20-a | LIB-PRE-20 | Normal | Shipments S1 (2 jobs, one returned) and S2 (1 job) of supplier P; list; filter by another supplier | [S2, S1] with `open_jobs` 1 and 1; empty | held-out |
| T-PRE-21-a | LIB-PRE-21 | Normal | A `worn` copy's job returned `repaired` (actual 20.00); a damaged copy's job returned `unrepairable`; the first returned again | Job `returned` with outcome and cost, copy `available` and `good`; copy `damaged`; `409 INVALID_JOB_STATUS` | feedback |
| T-PRE-22-a | LIB-PRE-22 | Boundary | Jobs estimated 100.00 returned with 120.00 without note; 120.01 without note; 120.01 with a note | 200 `cost_overrun` false; `422`; 200 `cost_overrun` true | held-out |
| T-PRE-23-a | LIB-PRE-23 | Normal | Sent in-house job lost; shipped supplier job of a copy priced 80.00 lost; a requested job reported lost | Job `lost`, copy `lost` with branch null, `claim_amount` null; `claim_amount` 80.00; `409 INVALID_JOB_STATUS` | feedback |
| T-PRE-24-a | LIB-PRE-24 | Normal | Jobs J1 (sent, due 2026-11-09), J2 (requested, supplier), J3 (sent rebinding); on 2026-11-10 list; `overdue=true`; `provider=supplier`; `status=sent` | [J3, J2, J1]; [J1] with `is_overdue` true, `barcode`, `book_title`; [J2]; [J3, J1] | held-out |
| T-PRE-25-a | LIB-PRE-25 | Boundary | Job sent Mon (due 2026-11-09); process on 2026-11-09, 2026-11-10 and again | `{overdue 0, newly_overdue 0}`; `{1, 1}`; `{1, 0}` | feedback |
| T-PRE-25-b | LIB-PRE-25 | Boundary | Job requested on Mon 2026-11-02 09:00; process on 2027-01-01 09:00 and 09:00:01 | `expired_requests` 0; 1 and the job `cancelled` with `expired` | held-out |
| T-PRE-26-a | LIB-PRE-26 | Normal | At branch A: a damaged copy; a fragile copy; a worn copy lent 30 times; a worn copy lent 29 times; a damaged copy with an open job; a copy at branch B | Damaged (`damaged`), fragile (`fragile`) and the 30-loan copy (`worn_and_used`), by copy id | held-out |
| T-PRE-27-a | LIB-PRE-27 | Error | The only copy of a book is `in_repair`: lent; relocated; book availability | `409 COPY_NOT_AVAILABLE` with `details.status` `in_repair`; `409 INVALID_COPY_STATUS`; `available` 0, `total` 1 | feedback |
| T-PRE-28-a | LIB-PRE-28 | Error | Damaged copy with a requested job: direct repair; withdrawal; after cancelling the job, direct repair | `409 COPY_HAS_REPAIR_JOB` with `details.job_id` twice; 200 | held-out |
| T-PRE-29-a | LIB-PRE-29 | Normal | Book with a copy in repair, a worn copy and a good copy; copies with `status=in_repair`; with `condition=worn` | The repaired copy with `open_job_id`; the worn copy; the good copy has `open_job_id` null | feedback |
| T-PRE-30-a | LIB-PRE-30 | Normal | The only copy of a book at A is `available` but `fragile`; a member reserves it for pickup at A | 201 `waiting` | held-out |
| T-PRE-31-a | LIB-PRE-31 | Error | Admin sets a budget for an inactive branch | `409 BRANCH_INACTIVE` | feedback |
| T-PRE-32-a | LIB-PRE-32 | Error | Supplier with a requested job is deactivated; after the job is cancelled | `409 SUPPLIER_HAS_JOBS` with `details.job_ids`; 200 | held-out |
| T-PRE-33-a | LIB-PRE-33 | Normal | Book with copies at A (one in repair, due back 2026-11-09; one rebinding due 2026-11-23) and at B; a member reads the book | Row A `expected_back` 2026-11-23, `available` 0; row B `expected_back` null | feedback |
| T-PRE-34-a | LIB-PRE-34 | Error | Copy placed on reserve for a course; a repair job for it | `409 INVALID_COPY_STATUS` with `details.status` `on_reserve` | held-out |
| T-PRE-35-a | LIB-PRE-35 | Normal | Budget set; copy inspected; jobs created, changed, approved, sent, returned; a shipment; a job lost; one cancelled; process; audit log | One entry of each event | feedback |
| T-PRE-36-a | LIB-PRE-36 | Normal | The member who returned a copy damaged; the copy's job is created, approved, sent and returned | The member's notifications do not change | held-out |
| T-PRE-37-a | LIB-PRE-37 | Normal | Branch A budget 1000.00: job sent Mon returned Fri (repaired, 30.00), job sent Mon returned unrepairable on Wed 2026-11-11 (20.00), job lost, job sent and still out; branch B without budget or jobs; report 2026 | Only A: `{budget 1000.00, jobs_returned 2, repaired 1, unrepairable 1, lost 1, average_days 6.5, overdue_now 0}` | feedback |
| T-PRE-38-a | LIB-PRE-38 | Normal | Copy returned damaged (fee 30.00) repaired for 20.00; another (fee 10.00) repaired for 25.00; a job without loan; report 2026-11-02 – 2026-11-08 | Two rows with differences 10.00 and -15.00; totals `{damage_fees 40.00, costs 45.00, difference -5.00}` | feedback |
| T-PRE-38-b | LIB-PRE-38 | Error | `from` > `to`; 367 days; a member reads the report | `422`; `422`; `403` | held-out |
| T-PRE-39-a | LIB-PRE-39 | Normal | A copy `in_repair` and a `worn` copy; `GET /api/v1/export` | The keys of 22.1; the copy in repair has status `damaged`; no copy has `condition` | feedback |
| T-PRE-40-a | LIB-PRE-40 | Normal | Copy returned damaged at A (fee 30.00) while another member waits for the book at A; in-house repair 25.00 approved and sent Mon; returned repaired with 20.00 on Fri 2026-11-06 | `due_back` 2026-11-09; after the return the copy `on_hold` and the reservation `ready`; damage recovery difference 10.00 | held-out |
