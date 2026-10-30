# Test cases: Module 8: Notifications

Requirements: [`../../requirements.md`](../../requirements.md). Tests: [`../feedback/test_notifications.py`](../feedback/test_notifications.py), [`../heldout/test_notifications.py`](../heldout/test_notifications.py). Split rule and conventions: [`../README.md`](../README.md).

Dates are the clock's local date (`FixedClock`, start 2026-11-02 09:00 +03:00, a Monday). Expected dates and amounts come from the examples in the requirements or were computed with the working-day rules of section 3.2 and the default holiday list.

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-NOT-01-a | LIB-NOT-01 | Normal | Member registered, then a copy is lent to them | No notification after registration; after the loan exactly one `loan_created` with the loan's `loan_id` | feedback |
| T-NOT-01-b | LIB-NOT-01 | Normal | Loan renewed, then returned on time | Types (newest first): `loan_returned`, `loan_renewed`, `loan_created` | held-out |
| T-NOT-01-c | LIB-NOT-01 | Normal | Student loan due 2026-11-16 returned late on 2026-11-20 (one late fee) | One `loan_returned` and one `fee_created` with the fee's `fee_id` | feedback |
| T-NOT-01-d | LIB-NOT-01 | Normal | Loan reported lost on 2026-11-18 (three fees, LIB-E2E-04) | One `loan_lost` and three `fee_created` (one per fee) | held-out |
| T-NOT-01-e | LIB-NOT-01 | Normal | Damage fee 20.00; payment 5.00; admin waives the fee | One `payment_received` and one `fee_waived` (with `fee_id`) | feedback |
| T-NOT-01-f | LIB-NOT-01 | Normal | S2 reserves K with pickup A; C1 returned at A | S2 gets one `reservation_ready` with the `reservation_id`; S2 has no other notification | held-out |
| T-NOT-01-g | LIB-NOT-01 | Normal | S2 reserves K with pickup B; C1 returned at A (transfer to B) | S2 gets one `reservation_in_transit` | feedback |
| T-NOT-01-h | LIB-NOT-01 | Normal | S2's reservation ready on 2026-11-02 (`hold_until` 2026-11-05); `process-expired` on 2026-11-06 | S2 has `reservation_expired` (newest) and `reservation_ready` | held-out |
| T-NOT-01-i | LIB-NOT-01 | Normal | Waiting reservation cancelled by staff; another member cancels their own waiting reservation | Staff cancel: one `reservation_cancelled`; member's own cancel: no notification | feedback |
| T-NOT-01-j | LIB-NOT-01 | Normal | Member with a waiting reservation (no loans) is deactivated | Notifications `member_deactivated` and `reservation_cancelled` (reason `member_deactivated`), one each | held-out |
| T-NOT-01-k | LIB-NOT-01 | Normal | Membership renewed | One `membership_renewed` | feedback |
| T-NOT-01-l | LIB-NOT-01 | Normal | Events without a notification: member updated, reservation created, member activated after deactivation | Only `member_deactivated` is created | held-out |
| T-NOT-01-m | LIB-NOT-01, LIB-TECH-08 | Error | A lending request that fails (`409 COPY_NOT_AVAILABLE`) | No notification for the member | feedback |
| T-NOT-01-n | LIB-NOT-01 | Normal | S2's reservation ready, then S2 borrows the held copy (reservation fulfilled) | S2 has `loan_created` and `reservation_ready` only (fulfilment creates none) | held-out |
| T-NOT-02-a | LIB-NOT-02, LIB-COM-04 | Normal | Book titled "Quiet Harbor Atlas" lent on 2026-11-02 (due 2026-11-16) | `loan_created` message contains the title and "2026-11-16" | feedback |
| T-NOT-02-b | LIB-NOT-02, LIB-COM-13 | Normal | Late fee of 8.00 created at return on 2026-11-20 | `fee_created` message contains "8.00" | held-out |
| T-NOT-02-c | LIB-NOT-02, LIB-COM-04 | Normal | Reservation for "Distant Signal" ready on 2026-11-02 (`hold_until` 2026-11-05) | `reservation_ready` message contains the title and "2026-11-05" | feedback |
| T-NOT-02-d | LIB-NOT-02, LIB-COM-13 | Normal | Payment of 12.50 | `payment_received` message contains "12.50" | held-out |
| T-NOT-02-e | LIB-NOT-02, LIB-MEM-09 | Normal | Membership (valid until 2027-11-01) renewed on 2026-11-02 | `membership_renewed` message contains the new `valid_until` "2028-10-31" (2027-11-01 + 365 days) | feedback |
| T-NOT-03-a | LIB-NOT-03 | Normal | Notifications created at 09:00, 10:00 and 11:00 | Ordered by `created_at` descending: `loan_returned`, `loan_renewed`, `loan_created`; `created_at` has offset +03:00 | feedback |
| T-NOT-03-b | LIB-NOT-03 | Normal | The member marks `loan_renewed` read; filters `unread=true` and `unread=false` | `unread=true` → `loan_returned`, `loan_created`; `unread=false` → `loan_renewed` | held-out |
| T-NOT-03-c | LIB-NOT-03 | Normal | Filter `type=loan_created` | One item | feedback |
| T-NOT-03-d | LIB-NOT-03, 14.2 | Normal | Librarian reads `GET /api/v1/notifications` with `member_id`; a member calls the same endpoint | Librarian: the member's 3 notifications; member: `403 FORBIDDEN` | held-out |
| T-NOT-03-e | LIB-NOT-03, LIB-COM-18 | Normal | `page_size=2`, page 2 | One item (`loan_created`), `total` 3 | feedback |
| T-NOT-03-f | LIB-NOT-03, LIB-AUTH-25 | Error | Another member reads this member's notifications | `403 FORBIDDEN` | held-out |
| T-NOT-03-g | LIB-NOT-03 | Boundary | Two loans lent to the same member at the same time (09:00) | Same `created_at`: ordered by `id` descending | feedback |
| T-NOT-04-a | LIB-NOT-04 | Normal | Member marks own notification read at 2026-11-02 10:00 | `200` with the notification; `read_at` "2026-11-02T10:00:00+03:00" | feedback |
| T-NOT-04-b | LIB-NOT-04 | Boundary | Marked read at 10:00, marked again at 11:00 | Second call `200`; `read_at` stays "2026-11-02T10:00:00+03:00" | held-out |
| T-NOT-04-c | LIB-NOT-04 | Normal | Member with 3 unread notifications calls `read-all` twice | First `{"updated": 3}`, second `{"updated": 0}`; no unread left | feedback |
| T-NOT-04-d | LIB-NOT-04 | Error | The librarian marks a member's notification read | `403 FORBIDDEN`; `read_at` stays null | held-out |
| T-NOT-04-e | LIB-NOT-04, LIB-AUTH-25 | Error | Another member marks the notification read | `403 FORBIDDEN` | feedback |
| T-NOT-04-f | LIB-NOT-04 | Error | `read-all` for the member called by the librarian and by another member | Both `403 FORBIDDEN`; the notification stays unread | held-out |
| T-NOT-04-g | LIB-NOT-04, LIB-COM-28 | Error | Member marks unknown notification id 999999 | `404 NOT_FOUND` | feedback |
| T-NOT-05-a | LIB-NOT-05 | Normal | Student loan due Monday 2026-11-16; reminders run on Friday 2026-11-13 (requirement example) | `{"due_reminders": 1, "overdue_notices": 0}`; the member gets a `due_reminder` with the `loan_id` | feedback |
| T-NOT-05-b | LIB-NOT-05 | Normal | Guest loan due 2026-11-09; reminders run on 2026-11-10 | `{"due_reminders": 0, "overdue_notices": 1}`; the member gets an `overdue_notice` | held-out |
| T-NOT-05-c | LIB-NOT-05 | Boundary | Loan due 2026-11-16; reminders run on Thursday 2026-11-12 (next working day 2026-11-13) | `{"due_reminders": 0, "overdue_notices": 0}` | feedback |
| T-NOT-05-d | LIB-NOT-05 | Boundary | Student lent 2026-10-16 (due Friday 2026-10-30); reminders run on 2026-10-28 (29 Oct is a holiday) | `due_reminders` 1 (next working day after 2026-10-28 is 2026-10-30) | held-out |
| T-NOT-05-e | LIB-NOT-05 | Normal | Two loans due 2026-11-16, one already returned; one guest loan returned late; run on 2026-11-13 | Only the open loan: `{"due_reminders": 1, "overdue_notices": 0}` | feedback |
| T-NOT-05-f | LIB-NOT-05, 14.2 | Error | A member runs the reminders | `403 FORBIDDEN` | held-out |
| T-NOT-06-a | LIB-NOT-06 | Boundary | Reminders run twice on 2026-11-13 for a loan due 2026-11-16 | The member has exactly one `due_reminder` | feedback |
| T-NOT-06-b | LIB-NOT-06 | Boundary | Overdue guest loan (due 2026-11-09): reminders run twice on 2026-11-10 and once on 2026-11-11 | Two `overdue_notice` in total (one per day) | held-out |
| T-NOT-06-c | LIB-NOT-06 | Boundary | Loan due Monday 2026-11-16: reminders run on Friday 2026-11-13 and Saturday 2026-11-14 | One `due_reminder` (same `due_date`) | feedback |
| T-NOT-06-d | LIB-NOT-06 | Normal | Reminder on 2026-11-13 (due 2026-11-16); loan renewed on 2026-11-13 (due 2026-11-27); reminders run on 2026-11-26 | Two `due_reminder` (the new due date allows a new one) | held-out |
| T-NOT-07-a | LIB-NOT-07 | Normal | Member with one unread notification marks it read | `{"unread": 1}` before, `{"unread": 0}` after | feedback |
| T-NOT-07-b | LIB-NOT-07, 14.2, LIB-AUTH-25 | Normal | The librarian and another member read the unread count | Librarian: `{"unread": 1}`; other member: `403 FORBIDDEN` | held-out |
