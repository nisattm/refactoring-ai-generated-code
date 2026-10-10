# Requirements for the Generated Application

This is a short overview of the application that the LLMs generate. The binding specification is [`api-contract.md`](api-contract.md); the exact texts sent to the LLMs are in [`prompts/`](prompts/). If anything here differs from the contract, the contract wins.

The requirements are written in neutral language, as an ordinary developer would describe the application. They never ask for good or bad code.

## Application

A REST API for tracking students' courses, absences and grades.

## Technical constraints

- Java 17 or later, Spring Boot 3, Maven
- H2 in-memory database
- Runs with a single command: `mvn spring-boot:run` (port 8080, base path `/api`)
- Swagger UI at `/swagger-ui.html`
- No authentication, no external services, no user interface

## Entities

| Entity | Main fields |
| --- | --- |
| Student | student number (9 digits, unique), first name, last name, email |
| Course | code (unique), name, type (`THEORETICAL` / `PRACTICAL`), weekly hours (1–10), grading scheme |
| Absence | student, course, date, hours |
| Grade | student, course, midterm, final exam, project (at most one grade per student and course) |

## Features (one prompt each)

| Step | Feature | Key rules |
| --- | --- | --- |
| P1 | Student and course management | CRUD; validation; 404 / 409 for missing or duplicate records |
| P2 | Absence tracking | Total course hours = weekly hours × 14; allowed absence = total × limit, rounded up; limits 30% theoretical / 20% practical; status `NORMAL` / `WARNING` (3 hours or fewer remaining) / `FAILED` (more than allowed); limits and margin configurable |
| P3 | Grade calculation | `MIDTERM_FINAL` 40/60, `MIDTERM_PROJECT_FINAL` 30/30/40; exact average rounded half up; letter grades AA–FF; passing average 40 |
| P4 | Student report | One list per student with grade, absence status and result (`FAILED_ABSENCE` / `INCOMPLETE` / `FAILED_GRADE` / `PASSED`) |

## Change requests (sent after P4)

| Step | Change |
| --- | --- |
| DT1 | New grading scheme `PROJECT_ONLY` (100% project) |
| DT2 | Optional per-course absence limit `absenceLimitPercent` that overrides the type default |

The change requests simulate how requirements change after delivery and let us measure how the generated code grows and degrades under change.

## Models

The same prompts are given to three LLMs (Claude, GPT, Gemini), each producing its own codebase under `codebases/<model>/`. The procedure is in [`prompts/README.md`](prompts/README.md).
