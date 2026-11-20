"""Tests of experiments/feedback.py (ADR 004, W2): confirmed regressions only, cleaned, limited, deterministic."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr, escape

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments"))
import feedback  # noqa: E402

COLUMNS = "case,module,table,type,set,result\n"


def write_tests_csv(path: Path, rows: dict[tuple[str, str], str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{case},5,loans,Normal,{s},{result}\n" for (s, case), result in sorted(rows.items())]
    path.write_text(COLUMNS + "".join(lines), encoding="utf-8")
    return path


def make_testcase(name: str, tag: str | None = None, message: str = "", text: str = "") -> str:
    inner = f"<{tag} message={quoteattr(message)}>{escape(text)}</{tag}>" if tag else ""
    return f'<testcase classname="feedback.test_loans" name="{name}" time="0.1">{inner}</testcase>'


def junit(folder: Path, *cases: str, test_set: str = "feedback") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    body = "".join(cases)
    (folder / f"{test_set}.junit.xml").write_text(
        f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">{body}</testsuite></testsuites>',
        encoding="utf-8")


class Round:
    """A starting measurement, one round's tests.csv, two repetitions and the round's test folder."""

    def __init__(self, tmp: Path, before: dict, after: dict, repeat: dict | None = None, repeats: int = 2,
                 flaky: list[str] | None = None):
        self.before = write_tests_csv(tmp / "baseline" / "tests.csv", before)
        if flaky is not None:
            (tmp / "baseline" / "flaky.txt").write_text("# flaky\n" + "".join(f"{c}\n" for c in flaky), encoding="utf-8")
        self.after = write_tests_csv(tmp / "round" / "tests" / "tests.csv", after)
        rep = repeat if repeat is not None else {k: v for k, v in after.items() if v != "passed"}
        self.repeats = [write_tests_csv(tmp / "round" / f"repeat{n}" / "tests.csv", rep) for n in range(1, repeats + 1)]
        self.log_dir = tmp / "round" / "tests"

    def text(self) -> str:
        return feedback.format_feedback(self.before, self.after, self.repeats, self.log_dir)


F = "feedback"


def name_of(case: str) -> str:
    """``T-LOAN-05-a`` -> ``test_t_loan_05_a`` (the test naming rule of scripts/run_tests.py)."""
    return "test_" + case.replace("-", "_").lower()
LONG_TEXT = (
    "def test_t_loan_02_a(client):\n>       api.lend(client, x)\n\n/exp/run/tests/feedback/test_loans.py:12: \n"
    "_ _ _ _\n/exp/run/start/lms/loans/service.py:30: in lend\n    return self.helper(x)\n_ _ _ _\n"
    "self = <lms.loans.service.Svc object at 0x7f3a2b1c9d80>\n>       return x.missing\n"
    "E       AttributeError: 'Copy' object has no attribute 'missing'\n\n"
    "/exp/run/start/lms/loans/service.py:41: AttributeError"
)


def test_no_regression_gives_empty_text(tmp_path):
    r = Round(tmp_path, {(F, "T-LOAN-01-a"): "passed"}, {(F, "T-LOAN-01-a"): "passed"})
    assert r.text() == ""


def test_confirmed_regression_with_message_and_location(tmp_path):
    r = Round(tmp_path, {(F, "T-LOAN-02-a"): "passed"}, {(F, "T-LOAN-02-a"): "failed"})
    junit(r.log_dir, make_testcase("test_t_loan_02_a", "failure",
                              "AttributeError: 'Copy' object has no attribute 'missing'", LONG_TEXT))
    assert r.text() == (
        f"{feedback.HEADER}\n"
        "- T-LOAN-02-a\n"
        "  AttributeError: 'Copy' object has no attribute 'missing'\n"
        "  at lms/loans/service.py:41\n"
    )


def test_our_test_lines_paths_addresses_and_colours_are_removed(tmp_path):
    message = ("AssertionError: assert 'closed' == 'open'\n  \n  #x1B[0m#x1B[91m- open#x1B[39;49;00m\n"
               "  #x1B[92m+ closed#x1B[39;49;00m\n +  where 'closed' = loan['status']\n"
               "at /exp/run/tests/support/api.py:31\nobject at 0x7f3a2b1c9d80 in /tmp/pytest-of-root/pytest-3/x0/db.sqlite")
    r = Round(tmp_path, {(F, "T-LOAN-03-a"): "passed"}, {(F, "T-LOAN-03-a"): "failed"})
    junit(r.log_dir, make_testcase("test_t_loan_03_a", "failure", message, "E   assert 'closed' == 'open'"))
    text = r.text()
    assert "- open" in text and "+ closed" in text
    for gone in ("#x1B", "where", "support/api.py", "/tmp/", "/exp/", "0x7f3a"):
        assert gone not in text
    assert "object at 0x… in db.sqlite" in text


def test_api_paths_in_messages_are_kept(tmp_path):
    message = 'AssertionError: POST /api/v1/loans: expected 201, got 409: {"error":{"code":"COPY_NOT_AVAILABLE"}}'
    r = Round(tmp_path, {(F, "T-LOAN-01-a"): "passed"}, {(F, "T-LOAN-01-a"): "failed"})
    junit(r.log_dir, make_testcase("test_t_loan_01_a", "failure", message, "support/api.py:31: AssertionError"))
    text = r.text()
    assert "POST /api/v1/loans: expected 201, got 409" in text
    assert "at " not in text  # the failing line is in our helper, not in lms/


def test_only_confirmed_regressions_are_shown(tmp_path):
    before = {(F, c): "passed" for c in ("T-LOAN-01-a", "T-LOAN-02-a", "T-LOAN-03-a", "T-LOAN-04-a")}
    before[(F, "T-INV-20-a")] = "failed"                   # failed at the start: never shown
    after = {(F, "T-LOAN-01-a"): "failed", (F, "T-LOAN-02-a"): "failed", (F, "T-LOAN-03-a"): "failed",
             (F, "T-LOAN-04-a"): "passed", (F, "T-INV-20-a"): "failed"}
    repeat = {(F, "T-LOAN-01-a"): "failed", (F, "T-LOAN-02-a"): "passed", (F, "T-LOAN-03-a"): "failed"}
    r = Round(tmp_path, before, after, repeat=repeat, flaky=["T-LOAN-03-a"])
    junit(r.log_dir, *(make_testcase(f"test_t_loan_0{n}_a", "failure", "AssertionError: x") for n in (1, 2, 3)))
    text = r.text()
    assert "T-LOAN-01-a" in text                            # confirmed
    assert "T-LOAN-02-a" not in text                        # passed in a repetition
    assert "T-LOAN-03-a" not in text                        # flaky at the start
    assert "T-INV-20-a" not in text and "T-LOAN-04-a" not in text


@pytest.mark.parametrize("repeats", [0, 1])
def test_fewer_than_two_repetitions_is_not_confirmed(tmp_path, repeats):
    r = Round(tmp_path, {(F, "T-LOAN-01-a"): "passed"}, {(F, "T-LOAN-01-a"): "failed"}, repeats=repeats)
    assert r.text() == ""


def test_heldout_cases_are_never_shown(tmp_path):
    before = {(F, "T-LOAN-01-a"): "passed", ("heldout", "T-LOAN-01-b"): "passed"}
    r = Round(tmp_path, before, {(F, "T-LOAN-01-a"): "passed"})   # the round runs only the feedback set
    assert r.text() == ""


def test_missing_skipped_and_error_cases(tmp_path):
    before = {(F, c): "passed" for c in ("T-LOAN-05-a", "T-LOAN-06-a", "T-LOAN-07-a")}
    after = {(F, "T-LOAN-05-a"): "missing", (F, "T-LOAN-06-a"): "skipped", (F, "T-LOAN-07-a"): "error"}
    r = Round(tmp_path, before, after)
    junit(r.log_dir, make_testcase("test_t_loan_06_a", "skipped", "needs a later module"),
          make_testcase("test_t_loan_07_a", "error", "ImportError: cannot import name 'Svc' from 'lms.loans'"))
    assert r.text() == (
        f"{feedback.HEADER}\n"
        "- T-LOAN-05-a\n"
        f"  {feedback.MISSING}\n"
        "- T-LOAN-06-a\n"
        "  skipped: needs a later module\n"
        "- T-LOAN-07-a\n"
        "  error during setup or teardown: ImportError: cannot import name 'Svc' from 'lms.loans'\n"
    )


def test_identical_errors_are_merged(tmp_path):
    cases = ("T-LOAN-01-a", "T-LOAN-02-a", "T-RES-03-a")
    r = Round(tmp_path, {(F, c): "passed" for c in cases}, {(F, c): "failed" for c in cases})
    message = "ImportError: cannot import name 'lend' from 'lms.loans.service'"
    junit(r.log_dir, *(make_testcase(name_of(c), "failure", message) for c in cases))
    assert r.text() == f"{feedback.HEADER}\n- T-LOAN-01-a, T-LOAN-02-a, T-RES-03-a\n  {message}\n"


def test_parametrized_case_uses_its_first_failing_parameter(tmp_path):
    r = Round(tmp_path, {(F, "T-LOAN-04-b"): "passed"}, {(F, "T-LOAN-04-b"): "failed"})
    junit(r.log_dir, make_testcase("test_t_loan_04_b[2]", "failure", "assert 3 == 4"),
          make_testcase("test_t_loan_04_b[1]", "failure", "assert 2 == 3"), make_testcase("test_t_loan_04_b[0]"))
    assert "assert 2 == 3" in r.text() and "assert 3 == 4" not in r.text()


def test_no_junit_report_still_lists_the_case(tmp_path):
    r = Round(tmp_path, {(F, "T-LOAN-01-a"): "passed"}, {(F, "T-LOAN-01-a"): "failed"})
    assert r.text() == f"{feedback.HEADER}\n- T-LOAN-01-a\n  {feedback.NO_MESSAGE}\n"


def test_limits_per_test_total_lines_and_number_of_tests(tmp_path):
    cases = [f"T-LOAN-{n:02d}-a" for n in range(1, 21)]
    r = Round(tmp_path, {(F, c): "passed" for c in cases}, {(F, c): "failed" for c in cases})
    long_message = "\n".join(f"AssertionError line {k} of case" for k in range(10)) + "\n" + "x" * 500
    junit(r.log_dir, *(make_testcase(name_of(c), "failure", f"{c}: " + long_message, LONG_TEXT)
                       for c in cases))
    lines = r.text().splitlines()
    assert lines[0] == feedback.HEADER
    assert len(lines) <= feedback.MAX_LINES
    blocks = [ln for ln in lines if ln.startswith("- ")]
    assert len(blocks) <= feedback.MAX_TESTS
    shown = sum(len(b[2:].split(", ")) for b in blocks)
    assert lines[-1] == feedback.MORE.format(n=len(cases) - shown)
    index = [i for i, ln in enumerate(lines) if ln.startswith("- ")] + [len(lines) - 1]
    assert all(b - a <= feedback.MAX_LINES_PER_TEST for a, b in zip(index, index[1:]))
    assert all(len(ln) <= feedback.MAX_LINE_CHARS + 2 for ln in lines)


def test_same_input_gives_byte_identical_output(tmp_path):
    cases = ("T-LOAN-02-a", "T-LOAN-01-a")
    r = Round(tmp_path, {(F, c): "passed" for c in cases}, {(F, c): "failed" for c in cases})
    junit(r.log_dir, make_testcase("test_t_loan_02_a", "failure", "AttributeError: x", LONG_TEXT),
          make_testcase("test_t_loan_01_a", "failure", "AssertionError: y"))
    first = r.text()
    assert first == r.text()
    assert first.index("T-LOAN-01-a") < first.index("T-LOAN-02-a")     # sorted, not in report order
    cmd = [sys.executable, str(REPO / "experiments" / "feedback.py"), "--tests-before", str(r.before),
           "--tests-after", str(r.after), "--log-dir", str(r.log_dir)]
    for rep in r.repeats:
        cmd += ["--repeat", str(rep)]
    outputs = [subprocess.run(cmd, capture_output=True, check=True).stdout for _ in range(2)]
    assert outputs[0] == outputs[1]
    assert outputs[0].decode("utf-8").replace("\r\n", "\n") == first


def test_bad_csv_raises_value_error(tmp_path):
    bad = tmp_path / "tests.csv"
    bad.write_text("case,result\nT-LOAN-01-a,passed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        feedback.format_feedback(bad, bad, [], tmp_path)


def test_real_baseline_against_itself_gives_empty_text():
    """The frozen starting measurement compared with itself has no regression."""
    base = REPO / "results" / "baseline" / "final" / "v0-ai-baseline"
    repeats = [base / "tests_repeat1.csv", base / "tests_repeat2.csv"]
    assert feedback.format_feedback(base / "tests.csv", base / "tests.csv", repeats, base) == ""
