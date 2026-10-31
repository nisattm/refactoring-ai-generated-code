# Test cases: module 11 (Branches and transfers)

Generated from one case list; 17 cases for 9 requirements (feedback 8, held-out 9, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-BR-01-a | LIB-BR-01 | Normal | Admin creates branch `kampus` named `Kampüs` | 201; `code` `KAMPUS`, `is_active` true | feedback |
| T-BR-01-b | LIB-BR-01 | Error | Code `AA` again as `aa`; code `X` (1 char) and 11 chars; librarian creates a branch | `409 CONFLICT`; `422`; `403 FORBIDDEN` | held-out |
| T-BR-02-a | LIB-BR-02 | Normal | Branches `CC`, `AA` (fixture), `BB` (fixture), one inactive; list; filter `is_active=false`; member reads list | Ordered by code AA, BB, CC; filter returns the inactive one; member 200 | held-out |
| T-BR-03-a | LIB-BR-03 | Error | Deactivate a branch that is a member's home branch; one that holds a copy | `409 BRANCH_IN_USE` both | feedback |
| T-BR-03-b | LIB-BR-03 | Boundary | Branch whose only copy is withdrawn and with no members; branch that is the pickup branch of an active reservation | First 200 (`is_active` false); second `409 BRANCH_IN_USE` | held-out |
| T-BR-04-a | LIB-BR-04 | Error | Inactive branch used as member home branch, copy home branch, pickup branch | `409 BRANCH_INACTIVE` each | feedback |
| T-BR-04-b | LIB-BR-04 | Error | Passive member reserves with an inactive pickup branch (two 409 checks fail) | `409 BRANCH_INACTIVE` (checked before the others) | held-out |
| T-BR-05-a | LIB-BR-05 | Normal | Relocation started Friday 2026-11-06 | `started_on` 2026-11-06, `expected_on` 2026-11-10, `status` `in_transit`; copy `in_transfer` with `current_branch_id` null | feedback |
| T-BR-05-b | LIB-BR-05 | Boundary | Transfer started on 2026-10-28 (29 Oct holiday) | `expected_on` 2026-11-02 | held-out |
| T-BR-06-a | LIB-BR-06 | Normal | Relocate an available copy from A to B | 201 with the transfer (`from_branch_id` A, `to_branch_id` B) | feedback |
| T-BR-06-b | LIB-BR-06 | Error | Relocate a lent copy; relocate to its own branch; relocate a lent copy to an inactive branch | `409 INVALID_COPY_STATUS`; `409 SAME_BRANCH`; `409 BRANCH_INACTIVE` (first in order) | held-out |
| T-BR-07-a | LIB-BR-07 | Normal | Relocation A → B received | Transfer `received` on 2026-11-04; copy home and current branch B, `available` | feedback |
| T-BR-07-b | LIB-BR-07 | Normal | Copy returned at B (home A) → `return_home` transfer; received | Copy at A, home still A, `available` | held-out |
| T-BR-07-c | LIB-BR-07 | Normal | Reservation transfer arrives while the reservation is still `in_transit` | Reservation `ready` at the pickup branch with `hold_until` = arrival + 3 working days; copy `on_hold` | feedback |
| T-BR-07-d | LIB-BR-07 | Normal | Reservation cancelled while its copy travels to B; nobody else waiting | On arrival the copy is released: `return_home` transfer B → A starts, copy `in_transfer` | held-out |
| T-BR-08-a | LIB-BR-08 | Boundary | Transfer started 2026-11-06 (expected 2026-11-10): `process-arrivals` on 2026-11-09, then 2026-11-10 | 0 received; then 1 | held-out |
| T-BR-09-a | LIB-BR-09 | Normal | Two relocations; filters `status`, `reason`, `to_branch_id`; order | Ordered by `id` descending; filters match | feedback |
