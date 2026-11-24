"""Diagnosis of the ``stream.jsonl`` of a Claude Code call (Week 6, usage-limit analysis): where did the tokens go,
which files were read how often, and where was the call cut.

    python experiments/diagnose_stream.py <stream.jsonl | run folder> [...] [--top 5] [--json]

A run folder (``results/experiments/<approach>/<run-id>``) is searched for ``calls/call-N/stream.jsonl``. Per call and
per role the report shows the number of model calls (API messages), input and cache tokens, the largest context, the
tools used, the files read (total, distinct, read again), and where the call ended (role, step, last tool use,
unfinished or cut subagents, the ``result`` event, the last ``rate_limit_event``). It only reads; it never changes a
file and never talks to Claude. Standard library only, so it runs on the host without Docker.

Roles: ``orchestrator`` is every event without ``parent_tool_use_id``; a subagent's events carry the id of the
orchestrator's Agent / Task call, and the role is that call's ``subagent_type``.

Checked against the stream of scale-m01 (258 messages in 802 ``assistant`` events): the events of one message share
its ``message.id`` and the same ``usage``, so the usage of a message is counted once. The input and cache fields are
right; **``output_tokens`` of a message is only its first value and is never updated** (sum 2,333 against 250,646 in
``modelUsage``). The output of the call is therefore taken from ``modelUsage`` of the ``result`` event; it exists only
for the whole call, not per role (the per-role value is kept as ``output_partial`` and is not shown).

The context of a call is input + cache write + cache read tokens of that message. Compaction: events of type
``system`` whose subtype contains "compact" are counted (the Agent SDK documents ``compact_boundary`` with
``compact_metadata`` ``trigger`` and ``pre_tokens``). **Not verified**: scale-m01 has no compaction (largest context
661,170 of 1,000,000), so no real compaction event has been seen; ``context_drops`` (a call whose context is less than
half of the one before) is a second, indirect hint.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

ROLES = ("orchestrator", "analyzer", "refactoring", "reviewer")
SUBAGENT_TOOLS = ("Agent", "Task")      # the call is named Agent, the init event lists Task (setup check K1)
USAGE_KEYS = {"input": "input_tokens", "output": "output_tokens", "cache_write": "cache_creation_input_tokens",
              "cache_read": "cache_read_input_tokens"}
MODEL_USAGE_KEYS = {"input": "inputTokens", "output": "outputTokens", "cache_write": "cacheCreationInputTokens",
                    "cache_read": "cacheReadInputTokens"}
# the result of an Agent call that the usage limit cut in the middle (scale-m01); it is not flagged is_error
INTERRUPTED = re.compile(r"terminated early due to an API error", re.I)
TARGET_KEYS = ("file_path", "path", "pattern", "command", "subagent_type")


def parse_lines(text: str) -> tuple[list[dict], int]:
    """The JSON events of a log and the number of lines that are not JSON (a call killed by a limit can end in the
    middle of a line)."""
    events, bad = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            bad += 1
    return events, bad


def target(use: dict) -> str:
    data = use["input"]
    for key in TARGET_KEYS:
        if data.get(key):
            return str(data[key])[:120]
    return ""


def normal_path(path: str) -> str:
    return posixpath.normpath(path) if path else path


def role_of(parent: str | None, spawned: dict[str, str]) -> str:
    if not parent:
        return "orchestrator"
    kind = spawned.get(parent)
    if kind is None:
        return "unknown"
    return kind if kind in ROLES else f"other:{kind or '?'}"


def utilization(info: dict, window: str) -> float | None:
    value = ((info.get("unifiedWindows") or {}).get(window) or {}).get("utilization")
    return value if isinstance(value, (int, float)) else None


def analyze(text: str) -> dict:
    """The facts of one stream (see the module docstring); a plain dict, so ``--json`` prints it as it is."""
    events, bad_lines = parse_lines(text)
    spawned: dict[str, str] = {}            # Agent call id -> subagent_type (the role of its events)
    invocations: dict[str, dict] = {}       # Agent call id -> one subagent run
    messages: dict[str, dict] = {}          # message id -> role, invocation, usage (counted once)
    uses: list[dict] = []
    tool_results: dict[str, dict] = {}      # tool_use_id -> {"error": is_error, "text": the start of the result}
    compactions: list[dict] = []
    rate_limits: list[dict] = []
    init = result = None
    for number, event in enumerate(events):
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init" and init is None:
            init = event
        elif kind == "result":
            result = event
        elif kind == "user":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content")
                    text = content if isinstance(content, str) else " ".join(
                        str(c.get("text") or "") for c in content or [] if isinstance(c, dict))
                    tool_results[block.get("tool_use_id")] = {"error": bool(block.get("is_error")), "text": text[:300]}
        elif kind == "system" and "compact" in str(event.get("subtype") or "").lower():
            meta = event.get("compact_metadata") or {}
            last = list(messages.values())[-1] if messages else None
            compactions.append({"event": number, "subtype": event.get("subtype"), "trigger": meta.get("trigger"),
                                "pre_tokens": meta.get("pre_tokens"), "after_call": len(messages),
                                "role": last["role"] if last else None})
        elif kind == "rate_limit_event":
            info = event.get("rate_limit_info") or {}
            last = list(messages.values())[-1] if messages else None
            rate_limits.append({"event": number, "messages_before": len(messages), "status": info.get("status"),
                                "type": info.get("rateLimitType"), "five_hour": utilization(info, "five_hour"),
                                "seven_day": utilization(info, "seven_day"), "resets_at": info.get("resetsAt"),
                                "role": last["role"] if last else None})
        elif kind == "assistant":
            parent = event.get("parent_tool_use_id")
            role = role_of(parent, spawned)
            message = event.get("message") or {}
            key = message.get("id") or f"no-id-{number}"
            entry = messages.setdefault(key, {"order": len(messages) + 1, "role": role, "invocation": parent,
                                              "event": number, "usage": dict.fromkeys(USAGE_KEYS, 0)})
            usage = message.get("usage") or {}
            for name, field in USAGE_KEYS.items():
                value = usage.get(field)
                if isinstance(value, (int, float)):
                    entry["usage"][name] = max(entry["usage"][name], int(value))
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                use = {"id": block.get("id"), "name": block.get("name"), "input": block.get("input") or {},
                       "role": role, "invocation": parent, "message": entry["order"], "event": number}
                uses.append(use)
                if use["name"] in SUBAGENT_TOOLS:
                    spawned[use["id"]] = str(use["input"].get("subagent_type") or "?")
                    invocations[use["id"]] = {"id": use["id"], "role": role_of(use["id"], spawned),
                                              "order": len(invocations) + 1}
    for info in rate_limits:    # what had been used by the time of the event (the window itself is the account's)
        sofar = [m for m in messages.values() if m["order"] <= info["messages_before"]]
        info["cache_read_tokens_so_far"] = sum(m["usage"]["cache_read"] for m in sofar)

    roles = per_role(messages, uses, invocations)
    shared = shared_files(roles)
    for name, stats in roles.items():
        stats["also_read_by_other_roles"] = sum(1 for f in stats["files"] if len(shared.get(f, ())) > 1)
    for stats in roles.values():
        del stats["files"]
    return {"init": {k: (init or {}).get(k) for k in ("model", "claude_code_version", "session_id")},
            "events": len(events), "bad_lines": bad_lines, "messages": len(messages),
            "roles": roles, "invocations": invocation_rows(invocations, messages, uses, tool_results),
            "shared_files": sum(1 for names in shared.values() if len(names) > 1),
            "distinct_files_read": len(shared), "rate_limits": rate_limits,
            "compactions": compactions,
            # the output of a message is only its first value in the stream (never updated): not summed, see above
            "totals": {"stream": {n: sum(s[n] for s in roles.values()) for n in USAGE_KEYS if n != "output"},
                       "result": result_totals(result)},
            "end": ending(events, result, messages, uses, invocations, tool_results, rate_limits)}


def per_role(messages: dict, uses: list, invocations: dict) -> dict[str, dict]:
    names = [r for r in ROLES if any(m["role"] == r for m in messages.values())]
    names += sorted({m["role"] for m in messages.values()} - set(ROLES))
    roles: dict[str, dict] = {}
    for name in names:
        mine = [m for m in messages.values() if m["role"] == name]
        stats = {"calls": len(mine), "invocations": 1 if name == "orchestrator" else
                 sum(1 for i in invocations.values() if i["role"] == name),
                 **{(k if k != "output" else "output_partial"): sum(m["usage"][k] for m in mine) for k in USAGE_KEYS},
                 **context_stats(mine), "tools": {}, "files": {}}
        reads = [u for u in uses if u["role"] == name and u["name"] == "Read"]
        for use in (u for u in uses if u["role"] == name):
            stats["tools"][use["name"]] = stats["tools"].get(use["name"], 0) + 1
        for use in reads:
            path = normal_path(str(use["input"].get("file_path") or use["input"].get("path") or ""))
            if path:
                stats["files"][path] = stats["files"].get(path, 0) + 1
        roles[name] = stats
    for stats in roles.values():
        counts = stats["files"]
        stats["reads"] = sum(counts.values())
        stats["distinct_files"] = len(counts)
        stats["repeated_reads"] = stats["reads"] - len(counts)       # reads of a file that role had read already
        stats["most_read"] = sorted(([f, n] for f, n in counts.items() if n > 1), key=lambda x: (-x[1], x[0]))
    return roles


def context_of(message: dict) -> int:
    """Tokens the model was given in one call: new input plus what was read from and written to the cache. The input
    fields are right in the first event of a message (only ``output_tokens`` is not)."""
    usage = message["usage"]
    return usage["input"] + usage["cache_write"] + usage["cache_read"]


def context_stats(mine: list[dict]) -> dict:
    """The largest context of a role, at which of its calls, the last one, and the calls whose context is less than
    half of the one before in the same run of that role (a hint of compaction when no compaction event is in the
    stream)."""
    mine = [m for m in mine if context_of(m) > 0]      # the synthetic message that ends a cut call has no usage
    sizes = [context_of(m) for m in mine]
    drops = sum(1 for i in range(1, len(mine)) if mine[i]["invocation"] == mine[i - 1]["invocation"]
                and sizes[i] < sizes[i - 1] / 2)
    top = max(sizes, default=0)
    return {"max_context": top, "max_context_call": sizes.index(top) + 1 if sizes else 0,
            "last_context": sizes[-1] if sizes else 0, "context_drops": drops}


def shared_files(roles: dict[str, dict]) -> dict[str, list[str]]:
    shared: dict[str, list[str]] = {}
    for name, stats in roles.items():
        for path in stats["files"]:
            shared.setdefault(path, []).append(name)
    return shared


def invocation_rows(invocations: dict, messages: dict, uses: list, tool_results: dict) -> list[dict]:
    rows = []
    for inv in invocations.values():
        mine = [m for m in messages.values() if m["invocation"] == inv["id"]]
        rows.append({"order": inv["order"], "role": inv["role"], "id": str(inv["id"])[-8:], "calls": len(mine),
                     "max_context": max((context_of(m) for m in mine), default=0),
                     "cache_read": sum(m["usage"]["cache_read"] for m in mine),
                     "reads": sum(1 for u in uses if u["invocation"] == inv["id"] and u["name"] == "Read"),
                     "finished": inv["id"] in tool_results,
                     "error": bool((tool_results.get(inv["id"]) or {}).get("error")),
                     "cut_by_limit": bool(INTERRUPTED.search((tool_results.get(inv["id"]) or {}).get("text", "")))})
    return rows


def result_totals(result: dict | None) -> dict | None:
    """Tokens of the ``result`` event (``modelUsage`` summed over the models) to compare with the sum of the
    messages; whether the two agree is not assumed."""
    if not result:
        return None
    usage = result.get("modelUsage")
    if not isinstance(usage, dict) or not usage:
        return None
    return {n: sum(int((m or {}).get(f) or 0) for m in usage.values() if isinstance(m, dict))
            for n, f in MODEL_USAGE_KEYS.items()} | {"usd": result.get("total_cost_usd")}


def ending(events: list, result: dict | None, messages: dict, uses: list, invocations: dict, tool_results: dict,
           rate_limits: list) -> dict:
    """Where the call stopped: the last model call (role, step), the last tool use and whether it got a result,
    the subagents that never returned, the result event, the last rate-limit event."""
    last = list(messages.values())[-1] if messages else None
    last_use = uses[-1] if uses else None
    in_role = [m for m in messages.values() if last and m["role"] == last["role"]
               and m["invocation"] == last["invocation"]]
    open_subagents = [{"role": i["role"], "order": i["order"]} for i in invocations.values()
                      if i["id"] not in tool_results]
    end = {"result_event": result is not None, "open_subagents": open_subagents,
           "last_rate_limit": rate_limits[-1] if rate_limits else None,
           "last_model_call": None, "last_tool_use": None}
    if result:
        end.update({k: result.get(k) for k in ("subtype", "is_error", "terminal_reason", "api_error_status",
                                               "num_turns")})
    if last:
        end["last_model_call"] = {"role": last["role"], "step_in_call": last["order"], "of_calls": len(messages),
                                  "step_in_role_run": len(in_role)}
    if last_use:
        end["last_tool_use"] = {"role": last_use["role"], "name": last_use["name"], "target": target(last_use),
                                "got_result": last_use["id"] in tool_results}
    return end


# --- text report -----------------------------------------------------------------------------------------------

def number(value) -> str:
    return "-" if value is None else f"{value:,}" if isinstance(value, int) else str(value)


def pct(value) -> str:
    return "-" if value is None else f"{value * 100:.0f} %"


def table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " if i == 0 else " ---: "
                                                              for i in range(len(header))) + "|"]
    return lines + ["| " + " | ".join(number(c) for c in row) + " |" for row in rows]


def render(label: str, report: dict, top: int) -> str:
    out = [f"## {label}", ""]
    init = report["init"]
    out.append(f"{report['events']} events, {report['messages']} model calls, model {init['model']}, "
               f"version {init['claude_code_version']}, session {init['session_id']}"
               + (f", {report['bad_lines']} unreadable line(s)" if report["bad_lines"] else ""))
    out += ["", "Per role", ""]
    roles = report["roles"]
    out += table(["role", "runs", "calls", "input", "cache write", "cache read", "largest context", "at call",
                  "context drops", "reads", "distinct", "read again", "also read by another role"],
                 [[n, s["invocations"], s["calls"], s["input"], s["cache_write"], s["cache_read"], s["max_context"],
                   s["max_context_call"], s["context_drops"], s["reads"], s["distinct_files"], s["repeated_reads"],
                   s["also_read_by_other_roles"]] for n, s in roles.items()])
    totals = report["totals"]
    total_cache = totals["stream"]["cache_read"]
    out += ["", "Share of the cache reads: " + ", ".join(
        f"{n} {s['cache_read'] / total_cache * 100:.0f} %" for n, s in roles.items()) if total_cache else ""]
    out += ["", f"Sum of the messages (input and cache): {totals['stream']}"]
    out.append(f"`result` event (modelUsage), the whole call, with the real output tokens: {totals['result']}"
               if totals["result"] else "`result` event: no modelUsage, so no output tokens (the stream only has the "
               "first value of every message)")
    out += ["", f"Compaction events: {len(report['compactions'])}"
            + ("" if report["compactions"] else " (none in the stream; the subtype is not verified, see the top of "
               "this file)")]
    for c in report["compactions"]:
        out.append(f"- event {c['event']} {c['subtype']}: trigger {c['trigger']}, pre_tokens {c['pre_tokens']}, "
                   f"after call {c['after_call']} ({c['role']})")
    out += ["", f"Files read by more than one role: {report['shared_files']} of {report['distinct_files_read']}", ""]
    out += ["Tools per role", ""]
    for name, stats in roles.items():
        out.append(f"- {name}: " + ", ".join(f"{t} {n}" for t, n in sorted(stats["tools"].items(),
                                                                         key=lambda x: (-x[1], x[0]))))
    again = [(name, f, n) for name, s in roles.items() for f, n in s["most_read"][:top]]
    if again:
        out += ["", "Files one role read more than once", ""]
        out += table(["role", "file", "times"], again)
    if report["invocations"]:
        out += ["", "Subagent runs", ""]
        out += table(["#", "role", "calls", "largest context", "cache read", "reads", "returned"],
                     [[i["order"], i["role"], i["calls"], i["max_context"], i["cache_read"], i["reads"],
                       "CUT BY LIMIT" if i["cut_by_limit"] else "error" if i["error"] else "yes" if i["finished"]
                       else "NO"] for i in report["invocations"]])
    if report["rate_limits"]:
        out += ["", "Rate-limit events (usage when the event came)", ""]
        out += table(["event", "after call", "role", "status", "5 h", "7 d", "cache read so far"],
                     [[r["event"], r["messages_before"], r["role"], r["status"], pct(r["five_hour"]),
                       pct(r["seven_day"]), r["cache_read_tokens_so_far"]]
                      for r in report["rate_limits"]])
    out += ["", "End of the call", ""]
    end = report["end"]
    if end["result_event"]:
        out.append(f"- result: subtype {end.get('subtype')}, is_error {end.get('is_error')}, terminal_reason "
                   f"{end.get('terminal_reason')}, api_error_status {end.get('api_error_status')}, "
                   f"num_turns {end.get('num_turns')}")
    else:
        out.append("- no result event (the call did not finish)")
    if end["last_model_call"]:
        m = end["last_model_call"]
        out.append(f"- last model call: {m['role']}, call {m['step_in_call']} of {m['of_calls']} "
                   f"(call {m['step_in_role_run']} of that role's run)")
    if end["last_tool_use"]:
        u = end["last_tool_use"]
        out.append(f"- last tool use: {u['role']} {u['name']} {u['target']} "
                   f"({'answered' if u['got_result'] else 'no answer'})")
    out.append("- subagents that never returned: " + (", ".join(f"{s['role']} #{s['order']}"
                                                             for s in end["open_subagents"]) or "none"))
    return "\n".join(out) + "\n"


def collect(paths: list[str]) -> list[Path]:
    """The stream files named by the arguments, a run folder in call order."""
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found = list((path / "calls").glob("call-*/stream.jsonl")) or list(path.rglob("stream.jsonl"))
            files += sorted(found, key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(p))])
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"no such file or folder: {raw}")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="stream.jsonl files or run folders")
    parser.add_argument("--top", type=int, default=5, help="files listed per role as read more than once (default 5)")
    parser.add_argument("--json", action="store_true", help="print the facts as JSON instead of tables")
    args = parser.parse_args(argv)
    try:
        files = collect(args.paths)
    except FileNotFoundError as exc:
        print(f"diagnose_stream: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("diagnose_stream: no stream.jsonl found", file=sys.stderr)
        return 2
    reports = {str(f): analyze(f.read_text(encoding="utf-8", errors="replace")) for f in files}
    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    else:
        print("\n".join(render(label, report, args.top) for label, report in reports.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
