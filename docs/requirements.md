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
- **Course** (type: theoretical or practical)
- **Absence** (linked to a student and a course)
- **Grade** (midterm, final, optional project; linked to a student and a course)

## Features

1. **Student and course management:** create, list, update and delete students and courses.
2. **Absence tracking:** record absences and calculate the student's status for a course (Normal / Warning / Failed). Theoretical and practical courses have different absence limits; the limits must be configurable.
3. **Grade calculation:** record midterm, final and optional project grades. Two weighting schemes exist: midterm/final and midterm/project/final. Calculate the average and the letter grade.
4. **Student report:** return a single list of a student's courses, grades and absence status.

_Exact values (absence limits, weights, letter grade ranges) to be filled in by the team before generation._
