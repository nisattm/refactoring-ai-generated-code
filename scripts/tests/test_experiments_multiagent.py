"""Tests of the Multi-Agent engine (experiments/run_multiagent.py) and of its feedback test command
(experiments/feedback_tests.py): roles and budget from the stream, snapshots as rounds with the best-round rule (W1),
invalid runs, and the W2 text of the test command. Fake Claude, fake measurement, stub test runner."""

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
import feedback_tests  # noqa: E402
import run_multiagent  # noqa: E402

FAKE_TESTS = f"{sys.executable} {FIXTURES / 'fake_feedback_tests.py'}"


def start(tmp_path, monkeypatch, steps, run_id="m1", **call):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [{"steps": steps, **call}])
    toolkit = support.FakeToolkit()
    code = run_multiagent.main(support.argv(project, run_id, "--test-command", FAKE_TESTS), toolkit)
    out = tmp_path / "out" / "multiagent" / run_id
    record = json.loads((out / "run.json").read_text()) if (out / "run.json").is_file() else None
    return project, toolkit, code, record


def args_of(tmp_path, run_id="m1"):
    return json.loads((tmp_path / f"work-{run_id}" / "session" / "fake-call-1.json").read_text())["args"]


REFACTOR = {"agent": "refactoring", "write": {"lms/loans/service.py": "# refactored\n",
                                               "lms/quality.json": quality(mean_cc=2.5)}}


def test_success_with_three_roles(tmp_path, monkeypatch):
    project, toolkit, code, rec = start(tmp_path, monkeypatch, [
        {"agent": "analyzer"}, REFACTOR, {"test": True}, {"agent": "reviewer"}], text="REFACTORING_DONE")
    assert code == 0 and rec["outcome"] == "success" and rec["valid"] is True
    assert rec["roles"] == {"subagent_calls": {"analyzer": 1, "refactoring": 1, "reviewer": 1},
                            "interrupted_by_limit": {}, "test_runs": 1, "blocked": [], "read_only_shell": [],
                            "invalid": []}
    assert [r["source"] for r in rec["rounds"]] == ["test run 1"] and rec["best_round"] == 1
    assert support.run_git(project["repo"], "tag", "-l", "exp/multiagent/*") == "exp/multiagent/m1/r1"
    # the call: three subagents with their tools, the subagent tool offered, Bash only for the test command
    args = args_of(tmp_path)
    agents = json.loads(args[args.index("--agents") + 1])
    assert {r: a["tools"] for r, a in agents.items()} == {"analyzer": ["Read", "Glob", "Grep"],
                                                          "refactoring": ["Read", "Glob", "Grep", "Edit", "Write"],
                                                          "reviewer": ["Read", "Glob", "Grep"]}
    assert agents["analyzer"]["description"] == "The analyzer of lms/." and agents["reviewer"]["prompt"] == "You are the reviewer."
    assert args[args.index("--tools") + 1] == "Read,Glob,Grep,Edit,Write,Bash,Agent"
    assert f"Bash({FAKE_TESTS})" in args and "--safe-mode" not in args      # K1: it does not load subagents
    assert "Agent(general-purpose)" in args and "Agent(Explore)" in args       # K6c: built-in types denied
    assert FAKE_TESTS in args[1] and "at most 3 times" in args[1]           # placeholders of the orchestrator prompt
    # measured: the round with the feedback tests, then best (= round 1 = last) with both sets
    assert [(m["label"].split("-", 1)[1], m["set"]) for m in toolkit.measured] == [("rounds-r1", "feedback"),
                                                                                   ("final-r1", "both")]
    row = support.read_runs(tmp_path)[0]
    assert row["approach"] == "multiagent" and row["subagents_spawned"] == "3" and row["outcome"] == "success"


def test_rejected_snapshot_and_best_round(tmp_path, monkeypatch):
    _, toolkit, code, rec = start(tmp_path, monkeypatch, [
        {"agent": "analyzer"},
        {"agent": "refactoring", "write": {"lms/quality.json": quality(mean_cc=2.4, fail={"feedback": ["T-A-02-a"]})}},
        {"test": True},
        {"agent": "refactoring", "write": {"lms/quality.json": quality(mean_cc=2.6)}},
        {"test": True},
        {"agent": "reviewer"}])
    assert code == 0 and [r["accepted"] for r in rec["rounds"]] == [False, True] and rec["best_round"] == 2
    assert rec["rounds"][0]["feedback_lines"] == 1
    feedback = tmp_path / "out" / "multiagent" / "m1" / "rounds" / "r1" / "feedback.txt"
    assert "T-A-02-a: AssertionError" in feedback.read_text()             # what the orchestrator was told
    assert toolkit.measured[1]["previous_best"] is None                    # round 1 was not kept: start is the reference


def test_edit_after_the_last_test_run_is_a_round(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [
        REFACTOR, {"test": True},
        {"agent": "refactoring", "write": {"lms/quality.json": quality(mean_cc=2.3)}}])
    assert code == 0 and [r["source"] for r in rec["rounds"]] == ["test run 1", "end of the call"]
    assert rec["best_round"] == 2


def test_test_run_before_any_change_is_not_a_round(tmp_path, monkeypatch):
    _, _, code, rec = start(tmp_path, monkeypatch, [{"test": True}, REFACTOR, {"test": True}])
    assert code == 0 and [r["source"] for r in rec["rounds"]] == ["test run 2"]


def test_no_change(tmp_path, monkeypatch):
    _, toolkit, code, rec = start(tmp_path, monkeypatch, [{"agent": "analyzer"}, {"agent": "reviewer"}])
    assert code == 0 and rec["outcome"] == "no_change" and toolkit.measured == []


@pytest.mark.parametrize("steps, reason", [
    ([{"agent": "general-purpose"}], "type 'general-purpose'"),
    ([{"orchestrator_write": {"lms/a.py": "x = 1\n"}}], "orchestrator used Edit itself"),
    ([{"agent": "analyzer", "write": {"lms/a.py": "x = 1\n"}}], "analyzer subagent used Write"),
    ([REFACTOR] * 4, "Refactoring subagent called 4 times"),
    ([REFACTOR, {"test": True}, {"test": True}, {"test": True}, {"test": True}], "test command run 4 times"),
    ([{"test": True, "command": "sed -i s/a/b/ lms/a.py"}], "shell command(s) that can change files ran"),
    ([{"test": True, "command": "cat lms/a.py > lms/b.py"}], "shell command(s) that can change files ran"),
    ([{"test": True, "command": "python -c 'print(1)'"}], "shell command(s) that can change files ran"),
])
def test_invalid_runs(tmp_path, monkeypatch, steps, reason):
    _, toolkit, code, rec = start(tmp_path, monkeypatch, steps)
    assert code == common.EXIT_INVALID and rec["outcome"] == "invalid" and toolkit.measured == []
    assert any(reason in r for r in rec["reasons"]), rec["reasons"]


@pytest.mark.parametrize("denied, data", [
    ("Bash", {"command": "pytest -q"}),
    ("Bash", {"command": "ls /"}),
    ("Read", {"file_path": "/exp-tests/test_secret.py"}),
    ("Glob", {"pattern": "**/*.py", "path": "/engine"}),
    ("Glob", {"pattern": "/engine/**/*"}),                      # pilot-m01: the folder is in the pattern
    ("Read", {"file_path": "../engine/experiments/feedback_tests.py"}),
    ("Grep", {"pattern": "def ", "path": "~/x"}),
])
def test_blocked_attempts_are_counted_not_invalid(tmp_path, monkeypatch, denied, data):
    _, toolkit, code, rec = start(tmp_path, monkeypatch, [REFACTOR, {"denied": denied, "input": data}, {"test": True}])
    assert code == 0 and rec["outcome"] == "success" and rec["valid"] is True
    assert len(rec["roles"]["blocked"]) == 1 and rec["roles"]["blocked"][0].startswith(denied)
    assert support.read_runs(tmp_path)[0]["permission_denials"] == "1"


@pytest.mark.parametrize("denied, data, parent", [
    ("Edit", {"file_path": "/work/lms/loans/service.py"}, None),
    ("Read", {"file_path": "lms/__init__.py"}, None),
    ("Glob", {"pattern": "lms/**/*.py"}, None),
    ("Glob", {"pattern": "/work/lms/**/*.py"}, None),
    ("Bash", {"command": "TEST"}, None),
    ("Agent", {"subagent_type": "analyzer"}, None),
])
def test_denied_needed_call_means_a_broken_setup(tmp_path, monkeypatch, denied, data, parent):
    if data.get("command") == "TEST":
        data = {"command": FAKE_TESTS}
    _, toolkit, code, rec = start(tmp_path, monkeypatch, [REFACTOR, {"denied": denied, "input": data, "parent": parent}])
    assert code == common.EXIT_INVALID and toolkit.measured == []
    assert any("broken setup" in r for r in rec["reasons"]), rec["reasons"]


@pytest.mark.parametrize("command", ["find /work/lms -type f", "cat /work/lms/a.py", "ls -la lms", "grep -rn def lms | head -5"])
def test_read_only_shell_in_work_is_counted_not_invalid(tmp_path, monkeypatch, command):
    # K6b: Claude Code runs read-only commands inside /work on its own; same effect as Read / Glob / Grep
    _, _, code, rec = start(tmp_path, monkeypatch, [REFACTOR, {"test": True, "command": command}, {"test": True}])
    assert code == 0 and rec["valid"] is True and rec["roles"]["read_only_shell"] == [command]


def test_built_in_subagent_denied_by_rule_is_counted_not_invalid(tmp_path, monkeypatch):
    # K6c: the denial is only in the tool_result of the Agent call, not in permission_denials
    _, _, code, rec = start(tmp_path, monkeypatch, [{"agent": "general-purpose", "refused": "rule"}, REFACTOR, {"test": True}])
    assert code == 0 and rec["valid"] is True and rec["roles"]["blocked"] == ["Agent: general-purpose"]
    assert "general-purpose" not in rec["roles"]["subagent_calls"]


def test_role_that_cannot_be_started_means_a_broken_setup(tmp_path, monkeypatch):
    # K1: with --safe-mode the roles were not loaded: "Agent type 'analyzer' not found"
    _, toolkit, code, rec = start(tmp_path, monkeypatch, [{"agent": "analyzer", "refused": "missing"}, REFACTOR, {"test": True}])
    assert code == common.EXIT_INVALID and toolkit.measured == []
    assert any("subagent call failed (broken setup): analyzer" in r for r in rec["reasons"])


def test_limit_cut_keeps_the_run_and_does_not_discard_it(tmp_path, monkeypatch):
    # Week 6: the run is not discarded any more; status limit_cut, state.json with the session id (test_experiments_pause.py)
    _, _, code, rec = start(tmp_path, monkeypatch, [REFACTOR], limit=True)
    assert code == common.EXIT_LIMIT and rec["status"] == "limit_cut" and "outcome" not in rec
    assert (tmp_path / "out" / "multiagent" / "m1" / "state.json").is_file()


def test_dry_run_prints_the_multiagent_command(tmp_path, capsys):
    project = support.make_project(tmp_path)
    code = run_multiagent.main(support.argv(project, "m1", "--dry-run"), support.FakeToolkit())
    out = capsys.readouterr().out
    assert code == 0
    assert "--safe-mode" not in out                                          # K1
    assert f"Bash({run_multiagent.TEST_COMMAND})" in out
    assert "--agents" in out and '"analyzer"' in out and '"reviewer"' in out
    assert "Agent(general-purpose)" in out and "Read(//exp-tests/**)" in out    # K4, K6c
    assert "BASH_MAX_TIMEOUT_MS=3600000" in out and "/exp-state " in out        # K7
    assert "role:      refactoring ['Read', 'Glob', 'Grep', 'Edit', 'Write']" in out
    assert "{test_command}" not in out and run_multiagent.TEST_COMMAND in out.split("--- orchestrator prompt ---")[1]
    assert not (tmp_path / "out" / "multiagent" / "m1").exists()               # nothing written


def test_deny_rules_and_role_files(tmp_path):
    assert run_multiagent.deny_rules(["/exp-tests"]) == tuple(
        f"{t}(//exp-tests/**)" for t in ("Read", "Glob", "Grep", "Edit", "Write"))
    (tmp_path / "bad.md").write_text("no header")
    with pytest.raises(common.EngineError):
        run_multiagent.load_role(tmp_path / "bad.md")
    with pytest.raises(common.EngineError):
        run_multiagent.load_role(tmp_path / "missing.md")


# --- experiments/feedback_tests.py with a stub test runner ---------------------------------------------------------

STUB_RUN_TESTS = r'''
import json, sys
from pathlib import Path
args = sys.argv[1:]
opt = lambda flag: args[args.index(flag) + 1] if flag in args else None
code, out = Path(opt("--code")), Path(opt("--out"))
out.mkdir(parents=True, exist_ok=True)
q = code / "lms" / "quality.json"
fail = (json.loads(q.read_text()) if q.is_file() else {}).get("fail", {}).get("feedback", [])
only = set(Path(opt("--cases")).read_text().split()) if opt("--cases") else None
rows = ["case,module,table,type,set,result"]
cases = []
for case in ("T-A-01-a", "T-A-02-a"):
    if only is None or case in only:
        rows.append(f"{case},1,a,Normal,feedback,{'failed' if case in fail else 'passed'}")
        name = "test_t_" + case[2:].replace("-", "_").lower()
        body = ('<failure message="AssertionError: assert 500 == 201">E   AssertionError: assert 500 == 201\n'
                '/tmp/feedback-tree-x/project/lms/loans/service.py:42: AssertionError</failure>') if case in fail else ""
        cases.append(f'<testcase classname="feedback.test_a" name="{name}">{body}</testcase>')
(out / "tests.csv").write_text("\n".join(rows) + "\n")
(out / "feedback.junit.xml").write_text("<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>")
sys.exit(1 if fail else 0)
'''


def feedback_config(tmp_path, fail):
    project = support.make_project(tmp_path)
    work = tmp_path / "work" / "model"
    (work / "lms").mkdir(parents=True)
    (work / "lms" / "quality.json").write_text(quality(fail={"feedback": fail}))
    start = project["repo"] / "dataset" / "lms" / "generated"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "run_tests.py").write_text(STUB_RUN_TESTS)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"code": str(work), "project": str(start), "tests": str(project["tests"]),
                                  "hashes": str(tmp_path / "h.json"), "baseline": str(project["baseline"]),
                                  "state": str(tmp_path / "state"), "scripts": str(stubs), "max_runs": 2}))
    (tmp_path / "state").mkdir()
    return config


def test_feedback_tests_prints_the_w2_text_and_keeps_snapshots(tmp_path, capsys):
    config = feedback_config(tmp_path, ["T-A-02-a"])
    assert feedback_tests.main(["--config", str(config)]) == 0
    text = capsys.readouterr().out
    assert "- T-A-02-a" in text and "assert 500 == 201" in text and "/tmp/" not in text
    snap = tmp_path / "state" / "snapshots" / "01"
    assert (snap / "lms" / "quality.json").is_file() and (snap / "repeat2" / "tests.csv").is_file()
    meta = json.loads((snap / "meta.json").read_text())
    assert meta["new_failures"] == ["T-A-02-a"] and meta["regressions_confirmed"] is True
    assert "T-A-02-a" in (snap / "feedback.txt").read_text()


def test_feedback_tests_without_regression_and_budget(tmp_path, capsys):
    config = feedback_config(tmp_path, [])
    assert feedback_tests.main(["--config", str(config)]) == 0
    assert capsys.readouterr().out.strip() == feedback_tests.NO_REGRESSION_TEXT
    feedback_tests.main(["--config", str(config)])
    capsys.readouterr()
    feedback_tests.main(["--config", str(config)])                          # third run, max_runs = 2
    assert capsys.readouterr().out.strip().splitlines()[-1] == feedback_tests.BUDGET_TEXT.format(max_runs=2)
    assert sorted(p.name for p in (tmp_path / "state" / "snapshots").iterdir()) == ["01", "02"]


def test_run_lock_stays_held_during_the_orchestrator_call(tmp_path, monkeypatch):
    # the feedback tests run inside the call, so W13 does not apply to Multi-Agent (ADR 005)
    lock = tmp_path / ".run.lock"
    seen, real_run = [], common.subprocess.run

    def spy(cmd, *args, **kwargs):
        if "fake_claude.py" in " ".join(map(str, cmd)):
            seen.append(lock.exists())
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(common.subprocess, "run", spy)
    _, _, code, rec = start(tmp_path, monkeypatch, [REFACTOR, {"test": True}])
    assert code == 0 and seen == [True] and rec["calls"][0]["lock_released"] is False
