# DT2 – Change request: per-course absence limit

Send only after DT1 is complete. Copy everything between the two lines below and send it as one message. Do not change, add or remove anything.

---

Change request for the existing course tracking application: the absence limit must be adjustable for individual courses. All existing endpoints and behavior must keep working exactly as before, except for the changes below.

1. Courses get a new optional field:

| Field | Type | Rules |
| --- | --- | --- |
| `absenceLimitPercent` | integer or null | Optional; 1 to 100 inclusive when present; absent or `null` means "use the configured default for the course type" |

2. `absenceLimitPercent` is accepted by `POST /api/courses` and `PUT /api/courses/{id}`, and returned in every course response (as `null` when it is not set). A value outside 1–100 → 400.
3. When a course has `absenceLimitPercent`, it replaces the configured theoretical or practical limit for that course. All other absence rules are unchanged, including rounding up: a `THEORETICAL` course with 3 hours/week (42 total hours) and `absenceLimitPercent` 10 has `allowedAbsenceHours` = 42 × 10 / 100 = 4.2 → 5.
4. The absence status endpoint and the student report use the course's effective limit.

Examples:

| Course | `absenceLimitPercent` | `allowedAbsenceHours` |
| --- | --- | --- |
| THEORETICAL, 3 hours/week | not set | 13 (configured default 30%) |
| THEORETICAL, 3 hours/week | 10 | 5 |
| PRACTICAL, 3 hours/week | 50 | 21 |
| PRACTICAL, 3 hours/week | 0 | request rejected with 400 |

---
