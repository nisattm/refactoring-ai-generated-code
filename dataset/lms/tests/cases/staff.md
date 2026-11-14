# Test cases: module 19 (Staff and shifts)

Generated from one case list; 78 cases for 51 requirements (feedback 41, held-out 37, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-STF-01-a | LIB-STF-01 | Normal | Admin creates a full-time profile without `weekly_hours` and `annual_leave_days` | 201; `weekly_hours` 40, `annual_leave_days` 14, active | feedback |
| T-STF-01-b | LIB-STF-01 | Error | Part-time without `weekly_hours`; full-time with 30; part-time 31 and 9; leave days 31; `started_on` tomorrow; librarian creates | `422` six times; `403` | held-out |
| T-STF-01-c | LIB-STF-01 | Normal | Part-time profile with 20 weekly hours | 201; `annual_leave_days` 7 | feedback |
| T-STF-02-a | LIB-STF-02 | Error | Unknown user; a member's user; an inactive user; a user with a profile; an inactive home branch | `404`; `409 NOT_STAFF_ROLE`; `409 USER_INACTIVE`; `409 CONFLICT` with `details.field` `user_id`; `409 BRANCH_INACTIVE` | feedback |
| T-STF-02-b | LIB-STF-02 | Normal | Profile for the bootstrap admin user | 201 | held-out |
| T-STF-03-a | LIB-STF-03 | Normal | PATCH employment `part_time` with 25 hours; PATCH employment `part_time` alone on a full-time profile (40 hours) | 200 with the new values; `422` | feedback |
| T-STF-04-a | LIB-STF-04 | Normal | Profile with a planned shift Tue and a pending leave; profile deactivated; a new shift planned | Shift `cancelled` with `staff_deactivated`; leave `cancelled`; `409 STAFF_INACTIVE` | held-out |
| T-STF-05-a | LIB-STF-05 | Normal | Profiles P1 (A, full-time) and P2 (B, part-time); list, filters; P2 reads `staff/me` | Order P1, P2 with `full_name` and `email`; `home_branch_id` B → P2; `employment=full_time` → P1; `me` → P2 | feedback |
| T-STF-05-b | LIB-STF-05 | Error | Librarian without a profile reads `staff/me`; staff member reads another profile and the list; member reads the list | `409 NOT_STAFF`; `403`; `403`; `403` | held-out |
| T-STF-06-a | LIB-STF-06 | Normal | Staff user with a planned shift Tue is deactivated (`PATCH /users`) | Profile inactive; shift `cancelled` with `staff_deactivated` | held-out |
| T-STF-07-a | LIB-STF-07 | Normal | Member reads the hours of a branch never set; unknown branch | `{opens_at 08:00, closes_at 20:00, min_staff 1}`; `404` | feedback |
| T-STF-08-a | LIB-STF-08 | Error | Set 09:00–18:00, min 2; then 18:00–09:00; 09:00–12:30 (under 4 h); min 11; 09:15; librarian sets | 200 with the values; `422` four times; `403` | feedback |
| T-STF-08-b | LIB-STF-08 | Error | Planned shift Tue 08:00–12:00; hours changed to 09:00–20:00 | `409 SHIFTS_OUTSIDE_HOURS` with `details.shift_ids`; hours unchanged | held-out |
| T-STF-09-a | LIB-STF-09 | Boundary | Branch hours 10:00–18:00; equipment lent Mon 09:30, then 10:00 | `409 DESK_CLOSED` with `opens_at` Mon 10:00; then 201 | feedback |
| T-STF-09-b | LIB-STF-09 | Normal | Closure of branch A on Tue; equipment lent Tue 10:00 | `409 DESK_CLOSED` with `opens_at` Wed 08:00 | held-out |
| T-STF-10-a | LIB-STF-10 | Normal | Admin adds a closure for Wed with reason Sayım | 201 with `date`, `reason`, `created_by` and zero counts | feedback |
| T-STF-10-b | LIB-STF-10 | Error | Closure today; on Saturday; twice on Wed; for an inactive branch; empty reason | `422`; `409 NOT_A_WORKING_DAY`; `409 CONFLICT`; `409 BRANCH_INACTIVE`; `422` | held-out |
| T-STF-11-a | LIB-STF-11 | Normal | Branch A on Wed: a planned shift, a room booking 10:00–11:00 and an equipment reservation 10:00; closure added for Wed | Counts 1, 1, 1; all three cancelled with `branch_closed`; the member gets `room_booking_cancelled` and `equipment_reservation_cancelled` | feedback |
| T-STF-11-b | LIB-STF-11 | Normal | Shift at branch B on Wed and a shift at branch A on Thu; closure of A on Wed | `cancelled_shifts` 0; both shifts stay `planned` | held-out |
| T-STF-12-a | LIB-STF-12 | Normal | Closure Wed cancels a shift; the closure is removed on Mon; another closure Thu removed on Thu | `204`, the shift stays `cancelled`; `409 CLOSURE_IN_PAST` | held-out |
| T-STF-13-a | LIB-STF-13 | Normal | Closures B Wed, A Thu, A Wed; list; `branch_id` A; `from`=`to`=Thu | A Wed, B Wed, A Thu; A Wed, A Thu; A Thu | feedback |
| T-STF-14-a | LIB-STF-14 | Normal | Closure of A on Wed 2026-11-11 (Sayım); open days 2026-11-09 – 2026-11-15 | Mon, Tue, Thu, Fri open 08:00–20:00; Wed `closure: Sayım`; Sat, Sun `weekend` | feedback |
| T-STF-14-b | LIB-STF-14 | Error | Open days 2026-10-28 – 2026-10-30; a range of 63 days | 10-29 `holiday`, 10-28 and 10-30 open; `422` | held-out |
| T-STF-15-a | LIB-STF-15 | Error | Closure of A on Wed; availability of a room of A on Wed; booking it | `open` false, `slots` empty; `409 ROOM_CLOSED` | feedback |
| T-STF-16-a | LIB-STF-16 | Error | Book lent Mon; closure of A on Wed; on Wed returned at A, then at B | `409 BRANCH_CLOSED_TODAY`; 200 | held-out |
| T-STF-17-a | LIB-STF-17 | Normal | Student loan of a member of A due 2026-11-16; closure of A on 2026-11-16; on 2026-11-17 the member borrows another book | `due_date` stays 2026-11-16; `409 MEMBER_HAS_OVERDUE` (closures do not move due dates) | feedback |
| T-STF-18-a | LIB-STF-18 | Normal | Admin plans a shift Tue 10:00–14:30 | 201: `planned`, `hours` 4.5, `staff_name` | feedback |
| T-STF-18-b | LIB-STF-18 | Error | Start 10:15; 1.5 hours; 10.5 hours; librarian plans | `422` three times; `403` | held-out |
| T-STF-19-a | LIB-STF-19 | Error | Shift at an inactive branch; shift yesterday | `409 BRANCH_INACTIVE`; `409 SHIFT_IN_PAST` | feedback |
| T-STF-19-b | LIB-STF-19 | Error | Shifts on Saturday, on the holiday 2027-01-01 and on a closure day | `409 BRANCH_NOT_OPEN` with `details.reason` `weekend`, `holiday`, `closure` | held-out |
| T-STF-19-c | LIB-STF-19 | Boundary | Default hours 08:00–20:00: shifts 07:30–11:30, 16:30–20:30, then 16:00–20:00 | `409 OUTSIDE_BRANCH_HOURS` twice; 201 | feedback |
| T-STF-19-d | LIB-STF-19 | Error | Approved annual leave 2026-11-09 – 2026-11-13; shift on 2026-11-10 | `409 STAFF_ON_LEAVE` with `details.leave_id` | held-out |
| T-STF-19-e | LIB-STF-19 | Boundary | Shift Tue 10:00–14:00; same staff Tue 13:00–17:00, then 14:00–18:00 | `409 SHIFT_OVERLAP` with `details.shift_id`; 201 (touching is not overlapping) | feedback |
| T-STF-19-f | LIB-STF-19 | Error | Inactive profile plans a shift on Saturday; active profile plans a shift yesterday on a Saturday (2026-10-31) | `STAFF_INACTIVE`; `SHIFT_IN_PAST` (order of the checks) | held-out |
| T-STF-20-a | LIB-STF-20 | Boundary | Branch hours 07:00–22:00; shift Mon 2026-11-09 14:00–22:00; Tue 08:00–12:00, then Tue 09:00–13:00 | `409 REST_PERIOD_TOO_SHORT`; 201 | feedback |
| T-STF-20-b | LIB-STF-20 | Normal | Branch hours 07:00–22:00; shift Wed 2026-11-11 07:00–15:00; then Tue 2026-11-10 14:00–22:00 (rest to the next day) | `409 REST_PERIOD_TOO_SHORT` (9 hours) | held-out |
| T-STF-21-a | LIB-STF-21 | Boundary | Part-time 20 h: shifts Mon 4 h, Tue 8 h, Wed 8 h (week of 2026-11-09); Thu 2 h; Mon cancelled; Thu 4 h; next Mon 4 h | `409 WEEKLY_HOURS_EXCEEDED` with `planned_hours` 20 and `limit` 20; then 201 twice | feedback |
| T-STF-22-a | LIB-STF-22 | Error | Shifts Tue 10:00–14:00 (S1) and 15:00–19:00; S1 changed to end 16:00, then 15:00; at Mon 10:30 a shift of Mon 10:00 is changed | `409 SHIFT_OVERLAP`; 200; `409 SHIFT_NOT_CHANGEABLE` | feedback |
| T-STF-22-b | LIB-STF-22 | Normal | Shift of P1 Tue 10:00–14:00 moved to P2 | 200 with `staff_id` P2 | held-out |
| T-STF-23-a | LIB-STF-23 | Normal | Cancel a planned shift; cancel it again | 200 `cancelled` with `staff_request`; `409 SHIFT_NOT_CHANGEABLE` | feedback |
| T-STF-24-a | LIB-STF-24 | Normal | Shifts S3 (P2, Wed 10:00), S1 (P1, Tue 14:00), S2 (P1, Tue 08:00 at B); list; filters; P1 reads the list and P2's shifts | Order S2, S1, S3; `branch_id` B → S2; `from`=`to`=Wed → S3; P1 sees S2, S1; P1 with `staff_id` P2 → `403` | held-out |
| T-STF-25-a | LIB-STF-25 | Normal | Shifts of branch A (Tue 2026-11-03 and Thu 11-05) and of branch B (Wed); copy week 2026-11-02 of A to 2026-11-16 | `created` 2, `skipped` empty; shifts of A on 11-17 and 11-19 with the same times; nothing for B | feedback |
| T-STF-26-a | LIB-STF-26 | Normal | Shifts of branch A on Mon 2026-11-02, Tue 11-03, Wed 11-04; closure on Tue 2026-11-10; copy week 2026-11-02 to 2026-11-09 | `created` 2; `skipped` [Tue shift, `BRANCH_NOT_OPEN`]; new shifts on 11-09 and 11-11 | held-out |
| T-STF-25-b | LIB-STF-25 | Error | Copy to a Tuesday; copy to the week before `from_week` | `422` both | held-out |
| T-STF-27-a | LIB-STF-27 | Normal | Shift Tue 10:00–12:00 of a staff member; read in the shift list | `hours` 2.0 and `staff_name` equal to the user's `full_name` | feedback |
| T-STF-28-a | LIB-STF-28 | Error | Admin checks in a librarian's shift; another librarian checks it in | `403` both | held-out |
| T-STF-29-a | LIB-STF-29 | Boundary | Shift Tue 10:00–14:00: check-in at 09:29, at 09:30, again | `409 CHECK_IN_TOO_EARLY` with `opens_at` 09:30; 200; `409 SHIFT_NOT_CHANGEABLE` | feedback |
| T-STF-29-b | LIB-STF-29 | Boundary | Shift Wed 10:00–14:00: check-in at 14:00; another shift Thu 10:00–14:00 checked in at 13:59 | `409 SHIFT_OVER`; 200 | held-out |
| T-STF-30-a | LIB-STF-30 | Boundary | Shifts 09:00–13:00 on Tue, Wed, Thu; check-ins at 09:05, 09:06 and 08:40 | `late_minutes` 0, 6, 0; `checked_in_at` set | held-out |
| T-STF-31-a | LIB-STF-31 | Normal | Shift Tue 09:00–17:00 in 08:50, out 17:20; shift Wed 09:00–17:00 in 09:30, out 16:00 | `completed` with `worked_minutes` 480 and 390 | feedback |
| T-STF-31-b | LIB-STF-31 | Error | Check-out without check-in; check-out twice | `409 NOT_CHECKED_IN`; `409 SHIFT_NOT_CHANGEABLE` | held-out |
| T-STF-32-a | LIB-STF-32 | Boundary | Shift S1 Tue 09:00–17:00 checked in at 09:00 and never checked out; process at 18:00, then 18:00:01 | `auto_checked_out` 0, then 1; S1 `completed`, `checked_out_at` 18:00, `worked_minutes` 480 | held-out |
| T-STF-33-a | LIB-STF-33 | Boundary | Shift Tue 09:00–17:00 without check-in; process at Tue 16:59 and at 17:00:01 | `missed` 0, then 1; status `missed` | feedback |
| T-STF-34-a | LIB-STF-34 | Normal | Staff member requests annual leave Mon 2026-11-09 – Fri 2026-11-13 with a note | 201: own `staff_id`, `pending`, `days` 5 | feedback |
| T-STF-34-b | LIB-STF-34 | Error | `from_date` after `to_date`; 31 calendar days; note of 501 characters; kind `paid`; librarian without profile | `422` four times; `409 NOT_STAFF` | held-out |
| T-STF-35-a | LIB-STF-35 | Boundary | Today Mon 2026-11-02: annual from 11-01; sick 2026-10-26 – 10-27 (7 days before); sick from 2026-10-25 | `409 LEAVE_IN_PAST`; 201; `409 LEAVE_IN_PAST` | feedback |
| T-STF-35-b | LIB-STF-35 | Error | Leave Sat–Sun; annual 11-09 – 11-13 then unpaid 11-12 – 11-16 | `409 NO_WORKING_DAYS`; `409 LEAVE_OVERLAP` with `details.leave_id` | held-out |
| T-STF-35-c | LIB-STF-35 | Boundary | Part-time profile (7 days): annual 2026-11-09 – 2026-11-18 (8 days); then 2026-11-09 – 2026-11-17 (7 days) | `409 LEAVE_BALANCE_EXCEEDED` with `details.remaining` 7; 201 | feedback |
| T-STF-36-a | LIB-STF-36 | Normal | On 2026-10-20 annual leave Fri 2026-10-23 – Tue 2026-11-03 is requested | `days` 7 (29 Oct holiday, 28 Oct arife counts, weekends not counted) | held-out |
| T-STF-37-a | LIB-STF-37 | Normal | P1: annual 11-16 (L2), unpaid 11-09 (L1); P2: annual 11-10 (L3); list; filters; P1 reads the list and P2's | Order L1, L3, L2; `kind=annual` → L3, L2; `staff_id` P1 → L1, L2; P1 sees L1, L2; P1 with `staff_id` P2 → `403` | feedback |
| T-STF-38-a | LIB-STF-38 | Normal | Admin approves L1 with a note; approves it again; rejects L2 | L1 `approved`, `decided_by` and `decision_note` set; `409 LEAVE_NOT_PENDING`; L2 `rejected` | feedback |
| T-STF-38-b | LIB-STF-38 | Error | Admin with a profile approves own leave; a librarian approves a leave | `409 OWN_LEAVE`; `403` | held-out |
| T-STF-39-a | LIB-STF-39 | Normal | Shifts on 11-10 and 11-16; annual leave 11-09 – 11-13 approved | `cancelled_shift_ids` [11-10 shift]; it is `cancelled` with `leave`; the 11-16 shift stays `planned` | feedback |
| T-STF-40-a | LIB-STF-40 | Normal | Full-time (14 days): approved annual 11-09 – 11-13 (5), pending annual 11-16 – 11-18 (3); balance 2026 and 2027 | 2026 `{entitled 14, used 5, pending 3, remaining 6}`; 2027 `{14, 0, 0, 14}` | feedback |
| T-STF-40-b | LIB-STF-40 | Normal | Profile with 14 days started on 2026-07-01; balance 2026; another staff member reads it | `entitled` 7; `403` | held-out |
| T-STF-41-a | LIB-STF-41 | Normal | Owner cancels a pending leave; owner cancels an approved leave; admin cancels it | `cancelled`; `409 LEAVE_NOT_CANCELLABLE`; `cancelled` | feedback |
| T-STF-42-a | LIB-STF-42 | Normal | Shift Wed; sick leave Tue–Wed (2 days); sick leave 11-09 – 11-11 (3 days); balance | First `approved` with `decided_by` null, the Wed shift cancelled with `leave`; second `pending`; `used` 0 | held-out |
| T-STF-43-a | LIB-STF-43 | Normal | Tue 09:00–17:00 in 09:10, out 17:00; Wed 09:00–13:00 missed; sick Thu–Fri; report 2026-11-02 – 2026-11-08 | `{planned_hours 8, worked_hours 7.8, missed_shifts 1, late_minutes 10, leave_days 2}` | feedback |
| T-STF-43-b | LIB-STF-43 | Error | Range of 93 days; librarian reads the report | `422`; `403` | held-out |
| T-STF-44-a | LIB-STF-44 | Normal | `min_staff` 2; shifts 08:00–14:00 and 13:00–19:00 on 2026-11-09; coverage | 24 slots; 08:00 staff 1 not ok; 13:00 and 13:30 staff 2 ok; 19:30 staff 0 | feedback |
| T-STF-44-b | LIB-STF-44 | Normal | Coverage on Saturday | `open` false, `slots` empty | held-out |
| T-STF-45-a | LIB-STF-45 | Normal | Closure Wed 2026-11-11; shift Mon 11-09 08:00–18:00 only; understaffed days 11-09 – 11-15; a range of 32 days | Mon 4, Tue 24, Thu 24, Fri 24 (Wed and the weekend not listed); `422` | feedback |
| T-STF-46-a | LIB-STF-46 | Normal | Hours 08:00–20:00, `min_staff` 1; shifts 08:00–14:00 and 13:00–19:00 on 2026-11-09 | `missing_slots` 2 (19:00 and 19:30) | held-out |
| T-STF-47-a | LIB-STF-47 | Error | Branch QQ is the home branch of a staff profile; QQ deactivated | `409 BRANCH_IN_USE` | feedback |
| T-STF-48-a | LIB-STF-48 | Error | Staff member checked in on Tue 10:00; admin deactivates the user at 11:00 | `409 SHIFT_IN_PROGRESS`; the user stays active | held-out |
| T-STF-49-a | LIB-STF-49 | Normal | Member with a room booking on Wed at branch A; closure of A on Wed | The member's booking notification has type `room_booking_cancelled`; staff actions create no notifications | feedback |
| T-STF-50-a | LIB-STF-50 | Normal | Profile created, hours set, closure added, shift planned and cancelled, leave requested and approved; audit log filtered by event | One entry each | held-out |
| T-STF-51-a | LIB-STF-51 | Normal | Staff profile, shift and closure exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 | feedback |
