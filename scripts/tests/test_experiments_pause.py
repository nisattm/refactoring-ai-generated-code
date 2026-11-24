"""Pause and continue after a usage-limit cut (Week 6): Multi-Agent keeps the run as ``limit_cut``, waits for the end of
the 5-hour window with ``--auto-resume`` and continues the same session; the roles and the budget are checked over all
calls; the compaction window of the three engines. Fake Claude, fake measurement, a fake clock (no real waiting)."""

from __future__ import annotations

import json
import shutil
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
                                  "seven_day_util": 0.49, "cut_at": float(T0), "waited_s": 3900.0}]
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


# --- --resume-run: the same rules by hand ---------------------------------------------------------------------------

def first(tmp_path, monkeypatch, calls, *extra):
    """The first command of a run; returns the project, the toolkit, the exit code and the record."""
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, calls)
    toolkit = support.FakeToolkit()
    code = run_multiagent.main(support.argv(project, "m1", "--test-command", FAKE_TESTS, *extra), toolkit)
    return project, toolkit, code, load(tmp_path)


def load(tmp_path, run_id="m1") -> dict:
    return json.loads((tmp_path / "out" / "multiagent" / run_id / "run.json").read_text())


def again(tmp_path, project, toolkit, *extra):
    code = run_multiagent.main(support.argv(project, "m1", "--resume-run", *extra), toolkit)
    return code, load(tmp_path)


OK_CALL = {"steps": [REFACTOR, {"test": True}], "text": "REFACTORING_DONE", "cost": 0.3}


def test_resume_run_continues_the_same_session_by_hand(tmp_path, monkeypatch, clock):
    project, toolkit, code, rec = first(tmp_path, monkeypatch, [cut(steps=[CUT_REFACTOR]), OK_CALL])
    assert code == common.EXIT_LIMIT and rec["status"] == "limit_cut"
    clock.t = T0 + 3600 + 300 + 10                                   # the window has reopened
    code, rec = again(tmp_path, project, toolkit)
    assert code == 0 and rec["valid"] is True and clock.sleeps == []
    assert [c["status"] for c in rec["calls"]] == ["limit", "ok"] and rec["calls"][1]["kind"] == "resume"
    assert rec["pauses"] == 1 and rec["wait_s"] == 3910.0 and rec["manual_resumes"] == 1 and rec["auto_resume"] is False
    first_args, second_args = call_file(tmp_path, 1)["args"], call_file(tmp_path, 2)["args"]
    assert second_args[1] == common.CONTINUE_PROMPT and second_args[-2:] == ["--resume", "session-1"]
    assert second_args[2:-2] == first_args[2:]                         # --agents, tools, permissions: the same
    assert call_file(tmp_path, 2)["env"] == call_file(tmp_path, 1)["env"]
    assert rec["roles"]["subagent_calls"] == {"refactoring": 1} and rec["roles"]["interrupted_by_limit"] == {"refactoring": 1}
    assert rec["calls"][1]["usd_diff"] == pytest.approx(0.3)


def test_resume_run_needs_none_of_the_start_options(tmp_path, monkeypatch, clock):
    project, toolkit, _, _ = first(tmp_path, monkeypatch, [cut(steps=[REFACTOR]), OK_CALL])
    clock.t = T0 + 4000
    fake = f"{sys.executable} {FIXTURES / 'fake_claude.py'}"
    argv = ["--resume-run", "--run-id", "m1", "--local", "--claude-command", fake, "--repo", str(project["repo"]),
            "--out-root", str(tmp_path / "out"), "--cost-log", str(tmp_path / "metrics" / "cost-log.csv"),
            "--lock-file", str(tmp_path / ".run.lock"), "--prompts", str(project["prompts"]), "--keep-work"]
    assert run_multiagent.main(argv, toolkit) == 0
    assert load(tmp_path)["outcome"] == "success"


def test_resume_run_refuses_before_the_window_reopens(tmp_path, monkeypatch, clock):
    project, toolkit, _, _ = first(tmp_path, monkeypatch, [cut(steps=[REFACTOR]), OK_CALL])
    clock.t = T0 + 100
    code, rec = again(tmp_path, project, toolkit)
    assert code == common.EXIT_LIMIT and rec["status"] == "limit_cut" and len(rec["calls"]) == 1
    assert "the window opens" in rec["stop_reason"] and "--auto-resume" in rec["stop_reason"]
    assert not list(tmp_path.glob("work-*/session/fake-call-2.json")) and rec["pauses"] == 0


def test_resume_run_with_auto_resume_waits_for_the_window(tmp_path, monkeypatch, clock):
    project, toolkit, _, _ = first(tmp_path, monkeypatch, [cut(steps=[REFACTOR]), OK_CALL])
    clock.t = T0 + 100
    code, rec = again(tmp_path, project, toolkit, "--auto-resume")
    assert code == 0 and sum(clock.sleeps) == 3800 and clock.lock_free and all(clock.lock_free)
    assert rec["pauses"] == 1 and rec["wait_s"] == 3900.0                 # since the cut, not since this command


def test_resume_run_after_a_weekly_cut_only_after_the_reset(tmp_path, monkeypatch, clock):
    project, toolkit, code, rec = first(tmp_path, monkeypatch, [cut(weekly=True, steps=[REFACTOR]), OK_CALL])
    assert code == common.EXIT_LIMIT and rec["limit_kinds"] == ["seven_day"]
    weekly_reset = T0 + 3600 + 7200
    clock.t = weekly_reset - 600
    for extra in ((), ("--auto-resume",)):                              # not even --auto-resume waits for the week
        code, rec = again(tmp_path, project, toolkit, *extra)
        assert code == common.EXIT_LIMIT and "weekly limit" in rec["stop_reason"] and clock.sleeps == []
    clock.t = weekly_reset + 400
    code, rec = again(tmp_path, project, toolkit)
    assert code == 0 and rec["pauses"] == 1


def test_resume_run_when_the_cut_did_not_name_a_window(tmp_path, monkeypatch, clock):
    project, toolkit, code, rec = first(tmp_path, monkeypatch, [cut(resets_in=None, steps=[REFACTOR]), OK_CALL])
    assert code == common.EXIT_LIMIT and rec["limit_kinds"] == ["unknown"]
    code, rec = again(tmp_path, project, toolkit)                        # the person knows the window is open
    assert code == 0 and rec["pauses"] == 1 and clock.sleeps == []


def test_resume_run_keeps_the_pause_limits(tmp_path, monkeypatch, clock):
    calls = [cut(resets_in=1000 * n) for n in range(1, 5)] + [OK_CALL]
    project, toolkit, code, rec = first(tmp_path, monkeypatch, calls, "--auto-resume")
    assert code == common.EXIT_LIMIT and rec["pauses"] == 3 and len(rec["calls"]) == 4
    clock.t += 9999
    code, rec = again(tmp_path, project, toolkit)
    assert code == common.EXIT_LIMIT and "3 pauses already" in rec["stop_reason"] and len(rec["calls"]) == 4
    assert rec["status"] == "limit_cut" and not list(tmp_path.glob("work-*/session/fake-call-5.json"))


def test_resume_run_keeps_the_24_hour_limit(tmp_path, monkeypatch, clock):
    project, toolkit, _, _ = first(tmp_path, monkeypatch, [cut(steps=[REFACTOR]), OK_CALL])
    clock.t = T0 + 25 * 3600                                             # a day after the cut
    code, rec = again(tmp_path, project, toolkit)
    assert code == common.EXIT_LIMIT and "would pass 24 h of waiting" in rec["stop_reason"] and len(rec["calls"]) == 1


def test_a_run_cut_again_after_resume_can_be_resumed_again(tmp_path, monkeypatch, clock):
    project, toolkit, _, _ = first(tmp_path, monkeypatch, [cut(steps=[REFACTOR]), cut(resets_in=9000), OK_CALL])
    clock.t = T0 + 4000
    code, rec = again(tmp_path, project, toolkit)                        # cut again; no --auto-resume: stays cut
    assert code == common.EXIT_LIMIT and rec["pauses"] == 1 and len(rec["calls"]) == 2
    assert "--auto-resume is not set" in rec["stop_reason"]
    state = json.loads((tmp_path / "out" / "multiagent" / "m1" / "state.json").read_text())
    assert state["session_id"] == "session-1" and state["limit_cut_at_call"] == 2
    clock.t = T0 + 9000 + 400
    code, rec = again(tmp_path, project, toolkit)
    assert code == 0 and rec["pauses"] == 2 and rec["manual_resumes"] == 2 and len(rec["calls"]) == 3
    assert rec["roles"]["test_runs"] == 1


def rewrite_orchestrator(tmp_path, project):
    (project["prompts"] / "multiagent" / "orchestrator.md").write_text("Another task.\n")


def rewrite_reviewer(tmp_path, project):
    (project["prompts"] / "multiagent" / "reviewer.md").write_text("---\ndescription: Changed.\n---\nAnother reviewer.\n")


def remove_workspace(tmp_path, project):
    shutil.rmtree(tmp_path / "work-m1" / "state.git")


@pytest.mark.parametrize("make_wrong, message", [
    (rewrite_orchestrator, "orchestrator prompt is not the one"),
    (rewrite_reviewer, "role prompts are not the ones"),
    (remove_workspace, "is gone")])
def test_resume_run_refuses_a_changed_setup(tmp_path, monkeypatch, clock, capsys, make_wrong, message):
    project, toolkit, _, _ = first(tmp_path, monkeypatch, [cut(steps=[REFACTOR]), OK_CALL])
    clock.t = T0 + 4000
    make_wrong(tmp_path, project)
    code, rec = again(tmp_path, project, toolkit)
    assert code == common.EXIT_USAGE and message in capsys.readouterr().err
    assert rec["status"] == "limit_cut" and len(rec["calls"]) == 1       # nothing was changed


def test_resume_run_refuses_another_account_and_runs_that_are_not_cut(tmp_path, monkeypatch, clock, capsys):
    project, toolkit, _, _ = first(tmp_path, monkeypatch, [cut(steps=[REFACTOR]), OK_CALL])
    clock.t = T0 + 4000
    code, _ = again(tmp_path, project, toolkit, "--account", "acc-b")
    assert code == common.EXIT_USAGE and "another account is not supported" in capsys.readouterr().err
    assert again(tmp_path, project, toolkit)[0] == 0                     # the same account (acc-a) continues
    code, _ = again(tmp_path, project, toolkit)                          # now finished: not waiting any more
    assert code == common.EXIT_USAGE and "is not waiting after a usage-limit cut" in capsys.readouterr().err
    assert run_multiagent.main(support.argv(project, "nope", "--resume-run"), toolkit) == common.EXIT_USAGE
