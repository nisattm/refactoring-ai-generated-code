"""Tests of the baseline measurement: scripts/analyzer/baseline.py and scripts/measure_baseline.sh (ADR 003, D18, D26)."""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
SCRIPT = SCRIPTS / "measure_baseline.sh"
sys.path.insert(0, str(SCRIPTS))

from analyzer import baseline  # noqa: E402

bash = shutil.which("bash")
needs_bash = pytest.mark.skipif(bash is None, reason="bash is not installed")


# --- pure helpers ---------------------------------------------------------------------------------------------

def test_parse_modules():
    assert baseline.parse_modules("1-14") == (1, 14) and baseline.parse_modules("5") == (5, 5)
    for bad in ("0-3", "3-2", "1-30", "x"):
        with pytest.raises(ValueError):
            baseline.parse_modules(bad)


def test_pilot_stems_are_modules_1_to_14_plus_e2e_and_no_ui():
    stems = baseline.select_stems(baseline.DEFAULT_TESTS, 1, 14)
    assert stems == sorted(["core", "auth", "members", "catalog", "loans", "reservations", "fees", "notifications", "search",
                            "reports", "branches", "purchasing", "audit_io", "api", "e2e"])
    late = baseline.select_stems(baseline.DEFAULT_TESTS, 15, 29)
    assert "rooms" in late and "printing" in late and "e2e" not in late and not any(s.startswith("ui_") for s in late)


def test_subset_holds_only_the_chosen_test_files(tmp_path):
    stems = baseline.select_stems(baseline.DEFAULT_TESTS, 1, 3)
    subset = baseline.make_subset(baseline.DEFAULT_TESTS, stems, tmp_path / "tests")
    assert sorted(p.name for p in (subset / "feedback").glob("test_*.py")) == [f"test_{s}.py" for s in sorted(stems)]
    assert sorted(p.name for p in (subset / "heldout").glob("test_*.py")) == [f"test_{s}.py" for s in sorted(stems)]
    assert (subset / "conftest.py").is_file() and (subset / "support" / "api.py").is_file()
    assert sorted(p.stem for p in (subset / "cases").glob("*.md")) == sorted(stems)
    cases = baseline.run_tests.load_case_tables(subset)
    assert {c["table"] for c in cases.values()} == set(stems)


def test_failing_and_flaky_cases():
    run1 = {("feedback", "T-A-01-a"): "passed", ("feedback", "T-A-02-a"): "failed", ("feedback", "T-A-03-a"): "error",
            ("heldout", "T-A-04-b"): "missing", ("heldout", "T-A-05-b"): "passed"}
    run2 = {("feedback", "T-A-01-a"): "failed", ("feedback", "T-A-02-a"): "failed", ("feedback", "T-A-03-a"): "error",
            ("heldout", "T-A-04-b"): "missing", ("heldout", "T-A-05-b"): "passed"}
    assert baseline.failing_cases([run1]) == ["T-A-02-a", "T-A-03-a", "T-A-04-b"]
    assert baseline.failing_cases([run1, run2]) == ["T-A-01-a", "T-A-02-a", "T-A-03-a", "T-A-04-b"]
    repeat1 = {("feedback", "T-A-02-a"): "passed", ("feedback", "T-A-03-a"): "failed", ("feedback", "T-A-01-a"): "passed"}
    repeat2 = {("feedback", "T-A-02-a"): "failed", ("feedback", "T-A-03-a"): "failed", ("feedback", "T-A-01-a"): "passed"}
    # T-A-01-a: passed, failed, passed, passed -> mixed; T-A-02-a: failed, failed, passed, failed -> mixed;
    # T-A-03-a and T-A-04-b fail everywhere; T-A-05-b passes everywhere
    assert baseline.flaky_cases([run1, run2, repeat1, repeat2]) == ["T-A-01-a", "T-A-02-a"]
    assert baseline.flaky_cases([run1]) == []


def test_coverage_summary():
    report = {"totals": {"num_statements": 10, "covered_lines": 8, "num_branches": 4, "covered_branches": 1, "percent_covered": 64.2857},
              "files": {"/code/lms/core/db.py": {"summary": {"num_statements": 6, "covered_lines": 5, "num_branches": 2, "covered_branches": 1}},
                        "/code/lms/__init__.py": {"summary": {"num_statements": 4, "covered_lines": 3, "num_branches": 2, "covered_branches": 0}}}}
    summary = baseline.coverage_summary(report)
    assert summary["statement_coverage_pct"] == 80.0 and summary["branch_coverage_pct"] == 25.0
    assert summary["by_package"] == {"(root)": {"statements": 4, "covered": 3, "branches": 2, "covered_branches": 0},
                                     "core": {"statements": 6, "covered": 5, "branches": 2, "covered_branches": 1}}
    assert "not part of the success decision" in summary["scope"]


# --- a tiny project for the steps ------------------------------------------------------------------------------

CASES = """| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-X-01-a | LIB-X-01 | Normal | i | e | feedback |
| T-X-03-a | LIB-X-03 | Normal | i | e | feedback |
| T-X-05-a | LIB-X-05 | Normal | i | e | feedback |
| T-X-07-a | LIB-X-07 | Normal | i | e | feedback |
| T-X-02-b | LIB-X-02 | Normal | i | e | held-out |
"""
FEEDBACK = '''import os
from pathlib import Path

import lms


def test_t_x_01_a():
    assert lms.f(True) == 1 and lms.VALUE == 42


def test_t_x_03_a():
    """Fails the first time it runs, passes afterwards: a flaky test."""
    state = Path(os.environ["FLAKY_STATE"])
    if not state.exists():
        state.write_text("seen")
        assert False


def test_t_x_05_a():
    assert False


def test_t_x_07_a():
    """The run lock exists while the tests run."""
    lock = os.environ.get("MEASURE_LOCK_FILE")
    assert lock is None or Path(lock).exists()
'''
HELDOUT = "def test_t_x_02_b():\n    pass\n"
LMS = "VALUE = 42\n\n\ndef f(x):\n    if x:\n        return 1\n    return 2\n"


def project(root: Path) -> tuple[Path, Path]:
    tests = root / "tests"
    for name, body in (("feedback", FEEDBACK), ("heldout", HELDOUT)):
        (tests / name).mkdir(parents=True)
        (tests / name / "test_m.py").write_text(body, encoding="utf-8")
    (tests / "cases").mkdir()
    (tests / "cases" / "m.md").write_text(CASES, encoding="utf-8")
    (tests / "conftest.py").write_text("", encoding="utf-8")
    code = root / "code"
    (code / "lms").mkdir(parents=True)
    (code / "lms" / "__init__.py").write_text(LMS, encoding="utf-8")
    return code, tests


def rows(path: Path) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {(r["set"], r["case"]): r["result"] for r in csv.DictReader(handle)}


def test_steps_find_the_flaky_test_and_the_persistent_failure(tmp_path, monkeypatch):
    code, tests = project(tmp_path)
    monkeypatch.setenv("FLAKY_STATE", str(tmp_path / "state"))
    out = tmp_path / "out"
    assert baseline.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--label", "t", "--skip-analysis"]) == 0
    first = rows(out / "tests.csv")
    assert first[("feedback", "T-X-03-a")] == "failed" and first[("feedback", "T-X-05-a")] == "failed"
    assert first[("feedback", "T-X-01-a")] == "passed" and first[("heldout", "T-X-02-b")] == "passed"
    for number in (1, 2):                                     # only the failing cases run again
        again = rows(out / f"tests_repeat{number}.csv")
        assert again == {("feedback", "T-X-03-a"): "passed", ("feedback", "T-X-05-a"): "failed"}
    flaky = (out / "flaky.txt").read_text(encoding="utf-8").splitlines()
    assert [ln for ln in flaky if not ln.startswith("#")] == ["T-X-03-a"]
    info = json.loads((out / "baseline.json").read_text(encoding="utf-8"))
    assert info["valid"] is True and info["problems"] == []
    assert info["tests"]["failing_in_a_full_run"] == 2 and info["tests"]["flaky"] == 1 and info["tests"]["persistent_failures"] == 1
    assert info["tests"]["repetitions"] == 2 and info["tests"]["sets"]["feedback"]["failed"] == 2
    assert info["coverage"]["branch_coverage_pct"] is not None
    summary = json.loads((out / "coverage_summary.json").read_text(encoding="utf-8"))
    assert summary["branches"] == 2 and 0 < summary["branch_coverage_pct"] <= 100       # f(True) covers one of two branches
    assert (out / "raw" / "tests-run1" / "tests.csv").is_file() and (out / "raw" / "status.json").is_file()


def test_the_flaky_list_can_be_given_to_compare(tmp_path, monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    import compare
    code, tests = project(tmp_path)
    monkeypatch.setenv("FLAKY_STATE", str(tmp_path / "state"))
    out = tmp_path / "out"
    baseline.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--label", "t", "--skip-analysis", "--skip-coverage"])
    assert compare.read_flaky(out / "flaky.txt") == {"T-X-03-a"}
    assert not (out / "coverage_summary.json").exists()


def test_all_passing_needs_no_repetition(tmp_path, monkeypatch):
    code, tests = project(tmp_path)
    (tests / "feedback" / "test_m.py").write_text("def test_t_x_01_a():\n    pass\n", encoding="utf-8")
    (tests / "cases" / "m.md").write_text(CASES.split("| T-X-03-a")[0] + "| T-X-02-b | LIB-X-02 | Normal | i | e | held-out |\n",
                                          encoding="utf-8")
    out = tmp_path / "out"
    assert baseline.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--label", "t", "--skip-analysis",
                          "--skip-coverage"]) == 0
    assert not (out / "tests_repeat1.csv").exists()
    assert [ln for ln in (out / "flaky.txt").read_text(encoding="utf-8").splitlines() if not ln.startswith("#")] == []
    assert json.loads((out / "baseline.json").read_text(encoding="utf-8"))["tests"]["repetitions"] == 0


def test_second_full_run_catches_a_test_that_flips_between_the_full_runs(tmp_path, monkeypatch):
    code, tests = project(tmp_path)
    body = ('from pathlib import Path\n\ndef test_t_x_01_a():\n    pass\n\n'
            'def test_t_x_03_a():\n    marker = Path(__import__("os").environ["FLAKY_STATE"])\n'
            '    if marker.exists():\n        assert False\n    marker.write_text("x")\n')
    (tests / "feedback" / "test_m.py").write_text(body, encoding="utf-8")
    monkeypatch.setenv("FLAKY_STATE", str(tmp_path / "state"))
    out = tmp_path / "out"
    baseline.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--label", "t", "--skip-analysis",
                   "--skip-coverage", "--second-full-run"])
    # run 1 passes, run 2 fails (and so do both repetitions): passed once and failed otherwise = flaky
    assert "T-X-03-a" in (out / "flaky.txt").read_text(encoding="utf-8")
    assert (out / "raw" / "tests-run2" / "tests.csv").is_file()
    # the second run is kept outside raw/ (not committed), so that the final baseline records both full runs
    assert (out / "tests_run2.csv").read_text(encoding="utf-8") == (out / "raw" / "tests-run2" / "tests.csv").read_text(encoding="utf-8")
    assert json.loads((out / "tests_run2.json").read_text(encoding="utf-8"))["sets"]


def test_modules_option_runs_only_the_selected_test_files(tmp_path, monkeypatch):
    code, _ = project(tmp_path)
    # the real tests of modules 1-1 (core) against code that cannot import: they fail, but only core's cases are in the run
    out = tmp_path / "out"
    baseline.main(["--code", str(code), "--tests", str(baseline.DEFAULT_TESTS), "--out", str(out), "--label", "t",
                   "--skip-analysis", "--skip-coverage", "--modules", "1-1", "--timeout", "1200"])
    first = rows(out / "tests.csv")
    tables = {baseline.run_tests.load_case_tables(baseline.DEFAULT_TESTS)[c]["table"] for (_, c) in first}
    assert tables == {"core"} and len(first) > 50
    assert json.loads((out / "baseline.json").read_text(encoding="utf-8"))["test_files"] == ["core"]


def test_usage_errors_exit_2(tmp_path):
    assert baseline.main(["--code", str(tmp_path), "--out", str(tmp_path / "o"), "--label", "t"]) == 2
    code, tests = project(tmp_path)
    assert baseline.main(["--code", str(code), "--tests", str(tests), "--out", str(tmp_path / "o"), "--label", "t",
                          "--modules", "9-3"]) == 2


# --- measure_baseline.sh ---------------------------------------------------------------------------------------

def sh(*args, env=None, timeout=600):
    return subprocess.run([bash, str(SCRIPT), *args], capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **(env or {})}, check=False)


@needs_bash
def test_script_is_executable_text_with_lf_endings():
    assert b"\r" not in SCRIPT.read_bytes() and SCRIPT.read_bytes().startswith(b"#!/usr/bin/env bash")
    assert "--background" in sh("--help").stdout


@needs_bash
def test_dry_run_shows_the_docker_command_and_takes_no_lock(tmp_path):
    code, _ = project(tmp_path)
    lock = tmp_path / "lock"
    done = sh("--label", "x", "--code", str(code), "--dry-run", "--lock-file", str(lock), "--modules", "1-14")
    assert done.returncode == 0, done.stderr
    for part in ("docker run --rm --network none", "refactoring-env", "scripts/analyzer/baseline.py", "--label x",
                 "--modules 1-14", "/code"):
        assert part in done.stdout
    assert not lock.exists()


@needs_bash
def test_dry_run_with_a_git_ref_resolves_the_commit():
    known = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(REPO), "cat-file", "-e", "ce03f54^{commit}"],
                           capture_output=True, check=False)
    if known.returncode != 0:
        pytest.skip("the commit ce03f54 (pilot code) is not in this checkout")
    done = sh("--label", "pilot", "--code-ref", "ce03f54", "--dry-run")
    assert done.returncode == 0, done.stderr
    assert "ce03f54" in done.stdout and "--code-sha ce03f54" in done.stdout


@needs_bash
def test_usage_errors_of_the_script(tmp_path):
    code, _ = project(tmp_path)
    assert sh("--code", str(code)).returncode == 2                                   # no label
    assert sh("--label", "x").returncode == 2                                        # no code
    assert sh("--label", "x", "--code", str(code), "--code-ref", "HEAD").returncode == 2
    assert sh("--label", "x", "--code-ref", "no-such-ref-xyz", "--dry-run").returncode == 2
    assert sh("--label", "x", "--code", str(code), "--bogus").returncode == 2
    assert sh("--label", "x", "--code", str(tmp_path / "nothing")).returncode == 2
    assert sh("--label", "x", "--code", str(code), "--out", str(tmp_path / "o")).returncode == 2     # out outside the repo, not --local


@needs_bash
def test_a_held_lock_makes_the_script_wait_and_then_give_up(tmp_path):
    code, tests = project(tmp_path)
    lock = tmp_path / "lock"
    lock.write_text("who=someone\nwhat=another run\nstart=now\npid=1\n", encoding="utf-8")
    started = time.monotonic()
    done = sh("--label", "x", "--code", str(code), "--tests", str(tests), "--out", str(tmp_path / "o"), "--local",
              "--lock-file", str(lock), "--wait", "2", "--poll", "1")
    assert done.returncode == 3 and "still held" in done.stderr and "who=someone" in done.stderr
    assert "waiting for" in done.stdout and time.monotonic() - started >= 2
    assert lock.read_text(encoding="utf-8").startswith("who=someone")              # not touched
    assert not (tmp_path / "o" / "baseline.json").exists()


@needs_bash
def test_the_script_takes_the_lock_for_the_run_and_releases_it(tmp_path):
    code, tests = project(tmp_path)
    lock = tmp_path / "lock"
    out = tmp_path / "o"
    done = sh("--label", "x", "--code", str(code), "--tests", str(tests), "--out", str(out), "--local", "--lock-file", str(lock),
              "--skip-analysis", "--skip-coverage", env={"FLAKY_STATE": str(tmp_path / "state")})
    assert done.returncode == 0, done.stdout + done.stderr
    assert "lock taken" in done.stdout and not lock.exists()
    first = rows(out / "tests.csv")
    assert first[("feedback", "T-X-07-a")] == "passed"                                # the test saw the lock file
    assert json.loads((out / "baseline.json").read_text(encoding="utf-8"))["valid"] is True


@needs_bash
def test_the_lock_is_released_when_the_run_fails(tmp_path):
    code, tests = project(tmp_path)
    lock = tmp_path / "lock"
    done = sh("--label", "x", "--code", str(code), "--tests", str(tmp_path / "no-tests"), "--out", str(tmp_path / "o"),
              "--local", "--lock-file", str(lock), "--skip-analysis")
    assert done.returncode == 2 and not lock.exists()


@needs_bash
def test_background_run_returns_at_once_and_finishes_alone(tmp_path):
    code, tests = project(tmp_path)
    lock = tmp_path / "lock"
    out = tmp_path / "o"
    done = sh("--label", "x", "--code", str(code), "--tests", str(tests), "--out", str(out), "--local", "--lock-file", str(lock),
              "--skip-analysis", "--skip-coverage", "--background", env={"FLAKY_STATE": str(tmp_path / "state")}, timeout=60)
    assert done.returncode == 0 and "process ID" in done.stdout
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline and not ((out / "baseline.json").exists() and not lock.exists()):
        time.sleep(1)
    assert (out / "baseline.json").exists() and not lock.exists()
    log = (out / "raw" / "measure.log").read_text(encoding="utf-8")
    assert "lock taken" in log and "lock released" in log
