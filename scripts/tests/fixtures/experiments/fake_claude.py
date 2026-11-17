"""A fake `claude -p` for the engine tests: edits files and prints a stream-json log, as told by a scenario file.

The scenario (path in FAKE_CLAUDE_SCENARIO) is a JSON list with one entry per call:

    {"write": {"lms/core.py": "..."}, "delete": ["lms/x.py"], "text": "REFACTORING_DONE", "subagents": 0,
     "tools": [...], "limit": false, "no_result": false, "cost": 0.5, "version": "9.9.9"}

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

    emit({"type": "system", "subtype": "init", "session_id": session_id, "tools": spec.get("tools", TOOLS),
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
    if spec.get("no_result"):
        print("Claude usage limit reached", file=sys.stderr)
        return 1
    usage = {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 20, "cacheReadInputTokens": 100,
                                   "cacheCreationInputTokens": 50, "costUSD": spec.get("cost", 0.25)}}
    if spec.get("limit"):
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "api_error_status": 429,
              "result": "Claude AI usage limit reached", "session_id": session_id, "terminal_reason": "error",
              "total_cost_usd": spec.get("cost", 0.1), "modelUsage": usage,
              "subagent_stats": {"spawned": 0}})
        return 1
    emit({"type": "result", "subtype": "success", "is_error": False, "result": spec.get("text", "Done."),
          "session_id": session_id, "terminal_reason": "completed", "num_turns": 3, "duration_ms": 1000,
          "total_cost_usd": spec.get("cost", 0.25), "modelUsage": usage,
          "subagent_stats": {"spawned": spec.get("subagents", 0)}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
