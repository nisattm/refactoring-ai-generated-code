# Test cases: module 25 (Purchase suggestions)

Generated from one case list; 52 cases for 47 requirements (feedback 26, held-out 26, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-SUG-01-a | LIB-SUG-01 | Normal | A student suggests a title with author, ISBN-less, reason and branch A | 201 `submitted` for the student with `submitted_at`; `book_id`, `quantity`, `purchase_order_id` null | feedback |
| T-SUG-01-b | LIB-SUG-01 | Error | Empty title; year 2027; invalid ISBN; a member sends `member_id`; staff omit it; staff with `member_id` | `422` five times; 201 for the member | held-out |
| T-SUG-02-a | LIB-SUG-02 | Normal | Suggestion of member A supported by B; read by A, by B and by C | `score` 2, `supporters` 1; A `mine` true, `supported_by_me` false; B `mine` false, `supported_by_me` true; C both false | held-out |
| T-SUG-03-a | LIB-SUG-03 | Error | A passive member suggests; a guest; a suggestion for an inactive branch | `MEMBER_PASSIVE`; `MEMBERSHIP_TYPE_NOT_ALLOWED`; `BRANCH_INACTIVE` | feedback |
| T-SUG-03-b | LIB-SUG-03 | Error | ISBN of a book with a copy; ISBN of another member's open suggestion | `BOOK_ALREADY_OWNED` with `details.book_id`; `DUPLICATE_SUGGESTION` with `details.suggestion_id` | held-out |
| T-SUG-04-a | LIB-SUG-04 | Boundary | A student with 3 open suggestions suggests a fourth; after withdrawing one, again; a staff member's sixth | `SUGGESTION_LIMIT_REACHED` with `details.limit` 3; 201; `limit` 5 | feedback |
| T-SUG-04-b | LIB-SUG-04 | Boundary | Suggestion with an ISBN rejected on 2026-11-02; the same member suggests it on 2027-04-30 and 2027-05-01 | `SUGGESTION_RECENTLY_REJECTED` with `details.until` 2027-05-01; 201 | held-out |
| T-SUG-05-a | LIB-SUG-05 | Error | Member changes the title; changes the ISBN to an owned book's; after approval changes the title | 200; `409 BOOK_ALREADY_OWNED`; `409 INVALID_SUGGESTION_STATUS` with `details.status` `approved` | feedback |
| T-SUG-06-a | LIB-SUG-06 | Normal | Member withdraws a submitted suggestion; member withdraws an approved one; staff withdraw it | 200 `withdrawn` with `member_request`; `409 INVALID_SUGGESTION_STATUS`; 200 | held-out |
| T-SUG-07-a | LIB-SUG-07 | Error | B supports A's suggestion; B again; A supports own; a guest; a passive member; staff; support of a rejected suggestion | 201; `ALREADY_SUPPORTED`; `CANNOT_SUPPORT_OWN`; `MEMBERSHIP_TYPE_NOT_ALLOWED`; `MEMBER_PASSIVE`; `403`; `INVALID_SUGGESTION_STATUS` | feedback |
| T-SUG-08-a | LIB-SUG-08 | Error | B stops supporting; stops again; C supports, the suggestion is rejected, C stops | 204 and `supporters` 0; `404`; `409 INVALID_SUGGESTION_STATUS` | held-out |
| T-SUG-09-a | LIB-SUG-09 | Normal | A student's suggestion supported by an academic and a staff member; the academic stops | `score` 4 with 2 supporters; then `score` 2 | feedback |
| T-SUG-10-a | LIB-SUG-10 | Normal | Supporters B (reserve) and C (no reserve); list; a member reads it | [B, C] with `full_name`, `membership_type`, `reserve_on_arrival`; `403` | held-out |
| T-SUG-11-a | LIB-SUG-11 | Normal | Member M has own S1, S2 (S2 withdrawn) and supports T1, T2 (T2 rejected); M reads own list; another member reads M's | `own` [S2, S1]; `supported` [T1]; `403` | feedback |
| T-SUG-12-a | LIB-SUG-12 | Normal | S1 (score 1), S2 (score 3), S3 (score 1, rejected); staff list; `status=submitted`; `q`; a member's list; the member reads S3 | Staff [S2, S1, S3]; [S2, S1]; member [S2, S1] without `member_id`; `404` | held-out |
| T-SUG-13-a | LIB-SUG-13 | Boundary | A member supports 20 open suggestions and then a 21st | 20 × 201; `409 SUPPORT_LIMIT_REACHED` with `details.limit` 20 | feedback |
| T-SUG-14-a | LIB-SUG-14 | Boundary | Member withdraws an own suggestion with 3 supporters; one with 2 supporters; staff withdraw the first | `409 SUGGESTION_HAS_SUPPORTERS`; 200; 200 | held-out |
| T-SUG-15-a | LIB-SUG-15 | Normal | Librarian approves for book X, 2 × 40.00 with a note | 200 `approved`, `reviewed_at`, `book_id`, `quantity`, `estimated_price`, `review_note`; one `suggestion_approved` notification with `suggestion_id` | feedback |
| T-SUG-15-b | LIB-SUG-15 | Error | Approve with quantity 11; price 0.00; an unknown book; a member approves | `422` three times; `403` | held-out |
| T-SUG-16-a | LIB-SUG-16 | Error | Approve an approved suggestion; a suggestion with ISBN of X for book Y; a second suggestion at A for the same book Y | `INVALID_SUGGESTION_STATUS`; `ISBN_MISMATCH`; 200 | held-out |
| T-SUG-17-a | LIB-SUG-17 | Normal | Reject a submitted suggestion `too_expensive`; reject an approved one; reject a rejected one | 200 `rejected` with reason and one `suggestion_rejected` notification; 200; `409 INVALID_SUGGESTION_STATUS` | feedback |
| T-SUG-18-a | LIB-SUG-18 | Normal | Book X whose only copy at A is on loan; suggestion of M (supporters B with, C without reserve) rejected `already_owned` without and with `book_id` X | `422`; 200; M and B have `waiting` reservations of X at A, C none | held-out |
| T-SUG-19-a | LIB-SUG-19 | Normal | S1 (score 3) and S2 (score 1); the librarian approves S2 first | 200 (the order is not enforced) | feedback |
| T-SUG-20-a | LIB-SUG-20 | Error | A librarian approves 4 × 100.00 (400.00) | `403`; the suggestion stays `submitted` | held-out |
| T-SUG-21-a | LIB-SUG-21 | Boundary | Librarian approves 3 × 100.00; another 3 × 100.01 by a librarian, then by an admin | 200; `403`; 200 | feedback |
| T-SUG-22-a | LIB-SUG-22 | Error | S1 merged into S2; merge into itself; into an unknown suggestion; an approved source; into a rejected target | 200 with S2, S1 `merged` with `merged_into_id`; `422`; `404`; `409 INVALID_SUGGESTION_STATUS` twice | held-out |
| T-SUG-23-a | LIB-SUG-23 | Normal | S1 by A (supported by B), S2 by C (supported by B); S1 merged into S2 | S2's supporters B, A; `score` 3 | feedback |
| T-SUG-24-a | LIB-SUG-24 | Error | Approved 1 × 40.00: change quantity to 3; a librarian changes the price to 120.00; change a submitted suggestion's approval | 200 `quantity` 3; `403`; `409 INVALID_SUGGESTION_STATUS` | held-out |
| T-SUG-25-a | LIB-SUG-25 | Normal | Book X whose only copy is lost; a member suggests X's ISBN; approved for X | 201; 200 | feedback |
| T-SUG-26-a | LIB-SUG-26 | Normal | Approved S1 (book X, 2 × 40.00) of member M at A; order with supplier P | 201 draft order of P at A with line X 2 × 40.00; S1 `ordered` with `purchase_order_id`, `ordered_at`; one `suggestion_ordered` notification | held-out |
| T-SUG-27-a | LIB-SUG-27 | Error | Order with an inactive supplier; with a submitted suggestion; with an approved suggestion of branch B; empty list; an id twice | `SUPPLIER_INACTIVE`; `INVALID_SUGGESTION_STATUS` with `details.suggestion_id`; `SUGGESTION_BRANCH_MISMATCH`; `422`; `422`; the good suggestion stays `approved` | feedback |
| T-SUG-28-a | LIB-SUG-28 | Normal | Approved S1 (X, 2 × 40.00), S2 (X, 1 × 45.00), S3 (Y, 1 × 20.00) at A ordered together | Lines X 3 × 45.00 and Y 1 × 20.00; `total` 155.00 | held-out |
| T-SUG-29-a | LIB-SUG-29 | Normal | Draft order from S1 (X) and S2 (Y); lines replaced by the Y line only; then the order cancelled | S1 `approved` with `purchase_order_id` null, S2 `ordered`; after cancelling S2 `approved` | feedback |
| T-SUG-30-a | LIB-SUG-30 | Normal | Ordered S1 (X) of member M supported by B; the order submitted and 1 copy received on 2026-11-05 | S1 `available` with `available_at`; one `suggestion_available` notification each for M and B | held-out |
| T-SUG-31-a | LIB-SUG-31 | Normal | S1 approved for 2 copies of X, ordered; 1 copy received on Mon, 1 on Tue | `available_at` Mon 09:00 after both receivings | feedback |
| T-SUG-32-a | LIB-SUG-32 | Normal | S1 of A for X at branch A, supporters B (reserve) and C (no reserve); ordered; 1 copy received | A's reservation of X `ready` with the new copy; B's `waiting`; C has none; A, B, C get `suggestion_available` | held-out |
| T-SUG-33-a | LIB-SUG-33 | Normal | S1 of A for X supported by D (reserve); D borrows a copy of X at branch B before the arrival; X arrives at A | A gets a reservation; D is skipped (no reservation, the arrival still succeeds) | feedback |
| T-SUG-34-a | LIB-SUG-34 | Boundary | Suggestion approved Mon 2026-11-02 09:00; process on 2027-01-31 09:00 and 09:00:01 | `expired_approved` 0, then 1; `expired`; one `suggestion_expired` notification | held-out |
| T-SUG-35-a | LIB-SUG-35 | Boundary | Suggestion submitted Mon 2026-11-02 09:00; process on 2027-03-02 09:00 and 09:00:01 | `expired_submitted` 0, then 1 | feedback |
| T-SUG-36-a | LIB-SUG-36 | Normal | Member M with a submitted and an approved suggestion, supporting another suggestion T, is deactivated | Submitted → `withdrawn` with `member_deactivated`; approved stays; T has 0 supporters | held-out |
| T-SUG-37-a | LIB-SUG-37 | Normal | A student with an open suggestion is changed to `guest`; suggests again | The open suggestion stays `submitted`; `409 MEMBERSHIP_TYPE_NOT_ALLOWED` | feedback |
| T-SUG-38-a | LIB-SUG-38 | Normal | Member with a submitted suggestion, one that arrived, and support of an open suggestion; a member without suggestions | `{open 1, supported 1, available_this_year 1}`; all 0 | held-out |
| T-SUG-39-a | LIB-SUG-39 | Error | Book without copies that an approved suggestion uses is deleted | `409 IN_USE` | feedback |
| T-SUG-40-a | LIB-SUG-40 | Normal | Order created from S1 and S2; a manual order | `suggestion_ids` [S1, S2]; [] | held-out |
| T-SUG-41-a | LIB-SUG-41 | Normal | Book X with an approved and an ordered suggestion and a rejected one | `open_suggestions` 2 | feedback |
| T-SUG-42-a | LIB-SUG-42 | Normal | A's suggestion is supported, changed, supported again and merged into another | A has no notifications | held-out |
| T-SUG-43-a | LIB-SUG-43 | Normal | Suggestions submitted, changed, supported, support removed, approved, approval changed, ordered, arrived, one rejected, one withdrawn, one merged; process; audit log | One entry per event (5 for `suggestion_submitted`) | feedback |
| T-SUG-44-a | LIB-SUG-44 | Normal | In the week of 2026-11-02 at A: S1 approved, ordered, arrived on 2026-11-05 (score 2 after a merge); S2 rejected `out_of_scope`; S3 withdrawn; S4 merged into S1; report | `submitted` 4, `approved` 1, `rejected.out_of_scope` 1, `withdrawn` 1, `merged` 1, `average_days_to_available` 3.0, top first S1 | feedback |
| T-SUG-44-b | LIB-SUG-44 | Error | `from` > `to`; 367 days; a member reads the report | `422`; `422`; `403` | held-out |
| T-SUG-45-a | LIB-SUG-45 | Normal | A suggestion with a supporter exists; `GET /api/v1/export` | The export has exactly the keys of 22.1 | feedback |
| T-SUG-46-a | LIB-SUG-46 | Error | A withdrawn suggestion: changed by its member, supported, withdrawn, approved, ordered | `409 INVALID_SUGGESTION_STATUS` each | held-out |
| T-SUG-47-a | LIB-SUG-47 | Error | Branch QQ (no copies, no members) with a submitted suggestion is deactivated; after the suggestion is withdrawn | `409 BRANCH_IN_USE`; 200 | feedback |
