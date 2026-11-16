"""Tests of scripts/compare.py (ADR 003, D17-D21): thresholds, null values, incompatible inputs, tests, OpenAPI, two decisions."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FROZEN = [{"id": "S01", "tool": "ast", "rule": "long function"}, {"id": "S03", "tool": "ruff", "rule": "PLR0913"}]
BASE = {"mean_cc": 3.0, "mean_cognitive": 2.0, "mi_weighted": 40.0, "duplication_pct": 2.0, "smell_count": 10}


def analysis(root: Path, name: str, primary: dict | None = None, *, sloc: int = 1000, functions=("a", "b"),
             classes=("C",), schema: str = "1.0", frozen=None, smells=None, tools=None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    values = {**BASE, **(primary or {})}
    summary = {"label": name, "primary": values, "smell_counts": smells or {"S01": 4, "S03": 6}, "schema_version": schema,
               "frozen_smell_list": frozen or FROZEN, "secondary": {"sloc": sloc}, "tool_versions": tools or {"radon": "6"},
               "code_sha": "abc", "code_content_hash": "h", "analyzer_sha": "x", "image_id": "img"}
    (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    write_csv(folder / "functions.csv", ["unit_id", "qualname"], [[f"m.py::{f}::function::1", f] for f in functions])
    write_csv(folder / "classes.csv", ["unit_id", "qualname"], [[f"m.py::{c}::class::1", c] for c in classes])
    write_csv(folder / "modules.csv", ["module_no", "files", "sloc", "units", "mean_cc", "mean_cognitive", "mi_weighted",
                                       "smells", "smells_per_ksloc", "duplication_pct"],
              [["5", 3, sloc, 2, values["mean_cc"], values["mean_cognitive"], values["mi_weighted"], 4, 4.0, 1.0]])
    write_csv(folder / "levels.csv", ["level", "aggregation", "mean_cc", "mean_cognitive", "mi_weighted", "smells_per_ksloc",
                                      "duplication_pct"], [["complex", "module mean", values["mean_cc"], 2.0, 40.0, 4.0, 1.0]])
    write_csv(folder / "project.csv", ["metric", "value", "kind", "note"],
              [["mean_cc", values["mean_cc"], "primary", ""], ["classes", 1, "secondary", ""]])
    return folder


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def make_tests(path: Path, rows: list[tuple]) -> Path:
    """rows: (set, case, result[, module, type])"""
    write_csv(path, ["case", "module", "table", "type", "set", "result"],
              [[r[1], r[3] if len(r) > 3 else "5", "loans", r[4] if len(r) > 4 else "Normal", r[0], r[2]] for r in rows])
    return path


def run(tmp_path, before, after, *extra, out_name="out") -> tuple[int, dict]:
    out = tmp_path / out_name
    code = compare.main(["--before", str(before), "--after", str(after), "--out", str(out), *map(str, extra)])
    report = json.loads((out / "compare.json").read_text(encoding="utf-8")) if (out / "compare.json").exists() else {}
    return code, report


def fake_code(root: Path, name: str, paths: dict, files: dict | None = None) -> Path:
    """A tiny ``lms`` whose OpenAPI schema is ``paths`` (the real one needs the whole stack)."""
    pkg = root / name / "lms"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "class Settings:\n    def __init__(self, database_url=None):\n        pass\n\n"
        "class _App:\n    def openapi(self):\n        return {'info': {'title': 'x'}, 'paths': %r}\n\n"
        "def create_app(settings):\n    return _App()\n" % (paths,), encoding="utf-8")
    for rel, text in (files or {}).items():
        (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
        (pkg / rel).write_text(text, encoding="utf-8")
    return pkg.parent


# --- thresholds (D20) -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("metric,before,after,status", [
    ("mean_cc", 3.0, 2.99, "improved"), ("mean_cc", 3.0, 2.9901, "same"), ("mean_cc", 3.0, 3.01, "worse"),
    ("mean_cc", 3.0, 3.0099, "same"), ("mean_cc", 3.0157, 3.0057, "improved"),          # float noise must not matter
    ("mean_cognitive", 2.0, 1.99, "improved"), ("mean_cognitive", 2.0, 1.9901, "same"), ("mean_cognitive", 2.0, 2.01, "worse"),
    ("mi_weighted", 40.0, 40.1, "improved"), ("mi_weighted", 40.0, 40.0999, "same"), ("mi_weighted", 40.0, 39.9, "worse"),
    ("mi_weighted", 40.0, 39.9001, "same"), ("mi_weighted", 38.1508, 38.2508, "improved"),
    ("duplication_pct", 2.0, 1.95, "improved"), ("duplication_pct", 2.0, 1.9501, "same"), ("duplication_pct", 2.0, 2.05, "worse"),
    ("duplication_pct", 2.8751, 2.8251, "improved"),
    ("smell_count", 10, 9, "improved"), ("smell_count", 10, 10, "same"), ("smell_count", 10, 11, "worse"),
])
def test_primary_thresholds(tmp_path, metric, before, after, status):
    b = analysis(tmp_path, "b", {metric: before})
    a = analysis(tmp_path, "a", {metric: after})
    code, report = run(tmp_path, b, a)
    assert code == 0 and report["primary"][metric]["status"] == status


def test_values_are_rounded_to_four_decimals_before_the_comparison(tmp_path):
    # 3.00004 -> 3.0000 and 2.99006 -> 2.9901: the difference is 0.0099, below the threshold
    b = analysis(tmp_path, "b", {"mean_cc": 3.00004})
    a = analysis(tmp_path, "a", {"mean_cc": 2.99006})
    assert run(tmp_path, b, a)[1]["primary"]["mean_cc"]["status"] == "same"


def test_below_threshold_difference_is_the_same_not_a_small_improvement(tmp_path):
    b = analysis(tmp_path, "b")
    a = analysis(tmp_path, "a", {"mean_cc": 2.995, "mi_weighted": 40.05})
    report = run(tmp_path, b, a)[1]
    assert {v["status"] for v in report["primary"].values()} == {"same"}
    assert report["run_successful"]["value"] is False                      # nothing improved


# --- null values, incompatible inputs, missing data -----------------------------------------------------------

def test_null_primary_after_makes_the_run_invalid(tmp_path):
    b = analysis(tmp_path, "b")
    a = analysis(tmp_path, "a", {"mean_cognitive": None, "smell_count": 5})
    code, report = run(tmp_path, b, a)
    assert code == 0 and report["invalid"] == ["mean_cognitive"]
    assert report["primary"]["mean_cognitive"]["status"] == "invalid"
    assert report["run_successful"]["value"] is False and report["round_accepted"]["value"] is False
    assert report["run_successful"]["criteria"][0] == {"name": "valid", "ok": False,
                                                       "detail": "primary metric(s) null after refactoring: mean_cognitive"}


def test_null_primary_before_is_missing_data(tmp_path):
    b = analysis(tmp_path, "b", {"mi_weighted": None})
    a = analysis(tmp_path, "a")
    code, report = run(tmp_path, b, a)
    assert code == 4 and report["status"] == "missing data" and "mi_weighted" in report["reason"]


def test_different_schema_versions_exit_3(tmp_path):
    b = analysis(tmp_path, "b", schema="1.0")
    a = analysis(tmp_path, "a", schema="1.1")
    code, report = run(tmp_path, b, a)
    assert code == 3 and report["status"] == "incompatible inputs" and "schema versions" in report["reason"]


def test_different_frozen_lists_exit_3(tmp_path):
    b = analysis(tmp_path, "b")
    a = analysis(tmp_path, "a", frozen=FROZEN[:1])
    assert run(tmp_path, b, a)[0] == 3


def test_previous_best_with_another_list_exits_3(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a")
    best = analysis(tmp_path, "best", frozen=FROZEN[:1])
    assert run(tmp_path, b, a, "--previous-best", best)[0] == 3


def test_missing_summary_is_missing_data(tmp_path):
    b = analysis(tmp_path, "b")
    (tmp_path / "empty").mkdir()
    code, report = run(tmp_path, b, tmp_path / "empty")
    assert code == 4 and "summary.json" in report["reason"]


def test_tests_csv_without_columns_is_missing_data(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a")
    bad = tmp_path / "bad.csv"
    bad.write_text("x,y\n1,2\n", encoding="utf-8")
    assert run(tmp_path, b, a, "--tests-before", bad, "--tests-after", bad)[0] == 4


def test_usage_errors_exit_2(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a")
    t = make_tests(tmp_path / "t.csv", [("feedback", "T-A-01-a", "passed")])
    assert run(tmp_path, b, tmp_path / "nowhere")[0] == 2                          # not a folder
    assert run(tmp_path, b, a, "--tests-before", t)[0] == 2                        # tests go in pairs
    assert run(tmp_path, b, a, "--before-code", tmp_path)[0] == 2                  # code folders go in pairs
    assert run(tmp_path, b, a, "--tests-after-repeat", t)[0] == 2
    with pytest.raises(SystemExit) as exc:
        compare.main(["--before", str(b)])
    assert exc.value.code == 2


# --- tests (D17-D19) ----------------------------------------------------------------------------------------------

SET_F, SET_H = "feedback", "heldout"


def test_regressions_new_passes_and_lost_cases(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a")
    tb = make_tests(tmp_path / "tb.csv", [
        (SET_F, "T-A-01-a", "passed"), (SET_F, "T-A-02-a", "passed"), (SET_F, "T-A-03-a", "passed"),
        (SET_F, "T-A-04-a", "failed"), (SET_F, "T-A-05-a", "failed"), (SET_F, "T-A-06-a", "passed"),
        (SET_H, "T-A-01-b", "passed"), (SET_H, "T-A-07-b", "passed")])
    ta = make_tests(tmp_path / "ta.csv", [
        (SET_F, "T-A-01-a", "passed"), (SET_F, "T-A-02-a", "failed"), (SET_F, "T-A-03-a", "missing"),
        (SET_F, "T-A-04-a", "passed"), (SET_F, "T-A-05-a", "failed"),                    # T-A-06-a is not in the file at all
        (SET_H, "T-A-01-b", "error"), (SET_H, "T-A-07-b", "passed"), (SET_H, "T-A-99-b", "passed")])
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta)
    tests = report["tests"]
    assert code == 0
    assert {(r["set"], r["case"]) for r in tests["regressions"]} == {
        (SET_F, "T-A-02-a"), (SET_F, "T-A-03-a"), (SET_F, "T-A-06-a"), (SET_H, "T-A-01-b")}
    assert [(n["set"], n["case"]) for n in tests["new_passing"]] == [(SET_F, "T-A-04-a")]
    assert {(c["set"], c["case"]) for c in tests["lost_cases"]} == {(SET_F, "T-A-03-a"), (SET_F, "T-A-06-a")}
    assert tests["sets"][SET_F]["baseline_failing"] == 2 and tests["sets"][SET_F]["baseline_failing_still"] == 1
    assert tests["sets"][SET_H]["new_cases"] == 1
    assert tests["regressions_by_module"] == {"5": 4}
    assert report["run_successful"]["value"] is False and report["round_accepted"]["value"] is False


def test_failing_at_the_start_is_not_a_regression(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"smell_count": 5})
    tb = make_tests(tmp_path / "tb.csv", [(SET_F, "T-INV-20-a", "failed"), (SET_H, "T-A-01-b", "passed")])
    ta = make_tests(tmp_path / "ta.csv", [(SET_F, "T-INV-20-a", "failed"), (SET_H, "T-A-01-b", "passed")])
    cb = fake_code(tmp_path, "cb", {"/a": {}})
    ca = fake_code(tmp_path, "ca", {"/a": {}})
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta, "--before-code", cb, "--after-code", ca)
    assert report["tests"]["regression_count"] == 0 and report["tests"]["sets"][SET_F]["baseline_failing_still"] == 1
    assert report["run_successful"]["value"] is True


def test_flaky_tests_are_left_out(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a")
    tb = make_tests(tmp_path / "tb.csv", [(SET_F, "T-A-01-a", "passed"), (SET_F, "T-A-02-a", "passed")])
    ta = make_tests(tmp_path / "ta.csv", [(SET_F, "T-A-01-a", "failed"), (SET_F, "T-A-02-a", "passed")])
    flaky = tmp_path / "flaky.txt"
    flaky.write_text("# unstable at the start\nT-A-01-a\n", encoding="utf-8")
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta, "--flaky", flaky)
    assert report["tests"]["regression_count"] == 0
    assert report["tests"]["excluded_flaky"] == [{"set": SET_F, "case": "T-A-01-a"}]
    assert report["tests"]["sets"][SET_F]["before_passed"] == 1


def test_a_regression_must_fail_in_both_repetitions(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a")
    tb = make_tests(tmp_path / "tb.csv", [(SET_F, f"T-A-0{n}-a", "passed") for n in (1, 2, 3)])
    ta = make_tests(tmp_path / "ta.csv", [(SET_F, f"T-A-0{n}-a", "failed") for n in (1, 2, 3)])
    r1 = make_tests(tmp_path / "r1.csv", [(SET_F, "T-A-01-a", "failed"), (SET_F, "T-A-02-a", "passed"), (SET_F, "T-A-03-a", "failed")])
    r2 = make_tests(tmp_path / "r2.csv", [(SET_F, "T-A-01-a", "failed"), (SET_F, "T-A-02-a", "failed"), (SET_F, "T-A-03-a", "passed")])
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta,
                       "--tests-after-repeat", r1, "--tests-after-repeat", r2)
    tests = report["tests"]
    assert [r["case"] for r in tests["regressions"]] == ["T-A-01-a"] and tests["regressions"][0]["confirmed"] is True
    assert {r["case"] for r in tests["recovered_in_repeat"]} == {"T-A-02-a", "T-A-03-a"}
    assert tests["regressions_confirmed"] == 1 and tests["regressions_unconfirmed"] == 0


def test_without_repetitions_a_regression_is_counted_but_not_confirmed(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a")
    tb = make_tests(tmp_path / "tb.csv", [(SET_F, "T-A-01-a", "passed")])
    ta = make_tests(tmp_path / "ta.csv", [(SET_F, "T-A-01-a", "failed")])
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta)
    assert report["tests"]["regressions_unconfirmed"] == 1 and report["tests"]["regression_count"] == 1
    assert any("not confirmed" in w for w in report["warnings"])
    assert report["round_accepted"]["value"] is False


def test_a_set_that_was_not_run_is_not_compared(tmp_path):
    # an Iterative round runs only the feedback set: the missing held-out rows are not regressions
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"smell_count": 5})
    tb = make_tests(tmp_path / "tb.csv", [(SET_F, "T-A-01-a", "passed"), (SET_H, "T-A-01-b", "passed")])
    ta = make_tests(tmp_path / "ta.csv", [(SET_F, "T-A-01-a", "passed")])
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta)
    assert report["tests"]["sets_not_run"] == [SET_H] and report["tests"]["regression_count"] == 0
    assert report["round_accepted"]["criteria"][1]["ok"] is True
    assert report["run_successful"]["value"] is None                      # success needs both sets
    assert "held-out" in " ".join(report["run_successful"]["reasons"]) or "heldout" in " ".join(report["run_successful"]["reasons"])


def test_missing_case_in_a_run_set_is_a_regression_and_a_timeout_run_fails(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"smell_count": 5})
    tb = make_tests(tmp_path / "tb.csv", [(SET_F, "T-A-01-a", "passed"), (SET_H, "T-A-01-b", "passed")])
    ta = make_tests(tmp_path / "ta.csv", [(SET_F, "T-A-01-a", "missing"), (SET_H, "T-A-01-b", "missing")])   # a timed-out set
    report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta)[1]
    assert report["tests"]["regression_count"] == 2 and len(report["tests"]["lost_cases"]) == 2
    assert report["run_successful"]["value"] is False


# --- decisions ------------------------------------------------------------------------------------------------------

def test_without_tests_and_code_a_decision_is_null_unless_it_already_fails(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"smell_count": 5})
    report = run(tmp_path, b, a)[1]
    assert report["run_successful"]["value"] is None and report["round_accepted"]["value"] is None
    assert report["tests"] is None and report["openapi"]["checked"] is False
    worse = analysis(tmp_path, "w", {"smell_count": 12})
    assert run(tmp_path, b, worse, out_name="o2")[1]["run_successful"]["value"] is False


def test_both_decisions_true_when_everything_passes(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"mean_cc": 2.5, "smell_count": 8})
    rows = [(SET_F, "T-A-01-a", "passed"), (SET_H, "T-A-01-b", "passed")]
    tb, ta = make_tests(tmp_path / "tb.csv", rows), make_tests(tmp_path / "ta.csv", rows)
    cb = fake_code(tmp_path, "cb", {"/a": {}})
    ca = fake_code(tmp_path, "ca", {"/a": {}})
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta, "--before-code", cb, "--after-code", ca)
    assert code == 0 and report["run_successful"]["value"] is True and report["round_accepted"]["value"] is True
    assert report["openapi"]["changed"] is False and report["run_successful"]["reasons"] == []


def test_decisions_come_out_differently(tmp_path):
    """round_accepted: nothing worse; run_successful also needs an improvement. And the other way round with --previous-best."""
    rows = [(SET_F, "T-A-01-a", "passed")]
    tb, ta = make_tests(tmp_path / "tb.csv", rows), make_tests(tmp_path / "ta.csv", rows)
    cb = fake_code(tmp_path, "cb", {"/a": {}})
    ca = fake_code(tmp_path, "ca", {"/a": {}})
    code_args = ["--tests-before", tb, "--tests-after", ta, "--before-code", cb, "--after-code", ca]
    b = analysis(tmp_path, "b")
    # 1. no change at all: the round is accepted, the run is not successful
    same = analysis(tmp_path, "same")
    report = run(tmp_path, b, same, *code_args, out_name="o1")[1]
    assert report["round_accepted"]["value"] is True and report["run_successful"]["value"] is False
    assert "improved: none" in " ".join(report["run_successful"]["reasons"])
    # 2. better than the start but worse than the previous best: run_successful true, round_accepted false
    rows_both = [(SET_F, "T-A-01-a", "passed"), (SET_H, "T-A-01-b", "passed")]
    tb2, ta2 = make_tests(tmp_path / "tb2.csv", rows_both), make_tests(tmp_path / "ta2.csv", rows_both)
    args2 = ["--tests-before", tb2, "--tests-after", ta2, "--before-code", cb, "--after-code", ca]
    best = analysis(tmp_path, "best", {"mean_cc": 2.0})
    after = analysis(tmp_path, "after", {"mean_cc": 2.5})
    report = run(tmp_path, b, after, *args2, "--previous-best", best, out_name="o2")[1]
    assert report["run_successful"]["value"] is True
    assert report["round_accepted"]["value"] is False
    assert "previous best" in " ".join(report["round_accepted"]["reasons"])
    assert report["primary_vs_previous_best"]["mean_cc"]["status"] == "worse"
    # 3. no change and both sets run: round accepted, run not successful
    report = run(tmp_path, b, same, *args2, out_name="o3")[1]
    assert report["round_accepted"]["value"] is True and report["run_successful"]["value"] is False
    assert "improved: none" in " ".join(report["run_successful"]["reasons"])


def test_worse_primary_metric_fails_both(tmp_path):
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"mean_cc": 2.0, "duplication_pct": 2.5})
    report = run(tmp_path, b, a)[1]
    assert report["run_successful"]["value"] is False and report["round_accepted"]["value"] is False
    assert any("worse: duplication_pct" in r for r in report["run_successful"]["reasons"])


# --- OpenAPI, change size, SLOC, inventory (D21) -----------------------------------------------------------------

def test_changed_openapi_schema_is_never_accepted(tmp_path):
    rows = [(SET_F, "T-A-01-a", "passed"), (SET_H, "T-A-01-b", "passed")]
    tb, ta = make_tests(tmp_path / "tb.csv", rows), make_tests(tmp_path / "ta.csv", rows)
    cb = fake_code(tmp_path, "cb", {"/a": {}})
    ca = fake_code(tmp_path, "ca", {"/a": {}, "/b": {}})
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"mean_cc": 2.0, "smell_count": 1, "mi_weighted": 50.0})
    code, report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta, "--before-code", cb, "--after-code", ca)
    assert report["openapi"]["changed"] is True and report["openapi"]["before_hash"] != report["openapi"]["after_hash"]
    assert report["run_successful"]["value"] is False and report["round_accepted"]["value"] is False
    assert any("OpenAPI schema changed" in r for r in report["run_successful"]["reasons"])


def test_openapi_hash_does_not_depend_on_key_order(tmp_path):
    one = fake_code(tmp_path, "one", {"/a": {}, "/b": {}})
    two = fake_code(tmp_path, "two", {"/b": {}, "/a": {}})
    assert compare.openapi_hash(one)[0] == compare.openapi_hash(two)[0] and compare.openapi_hash(one)[0]


def test_code_that_cannot_build_its_schema_counts_as_changed(tmp_path):
    cb = fake_code(tmp_path, "cb", {"/a": {}})
    broken = tmp_path / "broken" / "lms"
    broken.mkdir(parents=True)
    (broken / "__init__.py").write_text("raise ImportError('gone')\n", encoding="utf-8")
    b, a = analysis(tmp_path, "b"), analysis(tmp_path, "a", {"smell_count": 1})
    report = run(tmp_path, b, a, "--before-code", cb, "--after-code", tmp_path / "broken")[1]
    assert report["openapi"]["changed"] is True and "gone" in report["openapi"]["error"]
    assert report["run_successful"]["value"] is False
    # but a starting code that cannot build it is missing data
    assert run(tmp_path, b, a, "--before-code", tmp_path / "broken", "--after-code", cb, out_name="o2")[0] == 4


def test_change_size_counts_lines_and_files_of_the_measured_python_only(tmp_path):
    cb = fake_code(tmp_path, "cb", {"/a": {}}, {"a.py": "a\nb\nc\n", "gone.py": "1\n", "same.py": "s\n",
                                                 "web/page.py": "x\n", "notes.txt": "n\n"})
    ca = fake_code(tmp_path, "ca", {"/a": {}}, {"a.py": "a\nB\nc\nd\n", "new.py": "1\n2\n", "same.py": "s\n",
                                                 "web/page.py": "y\ny\n", "notes.txt": "m\n"})
    size = compare.change_size(cb, ca)
    # a.py: +2 -1; gone.py: -1; new.py: +2 (the __init__.py files differ in nothing); web/ and .txt are not measured
    assert size == {"lines_added": 4, "lines_removed": 2, "files_changed": 1, "files_added": 1, "files_removed": 1}


def test_change_size_ignores_line_ending_differences(tmp_path):
    cb = fake_code(tmp_path, "cb", {"/a": {}}, {"a.py": "a\nb\n"})
    ca = fake_code(tmp_path, "ca", {"/a": {}}, {"a.py": "a\nb\n"})
    (ca / "lms" / "a.py").write_bytes(b"a\r\nb\r\n")
    assert compare.change_size(cb, ca)["files_changed"] == 0


def test_sloc_drop_above_15_percent_is_only_a_warning(tmp_path):
    b = analysis(tmp_path, "b", sloc=1000)
    a = analysis(tmp_path, "a", {"smell_count": 5}, sloc=800)
    rows = [(SET_F, "T-A-01-a", "passed"), (SET_H, "T-A-01-b", "passed")]
    tb, ta = make_tests(tmp_path / "tb.csv", rows), make_tests(tmp_path / "ta.csv", rows)
    cb = fake_code(tmp_path, "cb", {"/a": {}})
    ca = fake_code(tmp_path, "ca", {"/a": {}})
    report = run(tmp_path, b, a, "--tests-before", tb, "--tests-after", ta, "--before-code", cb, "--after-code", ca)[1]
    assert report["sloc"]["drop_pct"] == 20.0 and report["sloc"]["warning"] is True
    assert any("SLOC dropped" in w for w in report["warnings"])
    assert report["run_successful"]["value"] is True                      # a warning, not a failure
    exactly = run(tmp_path, b, analysis(tmp_path, "e", {"smell_count": 5}, sloc=850), out_name="o2")[1]
    assert exactly["sloc"]["drop_pct"] == 15.0 and exactly["sloc"]["warning"] is False


def test_inventory_counts_removed_units_by_name_not_by_file(tmp_path):
    b = analysis(tmp_path, "b", functions=("a", "b", "c"), classes=("C",))
    a = analysis(tmp_path, "a", functions=("a", "c", "new"), classes=())
    inv = run(tmp_path, b, a)[1]["inventory"]
    assert inv["removed_by_name"] == 2 and inv["added_by_name"] == 1 and inv["units_before"] == 4
    assert inv["removed"] == ["class C", "function b"] and inv["removed_share_pct"] == 50.0


# --- output files -------------------------------------------------------------------------------------------------

def test_compare_csv_and_determinism(tmp_path):
    b = analysis(tmp_path, "b")
    a = analysis(tmp_path, "a", {"mean_cc": 2.5, "smell_count": 8}, smells={"S01": 3, "S03": 5})
    run(tmp_path, b, a, out_name="o1")
    run(tmp_path, b, a, out_name="o2")
    for name in ("compare.json", "compare.csv"):
        assert (tmp_path / "o1" / name).read_bytes() == (tmp_path / "o2" / name).read_bytes()
    with (tmp_path / "o1" / "compare.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == list(compare.CSV_COLUMNS)
    primary = {r["metric"]: r for r in rows if r["kind"] == "primary"}
    assert primary["mean_cc"]["status"] == "improved" and primary["mean_cc"]["delta"] == "-0.5000"
    assert primary["smell_count"]["delta"] == "-2" or primary["smell_count"]["delta"] == "-2.0000"
    assert {r["scope"] for r in rows if r["kind"] == "smell"} == {"S01", "S03"}
    assert any(r["kind"] == "module" and r["scope"] == "5" and r["metric"] == "mean_cc" for r in rows)
    assert any(r["kind"] == "level" for r in rows) and any(r["kind"] == "secondary" and r["metric"] == "classes" for r in rows)


def test_tool_version_difference_is_a_warning(tmp_path):
    b = analysis(tmp_path, "b", tools={"radon": "6"})
    a = analysis(tmp_path, "a", tools={"radon": "7"})
    assert "tool versions differ between before and after" in run(tmp_path, b, a)[1]["warnings"]


def test_comparing_a_real_result_with_itself():
    trial = REPO / "results" / "baseline" / "trial" / "main-465b44f"
    if not trial.is_dir():
        pytest.skip("trial result not present")
    import tempfile
    with tempfile.TemporaryDirectory() as out:
        code = compare.main(["--before", str(trial), "--after", str(trial), "--out", out])
        report = json.loads((Path(out) / "compare.json").read_text(encoding="utf-8"))
    assert code == 0 and {v["status"] for v in report["primary"].values()} == {"same"}
    assert report["inventory"]["removed_by_name"] == 0 and report["sloc"]["drop_pct"] == 0.0
    assert report["run_successful"]["value"] is None or report["run_successful"]["value"] is False


def test_real_openapi_hash_is_stable():
    pytest.importorskip("fastapi")
    generated = REPO / "dataset" / "lms" / "generated"
    one, err = compare.openapi_hash(generated)
    assert err is None and len(one) == 64 and compare.openapi_hash(generated)[0] == one
