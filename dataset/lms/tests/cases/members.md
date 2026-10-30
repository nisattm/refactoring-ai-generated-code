# Test cases: module 3 (Members)

Generated from one case list; 29 cases for 13 requirements (feedback 17, held-out 12, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-MEM-01-a | LIB-MEM-01 | Normal | Register student Ayşe Yılmaz on 2026-11-02 | 201 `MemberOut`: `member_no` `M000001`, `status` `active`, `membership_valid` true; user account can log in with role `member` | feedback |
| T-MEM-01-b | LIB-MEM-01 | Error | Registration by a member; password `short1` | `403 FORBIDDEN`; `422 VALIDATION_ERROR` | held-out |
| T-MEM-02-a | LIB-MEM-02 | Error | Guest without `phone`; guest with `university_id` | `422 VALIDATION_ERROR` both | feedback |
| T-MEM-02-b | LIB-MEM-02 | Error | Academic without `university_id` | `422 VALIDATION_ERROR` | held-out |
| T-MEM-02-c | LIB-MEM-02 | Boundary | Guest with phone of 10 digits, 15 digits; 9 and 16 digits; `university_id` of 3 and 21 characters | 10 and 15 accepted; the others `422` | feedback |
| T-MEM-03-a | LIB-MEM-03 | Normal | Student and guest registered 2026-11-02 | `membership_start` 2026-11-02; `valid_until` 2027-11-01 and 2027-01-30 | feedback |
| T-MEM-04-a | LIB-MEM-04 | Boundary | Guest registered 2026-11-02; read on 2027-01-30 and 2027-01-31 | `membership_valid` true, then false | feedback |
| T-MEM-04-b | LIB-MEM-04 | Normal | Active, unexpired member is deactivated | `membership_valid` false | held-out |
| T-MEM-05-a | LIB-MEM-05 | Error | Second member with the same `university_id` | `409 CONFLICT`, `details.field` `university_id` | feedback |
| T-MEM-05-b | LIB-MEM-05 | Error | Member e-mail equal to the librarian's e-mail (different case) | `409 CONFLICT`, `details.field` `email` | held-out |
| T-MEM-06-a | LIB-MEM-06 | Normal | Members Işık (student), Can (guest); filters `q=ISIK`, `membership_type=guest`, `q=M000002` | Işık; Can; Can | feedback |
| T-MEM-06-b | LIB-MEM-06 | Normal | One expired guest, one valid student; filter `membership_valid=false`; ordering | Only the guest; list ordered by `id` | held-out |
| T-MEM-07-a | LIB-MEM-07 | Normal | PATCH `email` and `full_name` | 200; user account login works with the new e-mail and shows the new name | feedback |
| T-MEM-07-b | LIB-MEM-07 | Error | PATCH a guest: `university_id` only (type stays guest) | `409 MEMBER_FIELDS_INVALID` | held-out |
| T-MEM-08-a | LIB-MEM-08 | Normal | Student with an open loan (due 2026-11-16) becomes academic; new loan on 2026-11-03 | Old loan unchanged (due 2026-11-16, 2.00 TL); new loan due 2026-12-03, 1.00 TL | feedback |
| T-MEM-08-b | LIB-MEM-08 | Normal | Student → guest with `phone`; guest → staff without `university_id` | First 200 with `university_id` null; second `409 MEMBER_FIELDS_INVALID` | held-out |
| T-MEM-09-a | LIB-MEM-09 | Normal | Student (valid until 2027-11-01) renewed on 2026-11-02; guest renewed the same day | 2028-10-31 (+365 days); guest 2027-04-30 (+90) | feedback |
| T-MEM-09-b | LIB-MEM-09 | Boundary | Guest (valid until 2027-01-30) renewed on 2027-01-30 and another on 2027-02-15 | 2027-04-30 (+90); 2027-05-15 (today + 89) | held-out |
| T-MEM-09-c | LIB-MEM-09 | Error | Renew a passive member | `409 MEMBER_PASSIVE` | feedback |
| T-MEM-10-a | LIB-MEM-10 | Error | Deactivate a member with an open loan | `409 MEMBER_HAS_OPEN_LOANS` | feedback |
| T-MEM-10-b | LIB-MEM-10 | Normal | Member with an unpaid late fee (no open loan) and a waiting reservation is deactivated | 200 `passive`; reservation `cancelled` with `member_deactivated`; member can still log in | held-out |
| T-MEM-10-c | LIB-MEM-10 | Error | Deactivate a passive member | `409 MEMBER_PASSIVE` | feedback |
| T-MEM-11-a | LIB-MEM-11 | Normal | Activate a passive member | 200 `active`; `valid_until` unchanged | feedback |
| T-MEM-11-b | LIB-MEM-11 | Error | Activate an active member | `409 MEMBER_ALREADY_ACTIVE` | held-out |
| T-MEM-12-a | LIB-MEM-12 | Normal | New member without loans | `open_loans` 0, `overdue_loans` 0, `active_reservations` 0, `total_debt` `"0.00"`, `borrowing` eligible with no reasons | feedback |
| T-MEM-12-b | LIB-MEM-12 | Boundary | Guest with 2 open loans from 2026-11-02 (both overdue, accrued fees capped at 100.00 each); read on 2027-01-31 after the membership expired | `reasons` = [`MEMBERSHIP_EXPIRED`, `MEMBER_HAS_OVERDUE`, `MEMBER_BLOCKED_BY_DEBT`, `LOAN_LIMIT_REACHED`] in this order; not eligible | held-out |
| T-MEM-12-c | LIB-MEM-12 | Error | Member reads another member's summary | `403 FORBIDDEN` | feedback |
| T-MEM-13-a | LIB-MEM-13 | Normal | Member calls `GET /api/v1/members/me` | Own `MemberOut` | feedback |
| T-MEM-13-b | LIB-MEM-13 | Error | Librarian (no linked member) calls `/members/me` | `404 NOT_FOUND` | held-out |
