# P3 – Grade calculation

Copy everything between the two lines below and send it as one message. Do not change, add or remove anything.

---

Add grade recording and grade calculation to the existing course tracking application. All existing endpoints must keep working exactly as before, and the API conventions already used in the application (JSON field names, status codes, error body) also apply to the new endpoints.

A student has at most one grade per course. There is no enrollment step: a grade can be recorded for any existing student in any existing course.

## Grade request

`PUT /api/students/{studentId}/courses/{courseId}/grade`

```json
{
  "midterm": 55,
  "finalExam": 50,
  "project": 50
}
```

| Field | Type | Rules |
| --- | --- | --- |
| `midterm` | integer or null | 0 to 100 inclusive when present |
| `finalExam` | integer or null | 0 to 100 inclusive when present |
| `project` | integer or null | 0 to 100 inclusive when present |

Which fields are required depends on the course's `gradingScheme`. A field that is absent from the JSON counts as null.

| `gradingScheme` | `midterm` | `finalExam` | `project` |
| --- | --- | --- | --- |
| `MIDTERM_FINAL` | required | required | must be null |
| `MIDTERM_PROJECT_FINAL` | required | required | required |

A missing required field, a value that must be null but is not, or a value outside 0–100 → 400.

| Endpoint | Success | Errors |
| --- | --- | --- |
| `PUT /api/students/{studentId}/courses/{courseId}/grade` | 200, grade result; creates the grade or replaces the existing one | 404 student or course does not exist; 400 invalid |
| `GET /api/students/{studentId}/courses/{courseId}/grade` | 200, grade result | 404 student or course does not exist; 404 no grade recorded yet |

## Grade result

```json
{
  "studentId": 1,
  "courseId": 1,
  "gradingScheme": "MIDTERM_PROJECT_FINAL",
  "midterm": 55,
  "finalExam": 50,
  "project": 50,
  "average": 52,
  "letterGrade": "DC",
  "passed": true
}
```

Fields that are null for the course's scheme are returned as `null`.

## Calculation

Weights:

| `gradingScheme` | `midterm` | `project` | `finalExam` |
| --- | --- | --- | --- |
| `MIDTERM_FINAL` | 40% | — | 60% |
| `MIDTERM_PROJECT_FINAL` | 30% | 30% | 40% |

1. The weighted average is calculated exactly and then rounded to a whole number, half up (x.5 always rounds up): 51.5 → 52, 84.5 → 85. Results must not be affected by floating-point error.
2. `average` is that rounded whole number.
3. `letterGrade` comes from `average`:

| `letterGrade` | `average` |
| --- | --- |
| `AA` | 85–100 |
| `BA` | 78–84 |
| `BB` | 70–77 |
| `CB` | 63–69 |
| `CC` | 55–62 |
| `DC` | 48–54 |
| `DD` | 40–47 |
| `FF` | 0–39 |

4. `passed` is true when `average` ≥ 40, otherwise false.

Examples:

| Scheme | midterm / project / finalExam | Exact average | `average` | `letterGrade` | `passed` |
| --- | --- | --- | --- | --- | --- |
| MIDTERM_FINAL | 50 / – / 70 | 62.0 | 62 | CC | true |
| MIDTERM_FINAL | 30 / – / 45 | 39.0 | 39 | FF | false |
| MIDTERM_FINAL | 100 / – / 100 | 100.0 | 100 | AA | true |
| MIDTERM_PROJECT_FINAL | 55 / 50 / 50 | 51.5 | 52 | DC | true |
| MIDTERM_PROJECT_FINAL | 85 / 90 / 80 | 84.5 | 85 | AA | true |
| MIDTERM_PROJECT_FINAL | 30 / 35 / 50 | 39.5 | 40 | DD | true |
| MIDTERM_PROJECT_FINAL | 80 / 90 / 88 | 86.2 | 86 | AA | true |

## Changes to existing behavior

- Deleting a student also deletes all of that student's grades. Deleting a course also deletes all grades for that course.
- `PUT /api/courses/{id}` returns 409 if it changes the course's `gradingScheme` while the course has at least one grade.

---
