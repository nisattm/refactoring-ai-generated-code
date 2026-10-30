# Test cases: module 14 (API layer)

Generated from one case list; 6 cases for 5 requirements (feedback 3, held-out 3, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-API-01-a | LIB-API-01 | Normal | Every endpoint of the requirements, called without token with id 1 | No call returns `404` or `405` (authentication or validation answers first, so the route exists) | feedback |
| T-API-01-b | LIB-API-01 | Error | `GET /api/v1/books/abc`, `/books/0`, `/books/-1` as librarian | `422 VALIDATION_ERROR` each | held-out |
| T-API-02-a | LIB-API-02 | Error | `GET /api/v1/nothing-here`; `DELETE /api/v1/branches` | `404 NOT_FOUND`; `405 METHOD_NOT_ALLOWED`; both in the error format | held-out |
| T-API-03-a | LIB-API-03 | Normal | Copy without `shelf_location`; librarian's `UserOut` | `shelf_location` present with `null`; `member_id` and `last_login_at` keys present | feedback |
| T-API-04-a | LIB-API-04 | Normal | `GET /openapi.json` | Lists every endpoint of the requirements (path parameters compared by position) | held-out |
| T-API-05-a | LIB-API-05 | Error | `POST /api/v1/branches` with a JSON text but `Content-Type: text/plain` | `422 VALIDATION_ERROR` | feedback |
