# Test cases: module 18 (Interlibrary loans)

Generated from one case list; 76 cases for 40 requirements (feedback 40, held-out 36, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-ILL-01-a | LIB-ILL-01 | Normal | Admin creates partner `ank01` (fee 7.50, 2.00 per day, 3 outgoing) | 201; code `ANK01`, values kept, active | feedback |
| T-ILL-01-b | LIB-ILL-01 | Error | Code `A`; fee 50.01; daily 10.01; max_outgoing 0 and 21; email `x`; duplicate code `IST` / `ist`; librarian creates | `422` six times; `409 CONFLICT` with `details.field` `code`; `403` | held-out |
| T-ILL-02-a | LIB-ILL-02 | Normal | PATCH `name` and `request_fee`; PATCH `code` | 200 with the new values; `422` | feedback |
| T-ILL-02-b | LIB-ILL-02 | Normal | Request sent to a partner with fee 5.00; partner fee changed to 9.00; received and collected | `ill_request_fee` 5.00 (value at send time) | held-out |
| T-ILL-03-a | LIB-ILL-03 | Error | Inactive partner: send a request to it; new outgoing request | `409 PARTNER_INACTIVE` both | feedback |
| T-ILL-03-b | LIB-ILL-03 | Normal | Request sent; partner deactivated; book received | 200, `received` | held-out |
| T-ILL-04-a | LIB-ILL-04 | Normal | Partners IZM, ANK (name Ankara Merkez), BUR (inactive); list; `q=merkez`; `is_active=false` | ANK, BUR, IZM; ANK; BUR | feedback |
| T-ILL-04-b | LIB-ILL-04 | Normal | Partner with one sent incoming request, one cancelled one and one shipped outgoing request; member reads partners | `open_incoming` 1, `open_outgoing` 1; member `403` | held-out |
| T-ILL-05-a | LIB-ILL-05 | Normal | Member requests a book with a hyphenated ISBN | 201: `requested`, own `member_id`, ISBN without hyphens, `tried_partner_ids` empty, `partner_id` null | feedback |
| T-ILL-05-b | LIB-ILL-05 | Error | Librarian without `member_id`; member with `member_id`; invalid ISBN; empty title | `422` each | held-out |
| T-ILL-06-a | LIB-ILL-06 | Error | Passive member; member on 2027-11-02 (membership ended) | `409 MEMBER_PASSIVE`; `409 MEMBERSHIP_EXPIRED` | feedback |
| T-ILL-06-b | LIB-ILL-06 | Error | Guest requests | `409 ILL_NOT_ALLOWED_FOR_TYPE` | held-out |
| T-ILL-06-c | LIB-ILL-06 | Boundary | Member with debt 50.00; member with debt 49.99 | `409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` "50.00"; 201 | feedback |
| T-ILL-06-d | LIB-ILL-06 | Error | Member with a book loan due 2026-11-16 requests on 2026-11-17 | `409 MEMBER_HAS_OVERDUE` | held-out |
| T-ILL-06-e | LIB-ILL-06 | Boundary | Student with 2 open requests (one cancelled request does not count) makes a third | `409 ILL_LIMIT_REACHED` with `details.limit` 2 | feedback |
| T-ILL-06-f | LIB-ILL-06 | Error | ISBN of a catalog book with an available copy; ISBN of a catalog book whose only copy is on loan | `409 AVAILABLE_LOCALLY` with `details.book_id`; 201 | held-out |
| T-ILL-06-g | LIB-ILL-06 | Error | Member requests the same ISBN twice | `409 DUPLICATE_ILL_REQUEST` | feedback |
| T-ILL-06-h | LIB-ILL-06 | Error | Passive guest requests | `MEMBER_PASSIVE` (checked before the membership type) | held-out |
| T-ILL-07-a | LIB-ILL-07 | Normal | Librarian sends a request to partner P | 200: `sent`, `partner_id` P, `tried_partner_ids` [P] | feedback |
| T-ILL-07-b | LIB-ILL-07 | Error | Sent to P1 and rejected; sent to P1 again; then to P2 | `409 PARTNER_ALREADY_TRIED`; 200 with `tried_partner_ids` [P1, P2] | held-out |
| T-ILL-07-c | LIB-ILL-07 | Boundary | Rejected by three partners; sent to a fourth | `409 ILL_TRY_LIMIT_REACHED` | feedback |
| T-ILL-07-d | LIB-ILL-07 | Error | Send a `received` request; send a `cancelled` request | `409 INVALID_ILL_STATUS` with `details.status` `received` and `cancelled` | held-out |
| T-ILL-08-a | LIB-ILL-08 | Normal | Sent request rejected with a reason; a `requested` request rejected | 200 `rejected` with `reject_reason`, one `ill_request_rejected` notification; `409 INVALID_ILL_STATUS` | feedback |
| T-ILL-08-b | LIB-ILL-08 | Error | Reject with an empty reason; member rejects | `422`; `403` | held-out |
| T-ILL-09-a | LIB-ILL-09 | Normal | Member cancels own `requested` request; cancels again | 200 `cancelled`, `member_request`, `closed_on` today, no notification; `409 INVALID_ILL_STATUS` | feedback |
| T-ILL-09-b | LIB-ILL-09 | Normal | Librarian cancels a `sent` request; another member cancels a request | `staff_request` and one `ill_request_cancelled` notification; `403` | held-out |
| T-ILL-09-c | LIB-ILL-09 | Error | Cancel a `received` request | `409 INVALID_ILL_STATUS` | feedback |
| T-ILL-10-a | LIB-ILL-10 | Normal | Book "Nadir Eser" received Mon 2026-11-02 with partner due 2026-11-20, replacement 350.00, pickup at branch A | `received`, `received_on` 11-02, `collect_until` 11-09, `due_on` 11-17; one `ill_request_received` notification with the title | feedback |
| T-ILL-10-b | LIB-ILL-10 | Error | Receive with an inactive pickup branch; with replacement 0.00; receive a `requested` request | `409 BRANCH_INACTIVE`; `422`; `409 INVALID_ILL_STATUS` | held-out |
| T-ILL-11-a | LIB-ILL-11 | Boundary | Today Mon 2026-11-02: partner due Wed 2026-11-11 (due_on 11-06); Thu 2026-11-12 (due_on 11-09) | `409 ILL_PERIOD_TOO_SHORT` with `details.due_on` 2026-11-06; then 200 with `due_on` 2026-11-09 | feedback |
| T-ILL-12-a | LIB-ILL-12 | Normal | Partner due Mon 2026-11-16 | `due_on` Wed 2026-11-11 | feedback |
| T-ILL-12-b | LIB-ILL-12 | Normal | On Mon 2026-10-19 a book is received with partner due Mon 2026-11-02 | `due_on` Tue 2026-10-27 (29 Oct is a holiday) | held-out |
| T-ILL-13-a | LIB-ILL-13 | Normal | Received request collected on Mon | 200: `on_loan`, `collected_on` 2026-11-02, not overdue, accrued 0.00 | feedback |
| T-ILL-13-b | LIB-ILL-13 | Boundary | Received Mon (collect until 2026-11-09): one collected on 11-09, another on 11-10 | 200; `409 ILL_COLLECT_PERIOD_OVER` | held-out |
| T-ILL-13-c | LIB-ILL-13 | Error | Book received; member gets a debt of 50.00; collect | `409 MEMBER_BLOCKED_BY_DEBT`; the request stays `received` | feedback |
| T-ILL-14-a | LIB-ILL-14 | Normal | Partner fee 7.50: collected; partner fee 0.00: collected | One `ill_request_fee` 7.50 with `ill_request_id`; no fee for the second | held-out |
| T-ILL-15-a | LIB-ILL-15 | Normal | Member asks for a renewal of an on-loan request; asks again | 200 `renewal` `requested`; `409 ILL_RENEWAL_ALREADY_REQUESTED` | feedback |
| T-ILL-15-b | LIB-ILL-15 | Error | Renewal asked on 2026-11-18 (due 11-17); renewal asked for a `received` request | `409 ILL_OVERDUE`; `409 INVALID_ILL_STATUS` | held-out |
| T-ILL-16-a | LIB-ILL-16 | Normal | Renewal requested; partner approves until Fri 2026-12-04 | `renewal` `approved`, `partner_due_on` 12-04, `due_on` Tue 2026-12-01; one `ill_renewal_answered` notification | feedback |
| T-ILL-16-b | LIB-ILL-16 | Error | Answer without a renewal request; refused answer; approval with a date before the old one | `409 ILL_NO_RENEWAL_REQUESTED`; `renewal` `refused` and due dates unchanged; `422` | held-out |
| T-ILL-17-a | LIB-ILL-17 | Normal | On-loan request returned at branch B on 2026-11-10; returned again | 200 `returned`, `returned_on` 11-10, no fee; `409 INVALID_ILL_STATUS` | feedback |
| T-ILL-18-a | LIB-ILL-18 | Normal | Due 2026-11-17, 2.50 per day; returned 2026-11-20 | `ill_late_fee` 7.50 | feedback |
| T-ILL-18-b | LIB-ILL-18 | Boundary | Replacement 5.00, 2.00 per day: one returned 2026-11-20 (3 days late), one returned 2026-11-17 | Fee 5.00 (cap); no fee | held-out |
| T-ILL-19-a | LIB-ILL-19 | Boundary | Request due 2026-11-17; the member borrows a book on 11-17 and another on 11-18 | 201; `409 MEMBER_HAS_OVERDUE` | feedback |
| T-ILL-19-b | LIB-ILL-19 | Normal | Request due 2026-11-17, 2.50 per day; balance and request read on 2026-11-20 | Request overdue with accrued 7.50; balance `accrued_late_fees` 7.50, `total_debt` 7.50 | held-out |
| T-ILL-20-a | LIB-ILL-20 | Normal | Close a `returned` request; close an `on_loan` request | 200 `closed` with `closed_on`; `409 INVALID_ILL_STATUS` | held-out |
| T-ILL-21-a | LIB-ILL-21 | Normal | Request due 2026-11-17 (1.00 per day, replacement 200.00) reported lost on 2026-11-20 | `lost`; fees `ill_late_fee` 3.00 and `ill_lost` 200.00 | feedback |
| T-ILL-21-b | LIB-ILL-21 | Error | Reported lost before its due date; a returned request reported lost | Only `ill_lost`; `409 INVALID_ILL_STATUS` | held-out |
| T-ILL-22-a | LIB-ILL-22 | Boundary | Received Mon (collect until 2026-11-09); process on 11-09 and on 11-10; then close | `uncollected` 0, then 1; status `uncollected`, one `ill_request_uncollected` notification, no fee; close 200 | feedback |
| T-ILL-22-b | LIB-ILL-22 | Boundary | Copy shipped to a partner Mon (due 2026-11-30); process on 11-30 and on 12-01 | `{uncollected: 0, overdue_outgoing: 0}`, then `overdue_outgoing` 1 | held-out |
| T-ILL-23-a | LIB-ILL-23 | Normal | R1 (M1, on loan, due 11-17), R2 (M2, sent to P2), R3 (M1, requested); list on 2026-11-18 and filters | Order R1, R2, R3; `status=sent` → R2; `partner_id` P2 → R2; `overdue=true` → R1; `member_id` M1 → R1, R3 | feedback |
| T-ILL-23-b | LIB-ILL-23 | Error | Member reads own request, a request of another member, the general list, own list | 200; 403; 403; 200 with 1 item | held-out |
| T-ILL-24-a | LIB-ILL-24 | Normal | Librarian creates an outgoing request; one for an unknown book; member creates one | 201 `requested` with `copy_id` null; `404`; `403` | held-out |
| T-ILL-25-a | LIB-ILL-25 | Normal | Outgoing request shipped with an available copy on Mon | `shipped`, `shipped_on` 11-02, `due_on` 11-30; copy `at_partner`; book availability 0 of 1 | feedback |
| T-ILL-25-b | LIB-ILL-25 | Error | Ship with a copy of another book; with a copy on loan | `422`; `409 INVALID_COPY_STATUS` | held-out |
| T-ILL-25-c | LIB-ILL-25 | Error | Partner has a copy due 2026-11-30 not returned; on 12-01 a second request is shipped | `409 PARTNER_HAS_OVERDUE` | feedback |
| T-ILL-26-a | LIB-ILL-26 | Normal | Decline a requested outgoing request; decline a shipped one | 200 `declined`; `409 INVALID_ILL_STATUS` | held-out |
| T-ILL-27-a | LIB-ILL-27 | Boundary | Partner with `max_outgoing` 2 and two requested outgoing requests: a third; after one is declined, again | `409 PARTNER_LIMIT_REACHED` with `details.limit` 2; then 201 | feedback |
| T-ILL-28-a | LIB-ILL-28 | Normal | Copy (home branch A) shipped Mon; returned at branch B on 2026-11-10 (no reservation) | Outgoing `returned`, `returned_on` 11-10; copy `in_transfer` (return transfer to its home branch, LIB-RES-08 (a)) | feedback |
| T-ILL-28-b | LIB-ILL-28 | Normal | Only copy at a partner; a member reserves the book for pickup at A; copy returned at A | Copy `on_hold`; reservation `ready` | held-out |
| T-ILL-29-a | LIB-ILL-29 | Normal | Copy (price 120.00) shipped; partner reports it lost | Outgoing `lost`, `amount_due` 120.00; copy `lost` | feedback |
| T-ILL-30-a | LIB-ILL-30 | Normal | O1 (P1, book "Kırmızı", shipped with barcode OUT-001), O2 (P2, requested); list and filters | Order O1, O2; O1 `book_title` Kırmızı, `barcode` OUT-001; O2 `barcode` null; `status=requested` → O2; `partner_id` P1 → O1 | held-out |
| T-ILL-31-a | LIB-ILL-31 | Normal | Copy at a partner: lent to a member; copies listed with `status=at_partner` | `409 COPY_NOT_AVAILABLE` with `details.status` `at_partner`; the copy is listed | feedback |
| T-ILL-32-a | LIB-ILL-32 | Error | Member with an on-loan request is deactivated | `409 MEMBER_HAS_OPEN_LOANS` | feedback |
| T-ILL-32-b | LIB-ILL-32 | Normal | Member with a `requested` and a `sent` request is deactivated | Both `cancelled` with `member_deactivated`; two `ill_request_cancelled` notifications | held-out |
| T-ILL-33-a | LIB-ILL-33 | Error | Branch QQ is the pickup branch of a received request; QQ deactivated | `409 BRANCH_IN_USE` | feedback |
| T-ILL-34-a | LIB-ILL-34 | Normal | Academic with an overdue on-loan request (due 11-17) and a requested one; summary on 2026-11-18 | `ill` = `{open_requests: 2, on_loan: 1, overdue: 1}`; `borrowing.eligible` false with `MEMBER_HAS_OVERDUE` | held-out |
| T-ILL-35-a | LIB-ILL-35 | Normal | Request fee 8.00; payment 3.00; admin waives the fee; fee list `kind=ill_request_fee` | Paid 3.00, outstanding 5.00; `waived`; the list has this fee | feedback |
| T-ILL-36-a | LIB-ILL-36 | Normal | Book "Mavi Defter" received with pickup at branch A (collect until 2026-11-09) | `ill_request_received` message contains the title, the branch name and 2026-11-09 | feedback |
| T-ILL-36-b | LIB-ILL-36 | Normal | Member requests, the request is sent, received, collected (no fee), renewal asked and returned | The member's notifications: only `ill_request_received` | held-out |
| T-ILL-37-a | LIB-ILL-37 | Normal | Partner created; request created, sent, received, collected, returned, closed; audit log filtered by event | One entry each | feedback |
| T-ILL-37-b | LIB-ILL-37 | Normal | Outgoing request created, shipped and returned | One entry each for `ill_outgoing_created`, `ill_outgoing_shipped`, `ill_outgoing_returned` | held-out |
| T-ILL-38-a | LIB-ILL-38 | Normal | Partners AAA and BBB (unused). AAA: request R1 sent and rejected, R2 sent and received, returned late on 11-20; an outgoing copy (price 90.00) shipped and lost. Report 2026-11-01 – 2026-11-30 | AAA `{sent 2, rejected 1, received 1, late_returns 1, outgoing_shipped 1, outgoing_returned 0, outgoing_lost 1, amount_due "90.00"}`; BBB all 0 and "0.00" | feedback |
| T-ILL-38-b | LIB-ILL-38 | Error | `from` > `to`; range of 367 days; member reads the report; librarian reads 2026-01-01 – 2026-12-31 | `422`; `422`; `403`; 200 | held-out |
| T-ILL-39-a | LIB-ILL-39 | Normal | Partner, requests and a copy at a partner exist; `GET /api/v1/export` | The export has exactly the keys of 22.1; the copy is exported with status `at_partner` | feedback |
| T-ILL-40-a | LIB-ILL-40 | Error | Book without copies that has a declined outgoing request is deleted | `409 IN_USE` | held-out |
