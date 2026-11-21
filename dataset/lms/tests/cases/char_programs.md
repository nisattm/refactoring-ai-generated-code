# Characterization cases: module 26 (Reading programs)

Characterization tests record the **current** behavior of the starting code (`v0-ai-baseline`, `3bd1412`) where the requirement tests leave branches uncovered (issue #115). They are not derived from a requirement; `Requirement` names the closest one. Behavior that contradicts a requirement is not recorded. Split rule: [`../README.md`](../README.md#feedback--held-out-split).

Programs are drafts from 2026-11-02 to 2026-11-30 with `goal_books` 2 unless stated otherwise.

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-CHAR-RDP-01-a | LIB-RDP-02 | Characterization | PATCH `/programs/999999` with `{}` | `404 NOT_FOUND`, details `{resource: program, id: 999999}` | feedback |
| T-CHAR-RDP-02-a | LIB-RDP-01 | Characterization | POST a program with `branch_id` 999999 | `422`, fields `(branch_id, branch 999999 does not exist)` | held-out |
| T-CHAR-RDP-03-a | LIB-RDP-02 | Characterization | PATCH a draft with a new `name` | 200 with the new name | feedback |
| T-CHAR-RDP-04-a | LIB-RDP-02 | Characterization | PATCH a draft with its own `goal_books` 2 | 200; `goal_books` 2 | held-out |
| T-CHAR-RDP-05-a | LIB-RDP-02 | Characterization | PATCH a draft with `ends_on` 2026-12-01 and `reward_waiver` `5.00` | 200; `ends_on` 2026-12-01, `reward_waiver` `5.00` | feedback |
| T-CHAR-RDP-06-a | LIB-RDP-02 | Characterization | Draft in branch A; PATCH `branch_id` to branch B | 200; `branch_id` B | held-out |
| T-CHAR-RDP-07-a | LIB-RDP-02 | Characterization | Published program; PATCH `max_participants` 10; PATCH `ends_on` 2026-11-20 | 200 with `max_participants` 10; `422`, fields `(ends_on, ends_on must not be earlier than today or the current ends_on)` | feedback |
| T-CHAR-RDP-08-a | LIB-RDP-08 | Characterization | PUT `/programs/{id}/books` with `[b, b, 999999]` | `422`, fields `(book_ids, book_ids must be distinct)`, `(book_ids.2, book 999999 does not exist)` | held-out |
| T-CHAR-RDP-09-a | LIB-RDP-07 | Characterization | Programs in branch A and branch B; GET `/programs?branch_id=A` | Only the program of branch A | feedback |
