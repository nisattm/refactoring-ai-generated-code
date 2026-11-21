"""End-to-end tests of experiments/run_iterative.py with a fake Claude and a fake measurement step (ADR 004, W1,
W2, W4, W5, W6)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests" / "fixtures" / "experiments"))

import support  # noqa: E402
from support import common, quality  # noqa: E402

sys.path.insert(0, str(SCRIPTS.parent / "experiments"))
import run_iterative  # noqa: E402

DONE = common.DONE_MARKER


def start(tmp_path, monkeypatch, calls, run_id="i1"):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, calls)
    toolkit = support.FakeToolkit()
    code = run_iterative.main(support.argv(project, run_id), toolkit)
    return project, toolkit, code, record(tmp_path, run_id)


def record(tmp_path, run_id="i1"):
    return json.loads((tmp_path / "out" / "iterative" / run_id / "run.json").read_text())


def call_args(tmp_path, number, run_id="i1"):
    return json.loads((tmp_path / f"work-{run_id}" / "session" / f"fake-call-{number}.json").read_text())["args"]


def model_file(tmp_path, rel, run_id="i1"):
    return (tmp_path / f"work-{run_id}" / "model" / rel).read_text()


def test_accept_then_reject_and_revert(tmp_path, monkeypatch):
    project, toolkit, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.5), "lms/loans/service.py": "# round 1\n"}},
        {"write": {"lms/quality.json": quality(mean_cc=2.8), "lms/loans/service.py": "# round 2\n"}},
        {"text": f"Nothing more. {DONE}"},
    ])
    assert code == 0 and rec["outcome"] == "success" and rec["stop_reason"].startswith(DONE)
    assert [r["accepted"] for r in rec["rounds"]] == [True, False]
    # rejected round: lms/ is back at round 1 and the next prompt has the fixed sentence (W5)
    assert model_file(tmp_path, "lms/loans/service.py") == "# round 1\n"
    third = call_args(tmp_path, 3)[1]
    assert common.REVERTED_TEXT in third and third.startswith("Round 3 of 4.") and "{other}" in third
    assert common.ACCEPTED_TEXT in call_args(tmp_path, 2)[1]
    # one session: calls 2 and 3 resume the session of call 1
    assert "--resume" not in call_args(tmp_path, 1)
    assert call_args(tmp_path, 2)[call_args(tmp_path, 2).index("--resume") + 1] == "session-1"
    # rounds: feedback set, against the best so far; final: both sets, best = round 1 = r1, last = r2 (W1)
    sets = [(m["label"].split("-", 1)[1], m["set"], m["previous_best"] is not None) for m in toolkit.measured]
    assert sets == [("rounds-r1", "feedback", False), ("rounds-r2", "feedback", True),
                    ("final-r1", "both", False), ("final-r2", "both", False)]
    assert rec["best_round"] == 1 and rec["final"]["round1"]["round"] == 1 and rec["final"]["last"]["round"] == 2
    tags = support.run_git(project["repo"], "tag", "-l", "exp/iterative/i1/*").split()
    assert tags == ["exp/iterative/i1/r1", "exp/iterative/i1/r2"]
    row = support.read_runs(tmp_path)[0]
    assert (row["calls"], row["code_rounds"], row["accepted_rounds"], row["rejected_rounds"]) == ("3", "2", "1", "1")
    assert (row["mean_cc_best"], row["mean_cc_r1"], row["mean_cc_last"]) == ("2.5", "2.5", "2.8")
    walls = [r["facts"]["wall_s"] for r in rec["rounds"]] + [rec["final"][k]["wall_s"] for k in ("best", "last")]
    assert abs(float(row["measure_s"]) - sum(walls)) < 0.05    # final r1 = best = round1, counted once


def test_regression_feedback_goes_into_the_next_prompt(tmp_path, monkeypatch):
    _, toolkit, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.0, fail={"feedback": ["T-A-02-a"]})}},
        {"write": {"lms/quality.json": quality(mean_cc=2.2)}, "text": DONE},
    ])
    assert code == 0 and [r["accepted"] for r in rec["rounds"]] == [False, True]
    second = call_args(tmp_path, 2)[1]
    assert "T-A-02-a: AssertionError" in second and common.REVERTED_TEXT in second
    assert len(toolkit.feedback_calls[0][2]) == 2          # two repetitions (D18) go to feedback.py
    assert rec["rounds"][0]["feedback_lines"] == 1
    assert rec["outcome"] == "success" and rec["best_round"] == 2


def test_done_in_call_one_still_needs_a_second_call(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.5)}, "text": DONE},
        {"text": DONE},
    ])
    assert code == 0 and len(rec["calls"]) == 2 and len(rec["rounds"]) == 1


def test_done_with_a_regression_does_not_stop(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.5)}},
        {"write": {"lms/quality.json": quality(mean_cc=2.0, fail={"feedback": ["T-A-01-a"]})}, "text": DONE},
        {"text": DONE},
    ])
    assert code == 0 and len(rec["calls"]) == 3 and rec["best_round"] == 1


def test_stop_after_three_code_rounds(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.9)}},
        {"write": {"lms/quality.json": quality(mean_cc=2.8)}},
        {"write": {"lms/quality.json": quality(mean_cc=2.7)}},
        {"write": {"lms/quality.json": quality(mean_cc=2.6)}},
    ])
    assert code == 0 and len(rec["calls"]) == 3 and rec["best_round"] == 3
    assert rec["stop_reason"] == "3 rounds changed code"


def test_stop_after_four_calls(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.9)}}, {}, {}, {}, {"write": {"lms/x.py": "x"}},
    ])
    assert code == 0 and len(rec["calls"]) == 4 and len(rec["rounds"]) == 1 and rec["stop_reason"] == "4 calls"
    assert call_args(tmp_path, 3)[1].startswith("Round 3 of 4.\n\n")   # no change: no sentence, no feedback


def test_api_change_round_is_rejected(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.0, api=True)}},
        {"text": DONE},
    ])
    assert code == 0 and rec["rounds"][0]["accepted"] is False and rec["outcome"] == "no_improvement"
    assert rec["best_round"] == 0 and rec["final"] == {"round1": {**rec["final"]["round1"]},
                                                       "last": {**rec["final"]["last"]}}


def test_subagent_makes_the_run_invalid(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.5)}},
        {"write": {"lms/quality.json": quality(mean_cc=2.4)}, "subagents": 2},
    ])
    assert code == common.EXIT_INVALID and rec["outcome"] == "invalid" and len(rec["rounds"]) == 1


def test_outside_lms_changes_are_discarded(tmp_path, monkeypatch):
    _, toolkit, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.5), "INTERFACE.md": "changed"}},
        {"write": {"todo.txt": "x"}, "text": DONE},
    ])
    assert code == 0 and model_file(tmp_path, "INTERFACE.md") == "# Interface\n"
    assert [c["outside_lms_changes"] for c in rec["calls"]] == [1, 1] and len(rec["rounds"]) == 1


def test_limit_cut_then_resume_with_another_account(tmp_path, monkeypatch):
    project, toolkit, code, rec = start(tmp_path, monkeypatch, [
        {"write": {"lms/quality.json": quality(mean_cc=2.5), "lms/loans/service.py": "# r1\n"}},
        {"write": {"lms/loans/service.py": "# half done\n"}, "limit": True, "cost": 0.2},
        {"write": {"lms/quality.json": quality(mean_cc=2.4)}, "text": DONE},
    ])
    assert code == common.EXIT_LIMIT and rec["status"] == "limit_cut"
    assert not (tmp_path / ".run.lock").exists() and not (tmp_path / "out" / "runs.csv").exists()
    base = support.argv(project, "i1")
    resume = ["--run-id", "i1", "--account", "acc-b", "--window-pct", "3", "--resume-run",
              *base[base.index("--local"):]]
    # not verified: refused (W6)
    assert run_iterative.main(resume, toolkit) == common.EXIT_USAGE
    assert run_iterative.main([*resume, "--account-switch-verified"], toolkit) == 0
    rec = record(tmp_path)
    assert rec["accounts_used"] == ["acc-a", "acc-b"] and rec["outcome"] == "success"
    # the half-done edit was undone, the same prompt went again in the same session
    assert call_args(tmp_path, 3)[1] == call_args(tmp_path, 2)[1]
    assert call_args(tmp_path, 3)[call_args(tmp_path, 3).index("--resume") + 1] == "session-1"
    assert [c["status"] for c in rec["calls"]] == ["ok", "limit", "ok"]   # the re-sent call counts once (W4)
    assert rec["best_round"] == 2 and model_file(tmp_path, "lms/loans/service.py") == "# r1\n"
    row = support.read_runs(tmp_path)[0]
    assert row["calls"] == "2" and row["usd_lost"] == "0.2" and row["accounts_used"] == "acc-a;acc-b"
    # cumulative session totals: 0.25, 0.45 (cut), 0.70 → shares 0.25, 0.2, 0.25 (W16)
    assert [c["usd_raw"] for c in rec["calls"]] == [0.25, 0.45, 0.7]
    assert [c["usd_diff"] for c in rec["calls"]] == [0.25, 0.2, 0.25]
    assert [c["tokens"]["input_tokens"] for c in rec["calls"]] == [10, 10, 10]
    assert row["usd_raw"] == "0.7" and row["usd_diff"] == "0.7" and row["input_tokens"] == "30"
    import csv
    with (tmp_path / "metrics" / "cost-log.csv").open(newline="") as handle:
        log = list(csv.DictReader(handle))
    assert [r["usd"] for r in log] == ["0.25", "0.2", "0.25"] and "session total usd 0.7" in log[2]["note"]
    assert rec["calls"][0]["rate_limit"]["rate_limit_info"]["utilization"] == 0.05


def test_limit_cut_then_discard(tmp_path, monkeypatch):
    project, toolkit, code, _ = start(tmp_path, monkeypatch, [{"limit": True}])
    assert code == common.EXIT_LIMIT
    base = support.argv(project, "i1")
    argv = ["--run-id", "i1", "--account", "acc-a", "--discard-run", *base[base.index("--local"):]]
    assert run_iterative.main(argv, toolkit) == common.EXIT_LIMIT
    rec = record(tmp_path)
    assert rec["outcome"] == "discarded_limit" and support.read_runs(tmp_path)[0]["valid"] == "false"
