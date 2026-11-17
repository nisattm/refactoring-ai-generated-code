# Code Quality Analyzer

The analyzer measures the Python code of the generated LMS (`lms/`) with the tools of [`metrics.md`](metrics.md) and writes the results as CSV and JSON files. `compare.py` compares two such results and applies the success rule. Every decision behind it (what is measured, thresholds, success) is in [`decisions/003`](decisions/003-analyzer-and-success-rule.md); this page explains how to use the scripts and what the output files contain. If this page and the ADR disagree, the ADR is right; change the ADR first.

| Script | Job |
| --- | --- |
| `scripts/analyze.py` | Measures one code folder; writes the result files |
| `scripts/compare.py` | Compares two results (and two test results); decides `round_accepted` and `run_successful` |
| `scripts/run_tests.py` | Runs the feedback and held-out tests; writes `tests.csv` per case |
| `scripts/measure_baseline.sh` | Whole baseline measurement: analyzer, tests, repetitions, flaky list, coverage |

Everything runs in the Docker image `refactoring-env` ([`environment.md`](environment.md)) with `--network none`. The analyzer needs Python 3.14 and the tools of the image; do not run it on the host.

## Quick start

All commands run in the image, in the repository folder (Git Bash on Windows: `MSYS_NO_PATHCONV=1` and `$(pwd -W)`):

```bash
docker run --rm --network none -v "$PWD:/work" -w /work refactoring-env \
  python scripts/analyze.py --code dataset/lms/generated --out results/baseline/trial/my-run --label my-run --with-secondary
```

`--code` is the folder that **contains** `lms/` (not `lms/` itself). The run takes about 40 s on the full code. The analyzer copies `lms/` into a clean neutral folder before measuring (D1), so configuration files of the generated project cannot influence a tool, and it never writes into the code folder.

Compare a refactored result with the starting result:

```bash
python scripts/compare.py --before results/baseline/final/v0-ai-baseline --after <analysis folder> --out <compare folder> \
  --tests-before results/baseline/final/v0-ai-baseline/tests.csv --tests-after <tests.csv of the new code> \
  --before-code <folder with the starting lms/> --after-code <folder with the refactored lms/>
```

## What the analyzer measures

- **Five primary metrics** (decide success): mean CC (Radon), mean Cognitive Complexity (complexipy), Maintainability Index weighted by SLOC (Radon), duplication % (jscpd) and the total smell count of the frozen list (D4–D8). Thresholds of "changed" are in D20.
- **Frozen smell list:** S01, S02, S03, S07, S09, S10, S11, S18, S19, S20, S21, S22, S23, each with exactly one tool or rule (D8). The same smell at the same place counts once (D9). The list is stored in every result (`frozen_smell_list`).
- **Secondary** (reported, never decide): class metrics, module and level views, Pylint information messages, Vulture, PyExamine, suppression comments, layer violations, the six static cases (D22), coverage (D26).
- **Module mapping and levels:** `scripts/analyzer/modules.csv` and `api_routers.csv` (D2, D3). Modules that are not generated yet (15–29 in the pilot) are reported as "not generated"; they get no mean and cause no crash.

`--with-secondary` adds the secondary tools (Vulture, PyExamine) and `modules_router.csv`. The baseline and every comparison use it.

## Result folder

`results/baseline/<trial|final>/<label>/` ([D23](decisions/003-analyzer-and-success-rule.md)). Every CSV row has `run_label` and `schema_version`; the columns are defined in `scripts/analyzer/schema.json` (column, type, unit, definition). CSV: UTF-8, comma, decimal point, numbers with four decimals, rows sorted. Two measurements of the same code give identical files; only the time fields in `summary.json` differ (D14).

| File | Content |
| --- | --- |
| `summary.json` | The contract for the runners (below) |
| `project.csv`, `levels.csv`, `modules.csv`, `modules_router.csv` | Project, level and module values (levels are means of the module values) |
| `smells.csv` | Every finding of the frozen list; `counted` is 1 once per (smell, file, unit) |
| `functions.csv`, `classes.csv`, `files.csv` | One row per function or method, class (with class kind and metrics) and file |
| `duplication.csv` | One row per clone found by jscpd |
| `architecture.csv` | Module dependencies, fan-in and fan-out, import cycles |
| `metrics_long.csv` | One value per unit and metric, for charts |
| `static_cases.csv` | The six static cases of D22 (`passed`, `failed`, `partial`) |
| `vulture.csv`, `pyexamine.csv` | Secondary tool findings, sorted and normalized |
| `tool_versions.json` | Versions of every tool |

`raw/` (raw tool output and logs) is not committed.

### `summary.json`

Keys the runners and `compare.py` rely on:

| Key | Content |
| --- | --- |
| `primary` | `mean_cc`, `mean_cognitive`, `mi_weighted`, `duplication_pct`, `smell_count`; `null` if a metric cannot be computed |
| `smell_counts` | Count per S-ID (counted rows of `smells.csv`) |
| `secondary` | Counts and views: units, classes by kind, suppressions, layer violations, `static_cases`, `sloc`, the second duplication value (`duplication_pct_union`), `module_stats_valid`, and more |
| `frozen_smell_list` | The list used; `compare.py` refuses two results with different lists |
| `code_sha`, `code_dirty`, `code_content_hash` | The measured code: commit, uncommitted changes, SHA-256 of the `lms/` files (D24) |
| `analyzer_sha`, `analyzer_dirty`, `image_id`, `tool_versions`, `schema_version` | The measuring side (D24) |
| `started_at`, `duration_s`, `tool_seconds` | Time fields (the only ones that differ between two runs) |
| `failures` | Problems of **primary** tools; non-empty means exit code 4 |
| `secondary_failures` | Problems of secondary tools (for example PyExamine crashes); do not change the exit code (ADR 003 addendum, point 3) |

For code that is not a git checkout (an export) give `--code-sha`.

### Two values for duplication

`duplication_pct` is the percentage jscpd reports: the lines of each clone counted once, divided by the lines of the files jscpd read. That is the primary metric. Module and level values need a value per file, so they use the union of the clone line ranges over all copies; the project-level union value is `secondary.duplication_pct_union`. Compare each only with itself (ADR 003 addendum, point 1).

## Exit codes

| Script | 0 | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- | --- |
| `analyze.py` | done | – | usage error | – | a primary tool did not run or its expected file set does not match (D13); the files are written, `summary.json` says what failed |
| `compare.py` | compared | – | usage error | incompatible inputs (other schema version or other frozen list) | missing data (a file or a baseline value) |
| `run_tests.py` | all passed | failures, errors or missing cases | usage problem | test files changed (invalid run) | a set timed out (invalid run) |
| `measure_baseline.sh` | done | – | usage error | `.run.lock` still held after the waiting time | the measurement is invalid (`baseline.json` says why) |

A result with exit code 4 is not a measurement; do not compare it.

## Comparing: `compare.py`

Inputs: `--before` and `--after` (analysis folders); optional `--tests-before`, `--tests-after`, `--tests-after-repeat` (twice), `--flaky`, `--previous-best`, `--before-code`, `--after-code`. Output in `--out`: `compare.json` and `compare.csv` (`kind, scope, metric, before, after, delta, threshold, status`).

Per primary metric the status is `improved`, `same`, `worse`, `invalid` (null after refactoring) or `not comparable` (null before). Values are rounded to four decimals and compared with the thresholds of D20.

Two **separate decisions**, each `{value, criteria, reasons}`:

| Decision | Criteria |
| --- | --- |
| `round_accepted` (one Iterative round) | all primary metrics measured; no test regression; no primary metric worse than the **previous best** (`--previous-best`, else the start); OpenAPI schema unchanged |
| `run_successful` (the success definition) | all primary metrics measured; no regression and both test sets run; no primary metric worse than the start; at least one improved; OpenAPI schema unchanged |

`value` is `false` as soon as one criterion fails, `true` only if every criterion was checked and passed, and `null` if one could not be checked (for example no `--before-code`, or the tests were not compared). `reasons` lists every criterion that is not `true`. A runner must treat `null` as "not accepted, not decided".

Tests: a case that passed at the start and is `failed`, `error`, `skipped` or `missing` afterwards is a regression, unless it passes in one of the two repetitions given with `--tests-after-repeat` (D18). Without two repetitions the regression is counted but `compare.json` warns that it is not confirmed. Cases in `--flaky` are left out. The OpenAPI hash (D21) and the change size (`git diff --no-index`) need `--before-code` and `--after-code`. `warnings` holds the SLOC drop above 15 %, invalid module statistics and unconfirmed regressions; `inventory` lists functions and classes removed and added by name.

## Tests: `run_tests.py`

```bash
python scripts/run_tests.py --code <folder with lms/> [--set feedback|heldout|both] [--out DIR] [--baseline hashes.json] [--timeout 7200] [--cases ids.txt] [--coverage]
```

Hashes the test files, runs each set in its own pytest process with the code on `PYTHONPATH`, hashes again, and writes `<out>/<set>.json`, `<out>/run.json` and `<out>/tests.csv`. `tests.csv` has one row per case: `case, module, table, type, set, result` with `result` one of `passed`, `failed`, `error`, `skipped`, `missing` (a case of the case tables that pytest did not report). A changed test file or a set that runs longer than the timeout makes the run invalid (exit 3 or 4). `--cases FILE` runs only the listed case IDs (the repetitions of failing tests); `--coverage` runs under `coverage --branch --source=lms`.

## Baseline measurement: `measure_baseline.sh`

```bash
scripts/measure_baseline.sh --label NAME (--code DIR | --code-ref GIT_REF) [--out DIR] [--modules 1-14] [--second-full-run] [--skip-analysis] [--skip-coverage] [--timeout SECONDS] [--background] [--wait SECONDS]
```

`--out` defaults to `results/baseline/trial/NAME`. `--code-ref` measures `dataset/lms/generated` as it is at that git ref (exported with `git archive`; the SHA goes into the result), for example the tag `v0-ai-baseline`. `--background` starts the run detached and prints the process ID; the log is `<out>/raw/measure.log`. `scripts/measure_baseline.sh --help` lists all options.

**Run lock.** The script takes `.run.lock` in the repository root (who, what, start time, process ID) before it starts, waits while another run holds it (exit code 3 after `--wait`, default 6 hours) and removes it at the end, also after an error or an interruption ([`environment.md`](environment.md#6-rules-for-resource-measurements)).

Steps (`scripts/analyzer/baseline.py`, which the script starts in the image):

1. Analyzer with the secondary tools.
2. One full test run (feedback and held-out). With `--second-full-run` a second one (the final baseline, D18).
3. The cases that failed in a full run are run twice more with `--cases`.
4. `flaky.txt`: cases with a mixed result over all these runs. They are left out of later comparisons.
5. A separate coverage run (`lms/` only, branch coverage), written to `coverage_summary.json`. Reported without a target; it never decides success (D19, D26).
6. `baseline.json`: steps, times, environment, test counts, and every problem that makes the measurement invalid.

Additional files of a baseline result:

| File | Content |
| --- | --- |
| `tests.csv`, `tests_run.json` | First full run: one row per case; counts per set |
| `tests_run2.csv`, `tests_run2.json` | Second full run (only with `--second-full-run`) |
| `tests_repeat1.csv`, `tests_repeat2.csv` | The two repetitions of the failing cases (only if some failed) |
| `flaky.txt` | Flaky case IDs, one per line (lines with `#` are comments) |
| `coverage_summary.json` | Statements and branches covered, per package |
| `baseline.json` | Steps, durations, environment, `problems` |

`--modules 1-14` restricts the tests to the test files of these modules, for code that does not have all modules (the pilot); the web interface tests are never part of it.

## Storage of results

- **Final baseline** (`results/baseline/final/v0-ai-baseline/`, measured on the `v0-ai-baseline` tag): everything except `raw/` is committed.
- **Trial and experiment results:** the unit-level detail files (`functions.csv`, `classes.csv`, `files.csv`, `metrics_long.csv`, `duplication.csv`, `pyexamine.csv`) are not committed (`.gitignore`). The summary, module, level, smell and test files are. The details can be rebuilt only while the measured code is kept; the start code is the `v0-ai-baseline` tag, the storage of the code of experiments is decided in Week 5 (ADR 003 addendum, point 6).
- All CSV and `summary.json` files under `results/` are marked `linguist-generated` in `.gitattributes`, so pull requests collapse them.

## For the Week 5 runners

A runner may rely on: `summary.json` (`primary`, `smell_counts`, `code_sha`, `failures`), `tests.csv`, `flaky.txt`, `compare.json` (`round_accepted.value`, `run_successful.value`, `reasons`, `primary`, `warnings`) and the exit codes above. A runner must record the commit and content hash of the code it measured, treat exit code 4 as "no measurement" and `value: null` as "not decided", and run the analyzer and the tests under `.run.lock` ([`environment.md`](environment.md#6-rules-for-resource-measurements)). It must not edit the test folders (the hash check makes such a run invalid).

## Tests of the analyzer

```bash
docker run --rm --network none -v "$PWD:/work" -w /work refactoring-env python -m pytest scripts/tests -q
```

The tests use two small projects (`scripts/tests/fixtures/analyzer/sample` and `poscontrol`); the positive control is a small project written to trigger the rules of the frozen list, to show that each rule fires. A new rule needs a fixture that triggers it. The full suite also runs a few real test files, so it takes a few minutes; take `.run.lock` first.

## Limits

- PyExamine exits 0 although a detector crashes on some files; the analyzer reports them in `secondary_failures`, and the PyExamine numbers are incomplete for those files.
- jscpd counts tokens its own way; the estimate of the analyzer can differ by tens of tokens, so files of 40–60 estimated tokens only produce a warning (D13).
- T-TECH-10-a is `partial`: the `ORDER BY` half is not checked by a script (ADR 003 addendum, point 4).
- Coverage is a separate run and has no target in Week 4 (D26); characterization tests are tracked in issue #115.
- In the coverage run of the final baseline the UI tests T-UIDIG-03-a and T-UIROOM-07-a failed, although both passed in the two full runs; the cause is not verified (timing under coverage is likely), so for Week 5 treat these two cases as sensitive to run conditions and check them first if they fail in an experiment.
