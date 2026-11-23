"""Tests of the experiment dashboard (experiments/dashboard.py): it reads what the engine writes, shows a running
call live, points to where a run went wrong and compares the approaches. Runs made with the fake Claude."""

from __future__ import annotations

import json
import shutil
import sys
import threading
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests" / "fixtures" / "experiments"))

import support  # noqa: E402
from support import quality  # noqa: E402

sys.path.insert(0, str(SCRIPTS.parent / "experiments"))
import dashboard  # noqa: E402
import run_iterative  # noqa: E402
import run_single  # noqa: E402


def make_runs(tmp_path, monkeypatch) -> Path:
    """A successful Single run, a failed Single run, an Iterative run with a rejected round, and a pilot copy."""
    root = tmp_path / "experiments"

    def go(module, run_id, calls):
        folder = tmp_path / f"p-{run_id}"
        folder.mkdir()
        project = support.make_project(folder)
        support.scenario(monkeypatch, folder, calls)
        argv = support.argv(project, run_id)
        argv[argv.index("--out-root") + 1] = str(root)
        module.main(argv, support.FakeToolkit())

    go(run_single, "s01", [{"write": {"lms/quality.json": quality(mean_cc=2.5)}}])
    go(run_single, "s02", [{"write": {"lms/quality.json": quality(mean_cc=2.6, fail={"heldout": ["T-A-01-b"]})}}])
    go(run_iterative, "i01", [
        {"write": {"lms/quality.json": quality(mean_cc=2.5, fail={"feedback": ["T-A-02-a"]})}},
        {"write": {"lms/quality.json": quality(mean_cc=2.7)}, "text": "REFACTORING_DONE"}, {"text": "REFACTORING_DONE"}])
    shutil.copytree(root / "iterative" / "i01", root / "pilot" / "iterative" / "i01")
    return root


def test_finds_runs_and_groups(tmp_path, monkeypatch):
    root = make_runs(tmp_path, monkeypatch)
    keys = sorted(dashboard.find_runs(root))
    assert keys == ["iterative/i01", "pilot/iterative/i01", "single/s01", "single/s02"]   # no tests/run.json etc.
    assert dashboard.group_of("pilot/iterative/i01", "iterative") == "pilot"
    assert dashboard.group_of("single/s01", "single") == ""


def test_summary_and_detail_point_to_the_failure(tmp_path, monkeypatch):
    root = make_runs(tmp_path, monkeypatch)
    ok = dashboard.summary("single/s01", root / "single" / "s01")
    assert ok["outcome"] == "success" and ok["deltas"]["mean_cc"] == -0.5 and ok["metric_status"]["mean_cc"] == "improved"
    failed = dashboard.detail("single/s02", root / "single" / "s02")
    assert failed["outcome"] == "failed" and failed["final"]["best"]["regressions"] == [{"case": "T-A-01-b", "module": "1"}]
    it = dashboard.detail("iterative/i01", root / "iterative" / "i01")
    first = it["rounds_detail"][0]
    assert first["accepted"] is False and first["regressions"] == [{"case": "T-A-02-a", "module": "1"}]
    assert "T-A-02-a" in first["feedback"]                                   # the text the model got
    assert it["rounds_detail"][1]["accepted"] is True and it["best_round"] == 2 and it["live"] is None


def test_live_view_of_a_running_call(tmp_path, monkeypatch):
    root = make_runs(tmp_path, monkeypatch)
    folder = root / "iterative" / "i01"
    record = json.loads((folder / "run.json").read_text())
    record.update({"status": "running", "calls": record["calls"][:1]})
    record["events"].append({"at": "2026-11-21T16:00:00+03:00", "text": "call 2 (round-n) started"})
    (folder / "run.json").write_text(json.dumps(record))
    stream = folder / "calls" / "call-2" / "stream.jsonl"
    stream.write_text("\n".join(json.dumps({"type": "assistant", "message": {"content": [block]}}) for block in [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "/work/lms/loans/service.py"}},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/work/lms/loans/service.py"}},
        {"type": "text", "text": "Splitting the fee calculation."}]) + "\n{not json\n")
    live = dashboard.detail("iterative/i01", folder)["live"]
    assert live["call"] == 2 and live["text"] == "Splitting the fee calculation."
    assert live["actions"] == [{"tool": "Read", "target": "lms/loans/service.py"},
                               {"tool": "Edit", "target": "lms/loans/service.py"}]


def test_compare_counts_only_finished_runs(tmp_path, monkeypatch):
    root = make_runs(tmp_path, monkeypatch)
    board = dashboard.Dashboard(root, tmp_path / ".run.lock")
    data = board.runs("real")
    single, iterative = data["compare"]["single"], data["compare"]["iterative"]
    assert (single["runs"], single["valid"], single["success"]) == (2, 2, 1)
    assert single["outcomes"]["failed"] == 1 and iterative["runs"] == 1
    assert data["compare"]["multiagent"]["runs"] == 0 and data["lock"] is None
    assert len(board.runs("pilot")["runs"]) == 1 and len(board.runs("all")["runs"]) == 4


def test_http_server_is_read_only_json(tmp_path, monkeypatch):
    root = make_runs(tmp_path, monkeypatch)
    (tmp_path / ".run.lock").write_text("who=x\nwhat=run_single.py s09\nstart=2026-11-21T13:00:00Z\npid=1\n")
    before = sorted((p.as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file())
    server = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.handler_for(
        dashboard.Dashboard(root, tmp_path / ".run.lock")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert "Refactoring Experiments" in page and "Multi-Agent" in page
        runs = json.loads(urllib.request.urlopen(base + "/api/runs").read())
        assert runs["lock"]["what"] == "run_single.py s09" and len(runs["runs"]) == 4
        one = json.loads(urllib.request.urlopen(base + "/api/run?key=single/s02").read())
        assert one["outcome"] == "failed"
        try:
            urllib.request.urlopen(base + "/api/run?key=../../etc")
            raise AssertionError("unknown key must be 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.shutdown()
        server.server_close()
    after = sorted((p.as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file())
    assert before == after                                                   # nothing was written


def test_tests_view_lists_every_case_with_its_story(tmp_path, monkeypatch):
    # the instructor asked to see which test passed or failed and why, inside the dashboard (2026-11-23)
    root = make_runs(tmp_path, monkeypatch)
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "a.md").write_text("# Test cases: module 1 (Area A)\n\n| ID | Requirement | Type | Input | Expected | Set |\n"
                                "| --- | --- | --- | --- | --- | --- |\n"
                                "| T-A-01-b | LIB-A-01 | Error | `GET /x` | `404` | held-out |\n")
    folder = root / "single" / "s02"
    record = json.loads((folder / "run.json").read_text())
    final = dashboard.rel_folder(record["final"]["best"]["folder"])
    (folder / final / "tests" / "heldout.junit.xml").write_text(
        '<testsuite><testcase name="test_t_a_01_b"><failure message="assert 500 == 404">trace</failure></testcase>'
        '<testcase name="test_t_a_01_a"/></testsuite>')
    view = dashboard.tests_view(folder, None, cases)
    assert view["selected"] == final and view["start_known"] and view["messages_here"]
    broke = view["cases"][0]                                   # problems first
    assert broke["case"] == "T-A-01-b" and broke["status"] == "regression" and broke["start"] == "passed"
    assert broke["expected"] == "`404`" and broke["area"] == "module 1 (Area A)" and "assert 500 == 404" in broke["message"]
    assert view["counts"]["heldout"]["regression"] == 1 and all(c["status"] == "passed" for c in view["cases"][1:])
    assert "Final check" in view["measurements"][0]["label"]
    assert dashboard.tests_view(folder, "../../..", cases)["selected"] == final     # unknown folder: the default


def test_iterative_measurements_and_paths(tmp_path, monkeypatch):
    root = make_runs(tmp_path, monkeypatch)
    record = json.loads((root / "iterative" / "i01" / "run.json").read_text())
    labels = [m["label"] for m in dashboard.measurements(record)]
    assert labels[0].startswith("Final check of round 2 (best result") and "Round 1: feedback tests" in labels
    view = dashboard.tests_view(root / "iterative" / "i01", "rounds/r1")
    assert [c["case"] for c in view["cases"] if c["status"] == "regression"] == ["T-A-02-a"]
    assert dashboard.rel_folder("final\\r1") == "final/r1"
    assert dashboard.repo_path("C:/Users/x/repo/results/baseline/trial/b") == dashboard.REPO / "results/baseline/trial/b"
    assert dashboard.repo_path("results/a") == dashboard.REPO / "results/a"


def test_tests_endpoint(tmp_path, monkeypatch):
    root = make_runs(tmp_path, monkeypatch)
    server = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.handler_for(
        dashboard.Dashboard(root, tmp_path / ".run.lock", tmp_path / "no-cases")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        data = json.loads(urllib.request.urlopen(base + "/api/tests?key=single/s02").read())
        assert data["counts"]["heldout"]["regression"] == 1
        page = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert "Guide" in page and "When is a refactoring successful?" in page and "metricChart" in page
        assert "What is refactoring?" in page and "What the refactoring changed" in page
    finally:
        server.shutdown()
        server.server_close()


def test_test_code_and_log_fallback(tmp_path):
    # clicking a test shows its code (from the repository) and, without a JUnit report, the pytest log section
    tests = tmp_path / "dataset" / "lms" / "tests"
    (tests / "heldout").mkdir(parents=True)
    (tests / "heldout" / "test_a.py").write_text('import pytest\n\n\n@pytest.mark.x\ndef test_t_a_01_b(client):\n'
                                                 '    """T-A-01-b"""\n    assert client.get("/x").status_code == 404\n')
    code = dashboard.test_source("T-A-01-b", "heldout", tests)
    assert code["line"] == 4 and code["code"].startswith("@pytest.mark.x") and "status_code == 404" in code["code"]
    assert dashboard.test_source("T-A-01-b", "../x", tests) is None and dashboard.test_source("x", "heldout", tests) is None
    log = tmp_path / "out"
    log.mkdir()
    (log / "heldout.log").write_text("F\n=== FAILURES ===\n____ test_t_a_01_b ____\n>   assert 500 == 404\nE   boom\n"
                                     "=== short test summary info ===\n")
    assert "E   boom" in dashboard.log_messages(log)["T-A-01-b"]
    real = dashboard.test_source("T-INV-20-a", "heldout")
    assert real["file"] == "dataset/lms/tests/heldout/test_inventory.py" and "def test_t_inv_20_a" in real["code"]


def test_changes_of_a_run(tmp_path, monkeypatch):
    # "what changed" for readers who are not programmers: files, lines, functions and smells from compare.json
    root = make_runs(tmp_path, monkeypatch)
    folder = root / "single" / "s01"
    record = json.loads((folder / "run.json").read_text())
    target = folder / dashboard.rel_folder(record["final"]["best"]["folder"]) / "compare" / "compare.json"
    data = json.loads(target.read_text()) if target.is_file() else {}
    data.update({"change_size": {"files_changed": 3, "lines_added": 10, "lines_removed": 20},
                 "inventory": {"added": ["function fee"], "removed": ["function old_fee", "class X"]},
                 "smell_counts": {"S01": {"before": 2, "after": 1}}, "sloc": {"before": 100, "after": 90}})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data))
    ch = dashboard.detail("single/s01", folder)["changes"]
    assert ch["kept"] and ch["size"]["files_changed"] == 3 and (ch["added"], ch["removed"]) == (1, 2)
    assert ch["smells"]["S01"] == {"before": 2, "after": 1} and ch["sloc"]["after"] == 90


def test_analyzer_page_reads_the_starting_code(tmp_path, monkeypatch):
    # "Code Quality Analyzer": what was measured in the starting code (size, metrics, smells, modules, tests, tools)
    root = make_runs(tmp_path, monkeypatch)
    base = json.loads((root / "single" / "s01" / "run.json").read_text())["baseline"]
    folder = dashboard.repo_path(base)
    (folder / "smells.csv").write_text("s_id,rule,path,unit,line,module_name,counted\nS01,50 lines,a/b.py,f,3,Core,1\n"
                                       "S01,46 lines,a/c.py,g,9,Core,0\n")
    (folder / "modules.csv").write_text("module_no,module_name,level,status,sloc,smells,smells_per_ksloc\n"
                                        "1,Core,simple,generated,100,1,10\n2,Later,simple,not generated,0,0,0\n")
    view = dashboard.analyzer_view(root, str(folder))
    assert view["selected"] == str(folder) and view["smells_total"] == 1 and view["smells"][0]["path"] == "a/b.py"
    assert [m["module_name"] for m in view["modules"]] == ["Core"]
    assert view["tests"]["feedback"]["passed"] == view["tests"]["feedback"]["total"] and view["failing"] == []
    assert any(b["id"] == str(folder) for b in view["baselines"])


def test_growth_from_pilot_to_full_code():
    # the repository holds both starting codes: the pilot (ce03f54) and the full code (v0-ai-baseline)
    view = dashboard.analyzer_view(dashboard.REPO / "results" / "experiments", None)
    g = view["growth"]
    assert g["pilot"]["sloc"] < g["full"]["sloc"] and g["pilot"]["modules"] < g["full"]["modules"]
    assert set(g["full"]["primary"]) >= {"mean_cc", "smell_count"}
    assert dashboard.growth([]) is None
