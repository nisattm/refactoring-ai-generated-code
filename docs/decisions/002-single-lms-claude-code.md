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
| Multi-Agent | Claude Code subagents (Analyzer, Refactoring, Reviewer) under an orchestrating `claude -p` session, as named in the instructor's notes; accepted trade-off: only each subagent's final message returns to the orchestrator ([`../approaches.md`](../approaches.md#multi-agent-with-claude-code-subagents)) |
| Run isolation | Fresh container and fresh project copy per run; tools limited per approach; runs with any model other than Sonnet 5.5 are invalid |
| Usage limits | Considered sufficient by the team (5-hour window resets); usage per run is still recorded in the pilot |
| Business rules | Summary in [`../../dataset/README.md`](../../dataset/README.md#business-rules-approved-29-october-2026); full specification in [`../../dataset/lms/requirements.md`](../../dataset/lms/requirements.md) |

## Approved details

Approved by Nisa (project lead) in the design discussion; recorded here because the requirements review could not see them.

| Date | Topic | Decision |
| --- | --- | --- |
| 2026-10-29 | Membership types | Student 14 days / 5 books / 1 renewal / 2 TL per working day; academic 30 / 10 / 2 / 1 TL; staff 21 / 7 / 2 / 1 TL; guest 7 / 2 / 0 / 5 TL |
| 2026-10-29 | Fees and blocks | Fee cap 100 TL per book, independent of the price; borrowing blocked at total debt ≥ 50 TL; lost book = accrued late fee + price + 25 TL |
| 2026-10-29 | Calendar | Working day = not Saturday, Sunday or official holiday (2026–2027 list); due date moves to the next working day; late days start the day after the due date; half-day eves (arife) are working days |
| 2026-10-29 | Renewal | New period starts on the renewal day; overdue loans and books with an active reservation (waiting, in transit or ready) cannot be renewed |
| 2026-10-29 | Reservations | At most 3 active per member; ready book held 3 working days; first-come, first-served queue without priority; reservation only if no copy is available at the pickup branch; waiting reservations do not expire |
| 2026-10-29 | Members | Validity 365 days (guest 90), counted including the start day; university/staff number for non-guests, phone for guests, no national ID; members with open loans cannot be deactivated; type change applies to new loans only |
| 2026-10-29 | Loans | Members with an overdue loan cannot borrow; damage fee entered by the librarian, > 0 and ≤ copy price; members may renew their own loans; return at any branch, copy returns home by transfer |
| 2026-10-29 | Fees | Partial payments allowed, applied to the oldest fee first; only admins waive fees, with a reason |
| 2026-10-29 | Roles and security | Roles member, librarian, admin; passwords with scrypt; random tokens stored as SHA-256 |
| 2026-10-29 | Level score | Business rules (0–5 / 6–12 / 13+), dependencies (0–1 / 2–3 / 4+), state transitions (none / 2 states / several); 0–1 simple, 2–3 medium, 4–6 complex; at least 2 modules per level |
| 2026-10-30 | Limits | Token valid 12 hours; 5 failed logins lock the account for 15 minutes; passwords 8–128 characters; page size default 20, maximum 100; purchase orders 1–50 lines, 1–100 copies per line; search correct on 100,000 books and 200,000 copies |
| 2026-10-30 | Password rule | Passwords contain at least one letter and at least one digit (in addition to 8–128 characters), as in LIB-AUTH-02 |
| 2026-10-30 | Level thresholds | Calibrated before generation: rules 0–9 / 10–13 / 14+, dependencies 0–2 / 3–5 / 6+ (the first thresholds gave only 1 simple module); common requirements (LIB-TECH, COM, IF) count for no module. Result: 2 simple, 5 medium, 7 complex |
| 2026-10-30 | Review decisions | Cross-module dependency table moved out of the requirements; data-dependent checks return 409 with specific codes; borrowing any copy fulfils an active reservation of the same book; package versions pinned as verified in the team's Docker image |
| 2026-10-30 | Import of passive members | A `passive` member may have `open` imported loans (LIB-IO-06, v0.6); needed so that `MEMBER_PASSIVE` on renewal (LIB-LOAN-07) can be tested |
| 2026-10-31 | Copy branch while on loan | `current_branch_id` of an `on_loan` copy stays the branch it was lent from until return or report-lost (v0.7) |
| 2026-10-31 | Pilots | Week 3 generation pilot covers generation only; the refactoring pilot moves to Week 5, when the runners exist. Generation uses the default effort and thinking of the pinned Claude Code version |
| 2026-10-31 | Generation restart after the pilot | The pilot (steps 00–01, tag `pilot-steps-00-01`) showed that the model could not run any code: `python3` and compound commands were denied. Allow list extended (`python3`, `mkdir`, `cd`, `pip3 install -r requirements.txt`), effort fixed explicitly as `--effort high`, steps 00–01 generated again from an empty folder. Pilot results kept under `results/generation/pilot/`, its cost rows marked `pilot` |
| 2026-10-31 | Bash allowed in the container | The wider list failed the permission check (`mkdir -p x && cd x && python3 …` denied; the model then gave up on Bash). `--allowedTools` is now `Read Write Edit Glob Grep Bash` with `dontAsk`: argument patterns are fragile and add nothing, since `python` can already do anything. The boundary is the container (only the working copy, removed after each step). The network stays open for the API; the tests are never in the container and no prompt or `REQUIREMENTS.md` names the repository |
| 2026-10-31 | Generation pushed to main | Steps run without pausing and are pushed directly to `main`; the ruleset is disabled only for the generation and re-enabled after `v0-ai-baseline`. Reviews by commit range in groups 00–01, 02–04, 05–07, 08–09 (comments on #44 / #45). Stop conditions unchanged |

## Consequences

- `README.md`, `approaches.md`, `metrics.md`, `testing.md`, `smell-catalog.md`, `dataset/README.md` and `scripts/README.md` were updated.
- Tests attach to the REST API and a fixed service interface, because internal code may change during refactoring.
- Pro usage limits (5-hour and weekly) are not published. Two pilots: the generation pilot (Week 3, steps 0–1, about 5,000 lines) checks the generation command, the tests and the cost log; the refactoring pilot (Week 5) measures usage per run before the number of repetitions is fixed.
- Changes after Fatima's review (29 October): tools per approach, clean environment, model check, rubric sampling by requirement, coverage target on the full suite, integration-error rule, four additional business rules, corrected statements on thinking, `cast` and the JSON output.
- Compatibility of the measurement tools (PyExamine, DPy, mutmut, memray) with Python 3.14 is not yet verified.
- Classifying modules instead of separate tasks, and reporting equivalent cost instead of API cost, were confirmed by the instructor on 31 October 2026 (#11).
- Week 3 task files prepared before 29 October (separate simple/medium tasks, API script) are void.
