"""Pause and continue after a usage-limit cut (Week 6): Multi-Agent keeps the run as ``limit_cut``, waits for the end of
the 5-hour window with ``--auto-resume`` and continues the same session; the roles and the budget are checked over all
calls; the compaction window of the three engines. Fake Claude, fake measurement, a fake clock (no real waiting)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
FIXTURES = SCRIPTS / "tests" / "fixtures" / "experiments"
sys.path.insert(0, str(FIXTURES))

import support  # noqa: E402
from support import common, quality  # noqa: E402

sys.path.insert(0, str(SCRIPTS.parent / "experiments"))
import run_iterative  # noqa: E402
import run_multiagent  # noqa: E402
import run_single  # noqa: E402

FAKE_TESTS = f"{sys.executable} {FIXTURES / 'fake_feedback_tests.py'}"
T0 = 1_800_000_000
REFACTOR = {"agent": "refactoring", "write": {"lms/quality.json": quality(mean_cc=2.5)}}
CUT_REFACTOR = {"agent": "refactoring", "write": {"lms/loans/service.py": "# half done\n"}, "interrupted": True}


class Clock:
    """A clock that only moves when the engine sleeps; it notes whether the run lock was free at every sleep."""

    def __init__(self, lock_file: Path):
        self.t, self.sleeps, self.lock_free, self.lock_file, self.interrupt = float(T0), [], [], lock_file, False

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        if self.interrupt:
            raise KeyboardInterrupt
        self.sleeps.append(seconds)
        self.lock_free.append(not self.lock_file.exists())
        self.t += seconds


@pytest.fixture
def clock(tmp_path, monkeypatch):
    fake = Clock(tmp_path / ".run.lock")
    monkeypatch.setattr(common, "CLOCK", fake.now)
    monkeypatch.setattr(common, "SLEEP", fake.sleep)
    return fake


def cut(resets_in: float | None = 3600, steps=(), **extra) -> dict:
    """A call that ends with the usage limit; the last rate_limit_event says when the window opens."""
    spec = {"steps": list(steps), "limit": True, "cost": 0.2, **extra}
    if resets_in is not None:
        spec["resets_at"] = T0 + resets_in
    return spec


def start(tmp_path, monkeypatch, calls, *extra, run_id="m1"):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, calls)
    toolkit = support.FakeToolkit()
    code = run_multiagent.main(support.argv(project, run_id, "--test-command", FAKE_TESTS, *extra), toolkit)
    out = tmp_path / "out" / "multiagent" / run_id
    record = json.loads((out / "run.json").read_text()) if (out / "run.json").is_file() else None
    return toolkit, code, record, out


def call_file(tmp_path, number: int) -> dict:
    return json.loads(next(tmp_path.glob(f"work-*/session/fake-call-{number}.json")).read_text())


# --- the cut call stays as it is ------------------------------------------------------------------------------------

def test_a_limit_cut_keeps_the_run_and_the_session(tmp_path, monkeypatch, clock):
    toolkit, code, rec, out = start(tmp_path, monkeypatch, [cut(steps=[REFACTOR])])
    assert code == common.EXIT_LIMIT and rec["status"] == "limit_cut" and "outcome" not in rec
    assert "--auto-resume is not set" in rec["stop_reason"]
    assert toolkit.measured == [] and clock.sleeps == []
    assert not (tmp_path / "out" / "runs.csv").exists()                      # no row: the run is not over
    state = json.loads((out / "state.json").read_text())
    assert state["session_id"] == "session-1" and state["limit_cut_at_call"] == 1
    assert state["pending"] == {"kind": "resume", "prompt": common.CONTINUE_PROMPT}
    assert (tmp_path / "work-m1" / "session" / "fake-call-1.json").is_file()   # work folder and session/ are kept
    assert (tmp_path / "work-m1" / "model" / "lms" / "quality.json").is_file()
    assert rec["limit_kinds"] == ["five_hour"] and rec["pauses"] == 0 and rec["wait_s"] == 0.0


def test_limit_then_wait_then_continue_the_same_session(tmp_path, monkeypatch, clock):
    toolkit, code, rec, out = start(tmp_path, monkeypatch, [
        cut(steps=[{"agent": "analyzer"}, CUT_REFACTOR]),
        {"steps": [REFACTOR, {"test": True}, {"agent": "reviewer"}], "text": "REFACTORING_DONE", "cost": 0.3}],
        "--auto-resume")
    assert code == 0 and rec["valid"] is True and rec["outcome"] == "success"
    assert [c["status"] for c in rec["calls"]] == ["limit", "ok"] and rec["calls"][1]["kind"] == "resume"
    # waited until resetsAt + 5 min, with the run lock free the whole time
    assert sum(clock.sleeps) == 3600 + 300 and clock.lock_free and all(clock.lock_free)
    assert not (tmp_path / ".run.lock").exists()
    assert rec["pauses"] == 1 and rec["wait_s"] == 3900.0 and rec["limit_kinds"] == ["five_hour"] and rec["auto_resume"]
    assert rec["limit_cuts"] == [{"call": 1, "kind": "five_hour", "resets_at": T0 + 3600, "five_hour_util": 1,
                                  "seven_day_util": 0.49, "waited_s": 3900.0}]
    # the second call: the same flags (--agents, tools, permissions, environment), --resume and the fixed sentence
    first, second = call_file(tmp_path, 1), call_file(tmp_path, 2)
    a1, a2 = first["args"], second["args"]
    assert a2[0] == "-p" and a2[1] == common.CONTINUE_PROMPT and a2[-2:] == ["--resume", "session-1"]
    assert a2[2:-2] == a1[2:] and a1[1] != a2[1] and "--resume" not in a1
    assert json.loads(a2[a2.index("--agents") + 1]).keys() == {"analyzer", "refactoring", "reviewer"}
    assert second["env"] == first["env"]
    assert rec["calls"][1]["session_in"] == "session-1" and rec["calls"][1]["session_id"] == "session-1"
    assert rec["calls"][1]["usd_diff"] == pytest.approx(0.3)                    # cumulative cost of the session (W16)
    assert json.loads((out / "state.json").read_text())["pending"] is None
    # the subagent the limit cut is recorded apart and is not a call of its role
    assert rec["roles"] == {"subagent_calls": {"analyzer": 1, "refactoring": 1, "reviewer": 1},
                            "interrupted_by_limit": {"refactoring": 1}, "test_runs": 1, "blocked": [],
                            "read_only_shell": [], "invalid": []}
    assert [m["set"] for m in toolkit.measured] == ["feedback", "both"]


def test_snapshot_numbers_continue_over_the_calls(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [
        cut(steps=[REFACTOR, {"test": True}]),
        {"steps": [{"agent": "refactoring", "write": {"lms/quality.json": quality(mean_cc=2.4)}}, {"test": True}]}],
        "--auto-resume")
    assert code == 0 and [r["source"] for r in rec["rounds"]] == ["test run 1", "test run 2"]
    assert sorted(p.name for p in (tmp_path / "work-m1" / "agent-state" / "snapshots").iterdir()) == ["01", "02"]
    assert rec["best_round"] == 2 and rec["roles"]["test_runs"] == 2


# --- the budget over all calls (M5) ------------------------------------------------------------------------------------

def test_refactoring_calls_are_summed_over_the_calls(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [cut(steps=[REFACTOR, REFACTOR]), {"steps": [REFACTOR, REFACTOR]}],
                            "--auto-resume")
    assert code == common.EXIT_INVALID and rec["roles"]["subagent_calls"] == {"refactoring": 4}
    assert any("Refactoring subagent called 4 times" in r for r in rec["reasons"])


def test_test_runs_are_summed_over_the_calls(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [
        cut(steps=[REFACTOR, {"test": True}, {"test": True}]), {"steps": [{"test": True}, {"test": True}]}],
        "--auto-resume")
    assert code == common.EXIT_INVALID and rec["roles"]["test_runs"] == 4
    assert any("test command run 4 times" in r for r in rec["reasons"])


def test_the_subagent_cut_by_the_limit_is_not_counted_against_the_budget(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [
        cut(steps=[REFACTOR, REFACTOR, CUT_REFACTOR]), {"steps": [REFACTOR, {"test": True}]}], "--auto-resume")
    assert code == 0 and rec["valid"] is True
    assert rec["roles"]["subagent_calls"] == {"refactoring": 3} and rec["roles"]["interrupted_by_limit"] == {"refactoring": 1}
    assert rec["roles"]["invalid"] == []


def test_a_forbidden_file_written_by_the_cut_call_still_makes_the_run_invalid(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [cut(write={"CLAUDE.md": "x"}), {"steps": [REFACTOR, {"test": True}]}],
                            "--auto-resume")
    assert code == common.EXIT_INVALID and any("CLAUDE.md" in r for r in rec["reasons"])


# --- when the engine does not wait ----------------------------------------------------------------------------------

def test_the_fourth_pause_is_not_made(tmp_path, monkeypatch, clock):
    calls = [cut(resets_in=1000 * n) for n in range(1, 5)]
    _, code, rec, out = start(tmp_path, monkeypatch, calls, "--auto-resume")
    assert code == common.EXIT_LIMIT and rec["status"] == "limit_cut" and rec["pauses"] == 3
    assert len(rec["calls"]) == 4 and "3 pauses already" in rec["stop_reason"]
    assert json.loads((out / "state.json").read_text())["pauses"] == 3          # nothing deleted, still resumable


def test_more_than_24_hours_of_waiting_is_not_made(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [cut(resets_in=25 * 3600)], "--auto-resume")
    assert code == common.EXIT_LIMIT and clock.sleeps == [] and rec["pauses"] == 0
    assert "would pass 24 h of waiting" in rec["stop_reason"]


def test_waiting_adds_up_to_the_24_hour_limit(tmp_path, monkeypatch, clock):
    calls = [cut(resets_in=20 * 3600), cut(resets_in=45 * 3600)]
    _, code, rec, _ = start(tmp_path, monkeypatch, calls, "--auto-resume")
    assert code == common.EXIT_LIMIT and rec["pauses"] == 1 and rec["wait_s"] == 20 * 3600 + 300
    assert "would pass 24 h of waiting" in rec["stop_reason"]


def test_the_weekly_limit_never_waits(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [cut(weekly=True)], "--auto-resume")
    assert code == common.EXIT_LIMIT and clock.sleeps == [] and rec["limit_kinds"] == ["seven_day"]
    assert rec["status"] == "limit_cut" and "weekly limit" in rec["stop_reason"]


def test_without_a_rate_limit_event_it_stops(tmp_path, monkeypatch, clock):
    _, code, rec, _ = start(tmp_path, monkeypatch, [cut(resets_in=None)], "--auto-resume")
    assert code == common.EXIT_LIMIT and clock.sleeps == [] and rec["limit_kinds"] == ["unknown"]
    assert "does not say" in rec["stop_reason"]


def test_ctrl_c_while_waiting_keeps_the_cut_run(tmp_path, monkeypatch, clock):
    clock.interrupt = True
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [cut(steps=[REFACTOR])])
    with pytest.raises(KeyboardInterrupt):
        run_multiagent.main(support.argv(project, "m1", "--test-command", FAKE_TESTS, "--auto-resume"),
                            support.FakeToolkit())
    out = tmp_path / "out" / "multiagent" / "m1"
    assert json.loads((out / "run.json").read_text())["status"] == "limit_cut"
    assert (out / "state.json").is_file() and not (tmp_path / ".run.lock").exists()


# --- the compaction window ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("runner, scenario_calls", [
    (run_single, [{}]), (run_iterative, [{}, {}, {}, {}]), (run_multiagent, [{}])])
def test_the_compact_window_is_in_the_environment_of_every_engine(tmp_path, monkeypatch, runner, scenario_calls):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, scenario_calls)
    extra = ("--test-command", FAKE_TESTS) if runner is run_multiagent else ()
    assert runner.main(support.argv(project, "c1", *extra, "--compact-window", "150000"), support.FakeToolkit()) == 0
    assert call_file(tmp_path, 1)["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "150000"
    record = json.loads(next((tmp_path / "out").glob("*/c1/run.json")).read_text())
    assert record["compact_window"] == 150000 and record["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "150000"


def test_the_compact_window_defaults_to_200000(tmp_path, monkeypatch):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [{}])
    assert run_single.main(support.argv(project, "c2"), support.FakeToolkit()) == 0
    assert call_file(tmp_path, 1)["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "200000"


def test_a_compact_window_below_one_is_refused_and_dry_run_shows_it(tmp_path, capsys):
    project = support.make_project(tmp_path)
    assert run_single.main(support.argv(project, "c3", "--compact-window", "0"), support.FakeToolkit()) == common.EXIT_USAGE
    assert run_multiagent.main(support.argv(project, "c4", "--dry-run", "--compact-window", "123456"),
                               support.FakeToolkit()) == 0
    assert "-e CLAUDE_CODE_AUTO_COMPACT_WINDOW=123456" in capsys.readouterr().out


# --- the helpers ---------------------------------------------------------------------------------------------------

SCALE_M01 = {"rate_limit_info": {"status": "rejected", "resetsAt": 1795377600, "rateLimitType": "five_hour",
                                 "overageStatus": "rejected", "isUsingOverage": False,
                                 "unifiedWindows": {"five_hour": {"utilization": 1, "resetsAt": 1795377600},
                                                    "seven_day": {"utilization": 0.49, "resetsAt": 1795554000}}},
             "session_id": "8ec22fe0"}


def test_limit_info_reads_the_scale_m01_event():
    info = common.limit_info(SCALE_M01)
    assert (info["kind"], info["resets_at"], info["five_hour_util"], info["seven_day_util"]) == ("five_hour", 1795377600, 1, 0.49)


def test_limit_info_weekly_wins_and_unclear_events_have_no_kind():
    weekly = json.loads(json.dumps(SCALE_M01))
    weekly["rate_limit_info"]["unifiedWindows"]["seven_day"]["utilization"] = 1
    assert common.limit_info(weekly)["kind"] == "seven_day" and common.limit_info(weekly)["resets_at"] == 1795554000
    warning = {"rate_limit_info": {"status": "allowed_warning", "rateLimitType": "five_hour",
                                   "unifiedWindows": {"five_hour": {"utilization": 0.99, "resetsAt": 5}}}}
    assert common.limit_info(warning)["kind"] is None and common.limit_info(None)["kind"] is None
    assert common.limit_info({"rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour",
                                                  "resetsAt": 77}})["resets_at"] == 77


def test_wait_until_ticks_and_returns_the_time_waited(clock):
    ticks = []
    waited = common.wait_until(T0 + 1200, margin_s=300, on_tick=ticks.append, tick_s=600, step_s=30)
    assert waited == 1500.0 and ticks == [900.0, 300.0] and common.wait_until(T0, margin_s=0) == 0.0


def test_resume_args_keep_the_flags_and_replace_the_prompt():
    args = ["-p", "long prompt", "--model", "m", "--agents", "{}"]
    assert common.resume_args(args, "again", "s9") == ["-p", "again", "--model", "m", "--agents", "{}", "--resume", "s9"]
    with pytest.raises(common.EngineError):
        common.resume_args(["--model", "m"], "x", "s9")
