"""The shell rule of 24 November 2026 (read-only commands never invalidate, in any role and approach; commands that
write, delete or are not on the list do) and ``--rejudge-run`` (the same run judged again without Claude)."""

from __future__ import annotations

import csv
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
REFACTOR = {"agent": "refactoring", "write": {"lms/quality.json": quality(mean_cc=2.5)}}
# the command of the Refactoring subagent in m01c (24 November 2026), which made the run invalid
M01C_COMMAND = "find /work/lms -name '*.py' | sort | xargs wc -l | sort -k2 | tail -n 200"


# --- the rule ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "find /work/lms -name '*.py' | sort | tail -n 200",
    "find /work/lms -type f | wc -l",
    "ls -la lms",
    "ls lms 2>/dev/null",
    "cat lms/a.py",
    "head -n 20 lms/a.py && tail -n 5 lms/a.py",
    "grep -rn 'def ' lms | sort | uniq -c | head -5",
    "sort -k2 -n lms/list.txt | uniq",
    "wc -l lms/a.py lms/b.py; ls",
    "grep -c x lms/a.py || ls",
])
def test_read_only_commands_of_the_list_are_accepted(command):
    assert common.classify_shell(command) == (True, "")


@pytest.mark.parametrize("command, why", [
    (M01C_COMMAND, "'xargs' is not on the list"),
    ("echo hi", "'echo'"),
    ("python -c 'print(1)'", "'python'"),
    ("rm -rf lms", "'rm'"),
    ("sed -i s/a/b/ lms/a.py", "'sed'"),
    ("tee out.txt", "'tee'"),
    ("find lms -name '*.pyc' -delete", "find with an action"),
    ("find lms -exec rm {} ;", "find with an action"),
    ("find lms -fprint out.txt", "find with an action"),
    ("sort -o out.txt in.txt", "sort with an output"),
    ("sort --output=out.txt in.txt", "sort with an output"),
    ("uniq in.txt out.txt", "uniq with an output"),
    ("cat a.py > b.py", "'>' is not allowed"),
    ("cat a.py >> b.py", "'>>' is not allowed"),
    ("cat < a.py", "'<' is not allowed"),
    ("ls $(pwd)", "'(' is not allowed"),
    ("ls `pwd`", "command substitution"),
    ("ls & rm x", "'&' is not allowed"),
    ("ls; rm x", "'rm'"),
    ("ls | xargs rm", "'xargs'"),
    ("ls 'unclosed", "cannot be parsed"),
    ("   ", "empty command"),
])
def test_other_commands_are_not_accepted(command, why):
    ok, reason = common.classify_shell(command)
    assert ok is False and why in reason, reason


def test_shell_check_separates_the_own_command_read_only_and_invalid():
    uses = [{"name": "Bash", "input": {"command": "ls lms"}}, {"name": "Read", "input": {"file_path": "/work/a"}},
            {"name": "Bash", "input": {"command": "python /engine/x.py"}}, {"name": "Bash", "input": {"command": "rm a"}}]
    report = common.shell_check(uses, allowed_command="python /engine/x.py")
    assert report["read_only"] == ["ls lms"] and len(report["invalid"]) == 1 and report["invalid"][0].startswith("rm a (")


# --- every role, over all calls -----------------------------------------------------------------------------------

def agent(call_id, role, parent=None):
    return {"name": "Agent", "id": call_id, "input": {"subagent_type": role}, "parent": parent}


def bash(command, parent=None, use_id="b"):
    return {"name": "Bash", "id": use_id, "input": {"command": command}, "parent": parent}


TEST_COMMAND = "python /engine/experiments/feedback_tests.py"


@pytest.mark.parametrize("role", ["analyzer", "refactoring", "reviewer"])
def test_a_subagent_may_run_read_only_commands(role):
    roles = run_multiagent.analyze_roles([agent("a1", role), bash("find /work/lms -type f | wc -l", "a1"),
                                          bash("ls lms", "a1", "c")], TEST_COMMAND)
    assert roles["invalid"] == [] and roles["read_only_shell_by_role"] == {role: 2}
    assert roles["read_only_shell"] == ["find /work/lms -type f | wc -l", "ls lms"]


@pytest.mark.parametrize("command", ["rm -rf lms", "python -c 1", M01C_COMMAND, "cat a > b"])
def test_a_subagent_command_that_writes_or_is_not_listed_makes_the_run_invalid(command):
    roles = run_multiagent.analyze_roles([agent("a1", "refactoring"), bash(command, "a1")], TEST_COMMAND)
    assert len(roles["invalid"]) == 1 and "refactoring: " in roles["invalid"][0] and roles["read_only_shell"] == []


def test_the_orchestrator_rule_is_the_same_and_its_test_command_is_still_a_test():
    ok = run_multiagent.analyze_roles([bash(TEST_COMMAND), bash("cat lms/a.py", use_id="c")], TEST_COMMAND)
    assert ok["test_runs"] == 1 and ok["read_only_shell"] == ["cat lms/a.py"] and ok["invalid"] == []
    assert ok["read_only_shell_by_role"] == {"orchestrator": 1}
    bad = run_multiagent.analyze_roles([bash("echo hi")], TEST_COMMAND)
    assert "not read-only commands of the list" in bad["invalid"][0]
    # a subagent does not run the test command: it is a command that is not on the list
    assert run_multiagent.analyze_roles([agent("a1", "reviewer"), bash(TEST_COMMAND, "a1")], TEST_COMMAND)["invalid"]


def test_a_shell_command_of_an_unknown_subagent_is_still_invalid():
    roles = run_multiagent.analyze_roles([bash("ls", "nobody")], TEST_COMMAND)
    assert roles["invalid"] == ["a tool call (Bash) of an unknown subagent"]


def multi(tmp_path, monkeypatch, steps, run_id="m1", *extra):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [{"steps": steps}])
    toolkit = support.FakeToolkit()
    code = run_multiagent.main(support.argv(project, run_id, "--test-command", FAKE_TESTS, *extra), toolkit)
    return project, toolkit, code, load(tmp_path, run_id)


def load(tmp_path, run_id="m1") -> dict:
    return json.loads((tmp_path / "out" / "multiagent" / run_id / "run.json").read_text())


def test_multiagent_run_with_a_read_only_command_of_the_refactoring_subagent_is_valid(tmp_path, monkeypatch):
    command = "find /work/lms -name '*.py' | sort | tail -n 200"
    _, toolkit, code, rec = multi(tmp_path, monkeypatch, [{**REFACTOR, "bash": [command]}, {"test": True}])
    assert code == 0 and rec["valid"] is True and rec["outcome"] == "success"
    assert rec["roles"]["read_only_shell"] == [command] and rec["roles"]["read_only_shell_by_role"] == {"refactoring": 1}


def test_multiagent_run_with_the_m01c_command_stays_invalid_because_of_xargs(tmp_path, monkeypatch):
    _, toolkit, code, rec = multi(tmp_path, monkeypatch, [{**REFACTOR, "bash": [M01C_COMMAND]}, {"test": True}])
    assert code == common.EXIT_INVALID and toolkit.measured == []
    assert any("refactoring: " in r and "'xargs' is not on the list" in r for r in rec["reasons"])


# --- Single and Iterative use the same function -------------------------------------------------------------------

def test_single_counts_read_only_commands_and_rejects_the_others(tmp_path, monkeypatch):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [{"bash": ["ls lms", "cat lms/a.py | head -3"], "write": {"lms/quality.json": quality(mean_cc=2.5)}}])
    assert run_single.main(support.argv(project, "s1"), support.FakeToolkit()) == 0
    rec = json.loads((tmp_path / "out" / "single" / "s1" / "run.json").read_text())
    assert rec["calls"][0]["read_only_shell"] == ["ls lms", "cat lms/a.py | head -3"] and rec["calls"][0]["invalid"] == []

    support.scenario(monkeypatch, tmp_path, [{"bash": ["ls lms", "rm -rf lms"]}])
    assert run_single.main(support.argv(project, "s2"), support.FakeToolkit()) == common.EXIT_INVALID
    rec = json.loads((tmp_path / "out" / "single" / "s2" / "run.json").read_text())
    assert any(r.startswith("shell command that is not a read-only command of the list: rm -rf lms") for r in rec["reasons"])


def test_iterative_uses_the_same_rule(tmp_path, monkeypatch):
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [{"bash": ["echo hi"]}])
    assert run_iterative.main(support.argv(project, "i1"), support.FakeToolkit()) == common.EXIT_INVALID
    rec = json.loads((tmp_path / "out" / "iterative" / "i1" / "run.json").read_text())
    assert any("'echo' is not on the list" in r for r in rec["reasons"])


# --- --rejudge-run -------------------------------------------------------------------------------------------------

def rows(tmp_path) -> list[dict]:
    with (tmp_path / "out" / "runs.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def invalid_under_the_old_rule(tmp_path, monkeypatch, steps):
    """A run that ended invalid as m01c did: the old rule is a classifier that refuses every shell command."""
    project = support.make_project(tmp_path)
    support.scenario(monkeypatch, tmp_path, [{"steps": steps}])
    toolkit = support.FakeToolkit()
    with monkeypatch.context() as old:
        old.setattr(common, "classify_shell", lambda command: (False, "the old rule"))
        code = run_multiagent.main(support.argv(project, "m1", "--test-command", FAKE_TESTS), toolkit)
    assert code == common.EXIT_INVALID and toolkit.measured == []
    copy = tmp_path / "work-copy"
    shutil.copytree(tmp_path / "work-m1", copy)
    return project, toolkit, copy


def rejudge(tmp_path, project, toolkit, copy, *extra):
    return run_multiagent.main(support.argv(project, "m1", "--rejudge-run", "--work-root", str(copy), *extra), toolkit)


def fake_calls(tmp_path) -> int:
    return len(list(tmp_path.glob("work-*/session/fake-call-*.json")))


def test_rejudge_measures_a_run_that_is_valid_under_the_new_rule(tmp_path, monkeypatch):
    project, toolkit, copy = invalid_under_the_old_rule(
        tmp_path, monkeypatch, [{**REFACTOR, "bash": ["find /work/lms -type f | wc -l"]}, {"test": True}])
    before = rows(tmp_path)
    assert len(before) == 1 and before[0]["outcome"] == "invalid"
    calls_before = fake_calls(tmp_path)
    assert rejudge(tmp_path, project, toolkit, copy) == 0
    rec = load(tmp_path)
    assert fake_calls(tmp_path) == calls_before                     # Claude was not called
    assert rec["valid"] is True and rec["outcome"] == "success" and rec["best_round"] == 1
    first, second = rec["decisions"]
    assert (first["outcome"], first["valid"]) == ("invalid", False) and "old rule" in first["reasons"][0]
    assert (second["outcome"], second["valid"], second["reasons"]) == ("success", True, [])
    assert rec["roles"]["read_only_shell_by_role"] == {"refactoring": 1} and first["roles"]["read_only_shell"] == []
    assert rec["work_root"] == str(copy) and copy.is_dir()           # rebound to the copy, which is kept
    after = rows(tmp_path)
    assert len(after) == 2 and after[0] == before[0]                 # the old row is not changed
    assert after[1]["run_id"] == "m1" and after[1]["valid"] == "true" and after[1]["outcome"] == "success"
    assert "rejudged with --rejudge-run" in after[1]["note"] and before[0]["finished_at"] in after[1]["note"]
    assert support.run_git(project["repo"], "tag", "-l", "exp/multiagent/m1/*") == "exp/multiagent/m1/r1"
    assert [m["set"] for m in toolkit.measured] == ["feedback", "both"]


def test_rejudge_of_a_run_that_is_still_invalid_adds_a_row_and_measures_nothing(tmp_path, monkeypatch):
    project, toolkit, copy = invalid_under_the_old_rule(
        tmp_path, monkeypatch, [{**REFACTOR, "bash": ["rm -rf lms"]}, {"test": True}])
    assert rejudge(tmp_path, project, toolkit, copy) == common.EXIT_INVALID
    rec = load(tmp_path)
    assert rec["valid"] is False and rec["outcome"] == "invalid" and toolkit.measured == []
    assert [d["valid"] for d in rec["decisions"]] == [False, False]
    assert "refactoring: rm -rf lms" in rec["decisions"][1]["reasons"][0]
    after = rows(tmp_path)
    assert [r["outcome"] for r in after] == ["invalid", "invalid"] and "rejudged" in after[1]["note"]
    assert support.run_git(project["repo"], "tag", "-l", "exp/multiagent/m1/*") == ""


def test_rejudge_refuses_what_cannot_be_judged_again(tmp_path, monkeypatch, capsys):
    project, toolkit, copy = invalid_under_the_old_rule(tmp_path, monkeypatch, [{**REFACTOR, "bash": ["ls"]}, {"test": True}])
    assert rejudge(tmp_path, project, toolkit, tmp_path / "nowhere") == common.EXIT_USAGE
    assert "is gone or incomplete" in capsys.readouterr().err
    assert rejudge(tmp_path, project, toolkit, copy) == 0
    assert rejudge(tmp_path, project, toolkit, copy) == common.EXIT_USAGE            # valid now: nothing to judge
    assert "did not end invalid" in capsys.readouterr().err
    assert run_multiagent.main(support.argv(project, "nope", "--rejudge-run"), toolkit) == common.EXIT_USAGE


def test_rejudge_twice_is_refused(tmp_path, monkeypatch, capsys):
    project, toolkit, copy = invalid_under_the_old_rule(tmp_path, monkeypatch, [{**REFACTOR, "bash": ["rm x"]}, {"test": True}])
    assert rejudge(tmp_path, project, toolkit, copy) == common.EXIT_INVALID
    assert rejudge(tmp_path, project, toolkit, copy) == common.EXIT_USAGE
    assert "already judged again" in capsys.readouterr().err and len(rows(tmp_path)) == 2


def test_resume_run_and_rejudge_run_exclude_each_other(tmp_path, capsys):
    project = support.make_project(tmp_path)
    assert run_multiagent.main(support.argv(project, "m1", "--resume-run", "--rejudge-run"), support.FakeToolkit()) == common.EXIT_USAGE
    assert "exclude each other" in capsys.readouterr().err
