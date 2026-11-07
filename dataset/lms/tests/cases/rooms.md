# Test cases: module 15 (Study rooms)

Generated from one case list; 99 cases for 45 requirements (feedback 54, held-out 45, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-ROOM-01-a | LIB-ROOM-01 | Normal | Admin creates an individual room without `capacity`, `min_participants`, `features`; code `ra1` | 201; capacity 1, min_participants 1, features `[]`, code `RA1`, active | feedback |
| T-ROOM-01-b | LIB-ROOM-01 | Error | Code `G1` twice in branch A; then `G1` in branch B | `409 CONFLICT` with `details.field` `code`; 201 in branch B | held-out |
| T-ROOM-01-c | LIB-ROOM-01 | Error | Group capacity 2; group min 1; individual capacity 2; opens 07:15; closes 23:30; opens = closes; feature `sofa`; duplicate feature | `422 VALIDATION_ERROR` each | feedback |
| T-ROOM-01-d | LIB-ROOM-01 | Error | Librarian creates a room | `403 FORBIDDEN` | held-out |
| T-ROOM-02-a | LIB-ROOM-02 | Error | Room in an inactive branch | `409 BRANCH_INACTIVE` | feedback |
| T-ROOM-02-b | LIB-ROOM-02 | Error | `PATCH` with `branch_id` | `422 VALIDATION_ERROR`; branch unchanged | held-out |
| T-ROOM-03-a | LIB-ROOM-03 | Normal | Rooms `BB` and `AB` in branch A, `AA` in branch B; list; filter `branch_id` B | Order AB, BB, AA (branch, then code); filter gives AA | feedback |
| T-ROOM-03-b | LIB-ROOM-03 | Normal | Filters `kind=group`, `min_capacity=5`, `feature=whiteboard&feature=projector` | Only the rooms matching every filter | held-out |
| T-ROOM-04-a | LIB-ROOM-04 | Normal | `PATCH` name and `closes_at` `21:00` | 200 with the new values | feedback |
| T-ROOM-04-b | LIB-ROOM-04 | Error | Group room capacity 6: `min_participants` 7; `kind` change | `422 VALIDATION_ERROR` both | held-out |
| T-ROOM-05-a | LIB-ROOM-05 | Error | Booking Tue 18:00-19:00; `PATCH closes_at` `18:00` | `409 ROOM_HAS_BOOKINGS`, `details.booking_ids` [id]; hours unchanged | feedback |
| T-ROOM-05-b | LIB-ROOM-05 | Error | Group booking with 4 persons; `capacity` 3; `min_participants` 5 | `409 ROOM_HAS_BOOKINGS` both | held-out |
| T-ROOM-06-a | LIB-ROOM-06 | Normal | Booking for Tuesday; room deactivated | Room inactive; booking `cancelled` with `room_closed`, `late_cancellation` false | feedback |
| T-ROOM-06-b | LIB-ROOM-06 | Error | Booking an inactive room | `409 ROOM_INACTIVE` | held-out |
| T-ROOM-07-a | LIB-ROOM-07 | Normal | Room 09:00-11:00; availability on Tuesday | Slots 09:00, 09:30, 10:00, 10:30, each 30 minutes, all free | feedback |
| T-ROOM-08-a | LIB-ROOM-08 | Normal | Room 09:00-11:00 with a booking 09:30-10:30; librarian reads availability | 09:30 and 10:00 not free with the booking id; 09:00 and 10:30 free | feedback |
| T-ROOM-08-b | LIB-ROOM-08 | Boundary | Availability on Saturday 2026-11-07; without `date` | `open` false and `slots` []; `422 VALIDATION_ERROR` | held-out |
| T-ROOM-08-c | LIB-ROOM-08 | Normal | Booking of member A; availability read by member A and by member B | A sees the booking id; B sees `booking_id` null and `free` false | feedback |
| T-ROOM-09-a | LIB-ROOM-09 | Normal | Free rooms Tue 10:30-11:30: R1 free, R2 booked 10:00-11:00, R3 open from 12:00, R4 inactive | Only R1 | feedback |
| T-ROOM-09-b | LIB-ROOM-09 | Error | `start_time` `10:15`; `end_time` before `start_time` | `422 VALIDATION_ERROR` both | held-out |
| T-ROOM-10-a | LIB-ROOM-10 | Normal | Member books Tue 10:00-11:00 without participants and purpose | 201; own `member_id`, `booked`, `participant_ids` [], `purpose` "", `duration_minutes` 60, `room_code`, `branch_id` | feedback |
| T-ROOM-10-b | LIB-ROOM-10 | Error | Librarian without `member_id`; member with own `member_id` | `422 VALIDATION_ERROR` both | held-out |
| T-ROOM-11-a | LIB-ROOM-11 | Error | Start `10:15`; start = end; end `11:45` | `422 VALIDATION_ERROR` each | feedback |
| T-ROOM-11-b | LIB-ROOM-11 | Boundary | Academic member: 30 minutes; 4 hours; 4.5 hours | 201; 201; `422 VALIDATION_ERROR` | held-out |
| T-ROOM-11-c | LIB-ROOM-11 | Error | Group room: a participant listed twice; the organizer as participant | `422 VALIDATION_ERROR` both | feedback |
| T-ROOM-12-a | LIB-ROOM-12 | Error | Booking for a passive member | `409 MEMBER_PASSIVE` | feedback |
| T-ROOM-12-b | LIB-ROOM-12 | Boundary | Student registered 2026-11-02 (valid until 2027-11-01); on 2027-10-28 books 2027-11-01 and 2027-11-02 | 201; `409 MEMBERSHIP_EXPIRED` | held-out |
| T-ROOM-12-c | LIB-ROOM-12 | Error | Guest member books | `409 ROOM_NOT_ALLOWED_FOR_TYPE` | feedback |
| T-ROOM-12-d | LIB-ROOM-12 | Error | Staff ban 2026-11-02 to 2026-11-05; booking for 2026-11-09 | `409 MEMBER_BANNED_FROM_ROOMS` with `details.ends_on` 2026-11-05 (in force today) | held-out |
| T-ROOM-12-e | LIB-ROOM-12 | Boundary | Member with a damage fee of 50.00 | `409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` "50.00" | feedback |
| T-ROOM-12-f | LIB-ROOM-12 | Error | Booking on Saturday 2026-11-07 | `409 ROOM_CLOSED` | held-out |
| T-ROOM-12-g | LIB-ROOM-12 | Boundary | Room 08:00-20:00: 07:30-08:30; 19:30-20:30; 19:00-20:00 | `409 OUTSIDE_ROOM_HOURS` twice; 201 | feedback |
| T-ROOM-12-h | LIB-ROOM-12 | Boundary | Now Mon 09:00: booking today 09:00-09:30; today 09:30-10:00 | `409 BOOKING_IN_PAST`; 201 | held-out |
| T-ROOM-12-i | LIB-ROOM-12 | Boundary | Student on Mon 2026-11-02 books 2026-11-09 and 2026-11-10 | 201; `409 BOOKING_TOO_FAR_AHEAD` with `details.latest_date` 2026-11-09 | feedback |
| T-ROOM-12-j | LIB-ROOM-12 | Boundary | Academic on Mon 2026-11-02 books 2026-11-16 and 2026-11-17 | 201; `409 BOOKING_TOO_FAR_AHEAD` | held-out |
| T-ROOM-12-k | LIB-ROOM-12 | Error | Order: guest books on Saturday; room and branch both inactive | `ROOM_NOT_ALLOWED_FOR_TYPE` (step 5 before 8); `BRANCH_INACTIVE` (step 1 before 2) | feedback |
| T-ROOM-12-l | LIB-ROOM-12 | Error | Member B books 10:30-11:30 where A has 10:00-11:00 | `409 ROOM_ALREADY_BOOKED` | held-out |
| T-ROOM-12-m | LIB-ROOM-12 | Error | Member books another room overlapping their own booking | `409 MEMBER_DOUBLE_BOOKED` with `details.member_id` | feedback |
| T-ROOM-13-a | LIB-ROOM-13 | Error | Individual room with a participant | `409 PARTICIPANTS_NOT_ALLOWED` | feedback |
| T-ROOM-13-b | LIB-ROOM-13 | Error | Participant id that does not exist | `404 NOT_FOUND` | held-out |
| T-ROOM-13-c | LIB-ROOM-13 | Error | Group room min 3; organizer + 1 participant | `409 NOT_ENOUGH_PARTICIPANTS` with `details.min_participants` 3 | feedback |
| T-ROOM-13-d | LIB-ROOM-13 | Error | Group room capacity 3; organizer + 3 participants | `409 ROOM_CAPACITY_EXCEEDED` with `details.capacity` 3 | held-out |
| T-ROOM-13-e | LIB-ROOM-13 | Error | Participants: P1 passive (smaller id), P2 guest | `409 PARTICIPANT_NOT_ELIGIBLE`, `member_id` P1, `reason` `MEMBER_PASSIVE`; with P2 only: `reason` `ROOM_NOT_ALLOWED_FOR_TYPE` | feedback |
| T-ROOM-13-f | LIB-ROOM-13 | Normal | Group booking with participants given in descending id order | 201; `participant_ids` ascending | held-out |
| T-ROOM-14-a | LIB-ROOM-14 | Boundary | A books 09:00-10:00, B books 10:00-11:00 in the same room; A books another room 10:00-10:30 | All 201 (touching intervals do not overlap) | held-out |
| T-ROOM-15-a | LIB-ROOM-15 | Error | Student with 2 hours on Tuesday books 30 more minutes | `409 DAILY_ROOM_QUOTA_EXCEEDED` with `member_id`, `used` "2.5" | feedback |
| T-ROOM-15-b | LIB-ROOM-15 | Error | Student is participant in 2-hour group bookings Mon, Tue, Wed; books Thu 30 minutes | `409 WEEKLY_ROOM_QUOTA_EXCEEDED`, `used` "6.5" | held-out |
| T-ROOM-15-c | LIB-ROOM-15 | Error | Student with 2 future bookings books a third | `409 ROOM_BOOKING_LIMIT_REACHED` with `details.limit` 2 | feedback |
| T-ROOM-15-d | LIB-ROOM-15 | Error | Participant P has 2 hours on Tuesday; group booking with P on Tuesday | `409 DAILY_ROOM_QUOTA_EXCEEDED` with `details.member_id` P | held-out |
| T-ROOM-16-a | LIB-ROOM-16 | Boundary | Student with 1.5 hours on Tuesday: books 1 hour; books 30 minutes | `409 DAILY_ROOM_QUOTA_EXCEEDED` with `used` "2.5"; 201 | feedback |
| T-ROOM-16-b | LIB-ROOM-16 | Boundary | Student with 6 hours in the week (as participant); books Thursday; books Monday of the next week | `409 WEEKLY_ROOM_QUOTA_EXCEEDED`; 201 | held-out |
| T-ROOM-17-a | LIB-ROOM-17 | Normal | Librarian books for a member | `created_by` = the librarian's user id; `member_id` = the member | feedback |
| T-ROOM-18-a | LIB-ROOM-18 | Normal | Bookings on Wed 10:00, Tue 14:00, Tue 10:00; P is participant of a group booking; member list of P | All-bookings list ordered by date, start; P's list contains the group booking | feedback |
| T-ROOM-18-b | LIB-ROOM-18 | Normal | Filters `status=cancelled`, `from`/`to` = Wednesday, `member_id` of a participant | Only the matching bookings | held-out |
| T-ROOM-19-a | LIB-ROOM-19 | Error | Group booking: an unrelated member reads it; a participant reads it | `403 FORBIDDEN`; 200 | feedback |
| T-ROOM-20-a | LIB-ROOM-20 | Normal | Organizer adds a participant and changes the purpose | 200; participants ascending; purpose changed | feedback |
| T-ROOM-20-b | LIB-ROOM-20 | Error | `PATCH` after the start; `PATCH` of a cancelled booking | `409 BOOKING_NOT_CHANGEABLE` both | held-out |
| T-ROOM-21-a | LIB-ROOM-21 | Normal | Group min 2 with organizer + P1 + P2; P1 leaves | 200; participants [P2]; still `booked` | feedback |
| T-ROOM-21-b | LIB-ROOM-21 | Normal | Group min 2 with organizer + P; P leaves | Booking `cancelled` with `not_enough_participants` | held-out |
| T-ROOM-21-c | LIB-ROOM-21 | Error | A member who is not a participant calls `leave` | `403 FORBIDDEN` | feedback |
| T-ROOM-22-a | LIB-ROOM-22 | Normal | Organizer cancels a day ahead; cancels again | `cancelled`, `member_request`, not late; second `409 BOOKING_NOT_ACTIVE` | feedback |
| T-ROOM-22-b | LIB-ROOM-22 | Normal | Librarian cancels 30 minutes before the start | `staff_request`, `late_cancellation` false | held-out |
| T-ROOM-22-c | LIB-ROOM-22 | Error | A participant (not organizer) cancels | `403 FORBIDDEN` | feedback |
| T-ROOM-23-a | LIB-ROOM-23 | Boundary | Start 10:00: organizer A cancels at 10:15; organizer B cancels at 10:16 | A: 200, late; B: `409 BOOKING_NOT_ACTIVE` | feedback |
| T-ROOM-24-a | LIB-ROOM-24 | Boundary | Start 14:00: organizer A cancels at 12:00; organizer B cancels at 12:01 | A not late; B late | held-out |
| T-ROOM-25-a | LIB-ROOM-25 | Normal | Student books Tue 10:00-12:00, cancels, books Tue 13:00-15:00 | 201 (the cancelled booking does not count) | feedback |
| T-ROOM-26-a | LIB-ROOM-26 | Normal | Group booking (organizer + P); room deactivated | Organizer and P each get a `room_booking_cancelled` notification | held-out |
| T-ROOM-27-a | LIB-ROOM-27 | Boundary | Start 10:00: check-in at 09:49; at 09:50 | `409 CHECK_IN_TOO_EARLY` with `details.earliest` 09:50; then 200 `checked_in` | feedback |
| T-ROOM-27-b | LIB-ROOM-27 | Boundary | Start 10:00: A checks in at 10:15; B checks in at 10:16 | A 200; B `409 CHECK_IN_TOO_LATE` | held-out |
| T-ROOM-27-c | LIB-ROOM-27 | Error | Check-in of a cancelled booking | `409 BOOKING_NOT_ACTIVE` | feedback |
| T-ROOM-28-a | LIB-ROOM-28 | Normal | Tue: booking 08:00-09:00 checked in at 08:00; booking 10:00-11:00 never checked in; process at 10:16 | `{no_shows: 1, completed: 1, bans: 0}`; statuses `completed` and `no_show` | feedback |
| T-ROOM-28-b | LIB-ROOM-28 | Boundary | Start 10:00: process at 10:15; again at 10:16 | 0 no-shows; then 1 | held-out |
| T-ROOM-28-c | LIB-ROOM-28 | Normal | Booking 10:00-11:00 due as a no-show, not processed; at 10:20 another member books the room 10:30-11:00 | 201 (the due no-show does not block the room); the first booking is still `booked` | feedback |
| T-ROOM-29-a | LIB-ROOM-29 | Normal | Academic booking 10:00-12:00 checked in at 10:00, checked out at 10:41 | `completed`, `end_time` 11:00, `duration_minutes` 60; 11:00-12:00 free again | feedback |
| T-ROOM-29-b | LIB-ROOM-29 | Boundary | Booking A 10:00-11:00 checked out at 10:05; booking B 10:00-11:00 checked out at 11:10 | A `end_time` 10:30 (minimum 30 minutes); B `end_time` 11:00 (not later than before) | held-out |
| T-ROOM-29-c | LIB-ROOM-29 | Error | Check-out of a `booked` booking | `409 BOOKING_NOT_ACTIVE` | feedback |
| T-ROOM-30-a | LIB-ROOM-30 | Normal | Group booking (organizer + P) is processed as a no-show | Organizer: one `no_show_fee` of 10.00 with `room_booking_id`, `loan_id` null; P: no fee | feedback |
| T-ROOM-30-b | LIB-ROOM-30 | Normal | After one no-show, the member's balance | `outstanding_fees` "10.00", `total_debt` "10.00" | held-out |
| T-ROOM-31-a | LIB-ROOM-31 | Normal | No-shows on Tue, Wed and Thu (2026-11-03 to 11-05) | Third processing reports `bans` 1; ban `no_shows` from 2026-11-05 to 2026-11-18 | feedback |
| T-ROOM-31-b | LIB-ROOM-31 | Normal | Three no-shows lead to a ban; after it ends, one more no-show | No second ban (earlier incidents do not count again) | held-out |
| T-ROOM-32-a | LIB-ROOM-32 | Boundary | No-shows on 2026-11-03 and 2026-11-10; late cancellation on 2026-11-20 | Ban from 2026-11-20 to 2026-12-03 | feedback |
| T-ROOM-32-b | LIB-ROOM-32 | Boundary | No-shows on 2026-11-03, 2026-12-03 and 2026-12-04 | No ban | held-out |
| T-ROOM-33-a | LIB-ROOM-33 | Normal | Member has bookings Tue and Wed; staff ban for Tuesday only | Tuesday `cancelled` with `member_banned`; Wednesday still `booked` | feedback |
| T-ROOM-33-b | LIB-ROOM-33 | Normal | Banned member is the only participant of a group booking (min 2) | Member removed; booking `cancelled` with `not_enough_participants` | held-out |
| T-ROOM-34-a | LIB-ROOM-34 | Error | Ban starting yesterday; `ends_on` before `starts_on`; librarian creates a ban | `422`; `422`; `403` | held-out |
| T-ROOM-35-a | LIB-ROOM-35 | Normal | Admin lifts a ban in force; member books; admin lifts it again | 200 with `lifted_at`; booking 201; `409 BAN_NOT_ACTIVE` | feedback |
| T-ROOM-36-a | LIB-ROOM-36 | Normal | Bans 2026-11-02 to 11-03 and 2026-11-10 to 11-12; list on 2026-11-02 | Order: the 11-10 ban first; `in_force` false and true | held-out |
| T-ROOM-37-a | LIB-ROOM-37 | Normal | Member organizes a booking and is the participant of another group booking (organizer + member + P); member deactivated | Own booking `cancelled` with `member_deactivated`; removed from the group booking, which stays `booked` | feedback |
| T-ROOM-37-b | LIB-ROOM-37 | Error | Member checked in to a room; deactivation | `409 MEMBER_IN_ROOM` | held-out |
| T-ROOM-38-a | LIB-ROOM-38 | Normal | Student with a future booking becomes `guest` | Booking `cancelled` with `staff_request` | held-out |
| T-ROOM-39-a | LIB-ROOM-39 | Error | Branch with an active room is deactivated; after the room is deactivated | `409 BRANCH_IN_USE`; then 200 | feedback |
| T-ROOM-40-a | LIB-ROOM-40 | Normal | Member with one booking Tue 10:00-11:00 and no ban; summary | `rooms` = `{upcoming_bookings: 1, banned_until: null, hours_this_week: "1.0"}` | held-out |
| T-ROOM-41-a | LIB-ROOM-41 | Normal | No-show is processed | Organizer gets one `room_no_show` notification with `room_booking_id` | feedback |
| T-ROOM-41-b | LIB-ROOM-41 | Normal | Group booking created with participant P; organizer's own notifications | P gets one `room_participant_added`; the organizer gets none | held-out |
| T-ROOM-42-a | LIB-ROOM-42 | Normal | Mon: group booking for Tue (organizer + P), individual booking for Wed; room reminders run twice; loan reminders run | `{room_reminders: 2}`, then 0; loan reminders unchanged `{due_reminders: 0, overdue_notices: 0}` | held-out |
| T-ROOM-43-a | LIB-ROOM-43 | Normal | Room created and booked; audit log filtered by event | One `room_created` and one `room_booking_created` entry | feedback |
| T-ROOM-44-a | LIB-ROOM-44 | Normal | Room 08:00-20:00; 2-hour booking on Tue checked in and completed; report 2026-11-02 to 2026-11-06 | `open_hours` "60.0", `booked_hours` "2.0", `used_hours` "2.0", `no_shows` 0, `utilization` "3.3" | feedback |
| T-ROOM-44-b | LIB-ROOM-44 | Error | `from` after `to`; range of 367 days; member | `422`; `422`; `403` | held-out |
| T-ROOM-45-a | LIB-ROOM-45 | Normal | Rooms and a booking exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 (no rooms or bookings) | feedback |
