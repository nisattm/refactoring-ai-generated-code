# Test cases: module 2 (Identity and access)

Generated from one case list; 42 cases for 25 requirements (feedback 22, held-out 19, static 1). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-AUTH-01-a | LIB-AUTH-01 | Normal | Fresh application; login with the bootstrap credentials | 200; `user.role` `admin`, `full_name` `Administrator`, active | feedback |
| T-AUTH-02-a | LIB-AUTH-02 | Boundary | Passwords `abcdefg1` (8 chars) and 128 chars with a digit | Both accepted | feedback |
| T-AUTH-02-b | LIB-AUTH-02 | Boundary | Passwords `abcdef1` (7), `abcdefgh` (no digit), `12345678` (no letter), 129 chars | `422 VALIDATION_ERROR` with field `password` each | heldout |
| T-AUTH-03-a | LIB-AUTH-03 | Static | Database row of a user | `password_hash` matches `scrypt$<32 hex>$<128 hex>` and verifies with n=16384, r=8, p=1, dklen=64 | static |
| T-AUTH-04-a | LIB-AUTH-04 | Error | `POST /api/v1/users` with `role` `member` | `422 VALIDATION_ERROR` | heldout |
| T-AUTH-05-a | LIB-AUTH-05 | Error | Create a user with the librarian's e-mail in upper case | `409 CONFLICT` | feedback |
| T-AUTH-06-a | LIB-AUTH-06 | Normal | Librarian logs in | 200 with `access_token`, `token_type` `bearer`, `expires_at`, `user` (no password fields) | heldout |
| T-AUTH-07-a | LIB-AUTH-07 | Normal | Two logins of the librarian | Two different 43-character URL-safe tokens; both valid | feedback |
| T-AUTH-08-a | LIB-AUTH-08 | Error | Unknown e-mail; known e-mail with wrong password | Both `401 INVALID_CREDENTIALS` with the same body | heldout |
| T-AUTH-09-a | LIB-AUTH-09 | Boundary | Five wrong passwords at 09:00; then the correct password | Fifth: 401; then `403 ACCOUNT_LOCKED` with `details.locked_until` 2026-11-02T09:15:00+03:00 | feedback |
| T-AUTH-09-b | LIB-AUTH-09 | Boundary | Locked at 09:00; login at 09:14 and at 09:15 | 09:14 `403 ACCOUNT_LOCKED`; 09:15 success | heldout |
| T-AUTH-09-c | LIB-AUTH-09 | Normal | Four wrong, one correct, four wrong, then correct | Last login succeeds (success resets the counter) | feedback |
| T-AUTH-09-d | LIB-AUTH-09 | Boundary | Locked; wrong passwords while locked; login after 15 minutes | Attempts while locked return 403 and do not count; after 15 min success | heldout |
| T-AUTH-10-a | LIB-AUTH-10 | Error | Admin deactivates a librarian; login with correct and with wrong password | Correct: `403 ACCOUNT_DISABLED`; wrong: `401 INVALID_CREDENTIALS` | heldout |
| T-AUTH-11-a | LIB-AUTH-11 | Boundary | Lock a librarian (5 failures), then deactivate it; login with the correct password | `403 ACCOUNT_LOCKED` (lock is checked before active) | feedback |
| T-AUTH-12-a | LIB-AUTH-12 | Error | `GET /api/v1/auth/me` without header; with `Bearer unknown` | `401 UNAUTHENTICATED` both | feedback |
| T-AUTH-12-b | LIB-AUTH-12 | Error | Token used 12 hours after login | `401 TOKEN_EXPIRED` | heldout |
| T-AUTH-13-a | LIB-AUTH-13 | Boundary | Login 09:00; request at 20:59:59 and at 21:00:00 | 200, then `401 TOKEN_EXPIRED` | feedback |
| T-AUTH-14-a | LIB-AUTH-14 | Normal | Logout, then reuse the token; a second session of the same user | 204; reuse `401 UNAUTHENTICATED`; the other session still works | heldout |
| T-AUTH-15-a | LIB-AUTH-15 | Normal | `GET /api/v1/auth/me` as librarian | `UserOut` with exactly the documented fields | feedback |
| T-AUTH-16-a | LIB-AUTH-16 | Normal | Two sessions; change password with session 1 | 204; session 1 valid, session 2 revoked; new password works, old does not | feedback |
| T-AUTH-16-b | LIB-AUTH-16 | Error | Wrong `current_password` five times, then normal login | `401 INVALID_CREDENTIALS` each; login still works (no lockout) | heldout |
| T-AUTH-16-c | LIB-AUTH-16 | Error | `new_password` equal to the current one | `409 PASSWORD_UNCHANGED` | feedback |
| T-AUTH-16-d | LIB-AUTH-16 | Error | Wrong `current_password` and a `new_password` without digit | `422 VALIDATION_ERROR` (policy checked first) | heldout |
| T-AUTH-17-a | LIB-AUTH-17 | Normal | Admin creates an admin | 201 with `UserOut`, `role` `admin` | feedback |
| T-AUTH-17-b | LIB-AUTH-17 | Error | Librarian calls `POST /api/v1/users` | `403 FORBIDDEN` | heldout |
| T-AUTH-18-a | LIB-AUTH-18 | Normal | Filters `role=librarian`, `is_active=false`, `q=LIB@` | Only matching users | heldout |
| T-AUTH-19-a | LIB-AUTH-19 | Normal | Member reads own user record (id from `/auth/me`) | 200 with own `UserOut`; `member_id` set | feedback |
| T-AUTH-19-b | LIB-AUTH-19 | Error | Librarian reads the admin's record and id 9999 | `403 FORBIDDEN` both (ownership before existence) | heldout |
| T-AUTH-19-c | LIB-AUTH-19 | Error | Admin reads id 9999 | `404 NOT_FOUND` | feedback |
| T-AUTH-20-a | LIB-AUTH-20 | Normal | Admin changes a librarian's `role` to `admin` and `full_name` | 200 with new values | feedback |
| T-AUTH-20-b | LIB-AUTH-20 | Error | `role` `member` in the request | `422 VALIDATION_ERROR` | heldout |
| T-AUTH-20-c | LIB-AUTH-20 | Error | Change the role of a member's user to `librarian` | `409 ROLE_CHANGE_NOT_ALLOWED` | feedback |
| T-AUTH-21-a | LIB-AUTH-21 | Normal | Deactivate a logged-in librarian | Its token returns `401 UNAUTHENTICATED` | feedback |
| T-AUTH-21-b | LIB-AUTH-21 | Normal | Locked librarian is deactivated and activated again | Login succeeds at once (lock cleared) | heldout |
| T-AUTH-22-a | LIB-AUTH-22 | Error | Only admin demotes itself to librarian; deactivates itself | `409 LAST_ADMIN`; `409` (`LAST_ADMIN` or `CANNOT_DEACTIVATE_SELF`) | feedback |
| T-AUTH-22-b | LIB-AUTH-22 | Error | Two admins; admin 1 deactivates itself; then deactivates admin 2 | `409 CANNOT_DEACTIVATE_SELF`; then 200 | heldout |
| T-AUTH-23-a | LIB-AUTH-23 | Normal | Locked librarian with an open session; admin resets the password | 204; old session 401; new password logs in at once | feedback |
| T-AUTH-23-b | LIB-AUTH-23 | Error | Librarian calls reset-password | `403 FORBIDDEN` | heldout |
| T-AUTH-24-a | LIB-AUTH-24 | Error | Member calls `GET /api/v1/users` and `POST /api/v1/branches` | `403 FORBIDDEN` both | feedback |
| T-AUTH-24-b | LIB-AUTH-24 | Error | No token: `GET /api/v1/books` | `401 UNAUTHENTICATED` | heldout |
| T-AUTH-25-a | LIB-AUTH-25 | Error | Member A reads member B's record; member A reads member id 9999 | `403 FORBIDDEN`; `404 NOT_FOUND` | feedback |
