"""Runs the LMS test sets against a code folder, checks that the tests were not changed and records every case.

    python scripts/run_tests.py --code <folder with the lms package> [--set feedback|heldout|both]
                                [--tests dataset/lms/tests] [--out results/] [--baseline hashes.json]
                                [--timeout 7200] [--cases ids.txt] [--coverage]

Steps (docs/testing.md, dataset/lms/tests/README.md, docs/decisions/003, D17-D19):
1. Hash every test file (scripts/test_hashes.py); with --baseline, the hashes must also
   match a stored reference.
2. Run each set (``feedback/``, ``heldout/``) in its own pytest process, with the code
   folder on PYTHONPATH and the tests outside it. A set that runs longer than --timeout
   seconds (default 7,200) is stopped and the run is invalid.
3. Hash again. Any change makes the run invalid.
4. Write ``<out>/<set>.json`` (counts, failed case IDs, missing case IDs), ``<out>/run.json`` and
   ``<out>/tests.csv``: one row per case with its module, type, set and result
   (``passed``, ``failed``, ``error``, ``skipped`` or ``missing``). A case of the case tables
   (``<tests>/cases/*.md``) that does not appear in the pytest report is ``missing``.

``--cases FILE`` runs only the cases listed in FILE (one ID such as ``T-LOAN-05-a`` per line; used for the
repetition of failing tests). ``--coverage`` runs pytest under ``coverage run --branch --source=lms`` and keeps
``<out>/coverage-<set>.data`` (coverage never decides success).

Exit code: 0 all passed, 1 failures, errors or missing cases, 2 usage problem, 3 test files changed
(invalid run), 4 a set timed out (invalid run). Standard library only; pytest (and coverage) must be
installed in the environment that runs the tests.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_hashes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS = ROOT / "dataset" / "lms" / "tests"
SETS = ("feedback", "heldout")
DEFAULT_TIMEOUT = 7200

# Case table file -> module number of the LMS (dataset/README.md). ``core`` is split by requirement:
# LIB-TECH, LIB-COM and LIB-IF are "common" (no module), the rest is module 1.
TABLE_MODULES = {
    "core": "1", "auth": "2", "members": "3", "catalog": "4", "loans": "5", "reservations": "6", "fees": "7",
    "notifications": "8", "search": "9", "reports": "10", "branches": "11", "purchasing": "12", "audit_io": "13",
    "api": "14", "rooms": "15", "equipment": "16", "digital": "17", "ill": "18", "staff": "19", "events": "20",
    "courses": "21", "donations": "22", "preservation": "23", "inventory": "24", "suggestions": "25",
    "programs": "26", "messaging": "27", "access": "28", "printing": "29", "e2e": "e2e",
    "ui_core": "ui", "ui_services": "ui", "ui_community": "ui", "ui_printing": "ui",
}
COMMON_PREFIXES = ("LIB-TECH", "LIB-COM", "LIB-IF")
CASE_ID = re.compile(r"T-[A-Z0-9]+(?:-[A-Za-z0-9]+)+")
RESULT_ORDER = ("error", "failed", "skipped", "passed")      # the worst result of a parametrized case wins
CSV_COLUMNS = ("case", "module", "table", "type", "set", "result")


def case_id(test_name: str) -> str:
    """``test_t_loan_05_c`` → ``T-LOAN-05-c``; ``test_t_e2e_01`` → ``T-E2E-01``; other names unchanged."""
    name = test_name.split("[", 1)[0]
    if not name.startswith("test_t_"):
        return test_name
    parts = name[len("test_t_"):].split("_")
    if parts and len(parts[-1]) == 1 and parts[-1].isalpha() and len(parts) >= 3:
        return "T-" + "-".join(p.upper() for p in parts[:-1]) + "-" + parts[-1]
    return "T-" + "-".join(p.upper() for p in parts)


def test_name(case: str) -> str:
    """``T-LOAN-05-a`` → ``test_t_loan_05_a`` (the inverse of ``case_id``)."""
    return "test_" + case.replace("-", "_").lower()


def parse_junit(path: str | Path) -> dict:
    """Counts, failed cases and the result of every case from a pytest JUnit XML report."""
    root = ET.parse(path).getroot()
    result = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "failed_cases": [], "cases": {}}
    outcomes: dict[str, set[str]] = {}
    for tc in root.iter("testcase"):
        result["tests"] += 1
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error", "skipped"):
                outcome = {"failure": "failed", "error": "errors", "skipped": "skipped"}[child.tag]
                break
        result[outcome] += 1
        case = case_id(tc.get("name", ""))
        outcomes.setdefault(case, set()).add({"errors": "error"}.get(outcome, outcome))
        if outcome in ("failed", "errors"):
            result["failed_cases"].append(case)
    result["failed_cases"].sort()
    for case, seen in outcomes.items():
        result["cases"][case] = next(r for r in RESULT_ORDER if r in seen)
    return result


def load_case_tables(tests: Path) -> dict[str, dict]:
    """Case ID -> {table, module, type, set, requirement} from ``<tests>/cases/*.md`` (empty if there are none)."""
    cases: dict[str, dict] = {}
    for md in sorted((tests / "cases").glob("*.md")) if (tests / "cases").is_dir() else []:
        for line in md.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6 or not CASE_ID.fullmatch(cells[0]):
                continue
            requirement, kind, case_set = cells[1], cells[2], cells[-1].replace("held-out", "heldout")
            module = TABLE_MODULES.get(md.stem, md.stem)
            if md.stem == "core" and requirement.startswith(COMMON_PREFIXES):
                module = "common"
            cases[cells[0]] = {"table": md.stem, "module": module, "type": kind, "set": case_set,
                               "requirement": requirement}
    return cases


def expected_cases(cases: dict[str, dict], name: str, only: set[str] | None) -> set[str]:
    """Cases the set ``name`` must report: its rows of the case tables (static cases are not run by pytest)."""
    wanted = {c for c, info in cases.items() if info["set"] == name}
    return wanted if only is None or not cases else wanted & only


def run_set(name: str, tests: Path, code: Path, out: Path, timeout: int, only: set[str] | None = None,
            known: dict[str, dict] | None = None, coverage: bool = False) -> dict:
    junit = out / f"{name}.junit.xml"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(code), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    expected = expected_cases(known or {}, name, only)
    if only is not None and known:
        selected = sorted(expected)
    else:
        selected = sorted(only) if only is not None else None
    result: dict
    if selected is not None and not selected:                     # --cases: nothing of this set was asked for
        result = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "failed_cases": [], "cases": {},
                  "empty_selection": True}
        (out / f"{name}.log").write_text("no case of this set selected\n", encoding="utf-8")
        exit_code, timed_out, started = 0, False, dt.datetime.now()
    else:
        runner = [sys.executable, "-m", "pytest"]
        if coverage:
            runner = [sys.executable, "-m", "coverage", "run", "--branch", "--source=lms",
                      f"--data-file={out / f'coverage-{name}.data'}", "-m", "pytest"]
        cmd = [*runner, str(tests / name), "--rootdir", str(tests), "--import-mode=importlib", "-p", "no:cacheprovider",
               "-q", "--junitxml", str(junit)]
        if selected is not None:
            cmd += ["-k", " or ".join(test_name(c) for c in selected)]
        started = dt.datetime.now()
        timed_out = False
        try:
            proc = subprocess.run(cmd, cwd=tests, env=env, capture_output=True, text=True,
                                  timeout=timeout, check=False)
            exit_code, output = proc.returncode, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            exit_code, timed_out, output = -1, True, f"TIMEOUT after {timeout} s\n{partial}"
        (out / f"{name}.log").write_text(output, encoding="utf-8")
        result = parse_junit(junit) if junit.exists() and not timed_out else {
            "tests": 0, "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "failed_cases": ["<no report>"], "cases": {},
        }
    seen = set(result["cases"])
    missing = sorted(expected - seen)
    result.update(set=name, pytest_exit_code=exit_code, timed_out=timed_out, missing=len(missing), missing_cases=missing,
                  duration_s=round((dt.datetime.now() - started).total_seconds(), 3))
    # ``cases`` goes to tests.csv, not to the set file (the set file keeps the earlier fields only)
    saved = {k: v for k, v in result.items() if k != "cases"}
    (out / f"{name}.json").write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return result


def case_rows(results: list[dict], known: dict[str, dict]) -> list[dict]:
    """One row per case: everything pytest reported, plus the expected cases that are ``missing``."""
    rows = []
    for r in results:
        info_of = lambda c: known.get(c, {"table": "", "module": "unknown", "type": "unknown"})  # noqa: E731
        for case, outcome in [*r["cases"].items(), *((c, "missing") for c in r["missing_cases"])]:
            info = info_of(case)
            rows.append({"case": case, "module": info["module"], "table": info["table"], "type": info["type"],
                         "set": r["set"], "result": outcome})
    return sorted(rows, key=lambda row: (row["set"], row["case"]))


def write_cases_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow([row[c] for c in CSV_COLUMNS])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the LMS test sets with test protection.")
    parser.add_argument("--code", type=Path, required=True, help="folder that contains the lms package")
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    parser.add_argument("--set", choices=(*SETS, "both"), default="both")
    parser.add_argument("--out", type=Path, default=Path("test-results"))
    parser.add_argument("--baseline", type=Path, help="stored hashes (test_hashes.py record)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per set (default 7200)")
    parser.add_argument("--cases", type=Path, help="run only the case IDs listed in this file (one per line)")
    parser.add_argument("--coverage", action="store_true", help="run pytest under coverage (branch, source lms)")
    args = parser.parse_args(argv)

    # Absolute paths: pytest runs with the tests folder as working directory, so a relative
    # --out would put the JUnit reports inside the tests folder.
    tests, code, out = args.tests.resolve(), args.code.resolve(), args.out.resolve()
    if not (tests / "conftest.py").is_file():
        print(f"no conftest.py in {tests}", file=sys.stderr)
        return 2
    if not code.is_dir():
        print(f"code folder not found: {code}", file=sys.stderr)
        return 2
    if tests == code or code in tests.parents:
        print("the tests must not be inside the code folder", file=sys.stderr)
        return 2
    if out == tests or tests in out.parents:
        print("the output folder must not be inside the tests folder", file=sys.stderr)
        return 2
    only: set[str] | None = None
    if args.cases:
        if not args.cases.is_file():
            print(f"case list not found: {args.cases}", file=sys.stderr)
            return 2
        only = {ln.strip() for ln in args.cases.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}
    out.mkdir(parents=True, exist_ok=True)

    before = test_hashes.compute(tests)
    problems: dict[str, list[str]] = {}
    if args.baseline:
        problems = test_hashes.compare(json.loads(args.baseline.read_text(encoding="utf-8")), before)

    known = load_case_tables(tests)
    if only is not None and known and only - set(known):
        print(f"warning: {len(only - set(known))} case ID(s) of --cases are in no case table, e.g. "
              f"{sorted(only - set(known))[:3]}", file=sys.stderr)
    sets = SETS if args.set == "both" else (args.set,)
    results = [run_set(s, tests, code, out, args.timeout, only, known, args.coverage) for s in sets]

    after_diff = test_hashes.compare(before, test_hashes.compute(tests))
    for kind, paths in after_diff.items():
        problems.setdefault(kind, []).extend(p for p in paths if p not in problems.get(kind, []))
    changed = not test_hashes.is_unchanged(problems)
    timed_out = [r["set"] for r in results if r["timed_out"]]
    reasons = ([f"test files changed: {problems}"] if changed else []) + [f"timeout in set {s}" for s in timed_out]
    valid = not reasons

    rows = case_rows(results, known)
    write_cases_csv(out / "tests.csv", rows)
    summary = {
        "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "code": str(code),
        "tests": str(tests),
        "valid": valid,
        "invalid_reasons": reasons,
        "timeout_s": args.timeout,
        "test_file_changes": problems,
        "sets": {r["set"]: {k: r[k] for k in ("tests", "passed", "failed", "errors", "skipped", "missing")} for r in results},
    }
    (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    for r in results:
        print(f"{r['set']:9} {r['passed']}/{r['tests']} passed, {r['failed']} failed, "
              f"{r['errors']} errors, {r['skipped']} skipped, {r['missing']} missing")
    if changed:
        print(f"INVALID RUN: test files changed: {problems}", file=sys.stderr)
        return 3
    if timed_out:
        print(f"INVALID RUN: timeout of {args.timeout} s in set(s) {', '.join(timed_out)}", file=sys.stderr)
        return 4
    return 0 if all(r["failed"] == 0 and r["errors"] == 0 and r["missing"] == 0
                    and (r["tests"] > 0 or r.get("empty_selection")) for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
