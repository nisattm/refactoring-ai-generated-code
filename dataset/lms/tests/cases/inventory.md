# Test cases: module 24 (Inventory counts)

Generated from one case list; 36 cases for 34 requirements (feedback 18, held-out 18, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-INV-01-a | LIB-INV-01 | Normal | Branch A with 2 available copies, 1 damaged and 1 on loan; librarian starts a count without prefix | 201 `open`, `started_at`, `shelf_prefix` null, `expected_count` 3 | feedback |
| T-INV-01-b | LIB-INV-01 | Error | Empty name; prefix of 21 characters; unknown branch; a member starts a count | `422` three times; `403` | held-out |
| T-INV-02-a | LIB-INV-02 | Normal | At A: copies on shelves `A-12` (available), `a-30` (on hold), `B-01`, no shelf, and a lost copy; count with prefix `A-` | `expected` = the `A-12` and `a-30` copies | held-out |
| T-INV-03-a | LIB-INV-03 | Error | Inactive branch; an active branch without copies; prefix `Z-` with no copy on such shelves | `BRANCH_INACTIVE`; `COUNT_EMPTY`; `COUNT_EMPTY` | feedback |
| T-INV-04-a | LIB-INV-04 | Boundary | Open count with prefix `A-1`; new counts `A-2`, `A-`, `a-12`, without prefix; the same at branch B | 201; `COUNT_SCOPE_OVERLAP` with `details.count_id` three times; B 201 | held-out |
| T-INV-05-a | LIB-INV-05 | Normal | Counts K1 (A) and K2 (B); K1 with 3 expected copies, 2 scanned and an unknown barcode; list; `branch_id` A; K1 | [K2, K1]; [K1]; `progress` `{expected 3, scanned_expected 2, remaining 1}`, `problems.unknown` 1 | feedback |
| T-INV-06-a | LIB-INV-06 | Normal | Cancel an open count; cancel it again; cancel an applied count | 200 `cancelled` with `staff_request`; `409 INVALID_COUNT_STATUS` with `details.status` `cancelled`; `409 INVALID_COUNT_STATUS` | held-out |
| T-INV-07-a | LIB-INV-07 | Error | Scan a lower-case barcode; scan 0 and 201 barcodes; scan into a closed count | 201 with `expected`; `422`; `422`; `409 INVALID_COUNT_STATUS` | feedback |
| T-INV-08-a | LIB-INV-08 | Normal | One request: expected copy twice; a withdrawn copy; a copy in transfer to A | `expected`, `duplicate`, `withdrawn`, `wrong_branch` | held-out |
| T-INV-09-a | LIB-INV-09 | Normal | Count of A with prefix `A-`: copy on `A-12`, again, copy on `B-01` at A, copy lent from A (shelf `A-13`), available copy of B, lost copy, `NOPE-0001` | `expected`, `duplicate`, `out_of_scope`, `unexpected_status`, `wrong_branch`, `found_lost`, `unknown` | feedback |
| T-INV-10-a | LIB-INV-10 | Normal | Count started; a new copy added at A afterwards and scanned | `out_of_scope`; `expected_count` unchanged | held-out |
| T-INV-11-a | LIB-INV-11 | Normal | Scans: expected, unknown, expected; list; `result=unknown` | Three scans in order; one `unknown` | feedback |
| T-INV-12-a | LIB-INV-12 | Normal | Copy scanned twice; the first scan removed; then the second; removing a scan of a closed count | 204; still scanned (`remaining` 0); 204 and `remaining` 1; `409 INVALID_COUNT_STATUS` | held-out |
| T-INV-13-a | LIB-INV-13 | Error | Copy expected in an open count: relocation; withdrawal; lending; after cancelling the count, relocation | `COPY_IN_COUNT` with `details.count_id` twice; lending 201; relocation 201 | feedback |
| T-INV-14-a | LIB-INV-14 | Normal | Expected C1, C2: C1 scanned; close | 200 `closed` with `closed_at`; lines C1 `found`, C2 `missing` | held-out |
| T-INV-15-a | LIB-INV-15 | Boundary | Count whose two expected copies are both lent before closing | `summary` `{expected 2, found 0, missing 0, moved 2, accuracy 100.0}` | feedback |
| T-INV-16-a | LIB-INV-16 | Normal | Expected C1–C5: C1–C3 scanned, C4 lent after the start, C5 not scanned; close | `summary` `{expected 5, found 3, missing 1, moved 1, accuracy 75.0}` | held-out |
| T-INV-17-a | LIB-INV-17 | Error | Lines of an open count; after closing `outcome=missing` | `409 INVALID_COUNT_STATUS`; the missing copy with `barcode`, `book_title`, `shelf_location` | feedback |
| T-INV-18-a | LIB-INV-18 | Normal | At A: C1 scanned, C2 not scanned, a lost copy of A scanned, an available copy of B scanned; close and apply; apply again | `{missing_marked 1, found 1, relocated 1}`; C2 `missing` since today; the lost copy `available` at A; B's copy `in_transfer` home; `409 INVALID_COUNT_STATUS` | feedback |
| T-INV-18-b | LIB-INV-18 | Normal | C2 missing at closing but lent before applying | `missing_marked` 0; C2 stays `on_loan` | held-out |
| T-INV-19-a | LIB-INV-19 | Boundary | Count with 10 missing copies applied by a librarian; another with 11 by a librarian, then by an admin | 200; `403`; 200 | feedback |
| T-INV-20-a | LIB-INV-20 | Normal | An `on_hold` copy of a ready reservation is not scanned; close and apply | Copy `missing`; reservation `waiting` with `copy_id`, `ready_on`, `hold_until` null; one `reservation_delayed` notification naming the title | held-out |
| T-INV-21-a | LIB-INV-21 | Normal | The only copy on reserve for a course's item is not scanned; close and apply | Copy `missing` with `reserve_item_id` null; the item `requested` | feedback |
| T-INV-22-a | LIB-INV-22 | Error | Missing copy found at A; lost copy found at A; available copy found; found at an inactive branch | 200 `available` with `missing_since` null twice; `409 INVALID_COPY_STATUS`; `409 BRANCH_INACTIVE` | held-out |
| T-INV-23-a | LIB-INV-23 | Normal | An open count of A and a missing copy of B; process on 2027-01-31 | `{expired_counts 1, marked_lost 1}`; count `cancelled` with `expired`; copy `lost` with branch null | feedback |
| T-INV-24-a | LIB-INV-24 | Boundary | Count started Mon 09:00, processed on 2026-11-09 09:00 and 09:00:01; copy missing since 2026-11-02 processed on 2027-01-30 and 2027-01-31 | `expired_counts` 0 then 1; `marked_lost` 0 then 1 | held-out |
| T-INV-25-a | LIB-INV-25 | Normal | Book with a missing and an available copy; copies with `status=missing` | Only the missing copy, with `missing_since` | feedback |
| T-INV-26-a | LIB-INV-26 | Error | A missing copy: lent; relocated; withdrawn | `409 COPY_NOT_AVAILABLE` with `details.status` `missing`; `409 INVALID_COPY_STATUS`; 200 | held-out |
| T-INV-27-a | LIB-INV-27 | Normal | Book whose only copy at A becomes missing; book availability; a reservation for it | No `availability` row with copies; `409 BOOK_NOT_LENDABLE` | feedback |
| T-INV-28-a | LIB-INV-28 | Normal | A lost copy scanned in an open count | The copy stays `lost` until the count is applied | held-out |
| T-INV-29-a | LIB-INV-29 | Error | Closure of A on Tue 2026-11-03; counts started on Sat 2026-11-07, on Tue 2026-11-03 and on Mon 2026-11-09 | `409 BRANCH_NOT_OPEN` twice; 201 | feedback |
| T-INV-30-a | LIB-INV-30 | Normal | The member whose lost copy is found by a count; the count is applied | The member's notifications do not change | held-out |
| T-INV-31-a | LIB-INV-31 | Normal | Count started, two scan requests, a scan removed, closed, applied; another started and cancelled; a copy found; process; audit log | One entry per event (two for `inventory_scans_added` and `inventory_count_started`) | feedback |
| T-INV-32-a | LIB-INV-32 | Normal | Branch A: count with 4 expected (3 found, 1 missing) and a lost copy found, applied; count of B not applied; report 2026 | Only A: `{counts_applied 1, last_applied_on 2026-11-02, expected 4, found 3, missing 1, accuracy 75.0, missing_now 1, found_again 1}` | held-out |
| T-INV-33-a | LIB-INV-33 | Normal | A missing copy; `GET /api/v1/export` | The keys of 22.1; the copy has status `lost` and no `missing_since` | feedback |
| T-INV-34-a | LIB-INV-34 | Normal | A member's ready reservation sent back to `waiting` by an applied count; the member summary | `active_reservations` 1 | held-out |
