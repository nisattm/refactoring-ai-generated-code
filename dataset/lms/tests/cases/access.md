# Test cases: module 28 (Member cards and building access)

Generated from one case list; 56 cases for 52 requirements (feedback 28, held-out 28, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-ACC-01-a | LIB-ACC-01 | Normal | Librarian issues the first card of a student registered on Mon | 201 `LC00000001`, `active`, `issued_on` Mon, `expires_on` 2027-11-01, no fee; one `card_issued` notification with the number | feedback |
| T-ACC-02-a | LIB-ACC-02 | Error | Card for a passive member; for a member whose membership ended (on 2027-11-02); a second card while one is active; a member issues | `MEMBER_PASSIVE`; `MEMBERSHIP_EXPIRED`; `CARD_ALREADY_ACTIVE` with `details.card_no`; `403` | held-out |
| T-ACC-03-a | LIB-ACC-03 | Normal | Card reported lost; a new card issued | New card with `replaces_id` of the old one and `fee_id` of an open `card_replacement` fee of 25.00 with `card_id` | feedback |
| T-ACC-04-a | LIB-ACC-04 | Boundary | First card; lost → second; damaged → third; lost → fourth (third replacement within 365 days) | Fees none, 25.00, 10.00, 50.00 | feedback |
| T-ACC-04-b | LIB-ACC-04 | Normal | Card expires (process on 2027-11-02); membership renewed; a new card issued | No fee | held-out |
| T-ACC-05-a | LIB-ACC-05 | Error | Member reports own card damaged; reports it again; reports another member's card | 200 `damaged` with `ended_on` Mon; `409 CARD_NOT_ACTIVE` with `details.status` `damaged`; `403` | feedback |
| T-ACC-06-a | LIB-ACC-06 | Normal | Member with an old lost card and a new one; list; look up the new number; an unknown number | [new, old]; card with `member` `{id, member_no, full_name, membership_type, status}`; `404` | held-out |
| T-ACC-07-a | LIB-ACC-07 | Normal | Membership renewed on Mon (valid until 2027-11-01) | The active card's `expires_on` becomes 2028-10-31 | feedback |
| T-ACC-08-a | LIB-ACC-08 | Normal | Two cards expiring 2027-11-01; process on 2027-11-02 | `cards_expired` 2; both `expired` with `ended_on` 2027-11-02 | held-out |
| T-ACC-09-a | LIB-ACC-09 | Boundary | Card expiring 2027-11-01; process on 2027-11-01 and 2027-11-02 | `cards_expired` 0 then 1 | feedback |
| T-ACC-10-a | LIB-ACC-10 | Error | Defaults of branch A; admin sets capacity 100 and price 7.50; capacity 0; price 100.01; unknown branch; a librarian sets | `{capacity null, guest_entry true, day_passes true, day_pass_price 5.00}`; 200 with the new values; `422`; `422`; `404`; `403` | held-out |
| T-ACC-11-a | LIB-ACC-11 | Error | Two people inside branch A; capacity 1; capacity 2 | `409 CAPACITY_BELOW_OCCUPANCY` with `details.occupancy` 2; 200 | feedback |
| T-ACC-12-a | LIB-ACC-12 | Normal | Capacity 10; a member and a day pass visitor inside; a member reads the occupancy | `{inside 2, members 1, visitors 1, capacity 10, free 8}` | held-out |
| T-ACC-13-a | LIB-ACC-13 | Normal | Member enters at 09:00, a day pass visitor at 09:30; inside list; a member reads it | Two rows in order (member with name, pass with code); `403` | feedback |
| T-ACC-14-a | LIB-ACC-14 | Error | Scan with a card; with both a card and a pass code; with neither; with an unknown card; direction `sideways`; a member scans | 200 `{result entered, visit_id, member_id}`; `422` three times; `404`; `403` | held-out |
| T-ACC-15-a | LIB-ACC-15 | Error | Lost card; a member whose membership ended (card still active, 2027-11-02 09:00); an inactive branch; Saturday | `CARD_NOT_ACTIVE` with `details.status` `lost`; `MEMBERSHIP_EXPIRED`; `BRANCH_INACTIVE`; `BRANCH_NOT_OPEN` | feedback |
| T-ACC-15-b | LIB-ACC-15 | Error | A banned member; a guest where `guest_entry` is false; a member inside branch B enters A; capacity 1 with one person inside | `ACCESS_BANNED` with `details.ends_on`; `GUEST_ENTRY_NOT_ALLOWED`; `ALREADY_INSIDE` with `details.branch_id` B; `BRANCH_FULL` with `details.capacity` 1 | held-out |
| T-ACC-16-a | LIB-ACC-16 | Normal | A member enters at 09:00 | The visit history shows the visit with `entered_at` 09:00, `left_at` null, `minutes` null | held-out |
| T-ACC-17-a | LIB-ACC-17 | Error | Exit without being inside; inside A, exit at B; exit at A with the card reported lost meanwhile | `NOT_INSIDE`; `WRONG_BRANCH` with `details.branch_id` A; 200 `left` | feedback |
| T-ACC-18-a | LIB-ACC-18 | Boundary | Entry at 07:59; at 08:00; again at 08:05; exit at 09:00 | `BRANCH_NOT_OPEN`; entered; `ALREADY_INSIDE`; left with `minutes` 60 | held-out |
| T-ACC-19-a | LIB-ACC-19 | Error | Day pass of A: entry at B; entry at A; entry again; exit; Monday's other pass used on Tuesday | `WRONG_BRANCH`; entered (pass `used`); `PASS_NOT_USABLE` with `details.status` `used`; left; `PASS_NOT_VALID_TODAY` | feedback |
| T-ACC-20-a | LIB-ACC-20 | Error | Staff end an open visit; end it again | 200 (`closed_by` `staff`; the member is no longer inside); `409 VISIT_NOT_OPEN` | held-out |
| T-ACC-21-a | LIB-ACC-21 | Normal | A lost card is scanned at A at 10:00; alerts; the member's notifications | One alert `{card_no, branch_id}` at 10:00; one `lost_card_used` notification | feedback |
| T-ACC-22-a | LIB-ACC-22 | Normal | Two members enter Mon at 10:00 and 15:00; process on Mon 21:00 | `visits_closed` 2 with `left_at` Mon 20:00 and `closed_by` `closing` | held-out |
| T-ACC-23-a | LIB-ACC-23 | Boundary | Member enters at 19:30; process at 19:59 and at 20:30 | `visits_closed` 0; then 1 with `left_at` 20:00 (`minutes` 30) | feedback |
| T-ACC-24-a | LIB-ACC-24 | Normal | An unused day pass of Mon and a used one (visitor still inside); process on Tue 07:00 | `{visits_closed 1, cards_expired 0, passes_expired 1}`; the unused pass `cancelled` | held-out |
| T-ACC-25-a | LIB-ACC-25 | Error | Sell a pass at A (price 7.50); with day passes disabled at B; at an inactive branch | 201 `unused` for today at 7.50; `DAY_PASSES_DISABLED`; `BRANCH_INACTIVE` | feedback |
| T-ACC-25-b | LIB-ACC-25 | Boundary | 50 passes sold at A today (one cancelled); a 51st; one at B | `DAY_PASS_LIMIT_REACHED` with `details.limit` 50; B 201 | held-out |
| T-ACC-26-a | LIB-ACC-26 | Normal | Three passes sold at branch AA on 2026-11-02; one at BB | Codes `DP-AA-20261102-1` … `-3`; `DP-BB-20261102-1` | held-out |
| T-ACC-27-a | LIB-ACC-27 | Error | Cancel an unused pass; cancel it again; cancel a used pass | 200 `cancelled`; `409 PASS_NOT_USABLE` twice | feedback |
| T-ACC-28-a | LIB-ACC-28 | Normal | Passes P1 (A), P2 (B), P3 (A, used); list; `branch_id` A; `status=used` | [P3, P2, P1]; [P3, P1]; [P3] | held-out |
| T-ACC-29-a | LIB-ACC-29 | Normal | A member inside A is banned from today until 2026-11-10; bans starting yesterday or longer than 365 days | 201; the visit ended (`inside` 0); one `access_banned` notification naming 2026-11-10; `422` twice | feedback |
| T-ACC-30-a | LIB-ACC-30 | Error | Lift a ban; lift again; the member enters | 200 with `lifted_at`; `409 BAN_ALREADY_LIFTED`; entered | held-out |
| T-ACC-31-a | LIB-ACC-31 | Normal | A future ban (2026-11-20 – 2026-11-25) and a current lifted one; the member reads own bans | [future (in_force false), current (in_force false)] | feedback |
| T-ACC-32-a | LIB-ACC-32 | Boundary | Ban 2026-11-02 – 2026-11-05; entry on 2026-11-05 and on 2026-11-06 | `ACCESS_BANNED` with `ends_on` 2026-11-05; entered | held-out |
| T-ACC-33-a | LIB-ACC-33 | Error | Ban 2026-11-02 – 2026-11-05; a new ban 2026-11-05 – 2026-11-08; after lifting the first, again | `409 BAN_OVERLAPS` with `details.ban_id`; 201 | feedback |
| T-ACC-34-a | LIB-ACC-34 | Normal | Visits: A Mon 09:00–09:45, B Tue 10:00–11:30; history; `branch_id` B; `from` Tue; another member reads it | [B (90), A (45)]; [B]; [B]; `403` | held-out |
| T-ACC-35-a | LIB-ACC-35 | Error | Loan by card number; by a lost card; by an unknown card; with both `member_id` and `card_no` | 201 for the card's member; `409 CARD_NOT_ACTIVE`; `404`; `422` | feedback |
| T-ACC-36-a | LIB-ACC-36 | Normal | A member inside A is deactivated | Card `revoked` with `ended_on` today; not inside any more | held-out |
| T-ACC-37-a | LIB-ACC-37 | Normal | A member with a card is deactivated and activated again; a new card issued | No card after activation; the new card has no fee | feedback |
| T-ACC-38-a | LIB-ACC-38 | Normal | Member with a card inside A after one earlier visit this month; a member without a card | `{card_no, card_status active, inside_branch_id A, visits_this_month 2}`; `{null, null, null, 0}` | held-out |
| T-ACC-39-a | LIB-ACC-39 | Normal | A replacement fee of 25.00; balance; payment of 25.00 | `outstanding_fees` 25.00; after the payment the fee `paid` | feedback |
| T-ACC-40-a | LIB-ACC-40 | Error | Branch QQ (no copies, no members): a member of A inside QQ; after the exit an unused day pass of QQ; after cancelling it | `BRANCH_IN_USE` twice; then 200 | held-out |
| T-ACC-41-a | LIB-ACC-41 | Normal | A member who is not inside the branch checks in to a room booking at A on Tue 10:00 | 200 `checked_in` | feedback |
| T-ACC-42-a | LIB-ACC-42 | Normal | A member with a card enters and leaves twice | No new notifications after the card was issued | held-out |
| T-ACC-43-a | LIB-ACC-43 | Normal | Card issued and reported; settings changed; entry and exit; a visit closed by hand; passes sold and cancelled; a ban created and lifted; process; a refused scan; audit log | One entry per event (2 `card_issued`, 3 `access_scanned`, 2 `day_pass_sold`) | feedback |
| T-ACC-44-a | LIB-ACC-44 | Normal | Branch A on Mon: M1 09:00–10:00, M2 09:30–11:00, M1 again 10:00–10:30, a day pass 12:00–12:30 (price 5.00) and an unused pass; one refused scan; report 2026-11-02 – 2026-11-08 | Row A `{visits 4, member_visits 3, unique_members 2, pass_visits 1, average_minutes 52.5, peak_occupancy 2, pass_revenue 10.00, denied 1}` | feedback |
| T-ACC-44-b | LIB-ACC-44 | Error | `from` > `to`; 2026-01-01 – 2027-01-10; a member reads the report | `422`; `422`; `403` | held-out |
| T-ACC-45-a | LIB-ACC-45 | Normal | Refused entry scans: a lost card and a full branch; audit log of `access_scanned`; report | No audit entries; report `denied` 2 | feedback |
| T-ACC-46-a | LIB-ACC-46 | Boundary | Visits 09:00–10:00, 09:30–11:00 and 10:00–10:30 at A | `peak_occupancy` 2 | held-out |
| T-ACC-47-a | LIB-ACC-47 | Normal | Cards, a visit and a pass exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 | feedback |
| T-ACC-48-a | LIB-ACC-48 | Normal | A member reads `members/me` with an active card; after reporting it lost | `card_no` the number; then null | held-out |
| T-ACC-49-a | LIB-ACC-49 | Boundary | Capacity 1 with a day pass visitor inside; another pass is used | `409 BRANCH_FULL` | feedback |
| T-ACC-50-a | LIB-ACC-50 | Normal | `guest_entry` false at A; a student inside A becomes a guest; leaves; enters again | Still inside after the change; leaving 200; entry `GUEST_ENTRY_NOT_ALLOWED` | held-out |
| T-ACC-51-a | LIB-ACC-51 | Normal | Capacity 2 with a member and a day pass visitor inside; a member enters; after one exit, again | `BRANCH_FULL` with `details.capacity` 2; entered | feedback |
| T-ACC-52-a | LIB-ACC-52 | Normal | Closure of A on Tue (created Mon); a member inside since Mon 19:00; entry on Tue 10:00; process on Tue 10:00 | Entry `BRANCH_NOT_OPEN`; the Monday visit is closed with `left_at` Mon 20:00 | held-out |
