"""End-to-end tests of experiments/run_single.py with a fake Claude and a fake measurement step (ADR 004, W3, W6,
W8-W10, W12, W13, W16)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests" / "fixtures" / "experiments"))

import support  # noqa: E402
from support import common, quality  # noqa: E402

sys.path.insert(0, str(SCRIPTS.parent / "experiments"))
import run_single  # noqa: E402

BETTER = "def fee(days):\n    return 2 * days\n"


def start(tmp_path, monkeypatch, calls, run_id="s1", *extra):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, calls)
    toolkit = support.FakeToolkit()
    code = run_single.main(support.argv(project, run_id, *extra), toolkit)
    out = tmp_path / "out" / "single" / run_id
    record = json.loads((out / "run.json").read_text()) if (out / "run.json").is_file() else None
    return project, toolkit, code, record


def test_success(tmp_path, monkeypatch):
    project, toolkit, code, record = start(tmp_path, monkeypatch, [
        {"write": {"lms/loans/service.py": BETTER, "lms/quality.json": quality(mean_cc=2.5)}, "cost": 0.75}])
    assert code == 0 and record["outcome"] == "success" and record["valid"] is True
    # the model saw only lms/, requirements.txt and INTERFACE.md (W3), with the W9 settings
    call = json.loads(next(tmp_path.glob("work-s1/session/fake-call-1.json")).read_text())
    assert call["env"]["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    assert call["args"][1] == "Refactor lms/.\n" and "--safe-mode" in call["args"] and "--allowedTools" in call["args"]
    assert sorted(p.name for p in Path(call["cwd"]).iterdir()) == ["INTERFACE.md", "lms", "requirements.txt"]
    # one full measurement (both sets) of the tagged code, compared with the start (no previous best)
    assert [(m["set"], m["previous_best"]) for m in toolkit.measured] == [("both", None)]
    tag_sha = support.run_git(project["repo"], "rev-parse", "exp/single/s1/r1")
    assert toolkit.measured[0]["code_sha"] == tag_sha == record["rounds"][0]["code_sha"]
    assert "web/index.html" in toolkit.measured[0]["tree_files"]
    # records: run.json, runs.csv, cost log; the lock is released
    assert record["calls"][0]["usd_raw"] == 0.75 and record["calls"][0]["files_written"]
    row = support.read_runs(tmp_path)[0]
    assert row["outcome"] == "success" and row["valid"] == "true" and row["best_tag"] == "exp/single/s1/r1"
    assert row["mean_cc_best"] == "2.5" and row["mean_cc_start"] == "3.0" and row["usd_raw"] == "0.75"
    assert row["account"] == "acc-a" and row["calls"] == "1" and row["window_pct_start"] == "5.0"
    # one measurement, counted once although it is the round, "best", "round1" and "last" (pilot-s01b: 270 s, not 1080)
    assert float(row["measure_s"]) == record["rounds"][0]["facts"]["wall_s"]
    with (tmp_path / "metrics" / "cost-log.csv").open(newline="") as handle:
        cost_rows = list(csv.DictReader(handle))
    assert cost_rows[0]["stage"] == "single" and cost_rows[0]["run_id"] == "s1" and cost_rows[0]["valid"] == "true"
    assert not (tmp_path / ".run.lock").exists()


def test_no_change(tmp_path, monkeypatch):
    _, toolkit, code, record = start(tmp_path, monkeypatch, [{"text": "Nothing to do."}])
    assert code == 0 and record["outcome"] == "no_change" and toolkit.measured == []


def test_regression_is_a_failed_run(tmp_path, monkeypatch):
    _, _, code, record = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.0, fail={"heldout": ["T-A-01-b"]})}}])
    assert code == 0 and record["outcome"] == "failed" and record["valid"] is True
    assert "regression" in record["reasons"][0]
    assert support.read_runs(tmp_path)[0]["regressions_heldout"] == "1"


def test_api_change_is_a_failed_run(tmp_path, monkeypatch):
    _, _, code, record = start(tmp_path, monkeypatch, [{"write": {"lms/quality.json": quality(mean_cc=2.0, api=True)}}])
    assert code == 0 and record["outcome"] == "failed" and "API changed (real API change)" in record["reasons"]
    assert support.read_runs(tmp_path)[0]["api_changed"] == "true"


def test_subagent_makes_the_run_invalid(tmp_path, monkeypatch):
    _, toolkit, code, record = start(tmp_path, monkeypatch, [{"write": {"lms/a.py": "x = 1\n"}, "subagents": 1}])
    assert code == common.EXIT_INVALID and record["outcome"] == "invalid" and toolkit.measured == []
    assert any("subagent" in r for r in record["reasons"])
    assert support.read_runs(tmp_path)[0]["valid"] == "false"


def test_denied_write_makes_the_run_invalid(tmp_path, monkeypatch):
    # a denied Write still ends with subtype "success": without this check the run would look valid
    _, toolkit, code, record = start(tmp_path, monkeypatch, [{"denied": ["Write", "Write"], "text": "Done."}])
    assert code == common.EXIT_INVALID and toolkit.measured == []
    assert "2 denied tool call(s): Write, Write" in record["reasons"]
    assert support.read_runs(tmp_path)[0]["permission_denials"] == "2"


def test_wrong_tools_and_version_make_the_run_invalid(tmp_path, monkeypatch):
    _, _, code, record = start(tmp_path, monkeypatch, [{"tools": ["Read", "Bash"], "version": "1.0.0"}])
    assert code == common.EXIT_INVALID
    assert any("tool list" in r for r in record["reasons"]) and any("version" in r for r in record["reasons"])


def test_limit_cut_discards_the_run(tmp_path, monkeypatch):
    project, toolkit, code, record = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.0)}, "limit": True, "cost": 0.3}])
    assert code == common.EXIT_LIMIT and record["outcome"] == "discarded_limit" and toolkit.measured == []
    row = support.read_runs(tmp_path)[0]
    assert row["valid"] == "false" and row["usd_lost"] == "0.3"
    assert support.run_git(project["repo"], "tag", "-l", "exp/*") == ""


def test_changes_outside_lms_are_discarded_and_counted(tmp_path, monkeypatch):
    _, toolkit, code, record = start(tmp_path, monkeypatch, [{"write": {
        "lms/quality.json": quality(mean_cc=2.5), "requirements.txt": "flask\n", "notes.md": "plan"}}])
    assert code == 0 and record["outcome"] == "success"
    assert record["outside_lms_changes"] == [{"call": 1, "changed": ["requirements.txt"], "added": ["notes.md"],
                                              "removed": []}]
    assert "notes.md" not in toolkit.measured[0]["tree_files"]
    assert support.read_runs(tmp_path)[0]["outside_lms_changes"] == "2"


def test_hidden_file_makes_the_run_invalid(tmp_path, monkeypatch):
    _, _, code, record = start(tmp_path, monkeypatch, [{"write": {"lms/a.py": "x = 1\n", "CLAUDE.md": "memo"}}])
    assert code == common.EXIT_INVALID and any("CLAUDE.md" in r for r in record["reasons"])


def test_claude_md_written_and_removed_makes_the_run_invalid(tmp_path, monkeypatch):
    # --safe-mode does not stop the write; the file is gone at the end, the stream still shows it
    _, _, code, record = start(tmp_path, monkeypatch, [{"write": {"lms/a.py": "x = 1\n", "CLAUDE.md": "memo"},
                                                        "delete": ["CLAUDE.md"]}])
    assert code == common.EXIT_INVALID and any("/work/CLAUDE.md" in r for r in record["reasons"])


def test_test_files_changed_makes_the_run_invalid(tmp_path, monkeypatch):
    _, _, code, record = start(tmp_path, monkeypatch, [{"write": {"lms/quality.json": quality(measure_status="invalid")}}])
    assert code == common.EXIT_INVALID and record["outcome"] == "invalid"


def test_inputs_are_checked(tmp_path, monkeypatch):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [])
    argv = support.argv(project, "s1")
    high = argv[:argv.index("--window-pct") + 1] + ["25"] + argv[argv.index("--window-pct") + 2:]
    assert run_single.main(high, support.FakeToolkit()) == common.EXIT_USAGE
    (project["baseline"] / "summary.json").write_text(json.dumps({"code_sha": "0" * 40, "primary": support.START}))
    assert run_single.main(argv, support.FakeToolkit()) == common.EXIT_USAGE
    (tmp_path / ".run.lock").write_text("pid=1\n")
    assert run_single.main(argv, support.FakeToolkit()) == common.EXIT_LOCK


def test_docker_not_running_stops_before_the_call(tmp_path, monkeypatch, capsys):
    import subprocess
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [])
    env = tmp_path / ".env"
    env.write_text("X=1\n")
    argv = [a for a in support.argv(project, "s1") if a != "--local"] + ["--env-file", str(env)]
    monkeypatch.setattr(common.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(common.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "no daemon"))
    assert run_single.main(argv, support.FakeToolkit()) == common.EXIT_USAGE
    assert "Docker is not running" in capsys.readouterr().err


def test_missing_detail_csv_of_the_baseline_stops_before_the_call(tmp_path, monkeypatch, capsys):
    # results/baseline/trial/ does not commit functions.csv and classes.csv; compare.py needs them
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [{"write": {"lms/a.py": "x = 1\n"}}])
    (project["baseline"] / "functions.csv").unlink()
    (project["baseline"] / "classes.csv").unlink()
    assert run_single.main(support.argv(project, "s1"), support.FakeToolkit()) == common.EXIT_USAGE
    assert "lacks functions.csv, classes.csv" in capsys.readouterr().err
    assert not list(tmp_path.glob("work-s1/session/fake-call-*.json"))     # no Claude call, no quota used
