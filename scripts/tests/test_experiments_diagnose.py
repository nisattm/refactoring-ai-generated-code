"""Tests of the stream diagnosis (experiments/diagnose_stream.py) with small made-up stream-json logs: the role of
every event, tokens counted once per message, repeated and shared reads, and where a cut call ended."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS.parent / "experiments"))

import diagnose_stream as diag  # noqa: E402


def stream(*events, tail: str = "") -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n" + tail


def usage(i=1, o=2, w=3, r=4) -> dict:
    return {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": w, "cache_read_input_tokens": r}


def use(call_id, name, **data) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": data}


def assistant(msg_id, *blocks, parent=None, tokens=None) -> dict:
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"id": msg_id, "content": list(blocks), "usage": tokens or usage()}}


def answer(call_id, error=False, parent=None) -> dict:
    return {"type": "user", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "is_error": error,
                                     "content": "ok"}]}}


def rate(five, seven=0.4, status="allowed") -> dict:
    return {"type": "rate_limit_event", "rate_limit_info": {
        "status": status, "resetsAt": 1795370400, "rateLimitType": "five_hour",
        "unifiedWindows": {"five_hour": {"utilization": five, "resetsAt": 1795370400},
                           "seven_day": {"utilization": seven, "resetsAt": 1795536000}}}}


INIT = {"type": "system", "subtype": "init", "model": "claude-sonnet-5-5", "claude_code_version": "2.1.308",
        "session_id": "s1"}

# an orchestrator that calls the analyzer, then the refactoring subagent, then runs out of window
FULL = [
    INIT,
    assistant("m1", use("a1", "Agent", subagent_type="analyzer"), tokens=usage(10, 20, 30, 40)),
    assistant("m2", use("r1", "Read", file_path="/work/lms/a.py"), parent="a1", tokens=usage(1, 5, 0, 100)),
    assistant("m3", use("r2", "Read", file_path="/work/lms/b.py"), parent="a1", tokens=usage(1, 5, 0, 200)),
    assistant("m4", use("r3", "Read", file_path="/work/lms/a.py"), parent="a1", tokens=usage(1, 5, 0, 300)),
    answer("a1"),
    rate(0.5),
    assistant("m5", use("f1", "Agent", subagent_type="refactoring"), tokens=usage(2, 7, 0, 50)),
    assistant("m6", use("r4", "Read", file_path="/work/lms/a.py"), parent="f1", tokens=usage(1, 9, 0, 400)),
    assistant("m6", use("e1", "Edit", file_path="/work/lms/a.py"), parent="f1", tokens=usage(1, 11, 0, 400)),
    rate(1.0, status="rejected"),
    {"type": "result", "subtype": "error_during_execution", "is_error": True, "terminal_reason": "api_error",
     "api_error_status": 429, "num_turns": 3, "total_cost_usd": 1.5,
     "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 16, "outputTokens": 48, "cacheCreationInputTokens": 30,
                                          "cacheReadInputTokens": 990}}},
]


def test_roles_tokens_and_calls_are_attributed_by_parent():
    report = diag.analyze(stream(*FULL))
    roles = report["roles"]
    assert list(roles) == ["orchestrator", "analyzer", "refactoring"]
    assert report["messages"] == 6 and [roles[r]["calls"] for r in roles] == [2, 3, 1]
    assert (roles["orchestrator"]["input"], roles["orchestrator"]["output"]) == (12, 27)
    assert roles["analyzer"]["cache_read"] == 600
    # m6 appears in two events with a growing usage: counted once, the largest value of every field
    assert (roles["refactoring"]["output"], roles["refactoring"]["cache_read"]) == (11, 400)
    assert roles["refactoring"]["tools"] == {"Read": 1, "Edit": 1} and roles["orchestrator"]["tools"] == {"Agent": 2}
    assert report["totals"]["stream"] == {"input": 16, "output": 53, "cache_write": 30, "cache_read": 1090}
    assert report["totals"]["result"] == {"input": 16, "output": 48, "cache_write": 30, "cache_read": 990,
                                          "usd": 1.5}


def test_reads_repeated_and_shared_between_roles():
    roles = diag.analyze(stream(*FULL))["roles"]
    analyzer = roles["analyzer"]
    assert (analyzer["reads"], analyzer["distinct_files"], analyzer["repeated_reads"]) == (3, 2, 1)
    assert analyzer["most_read"] == [["/work/lms/a.py", 2]]
    assert roles["refactoring"]["reads"] == 1 and roles["refactoring"]["repeated_reads"] == 0
    assert analyzer["also_read_by_other_roles"] == 1 and roles["refactoring"]["also_read_by_other_roles"] == 1
    report = diag.analyze(stream(*FULL))
    assert report["distinct_files_read"] == 2 and report["shared_files"] == 1
    assert "files" not in roles["analyzer"]


def test_paths_are_normalized_before_counting():
    events = [assistant("m1", use("r1", "Read", file_path="/work/lms/a.py"),
                        use("r2", "Read", file_path="/work/lms/../lms/a.py"))]
    stats = diag.analyze(stream(*events))["roles"]["orchestrator"]
    assert (stats["reads"], stats["distinct_files"], stats["repeated_reads"]) == (2, 1, 1)


def test_subagent_runs_and_the_one_that_never_returned():
    report = diag.analyze(stream(*FULL))
    runs = {r["role"]: r for r in report["invocations"]}
    assert runs["analyzer"]["finished"] is True and runs["analyzer"]["calls"] == 3 and runs["analyzer"]["reads"] == 3
    assert runs["refactoring"]["finished"] is False and runs["refactoring"]["output"] == 11
    assert report["end"]["open_subagents"] == [{"role": "refactoring", "order": 2}]


def test_the_end_of_a_limit_cut_call():
    end = diag.analyze(stream(*FULL))["end"]
    assert end["result_event"] is True and end["api_error_status"] == 429 and end["terminal_reason"] == "api_error"
    assert end["last_model_call"] == {"role": "refactoring", "step_in_call": 6, "of_calls": 6, "step_in_role_run": 1}
    assert end["last_tool_use"] == {"role": "refactoring", "name": "Edit", "target": "/work/lms/a.py",
                                    "got_result": False}
    assert end["last_rate_limit"]["status"] == "rejected" and end["last_rate_limit"]["five_hour"] == 1.0


def test_rate_limit_events_carry_the_usage_so_far():
    first, last = diag.analyze(stream(*FULL))["rate_limits"]
    assert (first["five_hour"], first["seven_day"], first["messages_before"], first["role"]) == (0.5, 0.4, 4, "analyzer")
    assert (first["output_tokens_so_far"], first["cache_read_tokens_so_far"]) == (20 + 15, 40 + 600)
    assert last["messages_before"] == 6 and last["role"] == "refactoring" and last["output_tokens_so_far"] == 53


def test_a_killed_call_without_result_and_with_a_cut_line():
    text = stream(INIT, assistant("m1", use("x", "Grep", pattern="def ")), tail='{"type": "assistant", "mess')
    report = diag.analyze(text)
    assert report["bad_lines"] == 1 and report["end"]["result_event"] is False and report["totals"]["result"] is None
    assert report["end"]["last_tool_use"]["target"] == "def " and report["end"]["last_tool_use"]["got_result"] is False
    assert report["end"]["open_subagents"] == []


def test_other_subagent_types_and_unknown_parents_get_their_own_role():
    events = [assistant("m1", use("g1", "Agent", subagent_type="general-purpose")),
              assistant("m2", use("r1", "Read", file_path="/work/x.py"), parent="g1"),
              assistant("m3", use("r2", "Read", file_path="/work/y.py"), parent="missing")]
    roles = diag.analyze(stream(*events))["roles"]
    assert list(roles) == ["orchestrator", "other:general-purpose", "unknown"]
    assert roles["other:general-purpose"]["reads"] == 1 and roles["unknown"]["reads"] == 1


def test_a_subagent_that_returned_an_error_is_marked():
    events = [assistant("m1", use("a1", "Agent", subagent_type="analyzer")), answer("a1", error=True)]
    run = diag.analyze(stream(*events))["invocations"][0]
    assert run["finished"] is True and run["error"] is True and run["calls"] == 0


def test_an_empty_stream():
    report = diag.analyze("")
    assert report["messages"] == 0 and report["roles"] == {} and report["end"]["last_model_call"] is None
    assert "no result event" in diag.render("empty", report, 5)


def test_report_text_names_roles_numbers_and_the_end():
    text = diag.render("call-1", diag.analyze(stream(*FULL)), 5)
    assert "| analyzer | 1 | 3 | 3 | 15 | 0 | 600 | 3 | 2 | 1 | 1 |" in text
    assert "| analyzer | /work/lms/a.py | 2 |" in text
    assert "api_error_status 429" in text and "refactoring #2" in text and "| 50 % |" in text


def test_main_reads_a_run_folder_in_call_order(tmp_path, capsys):
    run = tmp_path / "scale-m01"
    for number in (10, 2, 1):
        folder = run / "calls" / f"call-{number}"
        folder.mkdir(parents=True)
        (folder / "stream.jsonl").write_text(stream(INIT, assistant(f"m{number}", use("r", "Read", file_path="/a"))))
    assert diag.main([str(run), "--json"]) == 0
    assert [Path(p).parent.name for p in json.loads(capsys.readouterr().out)] == ["call-1", "call-2", "call-10"]
    assert diag.main([str(run / "calls" / "call-2" / "stream.jsonl")]) == 0
    assert "## " in capsys.readouterr().out


def test_main_reports_a_missing_path_and_an_empty_folder(tmp_path, capsys):
    assert diag.main([str(tmp_path / "nope.jsonl")]) == 2
    assert diag.main([str(tmp_path)]) == 2
    assert "diagnose_stream:" in capsys.readouterr().err
