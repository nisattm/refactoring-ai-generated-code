# Test cases: module 1 (Core), technical constraints, common rules and fixed interface

Generated from one case list; 87 cases for 64 requirements (feedback 43, held-out 33, static 11). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-TECH-01-a | LIB-TECH-01 | Static | Docker image | Python 3.14 (check-tools output) | static |
| T-TECH-02-a | LIB-TECH-02 | Static | Imports of the generated code | Only FastAPI, Uvicorn, Pydantic, SQLAlchemy and the standard library (S22 check) | static |
| T-TECH-03-a | LIB-TECH-03 | Static | Test imports | Only pytest, httpx, Hypothesis besides the standard library | static |
| T-TECH-04-a | LIB-TECH-04 | Static | `requirements.txt` of the generated code | Exactly the seven pinned versions | static |
| T-TECH-05-a | LIB-TECH-05 | Normal | `database_url` pointing to a file in a temporary folder; create a branch | The SQLite file exists and holds the data after restarting the app | feedback |
| T-TECH-06-a | LIB-TECH-06 | Static | Source code | Synchronous SQLAlchemy `Session`; no `async def` endpoints | static |
| T-TECH-07-a | LIB-TECH-07 | Normal | New empty database file | `create_app` creates the schema; bootstrap admin can log in | feedback |
| T-TECH-08-a | LIB-TECH-08 | Error | Register a member whose `university_id` is already used (member and user are created in one transaction) | `409 CONFLICT`; no user account with the new e-mail exists | feedback |
| T-TECH-08-b | LIB-TECH-08 | Boundary | Five failed logins for the librarian (each returns 401) | The failures are kept: the account is locked (exception to rollback) | held-out |
| T-TECH-09-a | LIB-TECH-09 | Normal | `FixedClock` set to 2027-03-08T10:00+03:00 | `/health` reports `today` 2027-03-08 (the clock, not the system time) | feedback |
| T-TECH-10-a | LIB-TECH-10 | Static | Source code | Randomness only for tokens and salts; every list query has an ORDER BY | static |
| T-TECH-11-a | LIB-TECH-11 | Static | Package layout | One package per module as in section 2.2 | static |
| T-TECH-12-a | LIB-TECH-12 | Static | `uvicorn "lms:create_app" --factory` in the container | Server starts; `GET /health` returns 200 | static |
| T-COM-01-a | LIB-COM-01 | Boundary | Clock 2026-11-02T22:30:00+00:00 (01:30 local on 3 Nov) | `today` 2026-11-03 | feedback |
| T-COM-02-a | LIB-COM-02 | Boundary | Clock 2026-11-02T23:59+03:00, then advance 1 minute | `today` 2026-11-02, then 2026-11-03 | held-out |
| T-COM-03-a | LIB-COM-03 | Normal | Login at 2026-11-02T09:00+03:00 | `expires_at` `"2026-11-02T21:00:00+03:00"` | feedback |
| T-COM-04-a | LIB-COM-04 | Error | `GET /api/v1/calendar/days/2026-02-30` | `422 VALIDATION_ERROR` | held-out |
| T-COM-05-a | LIB-COM-05 | Normal | 2026-11-07 (Saturday), 2026-11-09 (Monday) | Not a working day (`weekend`); working day | feedback |
| T-COM-06-a | LIB-COM-06 | Normal | `GET /api/v1/calendar/holidays?year=2026` | The 14 dates of the 2026 table, in order | feedback |
| T-COM-06-b | LIB-COM-06 | Boundary | Arife days 2026-10-28 (Wed) and 2027-03-08 (Mon) | Both are working days | held-out |
| T-COM-07-a | LIB-COM-07 | Boundary | 2028-05-01 (Monday, year not in the list) | Working day | feedback |
| T-COM-08-a | LIB-COM-08 | Normal | 2026-05-27 | 2026-06-01 | feedback |
| T-COM-08-b | LIB-COM-08 | Boundary | 2026-03-24 (working day); 2027-01-01 | 2026-03-24; 2027-01-04 | held-out |
| T-COM-09-a | LIB-COM-09 | Normal | 2026-10-28 + 2 working days | 2026-11-02 | feedback |
| T-COM-09-b | LIB-COM-09 | Boundary | 2026-05-26 + 2; 2026-11-06 (Fri) + 1 | 2026-06-02; 2026-11-09 | held-out |
| T-COM-10-a | LIB-COM-10 | Normal | 2026-06-01 → 2026-06-05 | 4 | feedback |
| T-COM-10-b | LIB-COM-10 | Boundary | 2026-10-23 → 2026-10-26; 2026-10-27 → 2026-10-30 | 1; 2 | held-out |
| T-COM-10-c | LIB-COM-10 | Boundary | end = start; end < start | 0; 0 | feedback |
| T-COM-11-a | LIB-COM-11 | Normal | Copy with price `"0.10"`, read back | `"0.10"` exactly (no float artefacts) | feedback |
| T-COM-12-a | LIB-COM-12 | Static | Fee calculations (module 7 tests) | ROUND_HALF_UP to two places; inputs have at most two decimals, so rounding is observed through fee tests | static |
| T-COM-13-a | LIB-COM-13 | Normal | Copy with price `"100.00"` | Response amount is the string `"100.00"` | feedback |
| T-COM-13-b | LIB-COM-13 | Error | Price as JSON number 100 | `422 VALIDATION_ERROR` | held-out |
| T-COM-13-c | LIB-COM-13 | Error | Price `"1.005"` (three decimals) | `422 VALIDATION_ERROR` | feedback |
| T-COM-14-a | LIB-COM-14 | Normal | Create two branches in a new database | ids 1 and 2 | held-out |
| T-COM-15-a | LIB-COM-15 | Normal | Branch name `"  Central  "` | Stored and returned as `"Central"` | feedback |
| T-COM-15-b | LIB-COM-15 | Error | Branch name of spaces only | `422 VALIDATION_ERROR` | held-out |
| T-COM-16-a | LIB-COM-16 | Boundary | User `full_name` of 200 characters | Accepted | feedback |
| T-COM-16-b | LIB-COM-16 | Boundary | User `full_name` of 201 characters | `422 VALIDATION_ERROR` | held-out |
| T-COM-17-a | LIB-COM-17 | Normal | User e-mail `"New.Staff@Library.Local"` | Stored and returned as `"new.staff@library.local"` | feedback |
| T-COM-17-b | LIB-COM-17 | Error | E-mails `"a@b"`, `"@x.com"`, `"a@@x.com"` | `422 VALIDATION_ERROR` each | held-out |
| T-COM-18-a | LIB-COM-18 | Boundary | `GET /api/v1/users?page_size=101`; `page=0` | `422 VALIDATION_ERROR` both | feedback |
| T-COM-18-b | LIB-COM-18 | Normal | `GET /api/v1/users` without parameters; `page_size=100` | `page` 1, `page_size` 20; 100 accepted | held-out |
| T-COM-19-a | LIB-COM-19 | Normal | 25 extra users; page 2 with page size 10 | 10 items, `total` 27 (admin + librarian + 25) | feedback |
| T-COM-19-b | LIB-COM-19 | Boundary | Page beyond the last page | 200 with `items` [] | held-out |
| T-COM-20-a | LIB-COM-20 | Normal | Users created in the order admin, librarian, x, y | List ordered by `id` ascending | held-out |
| T-COM-21-a | LIB-COM-21 | Error | `GET /users` without `/api/v1` | `404 NOT_FOUND` in the error format | feedback |
| T-COM-22-a | LIB-COM-22 | Normal | Create user, update user, logout | 201 with body; 200 with body; 204 without body | held-out |
| T-COM-23-a | LIB-COM-23 | Error | `POST /api/v1/users` with an extra field `nickname` | `422 VALIDATION_ERROR` | feedback |
| T-COM-24-a | LIB-COM-24 | Error | Header `Authorization: Token abc` (not Bearer) | `401 UNAUTHENTICATED` | held-out |
| T-COM-25-a | LIB-COM-25 | Normal | `GET /api/v1/users/9999` as admin | Body `{"error": {"code", "message", "details"}}` with `details` an object | feedback |
| T-COM-26-a | LIB-COM-26 | Normal | `POST /api/v1/users` with invalid `email` and missing `full_name` | `details.fields` names both fields | held-out |
| T-COM-27-a | LIB-COM-27 | Static | Forced internal error (fault injection in the pilot) | `500 INTERNAL_ERROR`, no stack trace in the body | static |
| T-COM-28-a | LIB-COM-28 | Error | No token and an invalid body to `POST /api/v1/users` | 401 (authentication first) | feedback |
| T-COM-28-b | LIB-COM-28 | Error | Librarian sends an invalid body to `POST /api/v1/users` (admin only) | `403 FORBIDDEN` (role before validation) | held-out |
| T-COM-28-c | LIB-COM-28 | Error | Admin: `PATCH /api/v1/users/9999` with invalid `role`; then with a valid body | 422 (validation before existence); then 404 | feedback |
| T-COM-29-a | LIB-COM-29 | Error | Register a member with `home_branch_id` 999 | `404 NOT_FOUND`, `details` `{"field": "home_branch_id", "id": 999}` | feedback |
| T-COM-30-a | LIB-COM-30 | Boundary | Users `isik@library.local` and `ISIK@library.local` | Second returns `409 CONFLICT` | feedback |
| T-COM-30-b | LIB-COM-30 | Normal | User named `"Işık Yılmaz"`; filter `q=ISIK` | The user is found | held-out |
| T-IF-01-a | LIB-IF-01 | Normal | `lms.create_app(settings)` | A FastAPI application | feedback |
| T-IF-02-a | LIB-IF-02 | Boundary | `create_app` twice on the same database file | No error; exactly one admin | held-out |
| T-IF-03-a | LIB-IF-03 | Normal | Two apps with different database files; branch created in one | The other app has no branch | feedback |
| T-IF-04-a | LIB-IF-04 | Normal | `lms.DEFAULT_HOLIDAYS` | 27 dates; contains 2026-10-29, not 2026-10-28 | held-out |
| T-IF-05-a | LIB-IF-05 | Normal | In-memory database: create a branch, read it in a later request | The branch is visible | feedback |
| T-IF-06-a | LIB-IF-06 | Boundary | `token_ttl_hours` 0 and 169 | `ValueError` both | feedback |
| T-IF-06-b | LIB-IF-06 | Boundary | `token_ttl_hours` 1 and 168 | Accepted | held-out |
| T-IF-07-a | LIB-IF-07 | Normal | `lms.SystemClock().now()` | Aware datetime with offset +03:00 | feedback |
| T-IF-08-a | LIB-IF-08 | Error | `FixedClock(naive)`; `set(naive)` | `ValueError` both | held-out |
| T-IF-09-a | LIB-IF-09 | Normal | `clock.advance(days=1)` between two requests | `today` changes from 2026-11-02 to 2026-11-03 without restart | feedback |
| T-IF-10-a | LIB-IF-10 | Normal | `GET /health` without token | 200 `{"status": "ok", "today": "2026-11-02"}` | held-out |
| T-IF-11-a | LIB-IF-11 | Normal | `import_dataset` with one branch and empty lists into an empty database | Counts `{"branches": 1, ...: 0}` | feedback |
| T-IF-11-b | LIB-IF-11 | Error | Second import into the same database; invalid `format_version` | `RuntimeError`; `ValueError` | held-out |
| T-IF-12-a | LIB-IF-12 | Normal | After creating a branch: `export_dataset(settings)` and `GET /api/v1/export` | Equal documents | held-out |
| T-CORE-01-a | LIB-CORE-01 | Normal | `holidays?year=2026` | `year` 2026; first entry `{"date": "2026-01-01", "name": "New Year's Day"}`; no auth needed | feedback |
| T-CORE-01-b | LIB-CORE-01 | Boundary | `year` 2030; `year` 1899 and 2101 | Empty list; `422` for both | held-out |
| T-CORE-01-c | LIB-CORE-01 | Normal | `year` 2027 | 13 dates; 2027-05-19 appears once | feedback |
| T-CORE-02-a | LIB-CORE-02 | Normal | 2026-10-29 | `{"date": "2026-10-29", "working_day": false, "reason": "holiday"}` | feedback |
| T-CORE-02-b | LIB-CORE-02 | Boundary | 2026-03-21 (Saturday and holiday) | `reason` `"holiday"` | held-out |
| T-CORE-03-a | LIB-CORE-03 | Normal | `next-working-day?date=2026-05-27` without token | `{"date": "2026-06-01"}` | feedback |
| T-CORE-04-a | LIB-CORE-04 | Normal | `add-working-days?date=2026-10-28&days=2` | `{"date": "2026-11-02"}` | feedback |
| T-CORE-04-b | LIB-CORE-04 | Boundary | `days` 0 and 366; `days` 365 | `422` for 0 and 366; 200 for 365 | held-out |
| T-CORE-05-a | LIB-CORE-05 | Normal | `working-days-between?start=2026-06-01&end=2026-06-05` | `{"working_days": 4}` | feedback |
| T-CORE-05-b | LIB-CORE-05 | Boundary | `end` − `start` = 3660 days; 3661 days | 200; `422` | held-out |
| T-CORE-06-a | LIB-CORE-06 | Error | `working-days-between` without `end` | `422`, `details.fields` contains `end` | held-out |
| T-CORE-07-a | LIB-CORE-07 | Normal | Academic lends a copy on 2026-12-02 | Loan `due_date` equals `next-working-day` of 2027-01-01 (2027-01-04) | feedback |
| T-CORE-08-a | LIB-CORE-08 | Static | Fee calculations (module 7 tests) | Rounding applied to final results only | static |
| T-CORE-09-a | LIB-CORE-09 | Normal | `GET /api/v1/books/9999` as librarian | `404` in the error format of LIB-COM-25 | feedback |
| T-CORE-10-a | LIB-CORE-10 | Boundary | `GET /api/v1/members?page_size=101` | `422 VALIDATION_ERROR` | held-out |
