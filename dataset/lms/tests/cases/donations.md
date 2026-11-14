# Test cases: module 22 (Donations)

Generated from one case list; 56 cases for 47 requirements (feedback 31, held-out 25, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-DON-01-a | LIB-DON-01 | Normal | A person with only `kind` and `name`; an organization with e-mail and phone | 201 each; defaults `anonymous` false, `is_active` true, `member_id` null | feedback |
| T-DON-01-b | LIB-DON-01 | Error | Kind `company`; empty name; unknown member; e-mail used by another donor (other case); a member that already has a donor; a member creates a donor | `422` three times; `409 CONFLICT` with `details.field` `email`, then `member_id`; `403` | held-out |
| T-DON-02-a | LIB-DON-02 | Error | An organization donor with `member_id` | `422` | feedback |
| T-DON-02-b | LIB-DON-02 | Normal | Member M (no donor) offers twice; member N offers while a donor already has N's e-mail | One donor for M with M's name, e-mail and `member_id`, used by both offers; N's new donor has `email` null | held-out |
| T-DON-03-a | LIB-DON-03 | Normal | Donors `zeynep`, `Ahmet`, organization `Mavi Vakfı`; list; `q=vak`; `kind=person` | Order Ahmet, Mavi Vakfı, zeynep with `level` `none` and `value_this_year` 0.00; `q` → Mavi Vakfı; `kind` → Ahmet, zeynep | feedback |
| T-DON-04-a | LIB-DON-04 | Error | PATCH name and `anonymous`; PATCH `kind`; PATCH a merged donor | 200; `422`; `409 DONOR_MERGED` | held-out |
| T-DON-05-a | LIB-DON-05 | Error | Deactivate a donor with an offered donation; after its cancellation deactivate; offer for the inactive donor | `409 DONOR_HAS_OPEN_DONATIONS` with `details.donation_ids`; 200; `409 DONOR_INACTIVE` | feedback |
| T-DON-06-a | LIB-DON-06 | Normal | Donor S with two donations merged into T | 200 with T; both donations have `donor_id` T; S inactive with `merged_into_id` T | feedback |
| T-DON-06-b | LIB-DON-06 | Error | Merge into itself; into an unknown donor; two member donors; an already merged donor; librarian merges | `422`; `404`; `409 DONOR_MERGE_CONFLICT`; `409 DONOR_MERGED`; `403` | held-out |
| T-DON-06-c | LIB-DON-06 | Normal | Member donor S (with e-mail) merged into T without member and e-mail | T gets S's `member_id` and `email` | feedback |
| T-DON-07-a | LIB-DON-07 | Normal | Donor with a received donation (2 × 40.00), an accepted one and a rejected one | `{donations 3, open_donations 1, copies_received 2, value_received 80.00, first/last_received_on 2026-11-02}`; years `[{2026, 80.00, none}]` | feedback |
| T-DON-08-a | LIB-DON-08 | Normal | Librarian offers 2 items (quantities 3 and 1) for a donor | 201 `offered` with `offered_at`; items `pending`, `received_quantity` 0; `items_count` 2, `copies_offered` 4 | feedback |
| T-DON-08-b | LIB-DON-08 | Error | No items; 31 items; total quantity 101; the same ISBN twice; invalid ISBN; years 1449 and 2027; quantity 21; condition `bad` | `422` each | held-out |
| T-DON-08-c | LIB-DON-08 | Boundary | 30 items; total quantity 100; year 2026 and 1450 | 201 each | feedback |
| T-DON-09-a | LIB-DON-09 | Error | A member offers with a `donor_id` | `422` | feedback |
| T-DON-10-a | LIB-DON-10 | Error | Offer to an inactive branch; a passive member offers | `409 BRANCH_INACTIVE`; `409 MEMBER_PASSIVE` | feedback |
| T-DON-10-b | LIB-DON-10 | Boundary | Donor with 3 open donations (offered, accepted, partially received) offers a fourth; after one is received fully, again | `409 DONOR_OFFER_LIMIT` with `details.limit` 3; 201 | held-out |
| T-DON-11-a | LIB-DON-11 | Error | PATCH note and items of an offer; PATCH after the review | 200 with the new items; `409 INVALID_DONATION_STATUS` with `details.status` `accepted` | feedback |
| T-DON-12-a | LIB-DON-12 | Normal | Member cancels own offer; member cancels own accepted donation; staff cancels it; staff cancels again | 200 `cancelled` with `donor_request`; `409 INVALID_DONATION_STATUS`; 200 with `staff_request`; `409 INVALID_DONATION_STATUS` | held-out |
| T-DON-13-a | LIB-DON-13 | Normal | Donations D1 (donor A), D2 (member M), D3 (A, cancelled); list; `status=offered`; `donor_id` A; M's own list; M reads D1 | [D3, D2, D1]; [D2, D1]; [D3, D1]; [D2]; `404` | feedback |
| T-DON-14-a | LIB-DON-14 | Normal | Items: poor 2020; good 1995; good 1996 with the ISBN of a book with 3 copies at A (one lost); new 2010 with the ISBN of a book with 4 copies at A; good 2015 without ISBN | `poor_condition`; `too_old`; `accepted` with `book_id`; `duplicate` with `book_id`; decision null | held-out |
| T-DON-15-a | LIB-DON-15 | Boundary | A book with 3 copies at branch A and none at B; good 2020 items with its ISBN offered to A and to B; a poor item from 1990 | A: `duplicate`; B: `accepted`; poor 1990: `poor_condition` (first rule) | feedback |
| T-DON-16-a | LIB-DON-16 | Normal | Offer with 3 items: accept 2 of 3 copies at 40.00, decline one `too_old`, accept one at 150.00 | 200 `accepted`, `reviewed_at`, `expected_by` 2026-11-16; items with decisions, `book_id`, `accepted_quantity`, `estimated_value` | feedback |
| T-DON-16-b | LIB-DON-16 | Error | Review missing one item; an item twice; accepted without `estimated_value`; accepted 4 of 3; declined with `book_id`; unknown `book_id`; a member reviews | `422` six times; `403` | held-out |
| T-DON-17-a | LIB-DON-17 | Error | Item with the ISBN of book X accepted for book Y; reviewed correctly; reviewed again | `409 ISBN_MISMATCH` with `details.item_id`; 200; `409 INVALID_DONATION_STATUS` | feedback |
| T-DON-18-a | LIB-DON-18 | Normal | A member's offer with 2 items, both declined | `rejected`, `expected_by` null; one `donation_reviewed` notification with `donation_id` | held-out |
| T-DON-19-a | LIB-DON-19 | Normal | Item accepted 3 × 40.00 for book X at branch A; 2 copies received | 200 `partially_received`; X has 2 new `available` copies at A with price 40.00, `acquired_on` today and `donation_id` | feedback |
| T-DON-20-a | LIB-DON-20 | Error | Empty `items`; empty `barcodes`; an item twice; an item of another donation | `422` three times; `404` | held-out |
| T-DON-21-a | LIB-DON-21 | Error | Receive for an offered donation; a declined item; 3 copies of an item accepted 2; an existing barcode together with a good item | `INVALID_DONATION_STATUS`; `ITEM_NOT_ACCEPTED` with `details.item_id`; `RECEIVE_EXCEEDS_ACCEPTED` with `details.item_id`; `CONFLICT`; no copy created | feedback |
| T-DON-22-a | LIB-DON-22 | Normal | A member's donation with I1 accepted 2 and I2 accepted 1: receive 1 of I1; receive 1 of I1 and 1 of I2 | `partially_received`, then `received`; two `donation_received` notifications | held-out |
| T-DON-23-a | LIB-DON-23 | Normal | I1 accepted 3 × 40.00, I2 1 × 150.00, I3 declined; receive 2 of I1; then 1 of I1 and 1 of I2; receipt | `partially_received`; `received`; receipt `total_copies` 4, `total_value` 270.00, lines for I1 (3, 120.00) and I2 (1, 150.00) | feedback |
| T-DON-24-a | LIB-DON-24 | Normal | Book with a donated copy and a bought copy; copies with `donated=true` and `donated=false` | One copy each; the bought copy has `donation_id` null | held-out |
| T-DON-25-a | LIB-DON-25 | Normal | Donated copy lent and reported lost on the day it arrived; withdrawn | 200 (the keep period does not apply to `lost` copies) | feedback |
| T-DON-26-a | LIB-DON-26 | Boundary | Copy received on 2026-11-02 withdrawn on 2027-04-30 and on 2027-05-01 | `409 DONATION_KEEP_PERIOD` with `details.keep_until` 2027-05-01; 200 | held-out |
| T-DON-27-a | LIB-DON-27 | Boundary | Member donation accepted on Mon (`expected_by` 2026-11-16) and another partially received; process on 2026-11-16 and on 2026-11-17 | `expired` 0, then 2; both `expired`; the received copy stays; one `donation_expired` notification for the member | feedback |
| T-DON-28-a | LIB-DON-28 | Normal | D1 received in two parts in 2026, D2 received in 2026, D3 received on 2027-01-04 | `DN-2026-0001` (kept at the second part), `DN-2026-0002`, `DN-2027-0001` | held-out |
| T-DON-29-a | LIB-DON-29 | Error | Receipt of a member's accepted donation before receiving; after receiving read by the member and by another member | `409 RECEIPT_NOT_AVAILABLE`; 200 with donor, branch and dates; `404` | feedback |
| T-DON-30-a | LIB-DON-30 | Normal | Donor receives 2 × 300.00 on Mon and 1 × 100.00 on Tue | `value_this_year` 700.00, `level` `bronze` | held-out |
| T-DON-31-a | LIB-DON-31 | Boundary | Donors with values 499.99, 500.00, 1999.99, 2000.00, 9999.99, 10000.00 | `none`, `bronze`, `bronze`, `silver`, `silver`, `gold` | feedback |
| T-DON-32-a | LIB-DON-32 | Boundary | Donor receives 600.00 on 2026-12-31 and 700.00 on 2027-01-04; history | years `[{2026, 600.00, bronze}, {2027, 700.00, bronze}]` | held-out |
| T-DON-33-a | LIB-DON-33 | Normal | Member donor receives 300.00 (none), 300.00 (bronze), 100.00 (bronze) and 1500.00 (silver) | Two `donor_level_reached` notifications | feedback |
| T-DON-34-a | LIB-DON-34 | Normal | Donors Zehra (silver), Ali (bronze), Can (gold), anonymous (bronze), Ece (none); a member reads the wall; year 2025; year 1999 | Can gold, Zehra silver, Ali bronze; `anonymous_count` 1; 2025 empty; `422` | held-out |
| T-DON-35-a | LIB-DON-35 | Error | Book X accepted (not received) in a donation for branch A; orders with X for A and for B submitted; after receiving, the order for A again | A: `409 DONATION_PENDING` with `details.book_ids` [X]; B: 200; then 200 | feedback |
| T-DON-36-a | LIB-DON-36 | Error | Branch QQ (no copies, no members) with an offered donation is deactivated; after the cancellation | `409 BRANCH_IN_USE`; 200 | held-out |
| T-DON-37-a | LIB-DON-37 | Normal | Member with an offered and an accepted donation is deactivated | Offered → `cancelled` with `member_deactivated`; accepted unchanged | feedback |
| T-DON-38-a | LIB-DON-38 | Normal | Member donor with one received donation (2 × 300.00) and one offer; a member without a donor | `{open 1, copies_received 2, value_this_year 600.00, level bronze}`; `{0, 0, 0.00, none}` | held-out |
| T-DON-39-a | LIB-DON-39 | Error | Book without copies that is the `book_id` of an accepted item is deleted; a book without copies and donations | `409 IN_USE`; `204` | feedback |
| T-DON-40-a | LIB-DON-40 | Normal | Anonymous donor with a bronze level; staff reads donors; the wall | Staff see the real name; the wall has no name and `anonymous_count` 1 | held-out |
| T-DON-41-a | LIB-DON-41 | Normal | A member offers, changes and cancels an offer | No notification | feedback |
| T-DON-42-a | LIB-DON-42 | Normal | Donor created, changed, merged; donation offered, changed, reviewed, received, another cancelled; process; audit log | One entry of each event | held-out |
| T-DON-43-a | LIB-DON-43 | Normal | Branch A: donation with items accepted 2 (received 1) and declined `duplicate` (quantity 3); donation declined `too_old`; branch B: an offer; report 2026-11-02 – 2026-11-08 | A `{donations 2, copies_offered 6, copies_accepted 2, copies_received 1, value_received 40.00, declined duplicate 1, too_old 1}`; B `{1, 1, 0, 0, 0.00}` | feedback |
| T-DON-43-b | LIB-DON-43 | Error | `from` > `to`; 367 days; a member reads the report | `422`; `422`; `403` | held-out |
| T-DON-44-a | LIB-DON-44 | Normal | Anonymous donor A 700.00 (1 copy), organization B 2 × 1500.00, donor C without receivings; donors report 2026 | B (3000.00, silver, 2 copies), A with its real name (700.00, bronze, 1); C not listed | held-out |
| T-DON-45-a | LIB-DON-45 | Error | A rejected donation is changed, cancelled, reviewed and received | `409 INVALID_DONATION_STATUS` each | feedback |
| T-DON-46-a | LIB-DON-46 | Normal | Donated copy valued 65.00 lent and reported lost | A `lost_book` fee of 65.00 | held-out |
| T-DON-47-a | LIB-DON-47 | Normal | A donated copy exists; `GET /api/v1/export` | The keys of 22.1; the exported copy has no `donation_id` | feedback |
