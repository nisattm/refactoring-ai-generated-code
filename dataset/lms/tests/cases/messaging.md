# Test cases: module 27 (Announcements and messages)

Generated from one case list; 52 cases for 47 requirements (feedback 26, held-out 26, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-MSG-01-a | LIB-MSG-01 | Normal | Librarian creates an announcement with only title and body | 201 `draft`; all four types, `normal`, not pinned, `publish_at` now, no expiry, all branches | feedback |
| T-MSG-01-b | LIB-MSG-01 | Error | Empty body; audience []; audience [kids]; a type twice; expiry before `publish_at`; expiry 91 days later; unknown branch; inactive branch; a member creates | `422` seven times; `409 BRANCH_INACTIVE`; `403` | held-out |
| T-MSG-01-c | LIB-MSG-01 | Boundary | Expiry exactly 90 days after `publish_at` (2026-11-02 09:00 → 2027-01-31 09:00) | 201 | feedback |
| T-MSG-02-a | LIB-MSG-02 | Error | Change a draft's title; a live announcement's `publish_at`; a withdrawn one's title | 200; `409 ANNOUNCEMENT_LIVE`; `409 INVALID_ANNOUNCEMENT_STATUS` with `details.status` `withdrawn` | feedback |
| T-MSG-02-b | LIB-MSG-02 | Normal | A live announcement read by a member; its body changed; its priority changed | Stats `reads` 1, then 0 after the body change; the priority change keeps marks | held-out |
| T-MSG-03-a | LIB-MSG-03 | Error | Publish a draft; publish again; publish one whose expiry (08:30) has passed | 200 `published` with `published_at` now; `INVALID_ANNOUNCEMENT_STATUS`; `ANNOUNCEMENT_EXPIRED` | feedback |
| T-MSG-03-b | LIB-MSG-03 | Boundary | Three live pinned announcements for branch A; a fourth pinned one for A | `409 PIN_LIMIT_REACHED` with `details.limit` 3 | held-out |
| T-MSG-04-a | LIB-MSG-04 | Normal | Announcement with `publish_at` 2026-11-03 09:00 published on Mon; a member's feed on Mon; process and feed on 2026-11-03 09:00 | Mon: `published_at` null and not in the feed; Tue: `published_at` 09:00 and in the feed | held-out |
| T-MSG-05-a | LIB-MSG-05 | Normal | A live announcement withdrawn; a member reads it; withdrawn again | 200 `withdrawn` with `withdrawn_at`; `404`; `409 INVALID_ANNOUNCEMENT_STATUS` | feedback |
| T-MSG-06-a | LIB-MSG-06 | Normal | Important announcement for students of A published now; a student of A, an academic of A, a student of B; a normal announcement | One `announcement` notification with `announcement_id` for the student of A only; none for the normal one | held-out |
| T-MSG-07-a | LIB-MSG-07 | Normal | Two scheduled announcements (Tue 09:00 and Wed 09:00); process on Tue 10:00 and again | `announcements_released` 1, then 0 | feedback |
| T-MSG-08-a | LIB-MSG-08 | Boundary | Important announcement for students, `publish_at` 2026-11-03 09:00, published on Mon with an active student; process at 08:59 and 09:00 | No notification on Mon; `announcements_released` 0, then 1 with one notification | held-out |
| T-MSG-09-a | LIB-MSG-09 | Normal | Live A1 (09:00), pinned A2 (published 10:00 with `publish_at` 08:00), A3 (10:00); one for academics only; the member reads A3 | Feed [A2, A3, A1] with `read` only on A3; `unread` 2; the academic one `404` | feedback |
| T-MSG-10-a | LIB-MSG-10 | Normal | Draft D, live L, scheduled S (Wed), withdrawn W; staff list; `status=published`; `live=true`; `scheduled=true` | [W, S, L, D]; [S, L]; [L]; [S] | held-out |
| T-MSG-11-a | LIB-MSG-11 | Error | Member marks a live announcement read at 09:00 and again at 10:00; marks a draft | 200 `{announcement_id, read_at 09:00}` both times; `404` | feedback |
| T-MSG-12-a | LIB-MSG-12 | Normal | Announcement for students of A with 3 students of A (2 read it), a passive student and a student of B; an announcement for guests with no guests | `{audience_size 3, reads 2, read_rate 66.7}`; `{0, 0, 0.0}` | held-out |
| T-MSG-13-a | LIB-MSG-13 | Normal | Announcement for A and [student, academic]; a student and an academic of A, a student of B, a guest of A | In the feeds of the first two only | feedback |
| T-MSG-14-a | LIB-MSG-14 | Normal | A member writes to branch A about a general question | 201 `open` with `created_at`, one message by `member`; staff writing → `403`; an empty subject → `422` | held-out |
| T-MSG-15-a | LIB-MSG-15 | Error | A passive member writes; a thread to an inactive branch; a member with 3 threads not closed writes a fourth; after closing one | `MEMBER_PASSIVE`; `BRANCH_INACTIVE`; `THREAD_LIMIT_REACHED` with `details.limit` 3; 201 | feedback |
| T-MSG-16-a | LIB-MSG-16 | Normal | T1 (09:00) and T2 (10:00) of M, staff reply to T1 at 11:00; M lists; another member lists; staff list `status=answered` | M: [T1, T2] with T1 `unread` 1; other member: empty; staff: [T1] | held-out |
| T-MSG-17-a | LIB-MSG-17 | Normal | Thread with an internal note and a staff reply; the member reads it; reads the list; another member reads it | Member sees 2 messages (no internal note); afterwards `unread` 0; `404` | feedback |
| T-MSG-18-a | LIB-MSG-18 | Error | A member sends `internal` true; replies to a closed thread | `422`; `409 THREAD_CLOSED` | held-out |
| T-MSG-19-a | LIB-MSG-19 | Normal | Thread opened Mon 09:00; internal note 10:00; staff reply 11:00; member reply 12:00 | `open` (no notification); `answered` with `first_reply_at` 11:00 and one `message_reply`; `open` with `due_at` Wed 12:00 | feedback |
| T-MSG-20-a | LIB-MSG-20 | Error | Thread of category `loan` with another member's loan; with own loan; `loan_id` in category `general`; `fee_id` of another member | `409 NOT_OWN_RECORD` with `details.field` `loan_id`; 201; `422`; `NOT_OWN_RECORD` with `fee_id` | held-out |
| T-MSG-21-a | LIB-MSG-21 | Normal | A member's thread about own fee of 10.00; staff read it | `member` with `member_no`, `full_name`, `membership_type`; `fee` with kind, amount, status | feedback |
| T-MSG-22-a | LIB-MSG-22 | Boundary | A thread's first message plus 9 member replies on Mon; an 11th; one more on Tue; staff reply many times | `409 MESSAGE_LIMIT_REACHED` with `details.limit` 10 on the 11th; Tue 201; staff 201 | held-out |
| T-MSG-23-a | LIB-MSG-23 | Boundary | Thread opened Fri 2026-11-06 16:00; overdue list on Tue 2026-11-10 16:00 and 16:00:01 | `due_at` Tue 16:00; not overdue, then overdue | feedback |
| T-MSG-24-a | LIB-MSG-24 | Error | Assign to another librarian; filter `assigned_to=me` for both; assign to a member's user; remove; assign a closed thread | 200; listed only for the assignee; `422`; `assigned_to` null; `409 THREAD_CLOSED` | held-out |
| T-MSG-25-a | LIB-MSG-25 | Normal | Unassigned thread: an internal note by librarian L1, a reply by L2 | `assigned_to` L2 | feedback |
| T-MSG-26-a | LIB-MSG-26 | Normal | Member closes own thread; closes again; staff close another | 200 `closed` with `member_request` and `closed_at`; `409 THREAD_CLOSED`; `staff_request` | held-out |
| T-MSG-27-a | LIB-MSG-27 | Boundary | Thread closed Mon 09:00: reopened on 2026-11-16 09:00; another closed Mon reopened on 2026-11-16 09:00:01; reopen an open thread | 200 `open` with a new `due_at`; `409 THREAD_REOPEN_NOT_ALLOWED`; `409 THREAD_NOT_CLOSED` | feedback |
| T-MSG-28-a | LIB-MSG-28 | Normal | An answered thread silent for 15 days, an open one and an answered one with a member reply on day 10; process on 2026-11-17 | `threads_closed` 1; the first `closed` with `inactive` | held-out |
| T-MSG-29-a | LIB-MSG-29 | Boundary | Staff reply on Mon 09:00; process on 2026-11-16 09:00 and 09:00:01 | `threads_closed` 0, then 1 | feedback |
| T-MSG-30-a | LIB-MSG-30 | Error | Rate an open thread; a closed thread without staff reply; a closed answered thread with 4; again; rating 6 | `THREAD_NOT_CLOSED`; `NOTHING_TO_RATE`; 200 `rating` 4; `ALREADY_RATED`; `422` | held-out |
| T-MSG-31-a | LIB-MSG-31 | Normal | Thread opened Mon 09:00 (due Wed 09:00); overdue list on Wed 14:59 | `overdue_by_hours` 5 | feedback |
| T-MSG-32-a | LIB-MSG-32 | Normal | Member with an open thread is deactivated; tries to reopen it | `closed` with `member_deactivated`; `409` | held-out |
| T-MSG-33-a | LIB-MSG-33 | Normal | Member with 2 live announcements (1 read), 2 open threads and one unread staff reply plus an internal note | `{unread_announcements 1, open_threads 2, unread_replies 1}` | feedback |
| T-MSG-34-a | LIB-MSG-34 | Error | Branch QQ (no copies, no members) with a member's open thread; after closing it, with a live announcement for QQ; after withdrawing it | `BRANCH_IN_USE` twice; then 200 | held-out |
| T-MSG-35-a | LIB-MSG-35 | Normal | Announcement for academics; a student reads the feed; becomes academic; reads again | Empty; then the announcement | feedback |
| T-MSG-36-a | LIB-MSG-36 | Normal | Thread assigned to librarian U; U's user is deactivated | `assigned_to` null | held-out |
| T-MSG-37-a | LIB-MSG-37 | Normal | A member writes, closes, reopens and rates a thread; a normal announcement is published for them | No notification | feedback |
| T-MSG-38-a | LIB-MSG-38 | Normal | Announcement created, changed, published, withdrawn; thread created, message added, assigned, closed, reopened, closed again, rated; process; audit log | One entry per event (2 for `thread_closed`, at least 2 for `thread_message_added`) | held-out |
| T-MSG-39-a | LIB-MSG-39 | Normal | Threads: T1 loan (replied after 2 hours, closed, rated 4), T2 general (replied after 1 hour, rated 5), T3 other (no reply, overdue on Thu); an important and a normal announcement with 1 read; report 2026-11-02 – 2026-11-08 on Thu | `threads` 3, `by_category` loan 1, general 1, other 1; `answered` 2; `average_first_reply_hours` 1.5; `overdue_now` 1; `closed` 2; `average_rating` 4.5; announcements `{published 2, important 1, reads 1}` | feedback |
| T-MSG-39-b | LIB-MSG-39 | Error | `from` > `to`; 367 days; a member reads the report | `422`; `422`; `403` | held-out |
| T-MSG-40-a | LIB-MSG-40 | Normal | An announcement and a thread exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 | held-out |
| T-MSG-41-a | LIB-MSG-41 | Error | A withdrawn announcement: changed, published, withdrawn | `409 INVALID_ANNOUNCEMENT_STATUS` each | feedback |
| T-MSG-42-a | LIB-MSG-42 | Normal | Process with nothing to do | 200 `{announcements_released 0, threads_closed 0}` | held-out |
| T-MSG-43-a | LIB-MSG-43 | Normal | Announcement expiring Mon 10:00, pinned for A, with 2 other pinned for A; at 10:00 staff list `live=false` and a member's feed; another pinned one for A published | Still `published` and in `live=false`; not in the feed; the new pinned one 200 | feedback |
| T-MSG-44-a | LIB-MSG-44 | Normal | Branch A has 3 live pinned announcements; a pinned one for all branches; a pinned one for B | 200 both | held-out |
| T-MSG-45-a | LIB-MSG-45 | Normal | Thread assigned to L1; librarian L2 replies | `assigned_to` stays L1; the thread `answered` | feedback |
| T-MSG-46-a | LIB-MSG-46 | Normal | Pinned announcement published Mon 09:00; three normal ones published later on Mon | The pinned one first in the member's feed | held-out |
| T-MSG-47-a | LIB-MSG-47 | Normal | A member reads a live announcement; its title is changed | `read` false again and `unread` 1 | feedback |
