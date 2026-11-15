# Test cases: module 26 (Reading programs)

Generated from one case list; 52 cases for 47 requirements (feedback 27, held-out 25, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-RDP-01-a | LIB-RDP-01 | Normal | Librarian creates a program for branch A, 2026-11-02 – 2026-11-30, goal 5, max 50, reward 20.00, without description and audience | 201 `draft`; `audience` `all`; `description` empty | feedback |
| T-RDP-01-b | LIB-RDP-01 | Error | 12 and 121 days long; goal 0; reward 50.01; audience `everyone`; a duplicate name (other case); an inactive branch; a member creates | `422` five times; `409 CONFLICT` with `details.field` `name`; `409 BRANCH_INACTIVE`; `403` | held-out |
| T-RDP-01-c | LIB-RDP-01 | Boundary | Programs 13 days (2026-11-02 – 2026-11-15) and 120 days (– 2027-03-02) long | 201 each | feedback |
| T-RDP-02-a | LIB-RDP-02 | Error | Draft: change goal; published with 2 participants: description; goal; `max_participants` 1; a cancelled program changed | 200; 200; `409 PROGRAM_PUBLISHED`; `409 PARTICIPANTS_ABOVE_LIMIT` with `details.participants` 2; `409 INVALID_PROGRAM_STATUS` | held-out |
| T-RDP-03-a | LIB-RDP-03 | Error | Publish a draft; publish again; publish a draft that ended on 2026-10-31 | 200 `published` with `published_at`; `INVALID_PROGRAM_STATUS`; `PROGRAM_ENDED` | feedback |
| T-RDP-04-a | LIB-RDP-04 | Normal | Published program (goal 1) with an active participant A and a completed participant B is cancelled; cancelled again | 200 `cancelled`; A `left` and one `program_cancelled` notification; B `completed`; `409 INVALID_PROGRAM_STATUS` | held-out |
| T-RDP-05-a | LIB-RDP-05 | Normal | Program (goal 1) ending 2026-11-30 with one completed and one active participant; process on 2026-12-01 | `{closed 1, participants_completed 1, participants_not_completed 1}`; program `closed` with `closed_at` | feedback |
| T-RDP-06-a | LIB-RDP-06 | Boundary | Program 2026-11-02 – 2026-11-30; process on 2026-11-30 and on 2026-12-01 | `closed` 0; then 1 | held-out |
| T-RDP-07-a | LIB-RDP-07 | Normal | Programs P1 (published, starts Mon), P2 (draft), P3 (published, starts 2026-11-16) with max 10 and one participant M; M lists; staff list `running=true`; M reads P2 | M: [P1, P3] with `my_participation` only on P3, P3 `participants` 1 and `free_places` 9; staff: [P1]; `404` | feedback |
| T-RDP-08-a | LIB-RDP-08 | Error | Featured books set to [Zeki, Ayna]; read by a member; 31 books; set on a closed program | 200; ordered Ayna, Zeki; `422`; `409 INVALID_PROGRAM_STATUS` | held-out |
| T-RDP-09-a | LIB-RDP-09 | Normal | Program "Kitap Kurdu" 2026-11-02 – 2026-11-30 with a featured book copied twice with `starts_on` 2027-01-04 | Drafts "Kitap Kurdu (copy)" and "Kitap Kurdu (copy 2)", 2027-01-04 – 2027-02-01, the same goal and featured book | feedback |
| T-RDP-10-a | LIB-RDP-10 | Normal | A student joins with `public` false; a member sends `member_id`; staff omit it; staff join a member | 201 `active`, `joined_at`, `points` 0, `books` 0, `level` `none`, `public` false; `422`; `422`; 201 | held-out |
| T-RDP-11-a | LIB-RDP-11 | Error | Join a draft; a program that ended yesterday; a passive member; an academic joins a `students` program; join twice | `PROGRAM_NOT_OPEN`; `PROGRAM_ENDED`; `MEMBER_PASSIVE`; `PROGRAM_NOT_FOR_TYPE`; `ALREADY_JOINED` | feedback |
| T-RDP-11-b | LIB-RDP-11 | Boundary | Program with max 1 and one participant; a member with debt 50.00; a member already in 3 active programs joins a fourth | `PROGRAM_FULL`; `MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` 50.00; `PROGRAM_LIMIT_REACHED` with `details.limit` 3 | held-out |
| T-RDP-11-c | LIB-RDP-11 | Boundary | Student registered 2026-11-02 (valid until 2027-11-01); program 2027-10-15 – 2027-12-01; joins on 2027-11-02 | `409 MEMBERSHIP_EXPIRED` | feedback |
| T-RDP-12-a | LIB-RDP-12 | Normal | Program from 2026-11-09; M joins on Mon 11-02; returns a book on 11-02 and another on 11-10 | Only the 11-10 return counts (`books` 1) | held-out |
| T-RDP-13-a | LIB-RDP-13 | Normal | M with one entry leaves; leaves again; joins again | 200 `left` with `member_request`; `409 PARTICIPATION_NOT_ACTIVE`; 201 with the same participation id, `active` and the entry kept | feedback |
| T-RDP-14-a | LIB-RDP-14 | Error | M sets own participation `public` false; another member changes it | 200; `403` | held-out |
| T-RDP-15-a | LIB-RDP-15 | Normal | M joins P1 (one book read) and later P2; M lists own programs | [P2, P1] with `program_name`, `goal_books`, `books`; P1 `rank` 1, P2 `rank` null | feedback |
| T-RDP-16-a | LIB-RDP-16 | Normal | Participant returns a book on time on Mon | One `loan` entry with `book_id`, `loan_id`, 10 points, `on` 2026-11-02; participation `points` 10, `books` 1 | held-out |
| T-RDP-17-a | LIB-RDP-17 | Normal | Program at A, goal 10: book X returned on time; X again; a loan from A returned 1 day late on 2026-11-17; a loan from B; a lost loan; a loan returned on 2026-12-01 | Entries: X 10, the late book 5; nothing else (`books` 2, `points` 15) | feedback |
| T-RDP-18-a | LIB-RDP-18 | Normal | M borrows a book on Mon 09:00, joins at 10:00 and returns the book at 11:00 | The return counts (`books` 1) | held-out |
| T-RDP-19-a | LIB-RDP-19 | Error | Manual entry of book X; X again; 3 manual entries then a fourth; an unknown book; a manual entry in a program starting 2026-11-16; for a participation that left | 201 `manual` 10 points; `BOOK_ALREADY_COUNTED`; `MANUAL_ENTRY_LIMIT` with `details.limit` 3; `422`; `PROGRAM_NOT_RUNNING`; `PARTICIPATION_NOT_ACTIVE` | feedback |
| T-RDP-20-a | LIB-RDP-20 | Error | Participation (goal 5) with a loan entry and a manual entry: remove the manual one; remove the loan one | 204 and `points` 10, `books` 1; `409 ENTRY_NOT_MANUAL` | held-out |
| T-RDP-21-a | LIB-RDP-21 | Normal | Participant registered for an event on Wed 14:00 at A; checked in at 13:45; checked in elsewhere again not possible | One `event` entry with `event_id`, 15 points; `books` 0 | feedback |
| T-RDP-22-a | LIB-RDP-22 | Normal | Entries: a loan (Mon 09:00) and a manual one (10:00); list; `source=manual` | [loan, manual] with `book_title`; [manual] | held-out |
| T-RDP-23-a | LIB-RDP-23 | Normal | Featured book F: returned on time; another featured book G added manually; a non-featured book returned on time | Points 15, 15, 10 | feedback |
| T-RDP-24-a | LIB-RDP-24 | Normal | Book entries on 2026-11-03, 2026-11-10 and 2026-11-17 (goal 10) | A `bonus` entry of 10 points after the third week; `points` 40 | held-out |
| T-RDP-25-a | LIB-RDP-25 | Boundary | Book entries on 2026-11-03, 2026-11-05, 2026-11-10 (no bonus yet), 2026-11-17 and 2026-11-24 | One bonus, added with the 2026-11-17 entry | feedback |
| T-RDP-26-a | LIB-RDP-26 | Normal | Goal 2: A 20 points (completed at 09:00), B 20 points (2 books at 10:00, completed later), C 10 points, D 0 points | Ranks A 1, B 2, C 3, D null | held-out |
| T-RDP-27-a | LIB-RDP-27 | Normal | Participants "Ayşe Nur Yılmaz" (20 points) and a non-public one (10 points); a member and staff read the leaderboard; a member reads a draft's | Member: [{1, Ayşe Y.}, {2, Anonymous}] without `member_id`; staff with `member_id`; `404` | feedback |
| T-RDP-28-a | LIB-RDP-28 | Normal | Goal 2: first book; second book at 10:00; a third book | `active`; then `completed` with `completed_at` 10:00 and one `program_completed` notification with `program_id`; the third still counts (`books` 3) | held-out |
| T-RDP-29-a | LIB-RDP-29 | Normal | Goal 2 completed with a loan and a manual entry; the manual entry removed | Still `completed`, `level` `bronze`, `books` 1 | feedback |
| T-RDP-30-a | LIB-RDP-30 | Normal | Goal 1: books 1, 2 and 3 | Levels bronze, silver, gold; two `program_level_reached` notifications | held-out |
| T-RDP-31-a | LIB-RDP-31 | Boundary | Goal 2: books 1, 2, 3, 4, 5, 6 | none, bronze, bronze, silver, silver, gold | feedback |
| T-RDP-32-a | LIB-RDP-32 | Normal | Student with open late fees 8.00 (11-20), 14.00 and 10.00 (both 11-25, in this order); joins a program with goal 1 and reward 20.00 on 11-25 and completes | 8.00 and 10.00 `waived`, 14.00 `open`; `reward_waived` 18.00 | held-out |
| T-RDP-33-a | LIB-RDP-33 | Normal | Program with reward 20.00 completed by a member without fees | `reward_waived` 0.00 | feedback |
| T-RDP-34-a | LIB-RDP-34 | Error | Goal 1: B completes at 09:00, A at 10:00; certificates; an active participant's certificate; another member reads A's | `RP-<id>-2` for A with name, level and books; `RP-<id>-1` for B; `409 NOT_COMPLETED`; `403` | held-out |
| T-RDP-35-a | LIB-RDP-35 | Normal | Program ending 2026-11-30 with one active and one completed participant (goal 1); process on 2026-11-27 | `reminders` 1; the active member gets one `program_ending` notification, the completed none | feedback |
| T-RDP-36-a | LIB-RDP-36 | Boundary | Program ending 2026-11-30 with an active participant; process on 2026-11-26, 2026-11-27, again 2026-11-27 and 2026-11-28 | `reminders` 0, 1, 0, 0 | held-out |
| T-RDP-37-a | LIB-RDP-37 | Normal | Goal 2: A completes and tries to leave; B reads one book, leaves, joins again and reads one more | `409 PARTICIPATION_NOT_ACTIVE`; B `completed` with `books` 2 | feedback |
| T-RDP-38-a | LIB-RDP-38 | Normal | A member with an active participation is deactivated | The participation `left` | held-out |
| T-RDP-39-a | LIB-RDP-39 | Normal | Member in two programs, completed one (goal 1, 10 points) and active in the other (10 points from the same book); a member without programs | `{active 1, completed_this_year 1, points_this_year 20}`; zeros | feedback |
| T-RDP-40-a | LIB-RDP-40 | Error | Branch QQ (no copies, no members) with a draft program is deactivated; after the program is cancelled | `409 BRANCH_IN_USE`; 200 | held-out |
| T-RDP-41-a | LIB-RDP-41 | Normal | Program at A; a loan made at A returned at B; a loan made at B returned at A | Only the first counts (`books` 1) | feedback |
| T-RDP-42-a | LIB-RDP-42 | Normal | A member joins (goal 5), gets an entry, a manual entry and leaves | No `program_*` notification (the loan itself notifies `loan_created` and `loan_returned`) | held-out |
| T-RDP-43-a | LIB-RDP-43 | Normal | Program created, changed, books set, published; members join (one leaves); manual entry added and removed; completion; another program cancelled; process; audit log | One entry per event (2 for `program_created` and `program_joined`) | feedback |
| T-RDP-44-a | LIB-RDP-44 | Normal | Program (goal 1, reward 20.00): A reads book X and completes; B reads X too and Y (goal reached); C nothing; a draft program; report for November | One row: `{participants 3, completed 2, completion_rate 66.7, books_counted 3, points 30, rewards_waived 0.00}`, top books X (2), Y (1) | feedback |
| T-RDP-44-b | LIB-RDP-44 | Error | `from` > `to`; 367 days; a member reads the report | `422`; `422`; `403` | held-out |
| T-RDP-45-a | LIB-RDP-45 | Normal | A program with a participant and an entry; `GET /api/v1/export` | The export has exactly the keys of 22.1 | feedback |
| T-RDP-46-a | LIB-RDP-46 | Normal | A late fee of 2.00 waived by a program reward; the member's balance and fee list `status=waived` | `outstanding_fees` 0.00; the fee listed as `waived` | held-out |
| T-RDP-47-a | LIB-RDP-47 | Normal | Participants: A 20 points, B 0 points, C left; list; `status=left` | `status=active`: A (rank 1), B (rank null) with `full_name`, `public`, `reward_waived`; `status=left`: C | feedback |
