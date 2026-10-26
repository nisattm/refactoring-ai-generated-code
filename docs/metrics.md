# Metrics

Extended after the instructor's feedback (26 October 2026): more metrics, design and logic quality, and detailed resource usage. Every metric is measured before and after refactoring with the same tool and version. Thresholds are fixed in the metrics meeting and recorded in [`decisions/`](decisions/).

## 1. Code quality: five layers

| Layer | Metric | What it shows | Tool |
| --- | --- | --- | --- |
| A. Size | LOC, SLOC, comment ratio; number of functions and classes; function length | Size of the code; whether refactoring bloated it | Radon (raw) |
| B. Complexity | Cyclomatic Complexity (CC) | Number of independent paths | Radon (cc) |
| | Cognitive Complexity | Mental effort for a reader; penalizes nesting more | complexipy |
| | Maximum nesting depth | Nested if/for levels | PyExamine; Pylint R1702 |
| | Halstead volume, difficulty, effort | Operator/operand density | Radon (hal) |
| | Maintainability Index (MI) | Composite maintainability indicator | Radon (mi) |
| C. Design | WMC, NOM (methods per class) | Class size and responsibility load | PyExamine |
| | CBO, fan-in / fan-out | Coupling between classes | PyExamine |
| | LCOM | Cohesion inside a class; low cohesion means a class does several jobs | PyExamine |
| | RFC, DIT, NOC | Methods a class can trigger; inheritance depth; number of subclasses | PyExamine |
| | Design and architecture smells | God Class, Feature Envy, cyclic dependency, deficient encapsulation | PyExamine, DPy |
| D. Duplication | Duplicated code (%), number of clone blocks | Copy-paste logic | jscpd |
| E. Logic | Number of logic smells ([`smell-catalog.md`](smell-catalog.md#logic-smells)) | Code that compiles but is redundant, contradictory or in the wrong place | Ruff, Pylint, Vulture |
| | Design and logic rubric score (1–5) | Design and logic quality the tools cannot capture | Human raters (+ optional LLM judge) |

**Why these tools.** PyExamine (Shivashankar & Martini, MSR 2025) uses 49 metrics at code, structural and architectural level for Python; recall in its evaluation is 0.914 (code), 0.893 (structural) and 0.806 (architectural) (Table V). DPy (Boloori & Sharma, MSR 2025 Data and Tool Showcase) detects 8 design and 11 implementation smells. The example PyExamine configuration uses 45 lines for Long Method and 15 methods for Large Class.

### Design and logic rubric

Some problems do not cause a compile error and still pass the tests, but the code is illogical. Each starting program and each refactoring result is scored from 1 to 5:

| Dimension | 1 (poor) | 5 (good) |
| --- | --- | --- |
| Responsibility distribution | Business rule in the wrong class; one class does everything | Each class and function has one clear job |
| Redundant / duplicated logic | Same check in several places; unnecessary conditions and conversions | Each rule lives in one place |
| Appropriate abstraction | No abstraction, or needless layers | As much abstraction as needed |
| Error handling | Errors swallowed or handled inconsistently | Errors handled consistently and meaningfully |
| Readability and naming | Meaningless names; flow hard to follow | Names express intent; flow easy to follow |

- Two team members score independently and blind (they do not know which approach produced the code); agreement is reported with Cohen's kappa.
- Optional LLM judge with the same rubric. In Wang et al. (2025), LLM-as-a-judge correlated with human scores at 68.51 (Pearson) for code generation (Abstract), so it complements but does not replace human raters. Claude judging Claude's own output may be biased; a different model should be considered.

## 2. Functional correctness

| Metric | Tool |
| --- | --- |
| Share of passing tests (feedback set and held-out set separately) | pytest |
| Successful refactoring: all held-out tests pass and at least one quality metric improves | pytest + analyzer |
| Branch coverage of the test suite | coverage.py |
| Mutation score of the test suite | mutmut (Linux / WSL only) |

## 3. Resource consumption

| Metric | Definition | Tool |
| --- | --- | --- |
| Wall-clock time | End-to-end run time of the task | pyperf; `time.perf_counter` |
| CPU time | User + system CPU time | psutil (`cpu_times`); `time.process_time` |
| Peak RAM (peak RSS) | Highest physical memory used by the process | psutil; `resource.getrusage` (`ru_maxrss`) on Linux |
| Python heap peak | Highest memory allocated by Python objects | tracemalloc |
| Allocations | Number and size of allocations; leaks | memray (Linux/macOS only); pytest-memray |
| Energy (optional) | Estimated energy consumption | CodeCarbon |
| LLM side | Input/output tokens, USD, response time | Usage information in each API response; `time.perf_counter` |

### Resource measurement protocol

- **Environment:** the same machine, a fixed Python version, inside a Linux Docker container. Required anyway because memray and mutmut do not run natively on Windows. CPU and RAM of the machine are recorded.
- **Workload:** for each task the team defines fixed measurement inputs in three sizes (e.g. 100, 10,000 and 100,000 book records). The same inputs are used before and after refactoring.
- **Repetition:** each measurement runs in a fresh subprocess, after warm-up runs, at least 10 times; median and interquartile range are reported.
- **Separation:** timing/CPU runs and memory profiling runs are separate, because profilers (memray, tracemalloc) distort timing.

## Sources

- K. Shivashankar, A. Martini. PyExamine: A Comprehensive, Un-Opinionated Smell Detection Tool for Python. MSR 2025. arXiv:2501.18327
- A. Boloori, T. Sharma. DPy: Code Smells Detection Tool for Python. MSR 2025 Data and Tool Showcase Track
- R. Wang et al. Can LLMs Replace Human Evaluators? An Empirical Study of LLM-as-a-Judge in Software Engineering. 2025. doi:10.1145/3728963. arXiv:2502.06193
- Tool documentation: Radon, complexipy, Ruff, Pylint, Vulture, jscpd, pyperf, psutil, tracemalloc, memray, coverage.py, mutmut, CodeCarbon
