# Test cases: module 29 (Printing and copying)

Generated from one case list; 49 cases for 47 requirements (feedback 26, held-out 23, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-PRT-01-a | LIB-PRT-01 | Error | Admin creates PR-001 at A; the same code again; a printer of an inactive branch; a librarian creates one | 201 `active` with `paper_left` 0; `409 CONFLICT`; `409 BRANCH_INACTIVE`; `403` | feedback |
| T-PRT-02-a | LIB-PRT-02 | Normal | Printers PR-003 (A, color), PR-001 (B), PR-002 (A); a member lists; filters `branch_id` A and `color` true | [PR-001, PR-002, PR-003]; [PR-002, PR-003]; [PR-003] | held-out |
| T-PRT-03-a | LIB-PRT-03 | Error | Printer set `out_of_service`, back to `active`, `retired`; then renamed | 200 each; `409 PRINTER_RETIRED` | feedback |
| T-PRT-04-a | LIB-PRT-04 | Normal | Color duplex printer with a color job and a plain job queued; `color` set false; then `out_of_service` | The color job `cancelled` with one `print_job_cancelled` notification; then the plain job `cancelled` | held-out |
| T-PRT-05-a | LIB-PRT-05 | Error | Librarian refills 500 sheets; 0 sheets; a retired printer | 200 `paper_left` 500; `422`; `409 PRINTER_RETIRED` | feedback |
| T-PRT-06-a | LIB-PRT-06 | Boundary | `paper_left` 4900: refill 101; refill 100 | `PAPER_CAPACITY_EXCEEDED` with `details.paper_left` 4900; 5000 | held-out |
| T-PRT-07-a | LIB-PRT-07 | Error | A member sends 4 pages; the librarian sends without `member_id`; the member sends with `member_id` | 201 `queued` with copies 1, color and duplex false, `sheets` 4; `422`; `422` | feedback |
| T-PRT-08-a | LIB-PRT-08 | Error | A passive member; printer `out_of_service`; color on a black-and-white printer; duplex on a simplex printer; a member whose membership ended (2027-11-02) | `MEMBER_PASSIVE`; `PRINTER_UNAVAILABLE` with `details.status`; `PRINTER_NO_COLOR`; `PRINTER_NO_DUPLEX`; `MEMBERSHIP_EXPIRED` | feedback |
| T-PRT-08-b | LIB-PRT-08 | Boundary | A member with 3 queued jobs sends a fourth; after cancelling one, again | `409 PRINT_QUEUE_FULL`; 201 | held-out |
| T-PRT-09-a | LIB-PRT-09 | Normal | 5 pages × 2 copies without and with duplex; 1 page × 2 copies with duplex | `sheets` 10, 6, 2 | feedback |
| T-PRT-10-a | LIB-PRT-10 | Boundary | 150 pages printed today and a queued job of 30: jobs of 21 and 20 pages; on Tue after cancelling the queued jobs, 200 pages | `DAILY_PAGE_LIMIT` with `details.remaining` 20; 201; Tue 201 | held-out |
| T-PRT-11-a | LIB-PRT-11 | Normal | Jobs J1 (P1, 09:00), J2 (P2, 09:10, cancelled), J3 (P1, 09:20); member list; `status=queued`; `printer_id` P2; another member reads | [J3, J2, J1] with `printer` and `amount` "0.00"; [J3, J1]; [J2]; `403` | feedback |
| T-PRT-12-a | LIB-PRT-12 | Error | A member cancels a queued job; cancels it again; cancels another member's job | 200 `cancelled`; `409 PRINT_JOB_NOT_QUEUED` with `details.status` `cancelled`; `403` | held-out |
| T-PRT-13-a | LIB-PRT-13 | Normal | Librarian releases a job of 3 pages × 2 copies at 10:00 (paper 100) | 200 `printed`, `released_at` 10:00; `paper_left` 94 | feedback |
| T-PRT-14-a | LIB-PRT-14 | Error | Release a cancelled job; a job on Saturday; the member releases while not inside branch A; a job of 20 sheets with 10 left | `PRINT_JOB_NOT_QUEUED`; `BRANCH_NOT_OPEN`; `NOT_IN_BRANCH` with `details.branch_id` A; `OUT_OF_PAPER` | held-out |
| T-PRT-15-a | LIB-PRT-15 | Normal | A member inside A releases own job; the librarian releases a job of a member who is not inside | 200 both | feedback |
| T-PRT-16-a | LIB-PRT-16 | Boundary | `paper_left` 10: a job of 11 sheets; a job of 10 sheets | `OUT_OF_PAPER` with `details.paper_left` 10; printed, `paper_left` 0 | held-out |
| T-PRT-17-a | LIB-PRT-17 | Normal | Student with a pack: black-and-white job of 120 pages; then a color job of 2 pages | `free_pages` 100, `pack_pages` 20, `charged_pages` 0; then 0, 0, 2 | feedback |
| T-PRT-18-a | LIB-PRT-18 | Normal | Guest job of 4 black-and-white pages; student job of 4 pages | Open `printing` fee 2.00 with `print_job_id`, stored in `fee_id`; one `fee_created` notification; the student job has no fee | held-out |
| T-PRT-19-a | LIB-PRT-19 | Normal | Student who used 95 free pages, with a pack of 50: black-and-white job of 30 pages | `free_pages` 5, `pack_pages` 25, `charged_pages` 0, no fee; the pack has 25 pages left | feedback |
| T-PRT-20-a | LIB-PRT-20 | Normal | Guest: color job of 3 pages × 2 copies; black-and-white job of 7 pages | `charged_pages` 6, fee 12.00; fee 3.50 | held-out |
| T-PRT-21-a | LIB-PRT-21 | Boundary | Student prints 100 pages on 2026-11-30; quota on 2026-11-30 and on 2026-12-01 | `free_pages_left` 0; then 100 | feedback |
| T-PRT-22-a | LIB-PRT-22 | Boundary | Guest with total debt 46.50: a job of 7 pages; a job of 6 pages; after buying a pack, a job of 10 pages | `MEMBER_BLOCKED_BY_DEBT` with `details.amount` 3.50; printed; printed from the pack | held-out |
| T-PRT-23-a | LIB-PRT-23 | Error | Fail a printed job with a reason; fail it again; fail a queued job; a reason of 4 characters | 200 `failed` with `failed_reason`; `PRINT_JOB_NOT_PRINTED` twice; `422` | feedback |
| T-PRT-24-a | LIB-PRT-24 | Normal | A guest's charged job of 4 pages is paid (2.00), then fails; a student's free job of 10 pages fails | The paid fee stays `paid`; the student's used free pages decrease by 10; one `print_job_failed` notification each | held-out |
| T-PRT-25-a | LIB-PRT-25 | Normal | Student with 95 free pages used and a pack: a job of 33 pages (5 free, 25 pack, 3 charged, fee 1.50) fails | Fee `waived`; free pages used 95; the pack has 50 pages left | feedback |
| T-PRT-26-a | LIB-PRT-26 | Boundary | Two jobs released Mon 10:00; one fails on Tue 10:00, the other on Tue 10:01 | `failed`; `FAIL_WINDOW_CLOSED` | held-out |
| T-PRT-27-a | LIB-PRT-27 | Error | Buy a pack; four more packs; a pack for a passive member; a member buys | 201 with 50 pages and an open `print_pack` fee of 20.00; the fifth with 4 packs left → `PACK_LIMIT_REACHED`; `MEMBER_PASSIVE`; `403` | feedback |
| T-PRT-28-a | LIB-PRT-28 | Normal | Guest with two packs, the first used up; the member lists packs; `with_pages_left=false` | [first, second]; [first] | held-out |
| T-PRT-29-a | LIB-PRT-29 | Error | Student printed 30 free pages and a color job of 2 pages; the member reads the quota; `month` 2026-10; `month` 2026-12 | `{2026-11, student, 100, 30, 70, 0, 32, 4.00}`; October with 0 used; `422` | feedback |
| T-PRT-30-a | LIB-PRT-30 | Normal | Student uses 100 free pages, becomes a guest; quota; a job of 2 pages | `free_pages` 0, `free_pages_left` 0; the job is charged (1.00) | held-out |
| T-PRT-31-a | LIB-PRT-31 | Normal | Two jobs sent Mon 09:00, one released; process on Tue 09:30 | `jobs_expired` 1; the queued job `expired` with one `print_job_expired` notification | feedback |
| T-PRT-32-a | LIB-PRT-32 | Boundary | Job sent Mon 10:00; process on Tue 09:59 and Tue 10:00 | `jobs_expired` 0; then 1 | held-out |
| T-PRT-33-a | LIB-PRT-33 | Boundary | Printer with 100 sheets; after releasing 1 sheet; filter `low_paper=true` | `low_paper` false; true; the printer listed | feedback |
| T-PRT-34-a | LIB-PRT-34 | Normal | Guest with a printing fee of 2.50 and a pack fee of 20.00; balance; payment of 22.50 | `outstanding_fees` 22.50; both fees `paid` | held-out |
| T-PRT-35-a | LIB-PRT-35 | Normal | A member with two queued jobs and a pack is deactivated | Both jobs `cancelled`, no `print_job_cancelled` notification; the pack keeps 50 pages | feedback |
| T-PRT-36-a | LIB-PRT-36 | Normal | Student who printed 40 free pages, with a pack and one queued job | Summary `printing` `{free_pages_left 60, pack_pages_left 50, queued_jobs 1}` | held-out |
| T-PRT-37-a | LIB-PRT-37 | Error | Branch QQ with an `out_of_service` printer is deactivated; after retiring the printer, again | `409 BRANCH_IN_USE`; 200 | feedback |
| T-PRT-38-a | LIB-PRT-38 | Normal | Closure of A on Tue (created Mon); on Tue 10:00 a job is sent and released | Sent 201; release `BRANCH_NOT_OPEN` | held-out |
| T-PRT-39-a | LIB-PRT-39 | Normal | A member inside A sends a job and leaves; a member who is not inside sends and cancels a job | The first job stays `queued`; 201 and 200 | feedback |
| T-PRT-40-a | LIB-PRT-40 | Error | Release by card for a member inside A with two queued jobs at P (and one at another printer); a lost card; an unknown card; a member who is not inside | `released` the two ids, `refused` []; the other job stays queued; `CARD_NOT_ACTIVE`; `404`; refused with `NOT_IN_BRANCH` | held-out |
| T-PRT-41-a | LIB-PRT-41 | Boundary | Three queued jobs of 10 sheets and `paper_left` 25; release by card | Two released, the third refused with `OUT_OF_PAPER`; `paper_left` 5 | feedback |
| T-PRT-42-a | LIB-PRT-42 | Normal | A student sends, releases and cancels jobs (all free) | No notifications | held-out |
| T-PRT-43-a | LIB-PRT-43 | Normal | Printer created, changed, refilled; jobs sent, released, cancelled, failed; a pack; process; a refused release; audit log | One entry per event (3 `print_job_submitted`, 2 `print_job_released`) | feedback |
| T-PRT-44-a | LIB-PRT-44 | Error | `from` > `to`; 2026-01-01 – 2027-01-10; a member reads the report | `422`; `422`; `403` | feedback |
| T-PRT-44-b | LIB-PRT-44 | Normal | Printers at A and B; at B one job of 4 duplex pages; a student of B buys a pack; report 2026-11-02 – 2026-11-08 with and without `branch_id` | Rows [A (all 0), B {jobs_printed 1, pages 4, sheets 2, free_pages 4, packs_sold 1, revenue 0.00}]; with `branch_id` B only B | held-out |
| T-PRT-45-a | LIB-PRT-45 | Normal | At A: a student's job of 10 pages (free), a color job of 2 pages (4.00), a guest's job of 3 pages (1.50) that fails | `{jobs_printed 3, pages 15, color_pages 2, sheets 15, free_pages 10, pack_pages 0, charged_pages 5, revenue 4.00, packs_sold 0, jobs_failed 1, refunds_pending 0.00}` | feedback |
| T-PRT-46-a | LIB-PRT-46 | Normal | A printer, a job and a pack exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 | held-out |
| T-PRT-47-a | LIB-PRT-47 | Normal | A student reads `members/me`; after printing 25 free pages | `free_pages_left` 100; then 75 | feedback |
