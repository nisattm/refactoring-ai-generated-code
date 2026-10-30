"""Runs the LMS test sets against a code folder and checks that the tests were not changed.

    python scripts/run_tests.py --code <folder with the lms package> [--set feedback|heldout|both]
                                [--tests dataset/lms/tests] [--out results/] [--baseline hashes.json]

Steps (docs/testing.md, dataset/lms/tests/README.md):
1. Hash every test file (scripts/test_hashes.py); with --baseline, the hashes must also
   match a stored reference.
2. Run each set (``feedback/``, ``heldout/``) in its own pytest process, with the code
   folder on PYTHONPATH and the tests outside it.
3. Hash again. Any change makes the run invalid.
4. Write ``<out>/<set>.json`` (counts and the case IDs that failed) and ``<out>/run.json``.

Exit code: 0 all passed, 1 failures or errors, 2 usage problem, 3 test files changed (invalid run).
Standard library only; pytest must be installed in the environment that runs the tests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_hashes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS = ROOT / "dataset" / "lms" / "tests"
SETS = ("feedback", "heldout")


def case_id(test_name: str) -> str:
    """``test_t_loan_05_c`` → ``T-LOAN-05-c``; ``test_t_e2e_01`` → ``T-E2E-01``; other names unchanged."""
    name = test_name.split("[", 1)[0]
    if not name.startswith("test_t_"):
        return test_name
    parts = name[len("test_t_"):].split("_")
    if parts and len(parts[-1]) == 1 and parts[-1].isalpha() and len(parts) >= 3:
        return "T-" + "-".join(p.upper() for p in parts[:-1]) + "-" + parts[-1]
    return "T-" + "-".join(p.upper() for p in parts)


def parse_junit(path: str | Path) -> dict:
    """Counts and failed cases from a pytest JUnit XML report."""
    root = ET.parse(path).getroot()
    result = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "failed_cases": []}
    for tc in root.iter("testcase"):
        result["tests"] += 1
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error", "skipped"):
                outcome = {"failure": "failed", "error": "errors", "skipped": "skipped"}[child.tag]
                break
        result[outcome] += 1
        if outcome in ("failed", "errors"):
            result["failed_cases"].append(case_id(tc.get("name", "")))
    result["failed_cases"].sort()
    return result


def run_set(name: str, tests: Path, code: Path, out: Path, timeout: int) -> dict:
    junit = out / f"{name}.junit.xml"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(code), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [
        sys.executable, "-m", "pytest", str(tests / name),
        "--rootdir", str(tests), "--import-mode=importlib", "-p", "no:cacheprovider",
        "-q", "--junitxml", str(junit),
    ]
    started = dt.datetime.now()
    try:
        proc = subprocess.run(cmd, cwd=tests, env=env, capture_output=True, text=True,
                              timeout=timeout, check=False)
        exit_code, output = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code, output = -1, f"TIMEOUT after {timeout} s\n{exc.stdout or ''}"
    (out / f"{name}.log").write_text(output, encoding="utf-8")

    result = parse_junit(junit) if junit.exists() else {
        "tests": 0, "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "failed_cases": ["<no report>"],
    }
    result.update(set=name, pytest_exit_code=exit_code,
                  duration_s=round((dt.datetime.now() - started).total_seconds(), 3))
    (out / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the LMS test sets with test protection.")
    parser.add_argument("--code", type=Path, required=True, help="folder that contains the lms package")
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    parser.add_argument("--set", choices=(*SETS, "both"), default="both")
    parser.add_argument("--out", type=Path, default=Path("test-results"))
    parser.add_argument("--baseline", type=Path, help="stored hashes (test_hashes.py record)")
    parser.add_argument("--timeout", type=int, default=3600, help="seconds per set")
    args = parser.parse_args(argv)

    tests, code = args.tests.resolve(), args.code.resolve()
    if not (tests / "conftest.py").is_file():
        print(f"no conftest.py in {tests}", file=sys.stderr)
        return 2
    if not code.is_dir():
        print(f"code folder not found: {code}", file=sys.stderr)
        return 2
    if tests == code or code in tests.parents:
        print("the tests must not be inside the code folder", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)

    before = test_hashes.compute(tests)
    problems: dict[str, list[str]] = {}
    if args.baseline:
        problems = test_hashes.compare(json.loads(args.baseline.read_text(encoding="utf-8")), before)

    sets = SETS if args.set == "both" else (args.set,)
    results = [run_set(s, tests, code, args.out, args.timeout) for s in sets]

    after_diff = test_hashes.compare(before, test_hashes.compute(tests))
    for kind, paths in after_diff.items():
        problems.setdefault(kind, []).extend(p for p in paths if p not in problems.get(kind, []))
    valid = test_hashes.is_unchanged(problems)

    summary = {
        "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "code": str(code),
        "tests": str(tests),
        "valid": valid,
        "test_file_changes": problems,
        "sets": {r["set"]: {k: r[k] for k in ("tests", "passed", "failed", "errors", "skipped")} for r in results},
    }
    (args.out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    for r in results:
        print(f"{r['set']:9} {r['passed']}/{r['tests']} passed, {r['failed']} failed, "
              f"{r['errors']} errors, {r['skipped']} skipped")
    if not valid:
        print(f"INVALID RUN: test files changed: {problems}", file=sys.stderr)
        return 3
    return 0 if all(r["failed"] == 0 and r["errors"] == 0 and r["tests"] > 0 for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
