"""Steps of a baseline measurement (ADR 003, D17-D19, D26): analyzer, test run, repetition of the failing
tests, flaky list and a separate coverage run.

    python scripts/analyzer/baseline.py --code <folder with lms/> --out results/baseline/trial/<label> --label <label>
        [--tests dataset/lms/tests] [--modules 1-14] [--code-sha SHA] [--second-full-run]
        [--skip-analysis] [--skip-coverage] [--timeout 7200]

Written for ``scripts/measure_baseline.sh``, which takes the run lock and starts it in the Docker image.
Output in ``<out>``: the analyzer files, ``tests.csv`` (first full run), ``tests_repeat1.csv`` and
``tests_repeat2.csv`` (the failing cases, run twice more), ``flaky.txt``, ``coverage_summary.json``,
``tests_run.json`` and ``baseline.json``; raw output of every step in ``<out>/raw/`` (not committed).

Exit code: 0 done · 2 usage error · 4 the analyzer failed or a test run is invalid (baseline.json says why).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import run_tests  # noqa: E402

DEFAULT_TESTS = run_tests.DEFAULT_TESTS


# --- pure helpers ---------------------------------------------------------------------------------------------

def parse_modules(spec: str) -> tuple[int, int]:
    """``1-14`` -> (1, 14); ``5`` -> (5, 5)."""
    low, _, high = spec.partition("-")
    first, last = int(low), int(high or low)
    if not 1 <= first <= last <= 29:
        raise ValueError(f"module range out of 1-29: {spec}")
    return first, last


def select_stems(tests: Path, low: int, high: int) -> list[str]:
    """Names of the test files (case table stems) of modules ``low``..``high``; ``e2e`` goes with a range that
    covers modules 1 to 14 (its scenarios run across them); the web interface tests (``ui_*``) are never in it."""
    stems = []
    for stem, module in sorted(run_tests.TABLE_MODULES.items()):
        wanted = (module.isdigit() and low <= int(module) <= high) or (module == "e2e" and low <= 1 and high >= 14)
        if wanted and (tests / "feedback" / f"test_{stem}.py").is_file():
            stems.append(stem)
    return stems


def make_subset(tests: Path, stems: list[str], dest: Path) -> Path:
    """A copy of the tests folder with only the given test files and case tables (outside the code folder)."""
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tests / "conftest.py", dest / "conftest.py")
    if (tests / "support").is_dir():
        shutil.copytree(tests / "support", dest / "support", ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "cases").mkdir()
    for name in ("feedback", "heldout"):
        (dest / name).mkdir()
        if (tests / name / "__init__.py").is_file():
            shutil.copy2(tests / name / "__init__.py", dest / name / "__init__.py")
        for stem in stems:
            shutil.copy2(tests / name / f"test_{stem}.py", dest / name / f"test_{stem}.py")
    for stem in stems:
        if (tests / "cases" / f"{stem}.md").is_file():
            shutil.copy2(tests / "cases" / f"{stem}.md", dest / "cases" / f"{stem}.md")
    return dest


def read_results(path: Path) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {(r["set"], r["case"]): r["result"] for r in csv.DictReader(handle)}


def failing_cases(runs: list[dict[tuple[str, str], str]]) -> list[str]:
    """Case IDs that did not pass in at least one full run (these are run twice more, D18)."""
    return sorted({case for run in runs for (_, case), result in run.items() if result != "passed"})


def flaky_cases(observations: list[dict[tuple[str, str], str]]) -> list[str]:
    """Cases with a mixed result over all runs and repetitions: passed at least once and not passed at least once."""
    seen: dict[tuple[str, str], list[str]] = {}
    for run in observations:
        for key, result in run.items():
            seen.setdefault(key, []).append(result)
    return sorted({case for (_, case), results in seen.items() if "passed" in results and any(r != "passed" for r in results)})


def coverage_summary(report: dict) -> dict:
    """Branch coverage of ``lms/`` from ``coverage json`` (it never decides success, ADR 003 D26)."""
    totals = report["totals"]
    branches, covered_branches = totals.get("num_branches", 0), totals.get("covered_branches", 0)
    by_package: dict[str, dict] = {}
    for path, data in report["files"].items():
        parts = Path(path).as_posix().split("/lms/", 1)[-1].split("/")
        package = parts[0] if len(parts) > 1 else "(root)"
        s, row = data["summary"], by_package.setdefault(package, {"statements": 0, "covered": 0, "branches": 0, "covered_branches": 0})
        row["statements"] += s["num_statements"]
        row["covered"] += s["covered_lines"]
        row["branches"] += s.get("num_branches", 0)
        row["covered_branches"] += s.get("covered_branches", 0)
    return {
        "scope": "lms/ only, branch coverage, separate run; not part of the success decision",
        "statements": totals["num_statements"], "covered_statements": totals["covered_lines"],
        "statement_coverage_pct": round(100 * totals["covered_lines"] / totals["num_statements"], 4) if totals["num_statements"] else None,
        "branches": branches, "covered_branches": covered_branches,
        "branch_coverage_pct": round(100 * covered_branches / branches, 4) if branches else None,
        "combined_coverage_pct": round(totals["percent_covered"], 4),
        "by_package": dict(sorted(by_package.items())),
    }


# --- steps ---------------------------------------------------------------------------------------------------

class Steps:
    def __init__(self, raw: Path):
        self.raw = raw
        self.items: list[dict] = []

    def run(self, name: str, cmd: list[str], ok_codes: tuple[int, ...]) -> int:
        started = time.perf_counter()
        print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {name}: {' '.join(cmd[2:5])} ...", flush=True)
        item = {"step": name, "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "state": "running"}
        self.items.append(item)
        self._save()
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        (self.raw / f"{name}.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        item.update(state="done" if proc.returncode in ok_codes else "failed", exit_code=proc.returncode,
                    seconds=round(time.perf_counter() - started, 1))
        print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {name}: exit {proc.returncode} in {item['seconds']} s", flush=True)
        tail = proc.stdout.strip().splitlines()[-3:]
        for line in tail:
            print("    " + line, flush=True)
        self._save()
        return proc.returncode

    def _save(self) -> None:
        (self.raw / "status.json").write_text(json.dumps(self.items, indent=2) + "\n", encoding="utf-8")


def environment() -> dict:
    ram = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                ram = round(int(line.split()[1]) / 2**20, 1)
    except OSError:
        pass
    return {"cpus": os.cpu_count(), "ram_gb": ram, "python": sys.version.split()[0],
            "cpuset_cpus": os.environ.get("MEASURE_CPUSET"), "memory": os.environ.get("MEASURE_MEMORY")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baseline measurement steps (ADR 003).")
    parser.add_argument("--code", type=Path, required=True, help="folder that contains lms/")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    parser.add_argument("--modules", help="only the test files of these modules, e.g. 1-14 (pilot code)")
    parser.add_argument("--code-sha", help="commit of the code when --code is an export")
    parser.add_argument("--second-full-run", action="store_true", help="a second full test run (the final baseline, D18)")
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--skip-coverage", action="store_true")
    parser.add_argument("--timeout", type=int, default=run_tests.DEFAULT_TIMEOUT, help="seconds per test set")
    args = parser.parse_args(argv)

    code, tests, out = args.code.resolve(), args.tests.resolve(), args.out.resolve()
    if not (code / "lms").is_dir() or not (tests / "conftest.py").is_file():
        print("need a code folder with lms/ and a tests folder with conftest.py", file=sys.stderr)
        return 2
    try:
        modules = parse_modules(args.modules) if args.modules else None
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    steps = Steps(raw)
    started = dt.datetime.now(dt.timezone.utc)
    result: dict = {"label": args.label, "started_at": started.isoformat(timespec="seconds"), "environment": environment(),
                    "modules": args.modules, "second_full_run": args.second_full_run, "problems": []}
    py = sys.executable

    # 1. analyzer
    if not args.skip_analysis:
        cmd = [py, str(SCRIPTS / "analyze.py"), "--code", str(code), "--out", str(out), "--label", args.label, "--with-secondary"]
        if args.code_sha:
            cmd += ["--code-sha", args.code_sha]
        if steps.run("analyze", cmd, (0,)) != 0:
            result["problems"].append("the analyzer exited with a code other than 0 (summary.json has the reasons)")
        summary = out / "summary.json"
        if summary.is_file():
            data = json.loads(summary.read_text(encoding="utf-8"))
            result["analysis"] = {"primary": data["primary"], "smell_counts": data["smell_counts"], "code_sha": data["code_sha"],
                                  "code_content_hash": data["code_content_hash"], "analyzer_sha": data["analyzer_sha"],
                                  "image_id": data["image_id"], "failures": data["failures"]}

    # 2. tests: all, or the test files of some modules only
    test_dir = tests
    scratch: Path | None = None
    if modules:
        stems = select_stems(tests, *modules)
        scratch = Path(tempfile.mkdtemp(prefix="baseline-tests-"))
        test_dir = make_subset(tests, stems, scratch / "tests")
        result["test_files"] = stems
        print(f"tests of modules {args.modules}: {', '.join(stems)}", flush=True)

    def full_run(name: str) -> dict[tuple[str, str], str] | None:
        folder = raw / name
        code_ = steps.run(name, [py, str(SCRIPTS / "run_tests.py"), "--code", str(code), "--tests", str(test_dir),
                                 "--out", str(folder), "--timeout", str(args.timeout)], (0, 1))
        if code_ not in (0, 1) or not (folder / "tests.csv").is_file():
            result["problems"].append(f"{name}: invalid run (exit code {code_}), see raw/{name}.log")
            return None
        return read_results(folder / "tests.csv")

    try:
        run1 = full_run("tests-run1")
        if run1 is not None:
            shutil.copy2(raw / "tests-run1" / "tests.csv", out / "tests.csv")
            shutil.copy2(raw / "tests-run1" / "run.json", out / "tests_run.json")
            full_runs = [run1]
            if args.second_full_run:
                run2 = full_run("tests-run2")
                if run2 is not None:
                    full_runs.append(run2)
            failing = failing_cases(full_runs)
            observations = list(full_runs)
            if failing:
                (raw / "failing.txt").write_text("\n".join(failing) + "\n", encoding="utf-8")
                for number in (1, 2):
                    name = f"tests-repeat{number}"
                    code_ = steps.run(name, [py, str(SCRIPTS / "run_tests.py"), "--code", str(code), "--tests", str(test_dir),
                                             "--out", str(raw / name), "--cases", str(raw / "failing.txt"),
                                             "--timeout", str(args.timeout)], (0, 1))
                    if code_ in (0, 1) and (raw / name / "tests.csv").is_file():
                        shutil.copy2(raw / name / "tests.csv", out / f"tests_repeat{number}.csv")
                        observations.append(read_results(raw / name / "tests.csv"))
                    else:
                        result["problems"].append(f"{name}: invalid run (exit code {code_})")
            flaky = flaky_cases(observations)
            (out / "flaky.txt").write_text(
                "# Cases with a mixed result over the full run(s) and the two repetitions of the failing cases (ADR 003, D18).\n"
                "# They are left out of the comparison.\n" + "".join(f"{c}\n" for c in flaky), encoding="utf-8")
            sets = json.loads((out / "tests_run.json").read_text(encoding="utf-8"))["sets"]
            result["tests"] = {"sets": sets, "failing_in_a_full_run": len(failing), "flaky": len(flaky),
                               "repetitions": sum(1 for n in (1, 2) if (out / f"tests_repeat{n}.csv").is_file()),
                               "persistent_failures": len(failing) - len(flaky)}

            # 3. coverage in a run of its own (never part of the success decision)
            if not args.skip_coverage:
                folder = raw / "coverage-run"
                steps.run("coverage-run", [py, str(SCRIPTS / "run_tests.py"), "--code", str(code), "--tests", str(test_dir),
                                           "--out", str(folder), "--coverage", "--timeout", str(args.timeout)], (0, 1))
                data_files = sorted(str(p) for p in folder.glob("coverage-*.data"))
                if data_files:
                    combined = folder / "combined.data"
                    steps.run("coverage-combine", [py, "-m", "coverage", "combine", "--keep", f"--data-file={combined}", *data_files], (0,))
                    steps.run("coverage-json", [py, "-m", "coverage", "json", f"--data-file={combined}", "-o", str(folder / "coverage.json")], (0,))
                    if (folder / "coverage.json").is_file():
                        summary_ = coverage_summary(json.loads((folder / "coverage.json").read_text(encoding="utf-8")))
                        (out / "coverage_summary.json").write_text(json.dumps(summary_, indent=2) + "\n", encoding="utf-8")
                        result["coverage"] = {k: summary_[k] for k in ("statement_coverage_pct", "branch_coverage_pct", "combined_coverage_pct")}
                else:
                    result["problems"].append("coverage-run produced no data file")
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    result["duration_s"] = round((dt.datetime.fromisoformat(result["finished_at"]) - started).total_seconds())
    result["steps"] = steps.items
    result["valid"] = not any("invalid run" in p or "analyzer" in p for p in result["problems"])
    (out / "baseline.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for problem in result["problems"]:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    print(f"{args.label}: done in {result['duration_s']} s; valid={result['valid']}", flush=True)
    return 0 if result["valid"] else 4


if __name__ == "__main__":
    sys.exit(main())
