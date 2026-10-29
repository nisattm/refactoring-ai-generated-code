# 002 – One LMS, Claude Code Pro, one refactoring of the whole project

**Date:** 2026-10-29
**Status:** Accepted. Library details (synchronous SQLAlchemy, pinned versions) are a proposal confirmed with the requirements document; Claude Code mechanics are checked in the pilot.

## Context

After the Weeks 1–2 feedback, the instructor asked for large, complex code in which all metrics can be tested, and said that refactoring module by module makes no sense because the modules depend on each other. The team has no API budget; a Claude Pro subscription is available. Week 3 asks for the tasks to be classified as simple, medium and complex.

## Decision

| Topic | Decision |
| --- | --- |
| Subject code | One Library Management System (LMS). No separate simple/medium tasks. |
| Size | A fully working LMS, about 30,000–40,000 lines of application code (Radon SLOC, tests excluded) |
| Interface | No frontend; a REST API layer instead |
| Tool | Claude Code with a Claude Pro subscription; no API |
| Model | Claude Sonnet 5.5 for generation and for all three approaches, selected by full model ID; effort level fixed |
| Refactoring | The whole project is refactored in one run by each approach; metrics are also reported per module and level |
| Generation | Code is generated piece by piece (it does not fit in one response); generated code is never edited by hand |
| Complexity levels | The 14 LMS modules are classified as simple, medium or complex (Week 3 classification). RQ4 is revised accordingly. |
| Database | SQLite |
| Python | 3.14, latest patch at setup, fixed for the whole study |
| Libraries | FastAPI + Uvicorn, Pydantic v2, SQLAlchemy 2.x (synchronous) + SQLite; pytest, httpx (TestClient), Hypothesis for tests; otherwise standard library only; versions pinned with `==` in `requirements.txt` |
| Cost | Tokens, time and equivalent cost at API list price instead of billed USD ([`../metrics.md`](../metrics.md#8-cost-of-the-refactoring-llm-side)) |
| Business rules | As listed in [`../../dataset/README.md`](../../dataset/README.md#business-rules-approved-29-october-2026) |

## Consequences

- `README.md`, `approaches.md`, `metrics.md`, `testing.md`, `smell-catalog.md`, `dataset/README.md` and `scripts/README.md` were updated.
- Tests attach to the REST API and a fixed service interface, because internal code may change during refactoring.
- Pro usage limits (5-hour and weekly) are not published. A pilot (about 5,000 lines generated, one refactoring) measures usage before the number of repetitions is fixed.
- Compatibility of the measurement tools (PyExamine, DPy, mutmut, memray) with Python 3.14 is not yet verified.
- Classifying modules instead of separate tasks is our reading of the Week 3 plan; written confirmation from the instructor is requested.
- Week 3 task files prepared before 29 October (separate simple/medium tasks, API script) are void.
