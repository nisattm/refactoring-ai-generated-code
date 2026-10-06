# Requirements for the Generated Application

This document is the requirements specification given to the LLM. It is written in neutral language, as an ordinary developer would describe the application. It does not ask for good or bad code.

## Application

A REST API for tracking courses, absences and grades of students.

## Technical constraints

- Java, Spring Boot, Maven
- H2 in-memory database
- Runs with a single command: `mvn spring-boot:run`
- No authentication, no external services, no user interface (Swagger UI is allowed for demonstration)

## Entities

- **Student**
- **Course** (type: theoretical or practical; weekly hours; whether it has a project)
- **Absence** (linked to a student and a course, recorded in hours)
- **Grade** (midterm, final, optional project; linked to a student and a course)

## Features

### 1. Student and course management

Create, list, update and delete students and courses.

### 2. Absence tracking

Record absences in hours and calculate the student's absence status for a course.

**Semester:** 14 weeks, 3 hours per week, 42 hours in total.

| Course type | Absence limit | Allowed absence | Warning from | Failed when |
| --- | --- | --- | --- | --- |
| Theoretical | 30% | 13 hours | 10 hours | more than 13 hours |
| Practical | 20% | 9 hours | 6 hours | more than 9 hours |

- Allowed absence = total course hours × absence limit, rounded up (42 × 30% = 12.6 → 13 hours).
- Status values:
  - **Normal:** absence is below the warning threshold.
  - **Warning:** absence has reached the warning threshold (3 hours or fewer remaining) but does not exceed the allowed absence.
  - **Failed:** absence exceeds the allowed absence.
- The absence limits (30% and 20%) and the warning margin (3 hours) must be configurable.

### 3. Grade calculation

Record midterm, final and optional project grades (each between 0 and 100) and calculate the average and the letter grade.

| Course | Midterm | Project | Final |
| --- | --- | --- | --- |
| Without project | 40% | – | 60% |
| With project | 30% | 30% | 40% |

The average is rounded to the nearest whole number (half up) before the letter grade is assigned.

| Letter grade | Average range | Result |
| --- | --- | --- |
| AA | 85–100 | Passed |
| BA | 78–84 | Passed |
| BB | 70–77 | Passed |
| CB | 63–69 | Passed |
| CC | 55–62 | Passed |
| DC | 48–54 | Passed |
| DD | 40–47 | Passed |
| FF | 0–39 | Failed |

The passing grade is 40 (DD).

### 4. Student report

Return a single list of a student's courses showing, for each course: grades, average, letter grade, total absence hours and absence status.
