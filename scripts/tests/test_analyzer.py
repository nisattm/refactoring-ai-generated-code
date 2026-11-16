"""Integration tests of the analyzer on the sample project (needs the measurement tools: run in the Docker image).

The sample project ``fixtures/analyzer/sample/lms`` holds one example of each smell. The expected counts
below were derived by reading the code, not copied from the output.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "analyzer" / "sample"
sys.path.insert(0, str(SCRIPTS))

from analyzer import SCHEMA_VERSION  # noqa: E402
from analyzer.report import load_schema  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ruff") is None or shutil.which("jscpd") is None,
                                reason="measurement tools are not installed (run inside the Docker image)")


def analyze(code: Path, out: Path, env: dict | None = None, *extra: str, label: str = "sample"):
    cmd = [sys.executable, str(SCRIPTS / "analyze.py"), "--code", str(code), "--out", str(out), "--label", label, *extra]
    return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False)


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summary(out: Path) -> dict:
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def copy_sample(tmp_path: Path) -> Path:
    target = tmp_path / "code"
    shutil.copytree(SAMPLE, target)
    return target


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("sample-out")
    proc = analyze(SAMPLE, out, None, "--with-secondary")
    return {"out": out, "proc": proc, "summary": summary(out) if (out / "summary.json").exists() else None}


# --- known counts (D8, D9) -------------------------------------------------------------------------------------

def test_run_succeeds(run):
    assert run["proc"].returncode == 0, run["proc"].stderr
    assert run["summary"]["failures"] == []


def test_smell_counts_per_id_and_total(run):
    # S09: PLR0916 (complex_condition), SIM102 (nested_if), SIM105 (swallow);
    # S11: label() and magic(); magic() has two comparisons but counts once (D9);
    # S19: swallow() has BLE001 and S110 and counts once; S23: bypass() (ANN401 x2, cast, type: ignore) once + casting()
    expected = {"S01": 1, "S02": 1, "S03": 2, "S07": 2, "S09": 3, "S10": 1, "S11": 2, "S18": 1, "S19": 1, "S20": 1,
                "S21": 1, "S22": 1, "S23": 2}
    s = run["summary"]
    assert s["smell_counts"] == expected
    assert s["primary"]["smell_count"] == sum(expected.values()) == 19


def test_same_smell_at_the_same_place_counts_once(run):
    smells = rows(run["out"] / "smells.csv")
    magic = [r for r in smells if r["s_id"] == "S11" and r["unit"] == "magic"]
    assert len(magic) == 2 and sorted(r["counted"] for r in magic) == ["0", "1"]
    bypass = [r for r in smells if r["s_id"] == "S23" and r["unit"] == "bypass"]
    assert len(bypass) == 4 and sum(int(r["counted"]) for r in bypass) == 1          # ANN401 x2, PGH003, cast(
    assert run["summary"]["secondary"]["raw_findings_by_rule"]["ruff:PLR2004"] == 3


def test_route_handlers_are_reported_separately(run):
    smells = [r for r in rows(run["out"] / "smells.csv") if r["s_id"] == "S03"]
    assert {r["unit"]: r["route_handler"] for r in smells} == {"list_loans": "1", "too_many": "0"}
    secondary = run["summary"]["secondary"]
    assert (secondary["s03_route_handlers"], secondary["s03_other"]) == (1, 1)


def test_ignore_noqa_counts_the_suppressed_unused_import(run):
    # `import json  # noqa: F401` is reported although it is suppressed, and the suppression is counted
    f401 = [r for r in rows(run["out"] / "smells.csv") if r["rule"] == "F401"]
    assert [(r["path"], r["line"]) for r in f401] == [("loans/service.py", "3")]
    assert run["summary"]["secondary"]["suppressions"] == {"noqa": 1, "type_ignore": 1, "pylint_disable": 0, "jscpd_ignore": 0}


def test_cycle_counts_with_and_without_function_level_imports(run):
    secondary = run["summary"]["secondary"]
    assert run["summary"]["smell_counts"]["S18"] == 1
    assert secondary["s18_without_function_level_imports"] == 1 and secondary["s18_files_in_cycles"] == 2
    cycles = [r for r in rows(run["out"] / "architecture.csv") if r["kind"] == "file_cycle_all_imports"]
    assert [r["note"] for r in cycles] == ["loans/a.py;loans/b.py"]


def test_excluded_files_are_not_measured(run):
    paths = {r["path"] for r in rows(run["out"] / "files.csv")}
    assert not any(p.startswith(("web/", "tests/")) or p.endswith("test_service.py") for p in paths)
    assert run["summary"]["secondary"]["files_excluded_by_d1"] == 3
    assert run["summary"]["secondary"]["files"] == 15


# --- metrics (D4-D7, D12, D15) ---------------------------------------------------------------------------------

def test_function_rows(run):
    by_id = {r["unit_id"]: r for r in rows(run["out"] / "functions.csv")}
    deep = by_id["loans/service.py::deep::function::1"]
    assert (deep["cc"], deep["cognitive"], deep["nesting"], deep["params"], deep["rank"]) == ("7", "21", "6", "1", "B")
    assert by_id["loans/service.py::complex_condition::function::1"]["cc"] == "7"       # 1 + if + 5 boolean operators
    assert by_id["api/loans.py::list_loans::function::1"]["route_handler"] == "1"
    assert by_id["loans/service.py::long_function::function::1"]["lines"] == "53"
    assert by_id["loans/service.py::Big.m01::method::1"]["kind"] == "method"
    assert by_id["loans/service.py::deep::function::1"]["module_name"] == "Loans and returns"


def test_primary_metrics_equal_the_means_of_the_unit_rows(run):
    units = rows(run["out"] / "functions.csv")
    cc = [int(r["cc"]) for r in units]
    cog = [int(r["cognitive"]) for r in units if r["cognitive"]]
    files = rows(run["out"] / "files.csv")
    weighted = sum(float(r["mi"]) * int(r["sloc"]) for r in files) / sum(int(r["sloc"]) for r in files)
    p = run["summary"]["primary"]
    assert p["mean_cc"] == pytest.approx(sum(cc) / len(cc), abs=1e-4)
    assert p["mean_cognitive"] == pytest.approx(sum(cog) / len(cog), abs=1e-4)
    assert p["mi_weighted"] == pytest.approx(weighted, abs=1e-3)       # MI is weighted by SLOC, not the plain mean
    assert run["summary"]["secondary"]["mi_plain_mean"] != p["mi_weighted"]
    assert run["summary"]["secondary"]["cc_units"] == len(cc)


def test_class_rows(run):
    classes = {r["qualname"]: r for r in rows(run["out"] / "classes.csv")}
    assert {n: c["class_kind"] for n, c in classes.items()} == {
        "Base": "orm", "Loan": "orm", "Status": "enum", "LoanIn": "schema", "Helper": "plain", "Big": "plain"}
    big = classes["Big"]
    assert (big["nom"], big["wmc"], big["lcom4"], big["rfc"]) == ("16", "16", "16", "16")
    assert (classes["Base"]["dit"], classes["Loan"]["dit"], classes["Base"]["noc"]) == ("1", "2", "1")
    assert run["summary"]["secondary"]["classes_by_kind"] == {"enum": 1, "orm": 2, "plain": 2, "schema": 1}


def test_duplication(run):
    clones = rows(run["out"] / "duplication.csv")
    assert len(clones) == 1 and {clones[0]["file_a"], clones[0]["file_b"]} == {"reservations/dup_a.py", "reservations/dup_b.py"}
    assert run["summary"]["primary"]["duplication_pct"] > 0
    reservations = next(r for r in rows(run["out"] / "modules.csv") if r["module_no"] == "6")
    assert float(reservations["duplication_pct"]) == 100.0           # both files of the module are one clone


# --- mapping: modules, unassigned, not generated (D2) ----------------------------------------------------------

def test_modules_rows(run):
    modules = rows(run["out"] / "modules.csv")
    assert [r["module_no"] for r in modules] == [str(n) for n in range(1, 30)] + ["unassigned"]
    status = {r["module_no"]: r["status"] for r in modules}
    assert status["29"] == "not generated" and status["1"] == "generated" and status["unassigned"] == "unassigned"
    generated = {n for n, s in status.items() if s == "generated"}
    assert generated == {"1", "5", "6", "14"}
    row29 = next(r for r in modules if r["module_no"] == "29")
    assert row29["mean_cc"] == "" and row29["files"] == "0"            # no mean is computed, no crash
    unassigned = next(r for r in modules if r["module_no"] == "unassigned")
    assert unassigned["files"] == "2" and unassigned["level"] == ""
    assert 0 < run["summary"]["unassigned_sloc_pct"] < 5 and run["summary"]["secondary"]["module_stats_valid"] is True
    assert run["summary"]["secondary"]["modules_not_generated"][-1] == "29"


def test_levels_rows(run):
    levels = rows(run["out"] / "levels.csv")
    labels = [(r["level"], r["aggregation"]) for r in levels]
    assert ("complex", "module mean") in labels and ("complex 15-29", "pooled units") in labels
    simple = next(r for r in levels if r["level"] == "simple" and r["aggregation"] == "module mean")
    assert simple["note"].startswith("descriptive") and simple["modules"] == "1"       # only module 1 exists in the sample
    modules = {r["module_no"]: r for r in rows(run["out"] / "modules.csv")}
    medium = next(r for r in levels if r["level"] == "medium" and r["aggregation"] == "module mean")
    assert float(medium["mean_cc"]) == pytest.approx(float(modules["14"]["mean_cc"]), abs=1e-4)   # mean of the module means


def test_router_view_is_written_with_secondary(run):
    router = rows(run["out"] / "modules_router.csv")
    assert any(r["module_no"] == "api/reports.py" for r in router) and any(r["module_no"] == "unassigned" for r in router)


# --- records and schema (D14, D24, D25) ------------------------------------------------------------------------

def test_summary_fields(run):
    s = run["summary"]
    for key in ("primary", "smell_counts", "secondary", "frozen_smell_list", "unassigned_sloc_pct", "code_sha",
                "code_content_hash", "analyzer_sha", "image_id", "tool_versions", "schema_version", "started_at",
                "duration_s"):
        assert key in s
    assert set(s["primary"]) == {"mean_cc", "mean_cognitive", "mi_weighted", "duplication_pct", "smell_count"}
    assert s["schema_version"] == SCHEMA_VERSION and len(s["code_content_hash"]) == 64
    assert [x["id"] for x in s["frozen_smell_list"]][0] == "S01"
    assert s["tool_versions"]["radon"] and s["tool_versions"]["jscpd"]
    assert json.loads((run["out"] / "tool_versions.json").read_text()) == s["tool_versions"]


def test_csv_headers_follow_the_schema(run):
    schema = load_schema()
    for name, spec in schema["files"].items():
        path = run["out"] / name
        if name == "modules_router.csv" or path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                header = next(csv.reader(handle))
            assert header == [c["name"] for c in spec["columns"]], name
            for row in rows(path):
                assert row["run_label"] == "sample" and row["schema_version"] == SCHEMA_VERSION
    assert {n for n in schema["files"]} <= {p.name for p in run["out"].iterdir()}


def test_numbers_have_four_decimals_and_a_decimal_point(run):
    for row in rows(run["out"] / "functions.csv"):
        if row["halstead_volume"]:
            assert len(row["halstead_volume"].split(".")[1]) == 4


def test_same_code_gives_identical_files(run, tmp_path):
    again = tmp_path / "again"
    assert analyze(SAMPLE, again, None, "--with-secondary").returncode == 0
    for path in sorted(run["out"].iterdir()):
        if path.is_file() and path.name != "summary.json":
            assert path.read_bytes() == (again / path.name).read_bytes(), path.name
    drop = ("started_at", "duration_s", "tool_seconds")
    one = {k: v for k, v in run["summary"].items() if k not in drop}
    two = {k: v for k, v in summary(again).items() if k not in drop}
    assert one == two


def test_crlf_checkout_gives_the_same_result(run, tmp_path):
    code = copy_sample(tmp_path)
    for path in code.rglob("*.py"):
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    out = tmp_path / "crlf"
    assert analyze(code, out).returncode == 0
    assert summary(out)["code_content_hash"] == run["summary"]["code_content_hash"]
    assert (out / "functions.csv").read_bytes() == (run["out"] / "functions.csv").read_bytes()


# --- exit codes (D13) ------------------------------------------------------------------------------------------

def test_usage_errors_exit_with_2(tmp_path):
    assert analyze(tmp_path, tmp_path / "o").returncode == 2                            # no lms/ package
    assert subprocess.run([sys.executable, str(SCRIPTS / "analyze.py")], capture_output=True).returncode == 2
    assert subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), "--code", str(SAMPLE)],
                          capture_output=True).returncode == 2                           # --out missing


def test_missing_tool_gives_exit_4_and_a_null_metric(tmp_path):
    out = tmp_path / "o"
    proc = analyze(SAMPLE, out, {"ANALYZER_CMD_RUFF": str(tmp_path / "no-such-ruff")})
    assert proc.returncode == 4
    s = summary(out)
    assert [f["tool"] for f in s["failures"]] == ["ruff"] and s["failures"][0]["kind"] == "tool"
    assert s["primary"]["smell_count"] is None
    assert s["smell_counts"]["S03"] is None and s["smell_counts"]["S01"] == 1       # AST smells are still measured
    assert s["primary"]["mean_cc"] is not None and s["primary"]["duplication_pct"] is not None


def test_file_set_mismatch_gives_exit_4(tmp_path):
    fake = tmp_path / "fake_jscpd.py"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if '--version' in args:\n"
        "    print('fake 0'); sys.exit(0)\n"
        "out = pathlib.Path(args[args.index('--output') + 1]); out.mkdir(parents=True, exist_ok=True)\n"
        "total = {'clones': 0, 'duplicatedLines': 0, 'lines': 0, 'percentage': 0, 'sources': 0}\n"
        "(out / 'jscpd-report.json').write_text(json.dumps({'statistics': {'total': total}, 'duplicates': []}))\n"
        "print('Top files:\\n  TOKENS LINES SIZE CX DUP% PATH')\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    out = tmp_path / "o"
    proc = analyze(SAMPLE, out, {"ANALYZER_CMD_JSCPD": str(fake)})                      # reads none of the files
    assert proc.returncode == 4
    s = summary(out)
    failure = s["failures"][0]
    assert failure["tool"] == "jscpd" and failure["kind"] == "fileset" and "loans/service.py" in failure["files"]
    assert s["primary"]["duplication_pct"] is None and s["primary"]["smell_count"] == 19


def test_syntax_error_gives_exit_4_and_null_primaries(tmp_path):
    code = copy_sample(tmp_path)
    (code / "lms" / "core" / "broken.py").write_text("def (:\n", encoding="utf-8")
    out = tmp_path / "o"
    assert analyze(code, out).returncode == 4
    s = summary(out)
    assert s["failures"][0]["tool"] == "ast" and s["failures"][0]["files"] == ["core/broken.py"]
    assert all(v is None for v in s["primary"].values())
    broken = next(r for r in rows(out / "files.csv") if r["path"] == "core/broken.py")
    assert broken["parse_error"].startswith("SyntaxError")


def test_unassigned_share_above_5_percent_marks_module_statistics_invalid(tmp_path):
    code = copy_sample(tmp_path)
    folder = code / "lms" / "newfolder"
    folder.mkdir()
    (folder / "big.py").write_text("".join(f"value_{n} = {n}\n" for n in range(60)), encoding="utf-8")
    out = tmp_path / "o"
    assert analyze(code, out).returncode == 0
    s = summary(out)
    assert s["unassigned_sloc_pct"] > 5 and s["secondary"]["module_stats_valid"] is False
    assert {r["valid"] for r in rows(out / "modules.csv")} == {"0"}
