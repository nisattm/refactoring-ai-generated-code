# DT1 – Change request: project-only grading

Send only after P4 is complete. Copy everything between the two lines below and send it as one message. Do not change, add or remove anything.

---

Change request for the existing course tracking application: some courses are graded only by a project. All existing endpoints and behavior must keep working exactly as before, except for the changes below.

1. Courses can use a third grading scheme: `PROJECT_ONLY`. It is accepted wherever `gradingScheme` is accepted and returned wherever it is returned.
2. For a `PROJECT_ONLY` course, the grade request must contain `project` (0 to 100 inclusive), and `midterm` and `finalExam` must be null or absent. Otherwise the response is 400.
3. For a `PROJECT_ONLY` course, the average is 100% of `project`. The existing rounding, `letterGrade`, `passed`, report and `result` rules apply unchanged. In the grade result and in the report, `midterm` and `finalExam` are `null`.

Examples:

| Grade request for a `PROJECT_ONLY` course | Response |
| --- | --- |
| `{ "project": 84 }` | 200; `average` 84, `letterGrade` "BA", `passed` true |
| `{ "project": 39 }` | 200; `average` 39, `letterGrade` "FF", `passed` false |
| `{ "midterm": 50, "project": 84 }` | 400 |
| `{ }` | 400 |

---
