# Characterization cases: module 13 (Audit log, import and export)

Characterization tests record the **current** behavior of the starting code (`v0-ai-baseline`, `3bd1412`) where the requirement tests leave branches uncovered (issue #115). They are not derived from a requirement; `Requirement` names the closest one. Behavior that contradicts a requirement is not recorded. Split rule: [`../README.md`](../README.md#feedback--held-out-split).

All cases import a variant of the small valid dataset of `feedback/test_audit_io.py` and expect `422 VALIDATION_ERROR` with the listed `(field, problem)` pairs in `details.fields`.

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-CHAR-IO-01-a | LIB-IO-03 | Characterization | Body is a JSON list `[]` | `fields` is exactly `[(body, the dataset must be a JSON object)]` | feedback |
| T-CHAR-IO-02-a | LIB-IO-03 | Characterization | No `format_version`; extra key `extra`; `authors` is a string; no `publishers` | `(format_version, field required)`, `(extra, unknown field)`, `(authors, must be a list)`, `(publishers, field required)` | held-out |
| T-CHAR-IO-03-a | LIB-IO-03 | Characterization | `books` gets a second element `"x"` | `(books[1], must be an object)` | feedback |
| T-CHAR-IO-04-a | LIB-IO-04 | Characterization | Book `publication_year` 2027; copy 2 `acquired_on` 2026-12-01 and `current_branch_id` null with status `available` | `(books[0].publication_year, publication_year must not be after 2026)`, `(copies[1].acquired_on, acquired_on must not be after today)`, `(copies[1].current_branch_id, a copy with status available needs a current branch)` | held-out |
| T-CHAR-IO-05-a | LIB-IO-04 | Characterization | Member 1 `valid_until` before `membership_start`; guest member 2 without `phone` | `(members[0].valid_until, valid_until must not be before membership_start)`, `(members[1].phone, phone is required for guests)` | feedback |
| T-CHAR-IO-06-a | LIB-IO-06 | Characterization | Open loan with `due_date` before `loan_date`, `returned_on` and `return_branch_id` set | `(loans[0].due_date, due_date must not be before loan_date)`, `(loans[0].returned_on, returned_on must be null for a open loan)`, `(loans[0].return_branch_id, return_branch_id must be null for a open loan)` | held-out |
| T-CHAR-IO-07-a | LIB-IO-06 | Characterization | Returned loan without `returned_on` and `return_branch_id`; returned loan with `returned_on` before `loan_date` | `(loans[1].returned_on, returned_on is required for a returned loan)`, `(loans[1].return_branch_id, return_branch_id is required for a returned loan)`, `(loans[2].returned_on, returned_on must not be before loan_date)` | feedback |
| T-CHAR-IO-08-a | LIB-IO-06 | Characterization | Second open loan on copy 1; open loan on copy 99; loan element `"x"` | `(loans[1].copy_id, the copy already has an open or lost loan)`, `(loans[2].copy_id, copies id 99 does not exist)`, `(loans[3], must be an object)` | held-out |
| T-CHAR-IO-09-a | LIB-IO-04 | Characterization | Valid dataset; member 1 e-mail `admin@library.local` (the bootstrap admin) | `fields` is exactly `[(members[0].email, a user with this e-mail address already exists)]` | feedback |
| T-CHAR-IO-10-a | LIB-IO-03 | Characterization | Valid dataset plus 150 unknown keys `x0` … `x149` | `fields` has exactly 100 entries | held-out |
