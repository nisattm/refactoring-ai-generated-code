# Test cases: module 6 (Reservations)

Generated from one case list; 36 cases for 14 requirements (feedback 19, held-out 17, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-RES-01-a | LIB-RES-01 | Normal | Member reserves a lent-out book for themselves (no `member_id`) | 201, `status` `waiting`, `member_id` = own id, `queue_position` 1 | feedback |
| T-RES-01-b | LIB-RES-01 | Error | Librarian without `member_id` | `422 VALIDATION_ERROR` | held-out |
| T-RES-01-c | LIB-RES-01 | Error | Member sends `member_id` (own id) | `422 VALIDATION_ERROR` | feedback |
| T-RES-02-a | LIB-RES-02 | Error | Passive member reserves | `409 MEMBER_PASSIVE` | feedback |
| T-RES-02-b | LIB-RES-02 | Boundary | Guest registered 2026-11-02 reserves on 2027-01-30 and on 2027-01-31 | First 201; second `409 MEMBERSHIP_EXPIRED` | held-out |
| T-RES-02-c | LIB-RES-02 | Error | Book without copies; book whose only copy is withdrawn | `409 BOOK_NOT_LENDABLE` both | feedback |
| T-RES-02-d | LIB-RES-02 | Error | Same member reserves the same book twice | `409 DUPLICATE_RESERVATION` | held-out |
| T-RES-02-e | LIB-RES-02 | Error | Member reserves the book they are borrowing | `409 ALREADY_BORROWED` | feedback |
| T-RES-02-f | LIB-RES-02 | Error | Copy of the book `available` at the pickup branch | `409 COPY_AVAILABLE_AT_BRANCH` | held-out |
| T-RES-02-g | LIB-RES-02 | Error | Passive member, book without copies (steps 1 and 3 fail) | `409 MEMBER_PASSIVE` (first failing step) | feedback |
| T-RES-02-h | LIB-RES-02 | Error | Member already reserved the book and has 3 active reservations (steps 4 and 6 fail) | `409 DUPLICATE_RESERVATION` | held-out |
| T-RES-03-a | LIB-RES-03 | Boundary | Member with 2 active reservations makes a 3rd, then a 4th | 3rd 201; 4th `409 RESERVATION_LIMIT_REACHED` | feedback |
| T-RES-03-b | LIB-RES-03 | Boundary | 3 active reservations; one is cancelled; new reservation | 201 (cancelled does not count) | held-out |
| T-RES-04-a | LIB-RES-04 | Normal | M1 reserves with pickup B, then M2 with pickup A; copy returned at A | M1 (first in queue) becomes `in_transit`; M2 stays `waiting` | feedback |
| T-RES-04-b | LIB-RES-04 | Normal | Guest reserves before an academic; copy returned at the pickup branch | Guest's reservation becomes `ready` (no priority by type) | held-out |
| T-RES-05-a | LIB-RES-05 | Normal | Only copy is `available` at B; member reserves with pickup A | Reservation `in_transit` at once; copy `in_transfer` | feedback |
| T-RES-06-a | LIB-RES-06 | Normal | Three members reserve the same book | Queue view lists them in creation order with `queue_position` 1, 2, 3 | held-out |
| T-RES-07-a | LIB-RES-07 | Normal | One waiting and one cancelled reservation; filter `status=cancelled` | Only the cancelled one | feedback |
| T-RES-08-a | LIB-RES-08 | Normal | Good return at the home branch, no reservation | Copy `available` | feedback |
| T-RES-08-b | LIB-RES-08 | Normal | Good return at a foreign branch (B), no reservation | Copy `in_transfer`; a `return_home` transfer B → A exists | held-out |
| T-RES-08-c | LIB-RES-08 | Normal | Waiting reservation with pickup A; copy returned at A | Reservation `ready`, copy `on_hold` and assigned | feedback |
| T-RES-08-d | LIB-RES-08 | Normal | Waiting reservation with pickup B; copy returned at A | Reservation `in_transit` with `copy_id`; `reservation` transfer A → B | held-out |
| T-RES-09-a | LIB-RES-09 | Normal | Reservation becomes ready on Monday 2026-11-02 | `ready_on` 2026-11-02, `hold_until` 2026-11-05; notification `reservation_ready` for the member | feedback |
| T-RES-09-b | LIB-RES-09 | Boundary | Reservation becomes ready on 2026-10-28 (29 Oct holiday, weekend follows) | `hold_until` 2026-11-03 | held-out |
| T-RES-10-a | LIB-RES-10 | Normal | Member borrows the held copy | Reservation `fulfilled`, `closed_at` set; copy `on_loan` | feedback |
| T-RES-10-b | LIB-RES-10 | Normal | Ready reservation (copy C1 held); member borrows another copy C2 that became available | Reservation `fulfilled`; C1 released (`available`) | held-out |
| T-RES-10-c | LIB-RES-10 | Normal | In-transit reservation (copy C1 travelling to B); member borrows copy C2 at A | Reservation `fulfilled`; transfer of C1 continues (`in_transit`) | feedback |
| T-RES-11-a | LIB-RES-11 | Normal | Ready 2026-11-02 (hold until 2026-11-05) for M1, M2 waiting; `process-expired` on 2026-11-06 | `{"expired": 1}`; M1 `expired`; M2 `ready` with `hold_until` 2026-11-11; copy stays `on_hold` | feedback |
| T-RES-11-b | LIB-RES-11 | Boundary | Hold expired (no other reservation); librarian lends the copy to the same member without running `process-expired` | Reservation is expired first; copy becomes `available` and the loan is created; reservation stays `expired` | held-out |
| T-RES-12-a | LIB-RES-12 | Boundary | `hold_until` 2026-11-05: `process-expired` on 2026-11-05, then on 2026-11-06 | 0 expired; then 1 expired | feedback |
| T-RES-12-b | LIB-RES-12 | Boundary | Member collects on the last hold day (2026-11-05) | Loan created; reservation `fulfilled` | held-out |
| T-RES-13-a | LIB-RES-13 | Normal | Member cancels own waiting reservation | 200; `cancelled`, `cancel_reason` `member_request` | feedback |
| T-RES-13-b | LIB-RES-13 | Normal | Librarian cancels a ready reservation; nobody else waiting | `cancel_reason` `staff_request`; copy `available` | held-out |
| T-RES-13-c | LIB-RES-13 | Error | Cancel an already cancelled reservation | `409 RESERVATION_NOT_ACTIVE` | feedback |
| T-RES-13-d | LIB-RES-13 | Error | Member cancels another member's reservation | `403 FORBIDDEN` | held-out |
| T-RES-14-a | LIB-RES-14 | Boundary | Waiting reservation; 200 days later `process-expired` | Still `waiting`; 0 expired | held-out |
