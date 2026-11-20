import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_tests  # noqa: E402

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4">
<testcase classname="test_loans" name="test_t_loan_05_a"/>
<testcase classname="test_loans" name="test_t_loan_05_c"><failure message="x"/></testcase>
<testcase classname="test_fees" name="test_t_fee_02_a"><error message="y"/></testcase>
<testcase classname="test_fees" name="test_t_e2e_01"><skipped message="z"/></testcase>
</testsuite></testsuites>
"""


def test_case_id():
    assert run_tests.case_id("test_t_loan_05_c") == "T-LOAN-05-c"
    assert run_tests.case_id("test_t_fee_10_a[param]") == "T-FEE-10-a"
    assert run_tests.case_id("test_t_e2e_01") == "T-E2E-01"
    assert run_tests.case_id("test_t_p_03") == "T-P-03"
    assert run_tests.case_id("test_other") == "test_other"


def test_parse_junit(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text(JUNIT, encoding="utf-8")
    r = run_tests.parse_junit(path)
    assert (r["tests"], r["passed"], r["failed"], r["errors"], r["skipped"]) == (4, 1, 1, 1, 1)
    assert r["failed_cases"] == ["T-FEE-02-a", "T-LOAN-05-c"]


def _project(tmp_path, feedback_body, heldout_body="def test_t_x_02_a():\n    pass\n"):
    tests = tmp_path / "tests"
    for name, body in (("feedback", feedback_body), ("heldout", heldout_body)):
        (tests / name).mkdir(parents=True)
        (tests / name / "test_m.py").write_text(body, encoding="utf-8")   # same basename in both sets
    (tests / "conftest.py").write_text("", encoding="utf-8")
    code = tmp_path / "code" / "lms"
    code.mkdir(parents=True)
    (code / "__init__.py").write_text("VALUE = 42\n", encoding="utf-8")
    return tests, code.parent


def test_run_passes_and_puts_code_on_path(tmp_path):
    tests, code = _project(tmp_path, "import lms\n\ndef test_t_x_01_a():\n    assert lms.VALUE == 42\n")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)]) == 0
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["valid"] is True
    assert run["sets"]["feedback"]["passed"] == 1 and run["sets"]["heldout"]["passed"] == 1


def test_run_reports_failures(tmp_path):
    tests, code = _project(tmp_path, "def test_t_x_01_a():\n    assert False\n")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out),
                           "--set", "feedback"]) == 1
    fb = json.loads((out / "feedback.json").read_text(encoding="utf-8"))
    assert fb["failed_cases"] == ["T-X-01-a"]
    assert not (out / "heldout.json").exists()


def test_run_is_invalid_when_a_test_file_changes(tmp_path):
    body = ("from pathlib import Path\n\n"
            "def test_t_x_01_a():\n"
            "    Path(__file__).write_text('def test_t_x_01_a():\\n    pass\\n')\n")
    tests, code = _project(tmp_path, body)
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)]) == 3
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["valid"] is False
    assert run["test_file_changes"]["changed"] == ["feedback/test_m.py"]


def test_tests_inside_code_folder_are_rejected(tmp_path):
    tests, _code = _project(tmp_path, "def test_t_x_01_a():\n    pass\n")
    assert run_tests.main(["--code", str(tmp_path), "--tests", str(tests), "--out", str(tmp_path / "o")]) == 2


def test_relative_out_is_written_outside_the_tests(tmp_path):
    # Regression: pytest runs inside the tests folder; a relative --out must still mean the
    # caller's working directory and must not add files to the tests (generation step 00).
    tests, code = _project(tmp_path, "def test_t_x_01_a():\n    pass\n")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", "out"]) == 0
    finally:
        os.chdir(cwd)
    assert (tmp_path / "out" / "feedback.junit.xml").exists()
    assert json.loads((tmp_path / "out" / "feedback.json").read_text(encoding="utf-8"))["passed"] == 1
    assert not list(tests.rglob("*.junit.xml"))


def test_out_inside_tests_folder_is_rejected(tmp_path):
    tests, code = _project(tmp_path, "def test_t_x_01_a():\n    pass\n")
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(tests / "results")]) == 2


# --- per-case results, missing cases, timeout, case selection (ADR 003, D19) ------------------------------------

CASES_MD = """# Test cases: sample

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-X-01-a | LIB-X-01 | Normal | i | e | feedback |
| T-X-01-b | LIB-X-01 | Error | i | e | held-out |
| T-X-02-a | LIB-X-02 | Boundary | i | e | feedback |
| T-X-03-a | LIB-X-03 | Normal | i | e | feedback |
| T-TECH-01-a | LIB-TECH-01 | Static | i | e | static |
"""


def _with_cases(tmp_path, feedback_body, heldout_body="def test_t_x_01_b():\n    pass\n", table="loans"):
    tests, code = _project(tmp_path, feedback_body, heldout_body)
    (tests / "cases").mkdir()
    (tests / "cases" / f"{table}.md").write_text(CASES_MD, encoding="utf-8")
    return tests, code


def _rows(out):
    import csv
    with (out / "tests.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_load_case_tables_reads_module_type_and_set(tmp_path):
    tests, _ = _with_cases(tmp_path, "")
    (tests / "cases" / "core.md").write_text(
        "| ID | Requirement | Type | Input | Expected | Set |\n| --- | --- | --- | --- | --- | --- |\n"
        "| T-COM-01-a | LIB-COM-01 | Error | i | e | held-out |\n| T-CAL-01-a | LIB-CORE-01 | Normal | i | e | feedback |\n",
        encoding="utf-8")
    cases = run_tests.load_case_tables(tests)
    assert cases["T-X-01-a"] == {"table": "loans", "module": "5", "type": "Normal", "set": "feedback", "requirement": "LIB-X-01"}
    assert cases["T-X-01-b"]["set"] == "heldout" and cases["T-TECH-01-a"]["set"] == "static"
    assert cases["T-COM-01-a"]["module"] == "common" and cases["T-CAL-01-a"]["module"] == "1"
    assert run_tests.load_case_tables(tmp_path / "nowhere") == {}


def test_characterization_tables_belong_to_the_module_of_their_table(tmp_path):
    tests, _ = _with_cases(tmp_path, "")
    head = "| ID | Requirement | Type | Input | Expected | Set |\n| --- | --- | --- | --- | --- | --- |\n"
    (tests / "cases" / "char_loans.md").write_text(
        head + "| T-CHAR-LOAN-01-a | — | Characterization | i | e | feedback |\n", encoding="utf-8")
    (tests / "cases" / "char_core.md").write_text(
        head + "| T-CHAR-COM-01-a | LIB-COM-02 | Characterization | i | e | held-out |\n"
               "| T-CHAR-CORE-01-a | LIB-CORE-01 | Characterization | i | e | feedback |\n", encoding="utf-8")
    cases = run_tests.load_case_tables(tests)
    assert cases["T-CHAR-LOAN-01-a"] == {"table": "char_loans", "module": "5", "type": "Characterization",
                                         "set": "feedback", "requirement": "—"}
    assert cases["T-CHAR-COM-01-a"]["module"] == "common" and cases["T-CHAR-CORE-01-a"]["module"] == "1"
    assert run_tests.case_id("test_t_char_loan_01_a") == "T-CHAR-LOAN-01-a"


def test_tests_csv_has_one_row_per_case_and_marks_missing(tmp_path):
    # T-X-02-a fails, T-X-03-a has no test at all (missing); the static case is not expected from pytest
    tests, code = _with_cases(tmp_path, "def test_t_x_01_a():\n    pass\n\ndef test_t_x_02_a():\n    assert False\n")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)]) == 1
    rows = {(r["set"], r["case"]): r for r in _rows(out)}
    assert rows[("feedback", "T-X-01-a")]["result"] == "passed"
    assert rows[("feedback", "T-X-02-a")]["result"] == "failed" and rows[("feedback", "T-X-02-a")]["type"] == "Boundary"
    assert rows[("feedback", "T-X-03-a")]["result"] == "missing"
    assert rows[("heldout", "T-X-01-b")]["result"] == "passed" and rows[("heldout", "T-X-01-b")]["module"] == "5"
    assert not any(case == "T-TECH-01-a" for _, case in rows)
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["sets"]["feedback"]["missing"] == 1 and run["sets"]["heldout"]["missing"] == 0
    assert json.loads((out / "feedback.json").read_text(encoding="utf-8"))["missing_cases"] == ["T-X-03-a"]
    header = (out / "tests.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "case,module,table,type,set,result"


def test_a_missing_case_alone_makes_the_exit_code_1(tmp_path):
    tests, code = _with_cases(tmp_path, "def test_t_x_01_a():\n    pass\n\ndef test_t_x_02_a():\n    pass\n")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)]) == 1   # T-X-03-a missing
    assert {r["result"] for r in _rows(out)} == {"passed", "missing"}


def test_all_passed_gives_exit_code_0_with_the_tables(tmp_path):
    body = "def test_t_x_01_a():\n    pass\n\ndef test_t_x_02_a():\n    pass\n\ndef test_t_x_03_a():\n    pass\n"
    tests, code = _with_cases(tmp_path, body)
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)]) == 0
    assert {r["result"] for r in _rows(out)} == {"passed"}


def test_results_error_and_skipped_are_recorded(tmp_path):
    body = ("import pytest\n\n@pytest.fixture\ndef broken():\n    raise RuntimeError('x')\n\n"
            "def test_t_x_01_a(broken):\n    pass\n\n@pytest.mark.skip\ndef test_t_x_02_a():\n    pass\n\n"
            "def test_t_x_03_a():\n    pass\n")
    tests, code = _with_cases(tmp_path, body)
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)]) == 1
    results = {r["case"]: r["result"] for r in _rows(out) if r["set"] == "feedback"}
    assert results == {"T-X-01-a": "error", "T-X-02-a": "skipped", "T-X-03-a": "passed"}


def test_parametrized_case_takes_the_worst_result(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text('<testsuites><testsuite>'
                    '<testcase name="test_t_x_01_a[1]"/><testcase name="test_t_x_01_a[2]"><failure message="x"/></testcase>'
                    '<testcase name="test_t_x_02_a[1]"/><testcase name="test_t_x_02_a[2]"><skipped message="x"/></testcase>'
                    '</testsuite></testsuites>', encoding="utf-8")
    assert run_tests.parse_junit(path)["cases"] == {"T-X-01-a": "failed", "T-X-02-a": "skipped"}


def test_timeout_makes_the_run_invalid(tmp_path):
    tests, code = _with_cases(tmp_path, "import time\n\ndef test_t_x_01_a():\n    time.sleep(30)\n")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--set", "feedback",
                           "--timeout", "2"]) == 4
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["valid"] is False and run["invalid_reasons"] == ["timeout in set feedback"] and run["timeout_s"] == 2
    assert json.loads((out / "feedback.json").read_text(encoding="utf-8"))["timed_out"] is True
    assert "TIMEOUT after 2 s" in (out / "feedback.log").read_text(encoding="utf-8")
    assert {r["result"] for r in _rows(out)} == {"missing"}


def test_default_timeout_is_7200_seconds():
    assert run_tests.DEFAULT_TIMEOUT == 7200


def test_changed_test_file_is_exit_3_before_a_timeout(tmp_path):
    body = ("from pathlib import Path\n\ndef test_t_x_01_a():\n"
            "    Path(__file__).write_text('def test_t_x_01_a():\\n    pass\\n')\n")
    tests, code = _with_cases(tmp_path, body)
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)]) == 3
    assert json.loads((out / "run.json").read_text(encoding="utf-8"))["valid"] is False


def test_cases_option_runs_only_the_listed_cases(tmp_path):
    body = "def test_t_x_01_a():\n    pass\n\ndef test_t_x_02_a():\n    assert False\n\ndef test_t_x_03_a():\n    pass\n"
    tests, code = _with_cases(tmp_path, body)
    listing = tmp_path / "ids.txt"
    listing.write_text("# failing at the start\nT-X-02-a\nT-X-01-b\n", encoding="utf-8")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--cases", str(listing)]) == 1
    results = {(r["set"], r["case"]): r["result"] for r in _rows(out)}
    assert results == {("feedback", "T-X-02-a"): "failed", ("heldout", "T-X-01-b"): "passed"}     # nothing else ran


def test_cases_option_with_ids_of_one_set_only(tmp_path):
    tests, code = _with_cases(tmp_path, "def test_t_x_01_a():\n    pass\n")
    listing = tmp_path / "ids.txt"
    listing.write_text("T-X-01-a\n", encoding="utf-8")
    out = tmp_path / "out"
    # the held-out set has no selected case: it is not run and does not fail the run
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--cases", str(listing)]) == 0
    assert {(r["set"], r["case"]) for r in _rows(out)} == {("feedback", "T-X-01-a")}


def test_cases_option_without_case_tables(tmp_path):
    tests, code = _project(tmp_path, "def test_t_x_01_a():\n    pass\n\ndef test_t_x_05_a():\n    assert False\n")
    listing = tmp_path / "ids.txt"
    listing.write_text("T-X-05-a\n", encoding="utf-8")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--cases", str(listing),
                           "--set", "feedback"]) == 1
    assert [(r["case"], r["result"], r["module"]) for r in _rows(out)] == [("T-X-05-a", "failed", "unknown")]


def test_cases_file_must_exist(tmp_path):
    tests, code = _project(tmp_path, "def test_t_x_01_a():\n    pass\n")
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(tmp_path / "o"),
                           "--cases", str(tmp_path / "no.txt")]) == 2


def test_coverage_option_keeps_a_data_file(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("coverage")
    tests, code = _project(tmp_path, "import lms\n\ndef test_t_x_01_a():\n    assert lms.VALUE == 42\n")
    out = tmp_path / "out"
    assert run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out), "--set", "feedback",
                           "--coverage"]) == 0
    assert (out / "coverage-feedback.data").is_file()


def test_old_output_fields_are_kept(tmp_path):
    tests, code = _project(tmp_path, "def test_t_x_01_a():\n    assert False\n")
    out = tmp_path / "out"
    run_tests.main(["--code", str(code), "--tests", str(tests), "--out", str(out)])
    fb = json.loads((out / "feedback.json").read_text(encoding="utf-8"))
    for key in ("tests", "passed", "failed", "errors", "skipped", "failed_cases", "set", "pytest_exit_code", "duration_s"):
        assert key in fb
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    for key in ("date", "code", "tests", "valid", "test_file_changes", "sets"):
        assert key in run
    assert set(run["sets"]["feedback"]) >= {"tests", "passed", "failed", "errors", "skipped"}
    assert (out / "feedback.junit.xml").exists() and (out / "feedback.log").exists()


# --- the real case tables of the LMS ----------------------------------------------------------------------------

def test_real_case_tables_are_complete_and_every_case_has_a_module():
    cases = run_tests.load_case_tables(run_tests.DEFAULT_TESTS)
    assert cases, "dataset/lms/tests/cases not found"
    assert {c["set"] for c in cases.values()} == {"feedback", "heldout", "static"}
    assert not [c for c, info in cases.items() if info["module"] in ("", "unknown") or info["module"] == info["table"]
                and info["table"] not in run_tests.TABLE_MODULES]
    assert {c["module"] for c in cases.values()} >= {"common", "1", "5", "14", "29", "e2e", "ui"}
    assert all(info["type"] in ("Normal", "Boundary", "Error", "Property", "Scenario", "Static", "Characterization")
               for info in cases.values())


def test_every_expected_case_has_a_test_function():
    """The IDs of the case tables and the names of the test functions agree, or ``missing`` would be a false alarm."""
    import subprocess
    tests = run_tests.DEFAULT_TESTS
    cases = run_tests.load_case_tables(tests)
    for name in run_tests.SETS:
        proc = subprocess.run([sys.executable, "-m", "pytest", str(tests / name), "--rootdir", str(tests),
                               "--import-mode=importlib", "-p", "no:cacheprovider", "--collect-only", "-q"],
                              cwd=tests, capture_output=True, text=True, check=False,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        collected = {run_tests.case_id(line.split("::")[-1]) for line in proc.stdout.splitlines() if "::" in line}
        expected = {c for c, info in cases.items() if info["set"] == name}
        assert expected - collected == set(), f"{name}: cases without a test: {sorted(expected - collected)[:5]}"
        assert collected - expected == set(), f"{name}: tests without a case: {sorted(collected - expected)[:5]}"
