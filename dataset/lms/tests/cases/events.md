# Test cases: module 20 (Events)

Generated from one case list; 66 cases for 47 requirements (feedback 35, held-out 31, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-EVT-01-a | LIB-EVT-01 | Normal | Librarian creates a talk on Wed 14:00–16:00, capacity 10, without description, room, fee, audience | 201 `draft`; fee 0.00, audience `all`, room and series null | feedback |
| T-EVT-01-b | LIB-EVT-01 | Error | 30 minutes; 4.5 hours; capacity 0 and 201; fee 200.01; kind `concert`; an individual room; a room of another branch; capacity 7 in a room for 6; unknown staff; member creates | `422` ten times; `403` | held-out |
| T-EVT-02-a | LIB-EVT-02 | Error | Event yesterday; on Saturday; Wed 19:00–21:00; in an inactive room | `EVENT_IN_PAST`; `BRANCH_NOT_OPEN` with reason `weekend`; `OUTSIDE_BRANCH_HOURS`; `ROOM_INACTIVE` | feedback |
| T-EVT-02-b | LIB-EVT-02 | Boundary | Group room booked Wed 14:00–15:00; event in that room 14:00–16:00; event 15:00–17:00; another event 16:00–17:00 | `ROOM_NOT_AVAILABLE` with `details.booking_id`; 201; `ROOM_NOT_AVAILABLE` with `details.event_id` | held-out |
| T-EVT-02-c | LIB-EVT-02 | Error | Inactive staff profile; inactive branch (no staff home) | `STAFF_INACTIVE`; `BRANCH_INACTIVE` | feedback |
| T-EVT-03-a | LIB-EVT-03 | Normal | Staff on shift Wed 08:00–18:00; event Wed 14:00–16:00 published; published again | 200 `published` with `published_at`; `409 INVALID_EVENT_STATUS` with `details.status` `published` | feedback |
| T-EVT-03-b | LIB-EVT-03 | Error | Event Wed 14:00–16:00: staff without a shift; staff with a shift 10:00–15:00; staff with a shift at another branch 08:00–18:00 | `409 STAFF_NOT_ON_SHIFT` each | held-out |
| T-EVT-03-c | LIB-EVT-03 | Boundary | Now Mon 09:00; events Tue 09:00–10:00 and Tue 08:30–09:30 (staff on shift Tue 08:00–12:00) | First published (exactly 24 hours); second `409 EVENT_TOO_SOON` | feedback |
| T-EVT-04-a | LIB-EVT-04 | Error | PATCH title and capacity of a draft; PATCH `audience`; PATCH a cancelled event | 200; `422`; `409 INVALID_EVENT_STATUS` | feedback |
| T-EVT-04-b | LIB-EVT-04 | Error | Published event Wed 14:00–16:00 (staff shift 08:00–18:00) moved to 17:00–19:00 | `409 STAFF_NOT_ON_SHIFT`; the event keeps its times | held-out |
| T-EVT-05-a | LIB-EVT-05 | Error | Fee changed to 15.00 before any registration; after a registration changed to 20.00 | 200; `409 FEE_LOCKED` | feedback |
| T-EVT-06-a | LIB-EVT-06 | Normal | Capacity 2: M1, M2 registered, M3 waiting; capacity set to 1; then to 3 | `409 CAPACITY_BELOW_REGISTERED` with `details.registered` 2; then 200 and M3 `registered` | held-out |
| T-EVT-07-a | LIB-EVT-07 | Normal | Published event with M1 registered and M2 waiting (capacity 1); start moved to 15:00–16:00 | One `event_changed` notification each for M1 and M2 | feedback |
| T-EVT-08-a | LIB-EVT-08 | Normal | Published E2 (Thu, capacity 2, one registration), published E1 (Wed, workshop), draft D (Wed); member and librarian list | Member: E1, E2; librarian: E1, D, E2 (by date and time); `kind=workshop` → E1; E2 `registered` 1, `free_places` 1 | feedback |
| T-EVT-08-b | LIB-EVT-08 | Error | Member reads a draft event | `404 NOT_FOUND` | held-out |
| T-EVT-09-a | LIB-EVT-09 | Normal | Published event; the staff member's shift is cancelled afterwards | `staff_covered` true, then false; the event stays `published` | feedback |
| T-EVT-10-a | LIB-EVT-10 | Normal | Event with fee 20.00, capacity 1: M1 registered (fee open), M2 waiting; librarian cancels the event | Event `cancelled` (`staff_request`); both registrations `cancelled` with `event_cancelled`; M1's fee `waived`; one `event_cancelled` notification each | feedback |
| T-EVT-10-b | LIB-EVT-10 | Error | Cancel a cancelled event; member cancels an event | `409 INVALID_EVENT_STATUS`; `403` | held-out |
| T-EVT-11-a | LIB-EVT-11 | Normal | Draft event in a group room Wed 14:00–16:00; a room booking 15:00–16:00; availability; free rooms 14:00–15:00 | `409 ROOM_ALREADY_BOOKED` with `details.event_id`; slots 14:00–15:30 not free with `booking_id` null; the room is not listed | feedback |
| T-EVT-12-a | LIB-EVT-12 | Normal | Published event Wed with M registered; draft event Wed; closure of the branch on Wed | `cancelled_events` 2; events `cancelled` with `branch_closed`; M's registration `cancelled` (`event_cancelled`) and one `event_cancelled` notification | held-out |
| T-EVT-13-a | LIB-EVT-13 | Normal | Series of 3 weeks from Tue 2026-11-10, 18:00–19:00, book club | 201: 3 draft events on 11-10, 11-17, 11-24 with the same `series_id`; `skipped` empty | feedback |
| T-EVT-13-b | LIB-EVT-13 | Error | Series with `weeks` 1 and 13 | `422` both | held-out |
| T-EVT-14-a | LIB-EVT-14 | Error | Series of 2 weeks starting on Saturday 2026-11-07 (every date fails) | `409 SERIES_EMPTY`; no event is created | held-out |
| T-EVT-15-a | LIB-EVT-15 | Normal | Series of 4 weeks from Tue 2026-11-10; closure of the branch on Tue 2026-11-24 | Created 11-10, 11-17, 12-01; skipped `{date 2026-11-24, error_code BRANCH_NOT_OPEN}` | feedback |
| T-EVT-16-a | LIB-EVT-16 | Normal | Series of 2 weeks (staff on shift both Tuesdays); the first event is published | First `published`, second still `draft` | held-out |
| T-EVT-17-a | LIB-EVT-17 | Normal | Series of 3 weeks from Wed 2026-11-04 14:00 (first published); on Wed 15:00 the series is cancelled; unknown series | `cancelled` lists the 2nd and 3rd events (`series_cancelled`); the first is unchanged; `404` | feedback |
| T-EVT-18-a | LIB-EVT-18 | Normal | Both events of a 2-week series published; a member registers for the first | The member has one registration | held-out |
| T-EVT-19-a | LIB-EVT-19 | Normal | Capacity 1: member registers herself; librarian registers a second member | 201 `registered` (position null); 201 `waitlisted` with position 1 | feedback |
| T-EVT-19-b | LIB-EVT-19 | Error | Librarian without `member_id`; member with `member_id` | `422` both | held-out |
| T-EVT-20-a | LIB-EVT-20 | Error | Registration for a draft; for a cancelled event; a passive member for a draft | `409 EVENT_NOT_OPEN` each | feedback |
| T-EVT-20-b | LIB-EVT-20 | Error | Passive member; event on Tue 2027-11-02 for a member whose membership ends 2027-11-01 | `409 MEMBER_PASSIVE`; `409 MEMBERSHIP_EXPIRED` | held-out |
| T-EVT-20-c | LIB-EVT-20 | Boundary | Member with debt 50.00; member with debt 49.99 | `409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` "50.00"; 201 | feedback |
| T-EVT-20-d | LIB-EVT-20 | Error | Member registers twice (registered); a waiting member registers again | `409 ALREADY_REGISTERED` both | held-out |
| T-EVT-20-e | LIB-EVT-20 | Boundary | Student registered for 5 upcoming events registers for a sixth | `409 EVENT_REGISTRATION_LIMIT_REACHED` with `details.limit` 5 | feedback |
| T-EVT-20-f | LIB-EVT-20 | Boundary | Capacity 1: M1 registered, M2 waiting; M3 registers | `409 WAITLIST_FULL` | held-out |
| T-EVT-21-a | LIB-EVT-21 | Normal | Fee 25.00, capacity 1: M1 registers, M2 waits; M1 cancels in time | M1 gets an `event_fee` 25.00 with `event_registration_id` (= `fee_id`); M2 no fee until promoted, then 25.00 | feedback |
| T-EVT-22-a | LIB-EVT-22 | Normal | Capacity 1: M2 registered at 09:00, M3 waiting, M1 cancelled; list of the event; M3's own list | Order M2 (registered), M3 (waitlisted), M1 (cancelled); `status=waitlisted` → M3; M3's list has `event_title` | held-out |
| T-EVT-23-a | LIB-EVT-23 | Normal | Capacity 2: M1, M2 registered; M3, M4 waiting; M2 cancels | M3 `registered` with `promoted_at`; M4 `waitlisted` position 1; one `event_promoted` notification for M3 | feedback |
| T-EVT-24-a | LIB-EVT-24 | Normal | Audience `students`: a student and an academic register; audience `all`: a guest; audience `academics`: a staff member (membership type `staff`) | 201; `409 EVENT_NOT_FOR_TYPE`; 201; `409 EVENT_NOT_FOR_TYPE` | held-out |
| T-EVT-25-a | LIB-EVT-25 | Boundary | M registered for Wed 14:00–16:00; registers for 15:30–17:00, then 16:00–17:00; M waiting for a full event 10:00–12:00, then registers for 11:00–12:00 | `409 EVENT_TIME_CONFLICT` with `details.event_id`; 201; the waiting registration causes no conflict | feedback |
| T-EVT-26-a | LIB-EVT-26 | Boundary | Event Tue 18:00–19:00 (staff on shift 10:00–20:00); registrations at Tue 16:59 and 17:00 | 201; `409 REGISTRATION_CLOSED` | held-out |
| T-EVT-27-a | LIB-EVT-27 | Normal | Member cancels own registration; cancels again; another member cancels a registration | 200 `cancelled`, `member_request`, `cancelled_at`; `409 REGISTRATION_NOT_ACTIVE`; `403` | feedback |
| T-EVT-27-b | LIB-EVT-27 | Error | Librarian cancels a registration at Wed 14:00 (event started) | `409 EVENT_STARTED` | held-out |
| T-EVT-28-a | LIB-EVT-28 | Normal | Fee 30.00; member cancels on Mon (more than 24 hours before Wed 14:00) | Fee `waived`; `late_cancellation` false | held-out |
| T-EVT-29-a | LIB-EVT-29 | Normal | Fee 30.00, capacity 1: M1 registered, M2 waiting; both cancel on Wed 10:00 | M1 `late_cancellation` true and fee stays `open`; M2 `late_cancellation` false | feedback |
| T-EVT-30-a | LIB-EVT-30 | Boundary | Event Thu 18:00–19:00, fee 10.00; M1 cancels at Wed 18:00, M2 at Wed 18:00:01 | M1 in time (fee `waived`); M2 late (fee `open`) | held-out |
| T-EVT-31-a | LIB-EVT-31 | Boundary | Capacity 1: M1 registered, M2 waiting; M1 cancels at Wed 13:01 (event 14:00) | M2 stays `waitlisted` (no promotion in the last hour) | feedback |
| T-EVT-32-a | LIB-EVT-32 | Boundary | Event Wed 14:00–16:00: check-in at 13:29 and 13:30; another at 16:00; a waiting registration | `409 CHECK_IN_NOT_OPEN`; 200 `attended`; `409 EVENT_OVER`; `409 REGISTRATION_NOT_ACTIVE` | held-out |
| T-EVT-33-a | LIB-EVT-33 | Boundary | Event Wed 14:00–16:00, capacity 2: M1 attended, M2 registered, M3 waiting; process at 16:00 and 16:00:01 | First all 0; then `{completed_events 1, no_shows 1, bans 0, reminders 0}`; event `completed`; M2 `no_show`; M3 `cancelled` (`event_cancelled`) | feedback |
| T-EVT-33-b | LIB-EVT-33 | Boundary | Event Thu 10:00 with M1 registered and M2 waiting (capacity 1); process Wed 09:59, Wed 10:00, again | `reminders` 0, 1, 0; M1 has one `event_reminder`, M2 none | held-out |
| T-EVT-34-a | LIB-EVT-34 | Normal | Member is a no-show at events on Wed 11-04 and Wed 11-11; processed after each | No ban after two no-shows (`bans` 0); the member can still register | held-out |
| T-EVT-35-a | LIB-EVT-35 | Normal | Member with no-shows on 11-03, 11-10 and a registration (fee 15.00) for an event on 12-01 where M2 waits; third no-show on 11-17 processed | The 12-01 registration `cancelled` with `member_banned`, fee waived; M2 promoted | feedback |
| T-EVT-36-a | LIB-EVT-36 | Normal | No-shows on events of Tue 2026-11-03, 11-10 and 11-17, processed on each day; registration for another event afterwards | Third process: `bans` 1; ban 2026-11-17 – 2026-12-16 with one `event_ban_started` notification; `409 MEMBER_BANNED_FROM_EVENTS` with `details.ends_on` 2026-12-16 | held-out |
| T-EVT-37-a | LIB-EVT-37 | Error | Member reads own bans; another member's bans | 200 (empty list); `403` | feedback |
| T-EVT-38-a | LIB-EVT-38 | Normal | Event fee 40.00; payment 15.00; balance | Fee paid 15.00, outstanding 25.00; `outstanding_fees` 25.00; fee list `kind=event_fee` has it | held-out |
| T-EVT-39-a | LIB-EVT-39 | Normal | Member registered for one upcoming event and waiting for another (capacity 1) | `events` = `{registered 1, waitlisted 1, no_shows_90_days 0, banned_until null}` | feedback |
| T-EVT-40-a | LIB-EVT-40 | Normal | Capacity 1: M1 registered (fee 12.00, unpaid), M2 waiting; M1 deactivated | 200; M1's registration `cancelled` with `member_deactivated`, fee stays `open`; M2 `registered` | held-out |
| T-EVT-41-a | LIB-EVT-41 | Normal | Capacity 1: M1 registered, M2 waiting; M1 deactivated (no fee) | M2 gets one `event_promoted` notification | feedback |
| T-EVT-42-a | LIB-EVT-42 | Error | Branch QQ (no staff home) has a draft event; QQ deactivated | `409 BRANCH_IN_USE` | held-out |
| T-EVT-43-a | LIB-EVT-43 | Error | Staff profile responsible for a draft event is deactivated; after the event is cancelled | `409 STAFF_HAS_EVENTS` with `details.event_ids`; then 200 | feedback |
| T-EVT-44-a | LIB-EVT-44 | Normal | Member registers for a free event and cancels; registers for another | The member has no notifications | feedback |
| T-EVT-44-b | LIB-EVT-44 | Normal | Event "Masal Saati" cancelled with a registered member | The `event_cancelled` notification has `event_id` and contains the title and the date | held-out |
| T-EVT-45-a | LIB-EVT-45 | Normal | Event created, changed, published; registration created and cancelled; event cancelled; process; audit log by event | One entry each | feedback |
| T-EVT-46-a | LIB-EVT-46 | Normal | Event E1 Wed (fee 10.00, capacity 3): M1 attended, M2 no-show, M3 late cancellation; event E2 Thu cancelled; draft D; report 2026-11-02 – 2026-11-08 | E1 `{status completed, capacity 3, registered 2, attended 1, no_shows 1, late_cancellations 1, fees_charged 30.00}`, E2 `cancelled` with zeros; D not listed | feedback |
| T-EVT-46-b | LIB-EVT-46 | Error | `from` > `to`; range of 367 days; member reads the report | `422`; `422`; `403` | held-out |
| T-EVT-47-a | LIB-EVT-47 | Normal | An event and a registration exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 | feedback |
