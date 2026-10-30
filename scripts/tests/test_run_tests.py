import json
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
