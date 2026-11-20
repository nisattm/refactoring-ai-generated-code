"""Unit tests of the experiment engine (experiments/common.py, experiments/measure.py; ADR 004)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests" / "fixtures" / "experiments"))

import support  # noqa: E402
from support import common  # noqa: E402

sys.path.insert(0, str(SCRIPTS.parent / "experiments"))
import measure  # noqa: E402


def stream(*events) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


INIT = {"type": "system", "subtype": "init", "tools": list(common.TOOLS), "model": common.MODEL,
        "claude_code_version": "2.1.308", "apiKeySource": "none", "session_id": "s1"}
USAGE = {common.MODEL: {"inputTokens": 1, "outputTokens": 2, "cacheReadInputTokens": 3, "cacheCreationInputTokens": 4}}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "result": "ok REFACTORING_DONE",
          "session_id": "s1", "modelUsage": USAGE, "total_cost_usd": 0.5, "subagent_stats": {"spawned": 0},
          "permission_denials": []}


def test_parse_stream_collects_tools_files_and_text():
    text = stream(INIT, {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "/work/lms/a.py"}},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/work/lms/b.py"}},
        {"type": "tool_use", "name": "Task", "input": {}}]}}, RESULT) + "not json\n"
    parsed = common.parse_stream(text)
    assert parsed["files_read"] == ["/work/lms/a.py"] and parsed["files_written"] == ["/work/lms/b.py"]
    assert parsed["subagent_attempts"] == 1 and parsed["tool_counts"]["Edit"] == 1
    assert common.DONE_MARKER in parsed["final_text"]


def test_per_call_share_of_cumulative_totals():
    first = {"usd": 0.0197, "input_tokens": 100, "cache_read_tokens": 1000, "note": "", "num_turns": 3}
    second = {"usd": 0.0251, "input_tokens": 150, "cache_read_tokens": 1800, "note": "", "num_turns": 2}
    share = common.per_call(second, first)
    assert share["usd"] == 0.0054 and share["input_tokens"] == 50 and share["cache_read_tokens"] == 800
    assert share["num_turns"] == 2 and common.per_call(first, None) == first
    assert common.per_call({"usd": 0.01, "input_tokens": 5}, first) == {"usd": 0.01, "input_tokens": 5}  # new session


def test_rate_limit_event_is_kept():
    event = {"type": "rate_limit_event", "rate_limit_info": {"rateLimitType": "five_hour", "utilization": 0.16}}
    assert common.parse_stream(stream(INIT, event, RESULT))["rate_limit"] == {"rate_limit_info": event["rate_limit_info"]}


def test_check_call_ok():
    assert common.check_call(common.parse_stream(stream(INIT, RESULT)), "", "2.1.308") == ("ok", [])


@pytest.mark.parametrize("init, result, expected", [
    ({"tools": ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]}, {}, "tool list"),
    ({"claude_code_version": "2.2.0"}, {}, "version"),
    ({"apiKeySource": "ANTHROPIC_API_KEY"}, {}, "credential"),
    ({}, {"subagent_stats": {"spawned": 2}}, "subagent"),
    ({}, {"subagent_stats": None}, "subagent_stats missing"),
    ({}, {"modelUsage": {"claude-opus-5-5": {"inputTokens": 1}}}, "other model"),
    ({}, {"permission_denials": [{"tool_name": "Write", "tool_use_id": "t1"}]}, "denied tool call(s): Write"),
    ({}, {"permission_denials": None}, "permission_denials missing"),
])
def test_check_call_invalid(init, result, expected):
    status, invalid = common.check_call(common.parse_stream(stream({**INIT, **init}, {**RESULT, **result})), "", "2.1.308")
    assert status == "ok" and any(expected in reason for reason in invalid), invalid


def test_check_call_limit_and_missing_result():
    limit = {**RESULT, "is_error": True, "subtype": "error_during_execution", "api_error_status": 429, "result": "x"}
    assert common.check_call(common.parse_stream(stream(INIT, limit)), "", None) == ("limit", [])
    text = {**RESULT, "is_error": True, "subtype": "error_during_execution", "result": "Claude usage limit reached"}
    assert common.check_call(common.parse_stream(stream(INIT, text)), "", None)[0] == "limit"
    assert common.check_call(common.parse_stream(stream(INIT)), "5-hour limit reached", None) == ("limit", [])
    status, invalid = common.check_call(common.parse_stream(stream(INIT)), "crash", None)
    assert status == "error" and invalid
    other = {**RESULT, "is_error": True, "subtype": "error_during_execution", "api_error_status": 500, "result": "boom"}
    assert common.check_call(common.parse_stream(stream(INIT, other)), "", None)[1]


def test_claude_args_have_the_w9_settings():
    args = common.claude_args("do it", "high", "s1")
    assert args[:2] == ["-p", "do it"]
    assert args[args.index("--tools") + 1] == "Read,Edit,Write,Glob,Grep"
    a = args.index("--allowedTools")
    assert args[a + 1:a + 6] == ["Read", "Edit", "Write", "Glob", "Grep"] and args[a + 6] == "--disallowedTools"
    i = args.index("--disallowedTools")
    assert args[i + 1:i + 3] == ["Task", "Agent"]
    for flag in ("--safe-mode", "--verbose"):
        assert flag in args
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert args[args.index("--resume") + 1] == "s1" and args[args.index("--model") + 1] == common.MODEL


def test_fill_prompt_only_fills_the_four_placeholders():
    text = common.fill_prompt("R{round}/{max_rounds} {feedback}|{reverted} {x} {}", round=2, max_rounds=4,
                              feedback="F", reverted="")
    assert text == "R2/4 F| {x} {}"
    with pytest.raises(ValueError):
        common.fill_prompt("x", other=1)


def test_hidden_or_forbidden():
    before = {"lms/a.py": "1"}
    after = {**before, "lms/.cache/x": "2", "CLAUDE.md": "3", "lms/sub/AGENTS.md": "4", "lms/b.py": "5"}
    assert common.hidden_or_forbidden(before, after) == ["CLAUDE.md", "lms/.cache/x", "lms/sub/AGENTS.md"]
    written = ["/work/lms/a.py", "/work/CLAUDE.md", "/root/.claude/settings.json", "/work/lms/AGENTS.md"]
    assert common.forbidden_writes(written) == ["/root/.claude/settings.json", "/work/CLAUDE.md", "/work/lms/AGENTS.md"]


def facts(**over):
    base = {"status": "ok", "problems": [], "run_successful": True, "reasons": [], "regressions": 0,
            "api_changed": False, "api_loads": True, "api_change_kind": None, "invalid_metrics": []}
    return {**base, **over}


@pytest.mark.parametrize("call_invalid, f, outcome, valid", [
    (["x"], facts(), "invalid", False),
    ([], None, "no_change", True),
    ([], facts(), "success", True),
    ([], facts(run_successful=False, reasons=["none improved"]), "no_improvement", True),
    ([], facts(run_successful=None), "no_improvement", True),
    ([], facts(regressions=2, run_successful=False), "failed", True),
    ([], facts(api_changed=True, api_change_kind="real API change", run_successful=False), "failed", True),
    ([], facts(api_loads=False, api_changed=True, run_successful=False), "failed", True),
    ([], facts(invalid_metrics=["mean_cc"], run_successful=False), "failed", True),
    ([], facts(status="timeout"), "failed", True),
    ([], facts(status="invalid", problems=["test files changed"]), "invalid", False),
    ([], facts(status="error", problems=["compare failed"]), "invalid", False),
])
def test_classify(call_invalid, f, outcome, valid):
    got = common.classify(call_invalid, f)
    assert got[:2] == (outcome, valid)


def test_run_lock(tmp_path):
    path = tmp_path / ".run.lock"
    with common.RunLock(path, "first", wait=0, poll=1):
        assert "what=first" in path.read_text() and "pid=" in path.read_text()
        with pytest.raises(common.EngineError) as exc:
            with common.RunLock(path, "second", wait=0, poll=1, log=lambda *_: None):
                pass
        assert exc.value.code == common.EXIT_LOCK
    assert not path.exists()


def test_workspace_and_tag(tmp_path):
    project = support.make_project(tmp_path)
    ws = common.Workspace(tmp_path / "work")
    ws.create(project["repo"], project["sha"], project["interface"], Path("missing"))
    assert sorted(ws.listing()) == ["INTERFACE.md", "lms/__init__.py", "lms/loans/__init__.py",
                                    "lms/loans/service.py", "requirements.txt"]
    assert not any(p.name.startswith(".") for p in ws.model.iterdir())
    before = ws.listing()
    (ws.model / "lms" / "loans" / "service.py").write_text("def fee(d):\n    return 2 * d\n")
    (ws.model / "requirements.txt").write_text("changed\n")
    (ws.model / "notes").mkdir()
    (ws.model / "notes" / "plan.md").write_text("x")
    (ws.model / "INTERFACE.md").unlink()
    changes = ws.discard_outside_lms(before)
    assert changes == {"changed": ["requirements.txt"], "added": ["notes/plan.md"], "removed": ["INTERFACE.md"]}
    assert (ws.model / "requirements.txt").read_text() == "fastapi\n" and (ws.model / "INTERFACE.md").is_file()
    assert not (ws.model / "notes").exists() and ws.lms_changed()
    commit = ws.commit("round 1")
    tree = ws.tree_for(commit, "r1")
    assert (tree / "web" / "index.html").is_file() and (tree / "tests" / "test_own.py").is_file()
    assert "2 * d" in (tree / "lms" / "loans" / "service.py").read_text()

    sha = common.tag_code(project["repo"], project["sha"], ws.model / "lms", "exp/single/t/r1", "msg")
    changed = support.run_git(project["repo"], "diff", "--name-only", project["sha"], "exp/single/t/r1").splitlines()
    assert changed == ["dataset/lms/generated/lms/loans/service.py"]
    assert support.run_git(project["repo"], "rev-parse", "exp/single/t/r1") == sha
    assert support.run_git(project["repo"], "status", "--porcelain") == "M dataset/lms/generated/lms/loans/service.py"
    assert "days * 4" in (project["repo"] / "dataset/lms/generated/lms/loans/service.py").read_text()
    with pytest.raises(common.EngineError):
        common.tag_code(project["repo"], project["sha"], ws.model / "lms", "exp/single/t/r1", "msg")

    (ws.model / "lms" / "loans" / "service.py").write_text("broken")
    (ws.model / "lms" / "new.py").write_text("x")
    ws.restore(commit)
    assert "2 * d" in (ws.model / "lms" / "loans" / "service.py").read_text()
    assert not (ws.model / "lms" / "new.py").exists() and not ws.lms_changed()


def test_new_failures():
    before = {("feedback", "A"): "passed", ("feedback", "B"): "passed", ("feedback", "C"): "failed",
              ("heldout", "D"): "passed", ("feedback", "F"): "passed"}
    after = {("feedback", "A"): "passed", ("feedback", "B"): "failed", ("feedback", "C"): "failed",
             ("feedback", "F"): "error"}
    assert measure.new_failures(before, after, {"F"}) == ["B"]


def test_api_change_kind():
    def schema(desc="d", name="LoanOut", field="days"):
        return {"paths": {"/loans": {"get": {"description": desc, "responses": {"200": {"content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}}}}}}},
                "components": {"schemas": {name: {"title": name, "properties": {field: {"type": "integer"}}}}}}
    assert measure.api_change_kind(schema(), schema(desc="other")) == "descriptions only"
    assert measure.api_change_kind(schema(), schema(name="LoanResponse")) == "schema names only"
    assert measure.api_change_kind(schema(), schema(field="weeks")) == "real API change"


STUB = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
name = Path(sys.argv[0]).stem
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps([name, args]) + "\n")
def opt(flag):
    return args[args.index(flag) + 1] if flag in args else None
out = Path(opt("--out"))
out.mkdir(parents=True, exist_ok=True)
if name == "analyze":
    (out / "summary.json").write_text("{}")
elif name == "run_tests":
    code = int(os.environ.get("STUB_TESTS_EXIT") or "0")
    if code in (3, 4):
        sys.exit(code)
    fail = os.environ.get("STUB_FAIL", "")
    rows = ["case,module,table,type,set,result", f"T-1,1,a,Normal,feedback,{'failed' if fail == 'T-1' else 'passed'}",
            "T-2,1,a,Normal,feedback,passed"]
    (out / "tests.csv").write_text("\n".join(rows) + "\n")
elif name == "compare":
    (out / "compare.json").write_text(json.dumps({"openapi": {"changed": os.environ.get("STUB_API") == "1"}}))
'''


def stub_measure(tmp_path, monkeypatch, **env):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("analyze", "run_tests", "compare"):
        (stubs / f"{name}.py").write_text(STUB)
    log = tmp_path / "steps.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    for key in ("STUB_TESTS_EXIT", "STUB_FAIL", "STUB_API"):
        monkeypatch.setenv(key, env.get(key, ""))
    monkeypatch.setattr(measure, "SCRIPTS", stubs)
    code_dir = tmp_path / "tree"
    (code_dir / "lms").mkdir(parents=True)
    base = tmp_path / "baseline"
    base.mkdir()
    (base / "tests.csv").write_text("case,module,table,type,set,result\nT-1,1,a,Normal,feedback,passed\n"
                                    "T-2,1,a,Normal,feedback,passed\nT-3,1,a,Normal,heldout,passed\n")
    (base / "flaky.txt").write_text("# none\n")
    out = tmp_path / "m"
    argv = ["--code", str(code_dir), "--tests", str(tmp_path / "t"), "--hashes", str(tmp_path / "h.json"),
            "--baseline", str(base), "--start-code", str(code_dir), "--out", str(out), "--label", "x",
            "--code-sha", "abc", "--set", "feedback", "--previous-best", str(tmp_path / "best")]
    code = measure.main(argv)
    steps = [json.loads(line) for line in log.read_text().splitlines()] if log.is_file() else []
    return code, json.loads((out / "measure.json").read_text()), steps


def test_measure_steps_without_new_failures(tmp_path, monkeypatch):
    code, info, steps = stub_measure(tmp_path, monkeypatch)
    assert code == 0 and info["status"] == "ok" and info["new_failures"] == []
    assert [s[0] for s in steps] == ["analyze", "run_tests", "compare"]
    analyze, tests, compare = (s[1] for s in steps)
    assert analyze[analyze.index("--code-sha") + 1] == "abc" and "--with-secondary" in analyze
    assert tests[tests.index("--set") + 1] == "feedback" and "--baseline" in tests
    for flag in ("--previous-best", "--before-code", "--after-code", "--flaky", "--tests-before"):
        assert flag in compare
    assert "--tests-after-repeat" not in compare


def test_measure_repeats_new_failures_twice(tmp_path, monkeypatch):
    code, info, steps = stub_measure(tmp_path, monkeypatch, STUB_FAIL="T-1", STUB_API="1")
    assert code == 0 and info["new_failures"] == ["T-1"]
    assert [s[0] for s in steps] == ["analyze", "run_tests", "run_tests", "run_tests", "compare"]
    assert all("--cases" in s[1] for s in steps[2:4])
    assert steps[4][1].count("--tests-after-repeat") == 2
    assert info["api_change_kind"] == "code does not load"     # the stub tree has no real lms package


def test_measure_invalid_and_timeout(tmp_path, monkeypatch):
    code, info, _ = stub_measure(tmp_path, monkeypatch, STUB_TESTS_EXIT="3")
    assert code == 3 and info["status"] == "invalid"


def test_measure_timeout_is_repeated_once(tmp_path, monkeypatch):
    code, info, steps = stub_measure(tmp_path, monkeypatch, STUB_TESTS_EXIT="4")
    assert code == 4 and info["status"] == "timeout"
    assert [s[0] for s in steps] == ["analyze", "run_tests", "run_tests"]
