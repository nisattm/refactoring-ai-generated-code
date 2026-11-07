# Test cases: module 17 (Digital resources)

Generated from one case list; 85 cases for 40 requirements (feedback 42, held-out 43, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-DIG-01-a | LIB-DIG-01 | Normal | Librarian creates an e-book of a book without `loan_days` | 201; `loan_days` 14, active, `book_id` set | feedback |
| T-DIG-01-b | LIB-DIG-01 | Error | Database with `loan_days`; database with `book_id`; e-book `loan_days` 22 and 0; unknown `book_id`; kind `audio`; empty title; member creates | `422` seven times; `403` | held-out |
| T-DIG-02-a | LIB-DIG-02 | Normal | PATCH `title` and `loan_days` 7; PATCH `kind` | 200 with the new values; `422` | feedback |
| T-DIG-02-b | LIB-DIG-02 | Normal | E-book (14 days, 2 copies): M1 borrows Mon 09:00; `loan_days` changed to 7; M2 borrows | M1 due 2026-11-16 09:00 (unchanged); M2 due 2026-11-09 09:00 | held-out |
| T-DIG-03-a | LIB-DIG-03 | Normal | E-book with 1 copy: M1 borrowed, M2 waiting; resource deactivated; M3 borrows and holds | M2's hold `cancelled` with `resource_inactive` and one `digital_hold_cancelled` notification; M1's loan still `open`; `409 RESOURCE_INACTIVE` twice | feedback |
| T-DIG-03-b | LIB-DIG-03 | Normal | Database with an open session; resource deactivated; another member opens a session | The session has `closed_at` and `open` false; `409 RESOURCE_INACTIVE` | held-out |
| T-DIG-04-a | LIB-DIG-04 | Normal | Resources Beta, Alfa (e-books) and Delta (database, provider Springer Nature); Beta deactivated; list and filters | Order Alfa, Beta, Delta; `q=springer` → Delta; `kind=database` → Delta; `is_active=false` → Beta | feedback |
| T-DIG-04-b | LIB-DIG-04 | Normal | E-book with 2 copies: M1 and M2 borrow, M3 waits; database with 3 seats and one open session | E-book capacity 2, in_use 2, available 0, waiting_holds 1; database 3, 1, 2, 0 | held-out |
| T-DIG-05-a | LIB-DIG-05 | Normal | Admin adds a subscription 2026-11-01 – 2026-11-30 (3 copies, 1200.00) and one from 2026-11-10 | 201 `active` with the values; 201 `pending` | feedback |
| T-DIG-05-b | LIB-DIG-05 | Error | Perpetual with `ends_on`; subscription without `ends_on`; `ends_on` before `starts_on`; copies 0; e-book 101 copies; database 501 seats; cost -1.00; librarian adds | `422` seven times (database 500 seats: 201); `403` | held-out |
| T-DIG-05-c | LIB-DIG-05 | Normal | License added to an inactive resource | 201 | feedback |
| T-DIG-06-a | LIB-DIG-06 | Error | License with an `ordered` purchase order; with a draft order; with an unknown order; then the referenced order is cancelled | 201 with `order_id`; `409 INVALID_ORDER_STATUS`; `422`; cancel `409 ORDER_HAS_LICENSE` | feedback |
| T-DIG-06-b | LIB-DIG-06 | Error | License with a cancelled purchase order | `409 INVALID_ORDER_STATUS` | held-out |
| T-DIG-07-a | LIB-DIG-07 | Normal | E-book with one license; M1 borrowed; license cancelled; cancelled again; M2 borrows | 200, `cancelled_on` 2026-11-02, `cancelled`; `409 INVALID_LICENSE_STATUS`; M2 `409 NO_ACTIVE_LICENSE`; M1's loan stays `open` | feedback |
| T-DIG-07-b | LIB-DIG-07 | Error | Subscription 2026-10-01 – 2026-11-01 (ended); cancel | `409 INVALID_LICENSE_STATUS` | held-out |
| T-DIG-08-a | LIB-DIG-08 | Normal | Licenses starting 2026-11-10 (pending) and 2026-10-01; librarian lists, with `status=pending`; member lists | Order 2026-10-01, 2026-11-10; filter → the pending one; member `403` | held-out |
| T-DIG-09-a | LIB-DIG-09 | Normal | Book with an active e-book (1 copy, borrowed) and an inactive e-book; unknown book | Only the active e-book with `available` 0; `404 NOT_FOUND` | feedback |
| T-DIG-10-a | LIB-DIG-10 | Normal | Pending license: copies 5, cost 50.00; active subscription: copies 4, then `ends_on` 2026-12-15; perpetual: `ends_on`; subscription `ends_on` 2026-11-01 (before today) | 200; `409 INVALID_LICENSE_STATUS`, then 200; `422`; `422` | feedback |
| T-DIG-10-b | LIB-DIG-10 | Error | Ended subscription: change `ends_on`; librarian changes a pending license | `409 INVALID_LICENSE_STATUS`; `403` | held-out |
| T-DIG-11-a | LIB-DIG-11 | Normal | Subscription 2026-11-01 – 2026-11-30 (3 copies) renewed to 2026-12-31 (900.00); renewed again | 201: new subscription 2026-12-01 – 2026-12-31, 3 copies, 900.00, `pending`; then `409 ALREADY_RENEWED` | feedback |
| T-DIG-11-b | LIB-DIG-11 | Error | Renew a perpetual license; a pending subscription; an active subscription (ends 2026-11-30) to 2026-11-30 | `409 NOT_A_SUBSCRIPTION`; `409 INVALID_LICENSE_STATUS`; `422` | held-out |
| T-DIG-12-a | LIB-DIG-12 | Normal | Active subscriptions ending 2026-11-20 (A), 2026-12-31 (B), 2026-11-10 renewed (C), 2026-11-05 (D); list; with `ending_within_days=3` | D, A (with `resource_title`); then only D | feedback |
| T-DIG-12-b | LIB-DIG-12 | Error | `ending_within_days` 0 and 366; member reads the list | `422` twice; `403` | held-out |
| T-DIG-13-a | LIB-DIG-13 | Normal | Perpetual 2 copies and subscription 3 copies until 2026-11-30; calendar 2026-11-28 – 2026-12-02 | Capacities 5, 5, 5, 2, 2 | feedback |
| T-DIG-13-b | LIB-DIG-13 | Error | Calendar 2026-11-01 – 2027-02-15 (more than 92 days); `from` after `to` | `422` both | held-out |
| T-DIG-14-a | LIB-DIG-14 | Boundary | Perpetual 2 copies and subscription 3 copies until 2026-11-30; resource read on 2026-11-30 and 2026-12-01 | `capacity` 5, then 2 | feedback |
| T-DIG-14-b | LIB-DIG-14 | Boundary | Perpetual 1 copy cancelled on 2026-11-04; subscription 2 copies from 2026-11-10; calendar 2026-11-03 – 2026-11-04 and 2026-11-09 – 2026-11-10 | 1, 0; 0, 2 | held-out |
| T-DIG-15-a | LIB-DIG-15 | Normal | Member borrows an e-book (14 days) on Mon 09:00 | 201: own `member_id`, `open`, `hold_id` null, `renewed` false, `ended_at` null | feedback |
| T-DIG-15-b | LIB-DIG-15 | Error | Librarian borrows without `member_id`; member sends `member_id` | `422` both | held-out |
| T-DIG-15-c | LIB-DIG-15 | Normal | 1 copy: M1 borrowed, M2 waits; M1 returns; M2 borrows | Loan with `hold_id` of M2's hold; the hold `fulfilled` with `closed_at` | feedback |
| T-DIG-16-a | LIB-DIG-16 | Error | Borrow a database; borrow an inactive e-book | `409 WRONG_RESOURCE_KIND`; `409 RESOURCE_INACTIVE` | feedback |
| T-DIG-16-b | LIB-DIG-16 | Error | Passive member; guest; member on Tue 2027-11-02 (membership ended 2027-11-01) | `409 MEMBER_PASSIVE`; `409 DIGITAL_NOT_ALLOWED_FOR_TYPE`; `409 MEMBERSHIP_EXPIRED` | held-out |
| T-DIG-16-c | LIB-DIG-16 | Boundary | Member with debt 50.00; member with debt 49.99 | `409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` "50.00"; 201 | feedback |
| T-DIG-16-d | LIB-DIG-16 | Error | Member borrows the same e-book (2 copies) twice | `409 ALREADY_BORROWED` | held-out |
| T-DIG-16-e | LIB-DIG-16 | Boundary | Student with 5 active digital loans borrows a sixth e-book | `409 DIGITAL_LOAN_LIMIT_REACHED` with `details.limit` 5 | feedback |
| T-DIG-16-f | LIB-DIG-16 | Error | E-book without license; e-book with only a pending license (from 2026-11-10) | `409 NO_ACTIVE_LICENSE` both | held-out |
| T-DIG-16-g | LIB-DIG-16 | Error | 1 copy borrowed by M1; M2 borrows; M2 places a hold; M3 borrows | `409 NO_COPY_AVAILABLE` with `details.waiting` 0, then 1 | feedback |
| T-DIG-16-h | LIB-DIG-16 | Error | Passive member borrows an inactive database; and an inactive e-book | `WRONG_RESOURCE_KIND`; `RESOURCE_INACTIVE` (resource checks before member checks) | held-out |
| T-DIG-17-a | LIB-DIG-17 | Normal | E-book of 14 days borrowed Mon 09:00; e-book of 3 days borrowed Mon 09:00:30 | Due Mon 2026-11-16 09:00; due Thu 2026-11-05 09:00:30 | feedback |
| T-DIG-18-a | LIB-DIG-18 | Boundary | 1 copy, 1 day: M1 borrows Mon 09:00; M2 borrows Tue 08:59:59, then Tue 09:00 | `409 NO_COPY_AVAILABLE`; then 201; M1's loan shown `expired` with `ended_at` Tue 09:00 | feedback |
| T-DIG-18-b | LIB-DIG-18 | Normal | 1-day e-book borrowed Mon 09:00; the same member borrows it again on Tue 09:00 | 201 (a finished loan is not `ALREADY_BORROWED`) | held-out |
| T-DIG-19-a | LIB-DIG-19 | Normal | Member returns an active loan at Mon 12:00; returns it again | 200 `returned`, `ended_at` 12:00; then `409 LOAN_NOT_OPEN` | feedback |
| T-DIG-19-b | LIB-DIG-19 | Error | Return a finished loan (1 day, on Tue 09:00); another member returns a loan | `409 LOAN_NOT_OPEN`; `403` | held-out |
| T-DIG-20-a | LIB-DIG-20 | Normal | L2 (M2, R2) Mon 10:00; L1 (M1, R1 of 1 day) Mon 09:00; L3 (M1, R2) Mon 11:00, returned; list on Tue 10:00 | Order L1, L2, L3; `status=expired` → L1; `returned` → L3; `open` → L2; `resource_id` R2 → L2, L3; `member_id` M1 → L1, L3 | feedback |
| T-DIG-20-b | LIB-DIG-20 | Error | Member reads own loan, a loan of another member, the general list, own list | 200; 403; 403; 200 with 1 item | held-out |
| T-DIG-21-a | LIB-DIG-21 | Boundary | Loan due Mon 2026-11-16 09:00; renew on Fri 2026-11-13 08:59:59, at 09:00, again | `409 RENEWAL_TOO_EARLY` with `renewable_from` 2026-11-13 09:00; 200 due 2026-11-30 09:00, `renewed` true, `renewed_at` set; `409 RENEWAL_LIMIT_REACHED` | feedback |
| T-DIG-21-b | LIB-DIG-21 | Error | 1 copy (3 days) borrowed by M1, M2 waiting; M1 renews | `409 RESOURCE_HAS_HOLDS` | held-out |
| T-DIG-21-c | LIB-DIG-21 | Error | 3-day loan; license cancelled; renew; renew on Thu 09:00 (finished) | `409 NO_ACTIVE_LICENSE`; `409 LOAN_NOT_OPEN` | feedback |
| T-DIG-21-d | LIB-DIG-21 | Normal | 3-day loan due Thu 09:00; `loan_days` changed to 7; renewed | Due Thu 2026-11-12 09:00 (current `loan_days`) | held-out |
| T-DIG-22-a | LIB-DIG-22 | Normal | 1 copy borrowed; M2 places a hold herself; librarian places one for M3 | 201 `waiting` with `position` 1; 201 with `position` 2 | held-out |
| T-DIG-23-a | LIB-DIG-23 | Error | M2 holds twice; M1 (borrower) holds | `409 DUPLICATE_HOLD`; `409 ALREADY_BORROWED` | feedback |
| T-DIG-23-b | LIB-DIG-23 | Error | Hold on an e-book with a free copy; on an e-book without license | `409 HOLD_NOT_NEEDED`; `409 NO_ACTIVE_LICENSE` | held-out |
| T-DIG-23-c | LIB-DIG-23 | Boundary | Six e-books borrowed by an academic; a student holds five, then the sixth | `409 DIGITAL_HOLD_LIMIT_REACHED` with `details.limit` 5 | feedback |
| T-DIG-23-d | LIB-DIG-23 | Error | Guest holds a borrowed e-book; member holds a database | `409 DIGITAL_NOT_ALLOWED_FOR_TYPE`; `409 WRONG_RESOURCE_KIND` | held-out |
| T-DIG-24-a | LIB-DIG-24 | Normal | 1 copy borrowed; M2 holds at Mon 10:00, M3 at Mon 09:30 (clock moved back); queue; the copy is returned; queue with `status=ready` | Queue M3 (position 1), M2 (2); after the return: waiting M2 (position 1), ready M3 | held-out |
| T-DIG-25-a | LIB-DIG-25 | Normal | Member cancels own waiting hold; cancels again | `cancelled`, `member_request`, `closed_at` set, no notification; then `409 HOLD_NOT_ACTIVE` | feedback |
| T-DIG-25-b | LIB-DIG-25 | Normal | 1 copy: M1 borrowed, M2 and M3 wait; M1 returns (M2 ready); librarian cancels M2's hold | `staff_request` and one `digital_hold_cancelled` notification for M2; M3's hold becomes `ready` | held-out |
| T-DIG-25-c | LIB-DIG-25 | Error | Hold ready at Mon 10:00 (lapsed after Wed 10:00); cancelled on Wed 10:00:01; another member cancels a hold | `409 HOLD_NOT_ACTIVE`; `403` | feedback |
| T-DIG-26-a | LIB-DIG-26 | Normal | E-book "Kayıp Şehir" with 1 copy: M1 borrowed, M2 and M3 wait; M1 returns on Tue 10:00 | M2 `ready`, `ready_until` Thu 10:00, one `digital_hold_ready` notification containing the title; M3 `waiting` with position 1 | feedback |
| T-DIG-26-b | LIB-DIG-26 | Normal | 1 copy borrowed by M1; M2 and M3 wait; admin adds a license of 2 copies | Both holds `ready` | held-out |
| T-DIG-26-c | LIB-DIG-26 | Normal | 1 copy, 1 day: M1 borrowed Mon 09:00, M2 waits; on Tue 09:00 M3 borrows; process | M2 still `waiting`; `409 NO_COPY_AVAILABLE` with `waiting` 1; process gives `holds_ready` 1 and M2 `ready` | feedback |
| T-DIG-27-a | LIB-DIG-27 | Boundary | M2's hold ready at Tue 10:00 (until Thu 10:00); M3 borrows on Tue 11:00, on Thu 10:00 and on Thu 10:00:01 | `409 NO_COPY_AVAILABLE` twice; then 201 (lapsed hold keeps no copy) | feedback |
| T-DIG-27-b | LIB-DIG-27 | Boundary | M2's hold ready at Tue 10:00; M2 borrows on Thu 10:00 | 201 with `hold_id` | held-out |
| T-DIG-28-a | LIB-DIG-28 | Normal | Member opens a database session on Mon 10:00 | 201: `expires_at` 11:00, `open` true, `closed_at` null | feedback |
| T-DIG-28-b | LIB-DIG-28 | Error | Session on an e-book; second session on the same database; student opens a session on a second database | `409 WRONG_RESOURCE_KIND`; `409 SESSION_ALREADY_OPEN` with `details.session_id`; `409 SESSION_LIMIT_REACHED` with `details.limit` 1 | held-out |
| T-DIG-28-c | LIB-DIG-28 | Error | Database with 1 seat used by M1 since 10:00; M2 opens; database without license | `409 NO_SEAT_AVAILABLE` with `next_free_at` 11:00; `409 NO_ACTIVE_LICENSE` | feedback |
| T-DIG-28-d | LIB-DIG-28 | Error | Guest; member with debt 50.00; academic opens sessions on three databases | `DIGITAL_NOT_ALLOWED_FOR_TYPE`; `MEMBER_BLOCKED_BY_DEBT`; third `SESSION_LIMIT_REACHED` with `details.limit` 2 | held-out |
| T-DIG-29-a | LIB-DIG-29 | Normal | 1 seat: M1's session closed at 10:15; closed again; M2 opens | 200 with `closed_at` 10:15, `open` false; `409 SESSION_NOT_OPEN`; M2 201 | feedback |
| T-DIG-29-b | LIB-DIG-29 | Error | Another member closes M1's session; M1 closes it at 11:00 (expired) | `403`; `409 SESSION_NOT_OPEN` | held-out |
| T-DIG-30-a | LIB-DIG-30 | Boundary | Member opens and closes 6 sessions of one database on Monday; opens a seventh; opens one on Tuesday | 7th `409 DAILY_SESSION_LIMIT_REACHED`; Tuesday 201 | held-out |
| T-DIG-31-a | LIB-DIG-31 | Boundary | 1 seat: M1 opens at 10:00; M2 opens at 10:59:59 and at 11:00; M1's session read | `409 NO_SEAT_AVAILABLE`; 201; M1's session `open` false, `closed_at` null | feedback |
| T-DIG-32-a | LIB-DIG-32 | Normal | Sessions S1 (10:00, closed), S2 (12:00, open); list; `open=true` | S2, S1; then only S2 | held-out |
| T-DIG-33-a | LIB-DIG-33 | Normal | Hold of M2 becomes ready after a return | One `digital_hold_ready` notification for M2 with `digital_hold_id` | feedback |
| T-DIG-33-b | LIB-DIG-33 | Normal | Member borrows, renews and returns e-books and opens a session | The member has no notifications | held-out |
| T-DIG-34-a | LIB-DIG-34 | Boundary | Loans of 1 day (due Tue 09:00) and 2 days (due Wed 09:00) borrowed Mon 09:00; process Mon 09:00 twice; process Tue 09:00 | `due_soon_notices` 1, 0; Tue 1 (and `expired_loans` 1); 2 `digital_loan_due_soon` notifications | held-out |
| T-DIG-35-a | LIB-DIG-35 | Normal | R1 (1 day): M1 borrowed Mon 09:00, M2 waits. R2: M3 borrowed and returned Mon 09:00, M4's hold ready until Wed 09:00. Process Wed 09:00:01 | `{expired_loans: 1, expired_holds: 1, holds_ready: 1, due_soon_notices: 0}`; M1's loan stored `expired`; M4's hold `expired`; M2 `ready`; notifications `digital_loan_expired` (M1) and `digital_hold_expired` (M4) | feedback |
| T-DIG-35-b | LIB-DIG-35 | Normal | Process twice at the same time after a loan finished; member reads process | Second call all counts 0; member `403` | held-out |
| T-DIG-36-a | LIB-DIG-36 | Normal | Member with one active loan, one waiting hold and one ready hold | `digital` = `{open_loans: 1, waiting_holds: 1, ready_holds: 1}`; `borrowing.eligible` true | held-out |
| T-DIG-37-a | LIB-DIG-37 | Normal | Member with an active loan, a waiting hold and an open session is deactivated | 200; loan `returned`; hold `cancelled` with `member_deactivated` and one `digital_hold_cancelled` notification; session closed | feedback |
| T-DIG-37-b | LIB-DIG-37 | Normal | 1 copy borrowed by M1, M2 waits; M1 deactivated | M2's hold `ready` | held-out |
| T-DIG-38-a | LIB-DIG-38 | Normal | Resource created, license added, e-book borrowed and returned, hold placed, session opened; audit log filtered by event | One entry each for `digital_resource_created` (2), `digital_license_added` (2), `digital_loan_created`, `digital_loan_returned`, `digital_hold_created`, `digital_session_opened` | feedback |
| T-DIG-38-b | LIB-DIG-38 | Normal | License cancelled; process run | One entry each for `digital_license_cancelled` and `digital_processed` | held-out |
| T-DIG-39-a | LIB-DIG-39 | Normal | Alfa (e-book, license 300.00 from 2026-11-01): M1 borrows and renews Mon, M2 holds, M1 returns Tue, M2 borrows. Beta (database, 50.00): M3 opens two sessions. Gamma (inactive e-book, no license). Report 2026-11-01 – 2026-11-20; with `kind=database` | Alfa `{loans 2, renewals 1, holds_placed 1, holds_expired 0, sessions 0, license_cost "300.00"}`; Beta sessions 2, cost "50.00"; Gamma all 0 and "0.00"; `kind=database` → Beta | feedback |
| T-DIG-39-b | LIB-DIG-39 | Error | `from` > `to`; range of 367 days; member reads the report; librarian reads 2026-01-01 – 2026-12-31 | `422`; `422`; `403`; 200 | held-out |
| T-DIG-40-a | LIB-DIG-40 | Normal | A digital resource, license and loan exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 (no digital data) | held-out |
