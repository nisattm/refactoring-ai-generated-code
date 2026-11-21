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
