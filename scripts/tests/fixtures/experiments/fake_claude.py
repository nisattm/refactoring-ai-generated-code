"""A fake `claude -p` for the engine tests: edits files and prints a stream-json log, as told by a scenario file.

The scenario (path in FAKE_CLAUDE_SCENARIO) is a JSON list with one entry per call:

    {"write": {"lms/core.py": "..."}, "delete": ["lms/x.py"], "text": "REFACTORING_DONE", "subagents": 0,
     "tools": [...], "denied": ["Write"], "limit": false, "no_result": false, "cost": 0.5, "version": "9.9.9"}

Every call's arguments are saved as CLAUDE_CONFIG_DIR/fake-call-N.json.
"""

import json
import os
import sys
from pathlib import Path

TOOLS = ["Read", "Edit", "Write", "Glob", "Grep"]


def main() -> int:
    session = Path(os.environ["CLAUDE_CONFIG_DIR"])
    counter = session / "fake-count"
    number = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(number))
    args = sys.argv[1:]
    (session / f"fake-call-{number}.json").write_text(json.dumps({"args": args, "cwd": os.getcwd(), "env": {
        k: os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS")}}))
    scenario = json.loads(Path(os.environ["FAKE_CLAUDE_SCENARIO"]).read_text())
    spec = scenario[number - 1] if number <= len(scenario) else {}
    session_id = args[args.index("--resume") + 1] if "--resume" in args else f"session-{number}"

    def emit(event: dict) -> None:
        print(json.dumps(event), flush=True)

    emit({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour",
                                                          "utilization": 0.05}})
    offered = args[args.index("--tools") + 1].split(",") if "--tools" in args else TOOLS
    offered = ["Task" if t == "Agent" else t for t in offered]          # as Claude Code 2.1.308 lists it (K1)
    denials = []
    emit({"type": "system", "subtype": "init", "session_id": session_id, "tools": spec.get("tools", offered),
          "model": spec.get("model", "claude-sonnet-5-5"), "claude_code_version": spec.get("version", "9.9.9"),
          "apiKeySource": "none"})
    for rel, content in spec.get("write", {}).items():
        path = Path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        emit({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": f"/work/{rel}"}}]}})
    for rel in spec.get("delete", []):
        Path(rel).unlink()
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read",
                                                        "input": {"file_path": "/work/INTERFACE.md"}}]}})
    if spec.get("subagents"):
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Task", "input": {}}]}})
    spawned = spec.get("subagents", 0)
    # Multi-Agent: "steps" of the orchestrator; tool uses of a subagent carry its call id as parent_tool_use_id
    for i, step in enumerate(spec.get("steps", [])):
        if "agent" in step and step.get("refused"):     # K1 / K6c: the Agent call returns an error, nothing runs
            call_id = f"agent-{number}-{i}"
            emit({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "tool_use",
                  "id": call_id, "name": "Agent", "input": {"subagent_type": step["agent"], "prompt": "task"}}]}})
            text = (f"Agent type '{step['agent']}' has been denied by permission rule 'Agent({step['agent']})' from cliArg."
                    if step["refused"] == "rule" else f"Agent type '{step['agent']}' not found. Available agents: claude")
            emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": call_id,
                                                           "is_error": True, "content": text}]}})
        elif "agent" in step:
            spawned += 1
            call_id = f"agent-{number}-{i}"
            emit({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "tool_use",
                  "id": call_id, "name": step.get("tool", "Agent"),
                  "input": {"subagent_type": step["agent"], "prompt": "task"}}]}})
            emit({"type": "assistant", "parent_tool_use_id": call_id, "message": {"content": [
                {"type": "tool_use", "id": f"{call_id}-r", "name": "Read", "input": {"file_path": "/work/lms/__init__.py"}}]}})
            for rel, content in step.get("write", {}).items():
                path = Path(rel)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                emit({"type": "assistant", "parent_tool_use_id": call_id, "message": {"content": [
                    {"type": "tool_use", "id": f"{call_id}-w", "name": step.get("write_tool", "Write"),
                     "input": {"file_path": f"/work/{rel}"}}]}})
        elif "denied" in step:            # a call the permissions blocked: in the stream and in permission_denials
            tool, data = step["denied"], step.get("input", {})
            use_id = f"denied-{number}-{i}"
            emit({"type": "assistant", "parent_tool_use_id": step.get("parent"), "message": {"content": [
                {"type": "tool_use", "id": use_id, "name": tool, "input": data}]}})
            denials.append({"tool_name": tool, "tool_use_id": use_id, "tool_input": data})
        elif "test" in step:
            allowed = args[args.index("--allowedTools") + 1:]
            rule = next(a for a in allowed if a.startswith("Bash("))
            command = step.get("command") or rule[len("Bash("):-1]
            emit({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "tool_use",
                  "id": f"bash-{number}-{i}", "name": "Bash", "input": {"command": command}}]}})
            if not step.get("command"):
                import shlex
                import subprocess
                subprocess.run(shlex.split(command), check=False, stdout=subprocess.DEVNULL)
        elif "orchestrator_write" in step:
            for rel, content in step["orchestrator_write"].items():
                Path(rel).write_text(content, encoding="utf-8")
                emit({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "tool_use",
                      "id": f"ow-{number}-{i}", "name": "Edit", "input": {"file_path": f"/work/{rel}"}}]}})
    if spec.get("no_result"):
        print("Claude usage limit reached", file=sys.stderr)
        return 1
    # like Claude Code: total_cost_usd and modelUsage are cumulative over a resumed session
    totals_file = session / f"fake-total-{session_id}.json"
    totals = json.loads(totals_file.read_text()) if totals_file.exists() else {"usd": 0.0, "calls": 0}
    totals = {"usd": round(totals["usd"] + spec.get("cost", 0.25), 6), "calls": totals["calls"] + 1}
    totals_file.write_text(json.dumps(totals))
    n = totals["calls"]
    usage = {"claude-sonnet-5-5": {"inputTokens": 10 * n, "outputTokens": 20 * n, "cacheReadInputTokens": 100 * n,
                                   "cacheCreationInputTokens": 50 * n, "costUSD": totals["usd"]}}
    if spec.get("limit"):
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "api_error_status": 429,
              "result": "Claude AI usage limit reached", "session_id": session_id, "terminal_reason": "error",
              "total_cost_usd": totals["usd"], "modelUsage": usage,
              "subagent_stats": {"spawned": 0}, "permission_denials": []})
        return 1
    emit({"type": "result", "subtype": "success", "is_error": False, "result": spec.get("text", "Done."),
          "session_id": session_id, "terminal_reason": "completed", "num_turns": 3, "duration_ms": 1000,
          "total_cost_usd": totals["usd"], "modelUsage": usage,
          "subagent_stats": {"spawned": spawned},
          "permission_denials": [{"tool_name": name, "tool_use_id": f"t{i}", "tool_input": {}}
                                 for i, name in enumerate(spec.get("denied", []))] + denials})
    return 0


if __name__ == "__main__":
    sys.exit(main())
