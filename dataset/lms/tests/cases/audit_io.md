# Test cases: module 13 (Audit log, import and export)

Generated from one case list; 25 cases for 18 requirements (feedback 14, held-out 11, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-AUD-01-a | LIB-AUD-01 | Normal | Admin creates a user; a failed login with an unknown e-mail | Entry `user_created` with `actor_user_id` = admin and `entity_type` `user`; entry `login_failed` with `actor_user_id` null | feedback |
| T-AUD-01-b | LIB-AUD-01 | Error | Registration that fails with `409 CONFLICT` (duplicate `university_id`) | Only one `member_registered` entry (the rolled-back request leaves none) | heldout |
| T-AUD-02-a | LIB-AUD-02 | Normal | PATCH a user's `full_name` from `Old` to `New` | `user_updated` details `{"full_name": {"old": "Old", "new": "New"}}` | feedback |
| T-AUD-02-b | LIB-AUD-02 | Error | User created with password `Passw0rd1`, password changed to `NewPassw0rd`, logins | No audit `details` contains a password, a hash or a token | heldout |
| T-AUD-03-a | LIB-AUD-03 | Normal | Several events; filters `event`, `entity_type`, `from`/`to`; order | Ordered by `id` descending; filters match; librarian gets `403` | feedback |
| T-AUD-04-a | LIB-AUD-04 | Error | `DELETE`, `PATCH`, `PUT` on `/api/v1/audit-log/{id}` and `DELETE /api/v1/audit-log` as admin | 404 or 405 each; the entry still exists | heldout |
| T-IO-01-a | LIB-IO-01 | Normal | Import the small dataset into an empty database | 200 with counts branches 2, authors 1, publishers 1, books 1, copies 2, members 2, loans 1 | feedback |
| T-IO-02-a | LIB-IO-02 | Boundary | Database with one branch; database with only an extra staff user | `409 DATABASE_NOT_EMPTY`; import succeeds | heldout |
| T-IO-03-a | LIB-IO-03 | Error | Dataset whose second member has e-mail `bad` | `422` with field `members[1].email`; nothing imported (no branches) | feedback |
| T-IO-04-a | LIB-IO-04 | Normal | Book with id 7 and ISBN-10 `0-306-40615-2` | `GET /api/v1/books/7` works; ISBN stored as `9780306406157` | feedback |
| T-IO-04-b | LIB-IO-04 | Error | Copy referring to book id 99; two members with the same e-mail | `422` each | heldout |
| T-IO-05-a | LIB-IO-05 | Normal | Imported member logs in; admin resets the password; member logs in again | `401 INVALID_CREDENTIALS`; then 200 | feedback |
| T-IO-06-a | LIB-IO-06 | Error | Open loan whose copy is `available`; lost loan whose copy is `lost` but has a branch | `422` each | feedback |
| T-IO-06-b | LIB-IO-06 | Normal | Lost loan with copy `lost` and `current_branch_id` null; returned loan | Import succeeds; no fees and no notifications; one `data_imported` audit entry | heldout |
| T-IO-07-a | LIB-IO-07 | Normal | Import, export, import the export into a second empty database, export again | Both exports are equal to each other and to the imported data | feedback |
| T-IO-08-a | LIB-IO-08 | Normal | `GET /api/v1/export/branches.csv`; `/export/users.csv`; librarian | CSV with header `id,code,name,address,is_active` and 2 rows ordered by id; `404 NOT_FOUND`; `403` | feedback |
| T-IO-08-b | LIB-IO-08 | Normal | `books.csv`, `copies.csv`, `members.csv`, `loans.csv` headers | Columns exactly as in requirements 22.2 | heldout |
| T-IO-09-a | LIB-IO-09 | Normal | `GET /api/v1/export` and `GET /api/v1/export/books.csv` | Two `data_exported` entries with entity `all` and `books` | feedback |
| T-IO-10-a | LIB-IO-10 | Error | `format_version` 2; `loans` list missing; unknown field `notes` in a branch | `422` each | feedback |
| T-IO-10-b | LIB-IO-10 | Boundary | All seven lists empty | Import succeeds with all counts 0 | heldout |
| T-IO-11-a | LIB-IO-11 | Error | Copy with status `on_hold`; copy with status `in_transfer` | `422` each | feedback |
| T-IO-11-b | LIB-IO-11 | Normal | Imported open loan of a guest | `LoanOut` has `loan_period_days` 7, `max_renewals` 0, `daily_fee` `"5.00"` | heldout |
| T-IO-12-a | LIB-IO-12 | Normal | Import with the members listed in reverse id order; export | Exactly the keys of 22.1; lists ordered by id; amounts as strings; no users | heldout |
| T-IO-13-a | LIB-IO-13 | Normal | `branches.csv` with a name containing a comma (`Campus, North`) | No BOM; lines end with `\r\n`; the name is quoted | feedback |
| T-IO-14-a | LIB-IO-14 | Normal | `copies.csv` and `members.csv`, `branches.csv` | Null `shelf_location` empty; booleans `true`; amounts `150.00`; dates `YYYY-MM-DD` | heldout |
