# 003 – Code Quality Analyzer, frozen smell list and success rule

**Date:** 2026-11-17
**Status:** Draft, waiting for approval by Nisa. After approval: Accepted.

## Context

Week 4 builds the Code Quality Analyzer and measures the starting code. The plan was fixed after five independent reviews and two discussion rounds; the PR 1 tool check ([`../../results/baseline/trial/tool-check.md`](../../results/baseline/trial/tool-check.md), PR #114) confirmed the tools on the Docker image (Python 3.14.10) and settled the open points marked "(PR 1)" below. The measured code is the Python package `lms/` of the generated LMS ([`002`](002-single-lms-claude-code.md)). The runners of Week 5 are written later in a separate session and depend on the file contracts (`summary.json`, `compare.json`) described in [`../analyzer.md`](../analyzer.md) (PR 8).

## Decision

### Scope and mapping

| ID | Decision |
| --- | --- |
| D1 | Only Python under `lms/` is measured. Excluded: `test_*.py`, `*_test.py`, `conftest.py`, `__pycache__` (and any `web/` or `tests/` folder inside the measured tree; in the generated project `web/` and `tests/` are siblings of `lms/`, so they are outside it anyway). The measurement runs on a clean copy of `lms/` in a neutral working folder, so that `pyproject.toml`, `setup.cfg`, `.pylintrc`, `ruff.toml`, `.gitignore` and `sitecustomize.py` of the project cannot influence a tool. |
| D2 | **Module mapping** is an explicit file, `scripts/analyzer/modules.csv` (path prefix → module number, name, level), following the package layout of the requirements, section 2.2. `api/` is entirely module 14; `lms/__init__.py` is module 1 (it holds the fixed service interface of requirements section 4, not Core code; noted in the file); `printing/` is module 29 and, while it does not exist, is reported as "not generated" (no mean is computed, no crash). Secondary view "module + its own router": `api/<package>.py` → the package's module (`calendar` → 1, `users` → 2, `transfers` → 11, `dataexchange` → 13); `api/reports.py` holds the router of module 10 and of modules 15–28 reports, so it is a separate row. After refactoring, files are mapped by the same prefix rules; new folders become **"unassigned"** and their SLOC share is reported. If it exceeds 5 %, the module-level statistics of that run are marked invalid. At the start it must be 0. |
| D3 | **Levels** come from the table in `dataset/README.md` (simple 2, medium 5, complex 22 modules). The level value is the **mean of the module values** (primary); pooled units are secondary. The complex level is also split into "2–7 and 13" and "15–29" as a sensitivity row. The simple level is descriptive only (2 modules). |

### Primary metrics (five)

| ID | Metric | Definition |
| --- | --- | --- |
| D4 | Mean CC | Radon `cc -j`. Only functions and methods; class rows and the second copy of each method are dropped. Nested functions are separate units: **1,787 units** on the starting code (1,771 + 16). *(PR 1)* |
| D5 | Mean Cognitive Complexity | complexipy 8.3.0 through its Python API `file_complexity()` (not the command line). **1,771 units**: complexipy adds nested functions to the enclosing function and makes no separate unit, while Radon does not add them to the parent. So the CC mean (1,787 units) and the Cognitive mean (1,771 units) are over different unit sets; both unit counts are reported in `summary.json`. Join key with Radon: (path, name, `line_end`); the 16 nested units have an empty cognitive value. *(PR 1)* |
| D6 | Maintainability Index | Radon `mi`, per file, averaged **weighted by SLOC**. The plain mean is secondary. (Starting code: weighted 38.15, plain 54.88; 43 files have MI = 100.) |
| D7 | Duplication % | jscpd 5.4.2, only `lms/**/*.py`, with `--min-lines 5 --min-tokens 50 --pattern '**/*.py' --no-gitignore` written explicitly; percentage of physical lines as jscpd reports it. Secondary: duplication relative to Radon SLOC and the absolute number of duplicated lines. |
| D8 | Total smell count | Only the frozen list below; each smell has exactly one tool or rule. |

### Frozen smell list (D8)

Ruff runs twice: the **stable run** (`ruff check --isolated --ignore-noqa --no-cache --output-format json --select PLR0913,F401,F841,SIM,PLR2004,S110,BLE001,B006,RET,ANN401,PGH003`) and the **preview run** (`--preview --select PLR0916`, only S09). `--preview` is never added to the stable run: it changes F401 itself (4 → 27 on the starting code, because the 24 model-registration imports of `core/db.py` count as unused) and may widen prefix selections. JSON output is required (the concise format prints rule names instead of codes under `--preview`). *(PR 1)*

| ID | Smell | Tool and rule | Starting code (`71e91e3`) |
| --- | --- | --- | --- |
| S01 | Long Method | own AST: function longer than 45 lines, docstring excluded | PR 3 |
| S02 | Large Class | own AST: more than 15 methods, `plain` classes only (D12) | PR 3 |
| S03 | Long Parameter List | Ruff PLR0913 (route handlers of FastAPI also reported separately) | 182 |
| S07 | Dead code | Ruff F401 + F841, stable run with `--ignore-noqa` | 4 + 0 |
| S09 | Complex Conditional | Ruff PLR0916 (preview run) + `SIM` prefix (stable run) | 1 + 1 |
| S10 | Deep Nesting | Pylint R1702 (needs no preview) | 0 |
| S11 | Magic Number | Ruff PLR2004 (only numbers in comparisons) | 42 |
| S18 | Cyclic dependency | own import graph: number of strongly connected components of size > 1 at file level; **primary value includes** the function-level model-registration imports of `core/db.py` (1 component of 25 files), the value without them (0) is reported next to it. Secondary: number of files inside cycles | 1 (0 without) |
| S19 | Swallowed or broad exception | Ruff S110 + BLE001 | 0 + 0 |
| S20 | Mutable default argument | Ruff B006 | 0 |
| S21 | Inconsistent or redundant return | Ruff `RET` prefix | 0 |
| S22 | Disallowed dependency | own script: imports (real `import` nodes by AST, not text search) outside the fixed library list of LIB-TECH-02, not the model's own `requirements.txt`. Allowed: standard library, `fastapi`, `starlette` and `pydantic_core` (sub-packages of FastAPI and Pydantic; one import each in the code), `uvicorn`, `pydantic`, `sqlalchemy`, `lms` | PR 3 |
| S23 | Bypassed type safety | Ruff ANN401 + PGH003 + count of `cast(` calls | 51 + 0 + 0 |

Not measured ("not measured", reported as such): S04, S05, S08, S12–S17. S06 is not in the total (duplication is primary). Rules that find nothing at the start stay in the list because the positive control (`scripts/tests/fixtures/analyzer/poscontrol/`) shows they fire. The list is part of every result (`frozen_smell_list` in `summary.json`); `compare.py` refuses to compare two results with different lists (exit code 3).

**Secondary, not in the total:** Pylint W0718, R1710, W0101 (information) and R0401 (cross-check of S18; 24 messages on the starting code, all paths of the same `core.db` cycle); Ruff F401 under `--preview` (27); Vulture at 80 % confidence (7 findings, all false alarms); PyExamine; suppression comments (D11); **architecture, layer violations** (below).

### Tool settings and reliability

| ID | Decision |
| --- | --- |
| D9 | The same smell at the same place is counted once. Key: (S-ID, file, enclosing function or class name). Each smell type is also reported with its own count. |
| D10 | **Ruff:** `--isolated --ignore-noqa --no-cache`, rules by `--select` on the command line, two runs as above. **Pylint:** our rcfile `scripts/analyzer/pylintrc`; only R1702, W0718, R1710, W0101 (+ R0401), `--persistent=n`, `-j 1`; Ruff's PLR1702 is not used. **Vulture:** secondary only (80 %). **PyExamine 0.2.3:** secondary only, explicit `--config`, run from the neutral folder (the command writes `code_analysis.log` into the working folder; the package is never imported). It exits 0 although `detect_middle_man` crashes on 11 `schemas.py` files; the analyzer reads stderr and reports every `Unexpected error analyzing <file>`. Its output order and the order of words inside descriptions change between runs, so it is sorted and normalized. |
| D11 | Suppression comments (`# noqa`, `# type: ignore`, `# pylint: disable`, `jscpd:ignore`) are counted (secondary), so that hiding a smell behind a comment is visible. Starting code: 38 `noqa`, 100 `type: ignore`. |
| D12 | **Class metrics by our own AST script:** WMC (sum of CC of the methods), NOM, CBO, LCOM4, RFC, DIT, NOC, fan-in and fan-out (module and class). Column **class kind**: `orm` (SQLAlchemy), `schema` (Pydantic), `enum`, `plain`. Primary class statistics and S02 use `plain` classes only; class counts per kind are secondary, so that changing a class kind to avoid a smell is visible. Pylint R0401 cross-checks the cycles. |
| D13 | For each tool the files processed must equal the files **expected for that tool**; otherwise exit code 4 naming tool and files. Expected sets (PR 1): Radon raw, mi, hal, complexipy, Ruff (`--show-files`): all `.py` files; Radon cc: files with at least one `def` or `class` (212 of 246); jscpd: files with at least 50 tokens, estimated with the Python tokenizer counting names, numbers, strings, operators and NEWLINE (215 of 246); Pylint: `modulesLinted` = files + 3 (empirical constant for this version); PyExamine: no crashed file; Vulture lists no files, so it is only checked for "ran". |
| D14 | Deterministic output: rows sorted, numbers in a fixed format (4 decimals), time stamps only in `summary.json`. Two measurements of the same code give byte-identical files (time fields excepted). Pylint's message order and PyExamine's row order are not stable, so all raw output is parsed and sorted. |
| D15 | **Unit identity:** (path, full name, kind, running number among units with the same name). The line number is not part of it. |
| D16 | **No fast mode:** all tools run on every measurement. On the starting code (29,019 SLOC): about 29 s for the primary tools, about 40 s including Vulture and PyExamine (Python 3.14.10, `--network none`). |

### Tests and success

| ID | Decision |
| --- | --- |
| D17 | Success is **relative to the starting code**: no test that passes at the start may fail after refactoring (feedback and held-out separately). Tests that already fail at the start (for example T-INV-20-a, a code error) are reported separately. |
| D18 | Unstable tests: one full run at the start; the remaining failures run twice more; a test with mixed results goes to the "flaky" list and is left out of the comparison. A second full start run is made at night in the background for the final baseline. After refactoring, a test that passed at the start and fails is run twice more; it counts as a regression only if it **fails in both repetitions**. |
| D19 | `run_tests.py` records the result of every case (passed, failed, error, skipped, missing); a case that passed at the start and does not appear in the result is a regression; a timeout (7,200 s per set) makes the run invalid. `tests.csv`: case, module, type (Normal, Error, …), set, result. Coverage runs separately and does not enter the success decision. |
| D20 | **"Changed" thresholds:** mean CC 0.01 · mean Cognitive 0.01 · MI 0.1 · duplication 0.05 percentage points · total smell count 1. Values are rounded to 4 decimals before comparison; a difference below the threshold is "same". Only a primary metric that is `null` after refactoring makes the run **invalid**. |
| D21 | **Gaming by deleting code:** `compare.py` computes the hash of the OpenAPI schema (`create_app(...).openapi()`, sorted keys), the difference of the function and class inventory and the SLOC drop. If the OpenAPI schema changes, the result is **not accepted**; a SLOC drop above 15 % is only a warning. |
| D22 | Six static cases that a script can check (LIB-TECH-02, -04, -06, -10, -11, -12) are recorded at the final baseline (PR 6). |
| D26 | Characterization tests and the 90 % branch-coverage target ([`../testing.md`](../testing.md#quality-gates)) are **not part of Week 4**. They are written after the final baseline measurement and before the first refactoring experiment, and tracked in a separate issue. Coverage is measured in PR 7 (branch coverage, `lms/` only, separate run) and reported **without a target**; it never enters the success decision (D19). |

### Records

| ID | Decision |
| --- | --- |
| D23 | One place for results: `results/baseline/<trial\|final>/<label>/`. `metrics/README.md`, the root `README.md` and `dataset/README.md` are corrected to it. |
| D24 | Every result stores the commit SHA of the measured code, the content hash (sorted SHA-256 of the `lms/` files), the commit of the analyzer, the image ID, the tool versions, the schema version and the run time. A tag name alone is not enough because the tag moves. |
| D25 | CSV: UTF-8, comma, decimal point; versioned schema `scripts/analyzer/schema.json` (column, type, unit, definition); every row has `run_label` and `schema_version`. A long-format `metrics_long.csv` (unit, metric, value) is written for charts. |

### Success and acceptance (used by `compare.py` and the approaches)

- **`run_successful`:** no regression (D17–D19), no primary metric worse, at least one improved (D20).
- **`round_accepted`** (Iterative rounds): no regression, no primary metric worse than the previous best, OpenAPI hash unchanged (D21).
- A result with a changed OpenAPI hash, a `null` primary metric or a timed-out test set is never accepted.

### Architecture (secondary)

Layer violation = number of import statements (found by AST) of three kinds. The sum is reported with the count per kind; it is **not** part of the smell total. (PR 1)

1. `lms/api/**` imports `lms.<package>.models` or `sqlalchemy*` (starting code: 34 + 17 = 51 statements in 21 of 33 API files). `get_session` from `lms.core.db` is dependency injection and does not count.
2. A domain package or `core` imports `lms.api` (starting code: 0).
3. `core` imports a domain package at module level (starting code: 0; the 24 function-level imports of `core/db.py` are counted in S18).

## Alternatives considered

- A fast mode without Pylint and PyExamine: rejected (D16); the full run takes about 40 s.
- One tool list per smell with several tools: rejected (D8/D9); counts would depend on which tools overlap.
- Mean cognitive complexity over the CC unit set: not possible, complexipy has no separate nested units (D5).
- Ruff `--preview` for the whole run: rejected because it moves S07 by 23 without any code quality change.

## Consequences

- `docs/metrics.md`, `approaches.md`, `testing.md` (success rule D17–D19; characterization tests and the 90 % target moved out of Week 4, D26), `environment.md`, `plan.md`, `smell-catalog.md`, `dataset/README.md` and `metrics/README.md` are updated to match (same PR, after approval of this draft), and `.gitignore` gets `.run.lock` and `results/baseline/**/raw/`.
- Until the characterization tests exist, the starting tests are the requirement, property and scenario tests only; for starting code that fails them, "no regression" (D17) is measured against what passes at the start.
- Open items checked later: detector behavior of PyExamine with `core` cycles and without `--config` (PR 6); number of FastAPI handlers among the 182 PLR0913 findings (PR 3); the default `--mode` of jscpd (PR 3).
- The Week 5 runners use `compare.py` and `summary.json` as described here; changing a decision above needs a new record.
