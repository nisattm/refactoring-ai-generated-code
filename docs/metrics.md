# Metrics

Extended after the instructor's feedback (26 October 2026) and completed on 29 October 2026: thresholds, success definition, aggregation levels, statistics, architecture and change-size metrics, performance workloads and cost without API billing. Every metric is measured before and after refactoring with the same tool and version.

The subject code is one Library Management System (LMS), refactored as a whole ([`decisions/002`](decisions/002-single-lms-claude-code.md)). Metrics are computed on the whole project and also reported per module and per complexity level.

**Scope (16 November 2026):** only the Python code of the application package `lms/`. The web interface (`web/`, HTML, CSS and JavaScript) and the tests the model wrote (`tests/`) are excluded from every metric.

**Tool status (17 November 2026):** the tools were checked on the Docker image (Python 3.14.10; [`../results/baseline/trial/tool-check.md`](../results/baseline/trial/tool-check.md)). The decisions on what is measured, with which tool and how the five primary metrics are computed are in [`decisions/003`](decisions/003-analyzer-and-success-rule.md). PyExamine runs but is **secondary** (it crashes silently on 11 files and its output order changes); DPy is not in the image and is not used. A metric whose tool does not run is reported as missing (`null`), never silently replaced by another tool.

## 1. Code quality: five layers

| Layer | Metric | What it shows | Tool |
| --- | --- | --- | --- |
| A. Size | LOC, SLOC, comment ratio; number of functions and classes; function length | Size of the code; whether refactoring bloated it | Radon (raw) |
| B. Complexity | Cyclomatic Complexity (CC) | Number of independent paths | Radon (cc) |
| | Cognitive Complexity | Mental effort for a reader; penalizes nesting more | complexipy |
| | Maximum nesting depth | Nested if/for levels | Pylint R1702 (smell S10) |
| | Halstead volume, difficulty, effort | Operator/operand density | Radon (hal) |
| | Maintainability Index (MI) | Composite maintainability indicator; project and module value is the mean **weighted by SLOC** (the plain mean is secondary) | Radon (mi) |
| C. Design | WMC, NOM (methods per class) | Class size and responsibility load | Our own AST script; primary class statistics use `plain` classes only (not ORM, Pydantic or enum classes) |
| | CBO, fan-in / fan-out | Coupling between classes | Own AST script |
| | LCOM (LCOM4) | Cohesion inside a class; low cohesion means a class does several jobs | Own AST script |
| | RFC, DIT, NOC | Methods a class can trigger; inheritance depth; number of subclasses | Own AST script |
| | Design and architecture smells | God Class (S02), cyclic dependency (S18); the others (Feature Envy, deficient encapsulation, …) are not measured | Own AST script / import graph; PyExamine as a secondary source |
| D. Duplication | Duplicated code (%), number of clone blocks | Copy-paste logic | jscpd (`--min-lines 5 --min-tokens 50`) |
| E. Logic | Number of logic smells ([`smell-catalog.md`](smell-catalog.md#logic-smells)) | Code that compiles but is redundant, contradictory or in the wrong place | Ruff and Pylint (Vulture secondary) |
| | Design and logic rubric score (1–5) | Design and logic quality the tools cannot capture | Human raters (+ optional LLM judge) |

**Why these tools.** PyExamine (Shivashankar & Martini, MSR 2025) uses 49 metrics at code, structural and architectural level for Python; recall in its evaluation is 0.914 (code), 0.893 (structural) and 0.806 (architectural) (Table V). DPy (Boloori & Sharma, MSR 2025 Data and Tool Showcase) detects 8 design and 11 implementation smells. In the tool check PyExamine 0.2.3 ran on Python 3.14.10 but exits with code 0 although one detector crashes on 11 files, and its output order is not stable; DPy is not in the image. Both therefore stay out of the primary metrics: class metrics and the design smells S02 and S18 come from our own AST script, and PyExamine is reported as a secondary source ([`decisions/003`](decisions/003-analyzer-and-success-rule.md), D10, D12).

### Additional metrics (added 29 October)

| Layer | Metric | What it shows | Tool |
| --- | --- | --- | --- |
| F. Architecture | Module dependency graph; number of cycles between modules; layer violations (e.g. API layer importing the database layer directly) | Whether the project is well structured as a whole; relevant because the whole project is refactored at once | Our own import graph (cycles: S18; layer violations: three rules in [`decisions/003`](decisions/003-analyzer-and-success-rule.md), **secondary**, not in the smell total); Pylint R0401 as a cross-check; PyExamine `--type architectural` as a secondary source |
| G. Change size | Lines added/removed, files changed, files added/removed | How much code a refactoring touched; context for cost and risk | `git diff --stat` between baseline and result |

### Design and logic rubric

Some problems do not cause a compile error and still pass the tests, but the code is illogical. Each sampled unit of the starting code and of each refactoring result is scored from 1 to 5:

| Dimension | 1 (poor) | 5 (good) |
| --- | --- | --- |
| Responsibility distribution | Business rule in the wrong class; one class does everything | Each class and function has one clear job |
| Redundant / duplicated logic | Same check in several places; unnecessary conditions and conversions | Each rule lives in one place |
| Appropriate abstraction | No abstraction, or needless layers | As much abstraction as needed |
| Error handling | Errors swallowed or handled inconsistently | Errors handled consistently and meaningfully |
| Readability and naming | Meaningless names; flow hard to follow | Names express intent; flow easy to follow |

- **Sampling by requirement (added 29 October).** About 40,000 lines cannot be scored by hand. Refactoring may split, merge or rename code, so units are sampled by **behavior**, not by name: from each of the 14 modules, 3 requirement IDs are drawn at random with a fixed, recorded seed. For each requirement, the scored code is the application code executed by that requirement's tests (found with coverage.py dynamic contexts), in the baseline and in every result. This gives a mapping that survives refactoring.
- Two team members score independently and blind (they do not know which approach produced the code); agreement is reported with Cohen's kappa.
- Optional LLM judge with the same rubric. In Wang et al. (2025), LLM-as-a-judge correlated with human scores at 68.51 (Pearson) for code generation (Abstract), so it complements but does not replace human raters. Claude judging Claude's own output may be biased; a different model should be considered.

## 2. Thresholds

Smell counts depend on thresholds, and tools disagree: Long Method is 30 lines in one GitHub detector and 45 lines in the PyExamine example configuration ([`smell-catalog.md`](smell-catalog.md#survey-of-the-github-code-smell-topic)). We therefore fix one set. Values are the tools' documented defaults as we understand them; the final set is recorded in [`decisions/003`](decisions/003-analyzer-and-success-rule.md) and every result stores the tool versions. Thresholds do not change during the study. Only the rows marked "smell" enter the total smell count (the frozen list S01–S23 of the ADR); the others are reported as information.

| Measure | Threshold / bands | Tool rule |
| --- | --- | --- |
| Cyclomatic Complexity | Radon ranks A 1–5, B 6–10, C 11–20, D 21–30, E 31–40, F 41+; "high" = rank C or worse | Radon |
| Cognitive Complexity | 15 per function | complexipy |
| Parameters per function | 5 (smell S03) | Ruff PLR0913 |
| Statements per function | 50 (information, secondary) | Ruff PLR0915 |
| Branches per function | 12 (information, secondary) | Ruff PLR0912 |
| Boolean expressions in one condition | 5 (smell S09; needs `--preview`, run separately) | Ruff PLR0916 |
| Nested blocks | 5 (smell S10) | Pylint R1702 |
| Long Method | 45 lines, docstring excluded (smell S01) | Own AST script |
| Large Class | 15 methods, `plain` classes only (smell S02) | Own AST script |
| Duplication | `--min-lines 5 --min-tokens 50`, written explicitly | jscpd |
| Magic number | Only numbers in comparisons, other than the rule's allowed values (smell S11) | Ruff PLR2004 |

## 3. Success definition

"At least one metric improves" is too weak with more than 20 metrics, so metrics are split into primary and secondary before the experiments.

- **Primary metrics (five):** mean CC (Radon, 1,787 units on the starting code), mean Cognitive Complexity (complexipy, 1,771 units; nested functions are part of their parent), Maintainability Index (mean of the files **weighted by SLOC**), duplicated code (%, jscpd) and total smell count (frozen list of S-IDs in [`decisions/003`](decisions/003-analyzer-and-success-rule.md); each smell has one tool or rule).
- **Secondary metrics:** all other metrics in this document (including the architecture metrics, PyExamine and Vulture results and the suppression-comment counts); reported, but not used for the success decision.
- **"Changed" thresholds** (values rounded to 4 decimals, a difference below the threshold is "same"): mean CC 0.01 · mean Cognitive 0.01 · MI 0.1 · duplication 0.05 percentage points · total smell count 1. A primary metric that is `null` after refactoring makes the run **invalid**.
- **Successful refactoring (relative to the starting code):** **no test that passes at the start fails afterwards** (feedback and held-out sets separately), **and** no primary metric gets worse, **and** at least one primary metric improves. Tests that already fail at the start (for example T-INV-20-a, a code error) are reported separately; flaky tests are left out of the comparison; a test counts as a regression only if it fails in two repetitions ([`testing.md`](testing.md#success-relative-to-the-starting-code)).
- **Acceptance of a result:** a changed OpenAPI schema, a missing test case, a timed-out test set or a `null` primary metric means the result is never accepted; a SLOC drop above 15 % is only a warning ([`approaches.md`](approaches.md#common-rules)).
- A result with regressions is a failure regardless of metrics.

## 4. Aggregation and reporting levels

| Level | How values are aggregated |
| --- | --- |
| Function / method | Raw values (CC, Cognitive Complexity, length, parameters) |
| Class | Raw design values (WMC, NOM, CBO, LCOM, RFC, DIT, NOC) |
| Module (29 LMS modules) | Mean, maximum and share of units above the threshold; smell count per KSLOC; duplication %. Files are assigned to modules by the explicit file `scripts/analyzer/modules.csv` (path prefix; `api/` is entirely module 14); a module without code (`printing/` while it does not exist) is "not generated" and gets no mean. New folders after refactoring are "unassigned"; above 5 % SLOC the module-level statistics of that run are invalid |
| Complexity level (simple / medium / complex) | **Mean of the module values** of that level (primary); pooled units are secondary. The complex level is also split into modules 2–7 and 13 against 15–29 as a sensitivity row; the simple level (2 modules) is descriptive only |
| Project | Same as module, over the whole code; architecture metrics; change size |

Level labels of the modules are defined in [`../dataset/README.md`](../dataset/README.md): 2 simple, 5 medium and 22 complex modules. Because the project is refactored as a whole, module and level results are a breakdown of one refactoring, not separate refactorings. Results are written to `results/baseline/<trial|final>/<label>/` ([`decisions/003`](decisions/003-analyzer-and-success-rule.md), D23–D25).

Test results are additionally reported per case type (Normal, Boundary, Error, Property, Scenario), taken from the `Type` column of the case tables ([`../dataset/lms/tests/README.md`](../dataset/lms/tests/README.md)). This complements, not replaces, the module levels. Common requirements (LIB-TECH, LIB-COM, LIB-IF) belong to no module; their tests are in the Core test files and are reported as "common".

## 5. Statistical analysis

- **Unit of analysis:** one run = one approach applied once to the same baseline. The number of runs per approach is set after the pilot, because Claude Code Pro usage limits are not published (see [`decisions/002`](decisions/002-single-lms-claude-code.md)).
- **Comparing the three approaches:** Kruskal-Wallis test per metric; if significant, pairwise Mann-Whitney U tests with Holm correction.
- **Effect size:** Cliff's delta.
- **Uncertainty:** 95% bootstrap confidence intervals of the median.
- **Before vs. after within an approach:** Wilcoxon signed-rank test on module-level values (baseline vs. result).
- **Quality–cost trade-off (Week 8):** primary metric change plotted against tokens and time per successful refactoring.
- **Limitation:** with one project, the sample size per approach equals the number of runs. With few runs, tests have little power, so effect sizes and descriptive results are reported first. Module-level values are not independent observations (modules depend on each other and are refactored together); this is stated as a limitation.

## 6. Functional correctness

| Metric | Tool |
| --- | --- |
| Share of passing tests (feedback set and held-out set separately) | pytest |
| Successful refactoring (Section 3) | pytest + analyzer |
| Branch coverage of the test suite (`lms/` only, separate run, reported without a target; never part of the success decision) | coverage.py |
| Mutation score of the test suite (on sampled modules, see [`testing.md`](testing.md)) | mutmut (Linux / WSL only) |

## 7. Resource consumption of the code

| Metric | Definition | Tool |
| --- | --- | --- |
| Wall-clock time | End-to-end run time of a workload | pyperf; `time.perf_counter` |
| CPU time | User + system CPU time | psutil (`cpu_times`); `time.process_time` |
| Peak RAM (peak RSS) | Highest physical memory used by the process | psutil; `resource.getrusage` (`ru_maxrss`) on Linux |
| Python heap peak | Highest memory allocated by Python objects | tracemalloc |
| Allocations | Number and size of allocations; leaks | memray (Linux/macOS only); pytest-memray |
| Energy (optional) | Estimated energy consumption | CodeCarbon |

### Workloads (added 29 October)

Each workload runs against the service layer (and once through the REST API for end-to-end timing) with fixed, generated input data in three sizes. Inputs are loaded with the LMS import function (module 13) and are identical before and after refactoring. The workloads cover the core modules 5, 7, 9 and 10 on purpose; the modules added in November (15–29) have no resource workload.

| ID | Workload | Sizes (books) | Mainly stresses |
| --- | --- | --- | --- |
| W1 | Search with filters, sorting and pagination | 100 / 10,000 / 100,000 | Time, RAM (module 9) |
| W2 | Monthly summary and most-borrowed report | 100 / 10,000 / 100,000 | CPU, memory (module 10) |
| W3 | 1,000 borrow–return cycles including late returns and fines | 100 / 10,000 / 100,000 | Time, allocations (modules 5, 7) |

Members, copies and loans are generated in proportion to the number of books; the generator, its seed and the proportions are stored in `dataset/lms/inputs/`.

### Resource measurement protocol

- **Environment:** the same machine, the fixed Python version, inside a Linux Docker container. Required anyway because memray and mutmut do not run natively on Windows. CPU and RAM of the machine are recorded.
- **Database:** SQLite file on the container's local disk, recreated from the same input before each measurement.
- **Repetition:** each measurement runs in a fresh subprocess, after warm-up runs, at least 10 times; median and interquartile range are reported.
- **Separation:** timing/CPU runs and memory profiling runs are separate, because profilers (memray, tracemalloc) distort timing.

## 8. Cost of the refactoring (LLM side)

We use Claude Code with a Claude Pro subscription, not the API ([`decisions/002`](decisions/002-single-lms-claude-code.md)). The subscription is a flat monthly fee, so a dollar amount per run is not billed. Cost is therefore measured as resource use:

| Metric | Source |
| --- | --- |
| Input, output, cache-read and cache-write tokens, per model | Claude Code `/usage` session block, which reports token usage by model |
| API time and wall-clock time | Same |
| Number of turns, model calls and subagent runs | Session log and our runner script |
| Plan usage (share of the 5-hour window used) | `/usage` plan usage bars; the documentation describes these figures as approximate |
| **Equivalent cost (USD)** | The cost figure Claude Code computes locally from token counts at list price. The documentation states it is an estimate and not relevant for billing on Pro. Reported as "estimated cost if run through the API". |

- **Collection:** the JSON result of each run (`claude -p --output-format json`), which contains `total_cost_usd`, a per-model cost breakdown, usage and `session_id`; Claude Code describes these cost figures as client-side estimates. With `--resume`, the figure is the conversation's running total, so per-round values are taken as differences. OpenTelemetry export is the alternative.
- **Thinking and effort fixed:** on Sonnet 5.5 thinking cannot be turned off completely (`disabled` is rejected; the lowest setting is `between_tools`). Thinking tokens count as output tokens, so the thinking setting and the effort level are the same in all three approaches and recorded.
- **Subagents included:** Multi-Agent token counts include the orchestrator and all subagents (the prompt-cache line of `/usage` covers the main conversation only, so the JSON result is used instead).
- **Model check:** a run whose per-model breakdown shows any model other than Claude Sonnet 5.5 is invalid.
- **Reported per run and per successful refactoring.**

Source: Claude Code documentation, "Manage costs effectively", https://code.claude.com/docs/en/costs (accessed 29 October 2026).

## Sources

- K. Shivashankar, A. Martini. PyExamine: A Comprehensive, Un-Opinionated Smell Detection Tool for Python. MSR 2025. arXiv:2501.18327
- A. Boloori, T. Sharma. DPy: Code Smells Detection Tool for Python. MSR 2025 Data and Tool Showcase Track
- R. Wang et al. Can LLMs Replace Human Evaluators? An Empirical Study of LLM-as-a-Judge in Software Engineering. 2025. doi:10.1145/3728963. arXiv:2502.06193
- Anthropic. Claude Code documentation: Manage costs effectively. https://code.claude.com/docs/en/costs
- Anthropic. Claude Code documentation: Run Claude Code programmatically. https://code.claude.com/docs/en/headless
- Anthropic. What's new in Claude Sonnet 5.5. https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5
- PyExamine usage guide. https://python-smell.readthedocs.io/en/latest/usage.html
- Tool documentation: Radon, complexipy, Ruff, Pylint, Vulture, jscpd, pyperf, psutil, tracemalloc, memray, coverage.py, mutmut, CodeCarbon
