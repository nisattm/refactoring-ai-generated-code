# P4 – Student report

Copy everything between the two lines below and send it as one message. Do not change, add or remove anything.

---

Add a student report to the existing course tracking application. All existing endpoints must keep working exactly as before, and the API conventions already used in the application (JSON field names, status codes, error body) also apply to the new endpoint.

## Endpoint

`GET /api/students/{studentId}/report` → 200 with the report; 404 if the student does not exist.

## Response

```json
{
  "studentId": 1,
  "studentNumber": "220201001",
  "fullName": "Ayşe Yılmaz",
  "courses": [
    {
      "courseId": 1,
      "courseCode": "SE402",
      "courseName": "Engineering Design II",
      "courseType": "THEORETICAL",
      "gradingScheme": "MIDTERM_PROJECT_FINAL",
      "grade": {
        "midterm": 55,
        "finalExam": 50,
        "project": 50,
        "average": 52,
        "letterGrade": "DC"
      },
      "absence": {
        "totalAbsenceHours": 10,
        "allowedAbsenceHours": 13,
        "remainingAbsenceHours": 3,
        "status": "WARNING"
      },
      "result": "PASSED"
    }
  ]
}
```

## Rules

1. `fullName` is `firstName`, one space, then `lastName`.
2. `courses` contains every course for which this student has at least one absence record or a grade, sorted by `courseCode` ascending. If there are none, `courses` is `[]`.
3. `grade` is `null` when no grade has been recorded for that course. Otherwise it contains the same `midterm`, `finalExam`, `project`, `average` and `letterGrade` values as the grade endpoint returns.
4. `absence` is always present and contains the same values as the absence status endpoint returns. When the course has a grade but no absence records, `totalAbsenceHours` is 0 and `status` is `NORMAL`.
5. `result` is decided in this order:
   1. `FAILED_ABSENCE` if `absence.status` is `FAILED`
   2. otherwise `INCOMPLETE` if `grade` is `null`
   3. otherwise `FAILED_GRADE` if `letterGrade` is `FF`
   4. otherwise `PASSED`

---
