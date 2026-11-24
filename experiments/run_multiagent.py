"""Multi-Agent run (approaches.md, ADR 005 draft M1–M7): one orchestrator call of Claude Code with three subagents
(Analyzer, Refactoring, Reviewer) and one feedback test command; every run of that command keeps a snapshot of
``lms/``, and the engine measures the snapshots as rounds and keeps the best one (W1), as for Iterative.

    python experiments/run_multiagent.py --start-ref <ref> --baseline <folder> [--tests-modules 1-14]
        --account <label> --run-id <id> --window-pct <0-10> [options]

Roles and tools (M2): the orchestrator reads and calls the subagents and the test command; Analyzer and Reviewer
only read; only the Refactoring subagent edits. The test command is ``experiments/feedback_tests.py`` (M3); the tests,
the starting project and the engine are mounted read-only and closed to Read / Glob / Grep (M4). After the call the
stream is checked (M5): at most 3 Refactoring calls and 3 test runs, no other subagent type, no edit by the
orchestrator or a read-only role, no other shell command.

A usage-limit cut does not discard the run: the status becomes ``limit_cut`` and the work folder, ``session/`` and
``state.json`` (with the session id) stay. With ``--auto-resume`` the engine waits for the end of the 5-hour window
(``resetsAt`` of the last rate_limit_event + 5 min, the run lock released), then continues the same session
(``--resume <session_id>``, the same ``--agents``, tools, permissions and environment) with a fixed sentence
(``common.CONTINUE_PROMPT``). At most 3 pauses and 24 hours of waiting; the weekly limit never waits. The roles and the
budget (M5) are checked over all calls; a subagent call that the limit cut in the middle is recorded separately.

The settings marked K1–K7 are the ones the Week 6 setup check verifies; they are constants below.

Exit code: 0 valid run · 1 invalid run, repeat it · 2 usage error · 3 run lock not free · 5 usage-limit cut
(``limit_cut``, nothing deleted).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import posixpath
import re
import shlex
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import run_iterative  # noqa: E402  (final measurement of best, round 1 and last: the same rule, W1)
from common import EngineError, Run  # noqa: E402

APPROACH = "multiagent"

# --- settings verified by the Week 6 setup check (K1–K7) ---------------------------------------------------------
SPAWN_TOOL = "Agent"                    # K1: --tools / --allowedTools accept "Agent"; the calls are named "Agent"
INIT_SPAWN_NAME = "Task"                # K1: ... but the init event lists the same tool as "Task"
SAFE_MODE = False                       # K1: --safe-mode does not load subagent definitions (neither --agents nor
                                        # .claude/agents/); its protection comes from the empty CLAUDE_CONFIG_DIR, the
                                        # clean workspace and the stream check of writes to CLAUDE.md / hidden files
READ_TOOLS = ("Read", "Glob", "Grep")
EDIT_TOOLS = ("Edit", "Write")
ROLES = {                               # M2; K2: a subagent's ``tools`` are enforced
    "analyzer": READ_TOOLS,
    "refactoring": READ_TOOLS + EDIT_TOOLS,
    "reviewer": READ_TOOLS,
}
# Edit/Write are offered to the session so that the Refactoring subagent can use them (K2); an edit by the
# orchestrator itself is found in the stream and makes the run invalid.
# K6c: the built-in subagent types (init.agents of 2.1.308) are denied with Agent(<type>); such a denial is not in
# permission_denials but in the tool_result of the Agent call ("... has been denied by permission rule ...")
BUILTIN_AGENTS = ("general-purpose", "Explore", "Plan", "statusline-setup", "claude")
ORCHESTRATOR_TOOLS = READ_TOOLS + EDIT_TOOLS + ("Bash", SPAWN_TOOL)
INIT_TOOLS = READ_TOOLS + EDIT_TOOLS + ("Bash", INIT_SPAWN_NAME)       # what the init event must list
SUBAGENT_MODEL = common.MODEL          # K5: the value the ``model`` field of --agents accepts
MAX_REFACTORING_CALLS = 3              # M5: 1 refactoring + at most 2 returns of the Reviewer
MAX_TEST_RUNS = 3
TEST_COMMAND = "python /engine/experiments/feedback_tests.py"
BASH_TIMEOUT_MS = "3600000"            # K7: the test command may run longer than the default 2 minutes of Bash
MOUNTS = {"engine": "/engine", "start": "/exp-start", "tests": "/exp-tests", "baseline": "/exp-baseline",
          "state": "/exp-state", "config": "/exp-config"}


def deny_rules(paths) -> tuple[str, ...]:
    """K4: Read / Glob / Grep / Edit / Write closed on the folders that are not the model's (absolute path rule)."""
    return tuple(f"{tool}(/{path.rstrip('/')}/**)" for path in paths for tool in READ_TOOLS + EDIT_TOOLS)


def load_role(path: Path) -> tuple[str, str]:
    """A role file: ``---`` / ``description: ...`` / ``---`` / prompt."""
    if not path.is_file():
        raise EngineError(f"role prompt not found: {path} (Aslınur's Multi-Agent prompt PR)")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise EngineError(f"{path}: no '---' header with a description")
    _, head, body = text.split("---", 2)
    description = next((line.split(":", 1)[1].strip() for line in head.splitlines()
                        if line.strip().startswith("description:")), "")
    if not description:
        raise EngineError(f"{path}: the header has no description")
    return description, body.strip()


def agents_json(prompts: Path) -> str:
    agents = {}
    for role, tools in ROLES.items():
        description, prompt = load_role(prompts / f"{role}.md")
        agents[role] = {"description": description, "prompt": prompt, "tools": list(tools), "model": SUBAGENT_MODEL}
    return json.dumps(agents, ensure_ascii=False)


# K6b: Claude Code runs read-only shell commands inside the working folder (cat, find, ls, ...) on its own, without
# --allowedTools, and denies the rest (python -c, anything outside /work). Such a command has the effect of Read /
# Glob / Grep and is only counted. As a second guard, a command that ran and could change files makes the run invalid.
MUTATING = re.compile(r"(^|[\s;&|(])(>|>>|tee|rm|mv|cp|sed\s+-i|perl\s+-i|chmod|chown|touch|mkdir|rmdir|ln|truncate|dd|"
                      r"python3?|pip3?|pytest|git|curl|wget|bash|sh)(\s|$|[;&|)<>])")


def can_change_files(command: str) -> bool:
    return bool(MUTATING.search(command)) or ">" in command or bool(re.search(r"\s-(delete|exec|execdir|fprint\w*)\b", command))


def inside_work(tool: str, data: dict) -> bool:
    """Whether a Read / Glob / Grep / Edit / Write call targets the model's folder (no path: the working folder).
    A Glob pattern can hold the folder itself (``/engine/**/*`` without ``path``, pilot-m01), so it is checked too;
    relative paths are resolved against /work (``../engine`` is outside)."""
    targets = [data.get("file_path") or data.get("path") or ""]
    if tool == "Glob":
        targets.append(data.get("pattern") or "")
    return all(_in_work(str(t)) for t in targets)


def _in_work(path: str) -> bool:
    if not path:
        return True
    if path.startswith("~"):
        return False
    full = posixpath.normpath(posixpath.join("/work", path))
    return full == "/work" or full.startswith("/work/")


def blocked_or_broken(denials: list, test_command: str) -> tuple[list[str], list[str]]:
    """Denied tool calls (ADR 005 draft): an attempt the setup is meant to block (another shell command, a read or
    write outside the model's folder) is only counted; a denial of something the roles need (the test command, the
    model's folder, a subagent call) means a broken setup and makes the run invalid (W10)."""
    blocked, broken = [], []
    for d in denials or []:
        tool, data = str(d.get("tool_name") or "?"), d.get("tool_input") or {}
        if tool == "Bash":
            command = " ".join(str(data.get("command") or "").split())
            (broken if command == " ".join(test_command.split()) else blocked).append(f"Bash: {command[:80]}")
        elif tool in READ_TOOLS + EDIT_TOOLS:
            target = data.get("file_path") or data.get("path") or data.get("pattern") or ""
            (broken if inside_work(tool, data) else blocked).append(f"{tool}: {str(target)[:80]}")
        else:
            broken.append(tool)
    return blocked, broken


INTERRUPTED = re.compile(r"terminated early due to an API error", re.I)


def interrupted_by_limit(result: dict | None) -> bool:
    """The result of an Agent call that the usage limit cut in the middle (scale-m01): the text starts with "Agent
    terminated early due to an API error: You've hit your session limit ... HTTP 429 ... PARTIAL output"; the result
    is not flagged ``is_error``."""
    text = (result or {}).get("text", "")
    return bool(INTERRUPTED.search(text) and common.LIMIT_PATTERN.search(text))


def analyze_roles(uses: list[dict], test_command: str, denials: list | None = None,
                  tool_results: dict | None = None) -> dict:
    """Who did what (M2, M5): subagent calls per role, test runs, blocked attempts, and the reasons that make the run
    invalid. ``uses``, ``denials`` and ``tool_results`` are those of **all** calls of the run (a run continued after a
    usage-limit cut has several), so the budget is checked over the sum. A subagent call that the limit cut in the
    middle is not counted as a call of its role and not a broken setup: it is listed under ``interrupted_by_limit``.
    Tool calls that were denied did not run and are judged by ``blocked_or_broken`` only."""
    denied_ids = {d.get("tool_use_id") for d in denials or [] if isinstance(d, dict)}
    blocked, broken = blocked_or_broken(denials or [], test_command)
    for u in uses:      # a subagent type denied by an Agent(<type>) rule: counted as blocked, not started (K6c)
        res = (tool_results or {}).get(u.get("id")) or {}
        if u["name"] in common.SUBAGENT_TOOLS and res.get("is_error") and "denied by permission rule" in res.get("text", ""):
            denied_ids.add(u.get("id"))
            blocked.append(f"Agent: {u['input'].get('subagent_type')}")
    uses = [u for u in uses if u.get("id") not in denied_ids]
    cut = {u.get("id") for u in uses if u["name"] in common.SUBAGENT_TOOLS and not u.get("parent")
           and interrupted_by_limit((tool_results or {}).get(u.get("id")))}
    failed = []         # an Agent call that returned an error (K1: "Agent type 'analyzer' not found"): broken setup
    for u in uses:
        res = (tool_results or {}).get(u.get("id")) or {}
        if (u["name"] in common.SUBAGENT_TOOLS and u.get("id") not in cut and res.get("is_error")
                and str(u["input"].get("subagent_type") or "") in ROLES):
            failed.append(f"{u['input'].get('subagent_type')}: {res.get('text', '')[:100]}")
    spawns = [u for u in uses if u["name"] in common.SUBAGENT_TOOLS and not u.get("parent")
              and not ((tool_results or {}).get(u.get("id")) or {}).get("is_error")]
    role_of = {u.get("id"): str(u["input"].get("subagent_type") or "") for u in spawns}    # also the cut ones: their tool calls
    calls: dict[str, int] = {}
    interrupted: dict[str, int] = {}
    for call_id, role in role_of.items():
        counts = interrupted if call_id in cut else calls
        counts[role] = counts.get(role, 0) + 1
    invalid = [f"subagent of type '{r}' called {n} time(s): only {', '.join(ROLES)} are allowed"
               for r, n in sorted(calls.items()) if r not in ROLES]
    invalid += [f"a needed tool call was denied (broken setup): {b}" for b in broken]
    invalid += [f"a subagent call failed (broken setup): {f}" for f in failed]
    tests, other_shell, read_only_shell = 0, [], []
    for u in uses:
        parent = u.get("parent")
        if not parent:
            if u["name"] in EDIT_TOOLS:
                invalid.append(f"the orchestrator used {u['name']} itself (only the Refactoring subagent edits)")
            elif u["name"] == "Bash":
                command = " ".join(str(u["input"].get("command") or "").split())
                if command == " ".join(test_command.split()):
                    tests += 1
                elif can_change_files(command):
                    other_shell.append(command[:80])
                else:
                    read_only_shell.append(command[:80])
            continue
        role = role_of.get(parent)
        if u["name"] in common.SUBAGENT_TOOLS:
            invalid.append(f"a subagent ({role or 'unknown'}) started another subagent")
        elif role in ROLES and u["name"] not in ROLES[role]:
            invalid.append(f"the {role} subagent used {u['name']} (not one of its tools)")
        elif role is None:
            invalid.append(f"a tool call ({u['name']}) of an unknown subagent")
    if other_shell:
        invalid.append(f"shell command(s) that can change files ran: {', '.join(other_shell[:3])}")
    if calls.get("refactoring", 0) > MAX_REFACTORING_CALLS:
        invalid.append(f"Refactoring subagent called {calls['refactoring']} times (at most {MAX_REFACTORING_CALLS})")
    if tests > MAX_TEST_RUNS:
        invalid.append(f"test command run {tests} times (at most {MAX_TEST_RUNS})")
    return {"subagent_calls": calls, "interrupted_by_limit": interrupted, "test_runs": tests, "blocked": blocked,
            "read_only_shell": read_only_shell, "invalid": sorted(set(invalid), key=invalid.index)}


def tree_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in common.code_files(folder):
        digest.update(path.relative_to(folder).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def dry_run(run: Run) -> int:
    """--dry-run: load the four prompt files, fill the orchestrator prompt and print the real Multi-Agent command
    (the --agents JSON is shortened to its roles and tools; the full role prompts are printed below it)."""
    run.check_inputs()
    prompt = common.fill_prompt(common.load_prompt(run.prompts, "multiagent/orchestrator.md"),
                                test_command=TEST_COMMAND, max_refactoring_calls=MAX_REFACTORING_CALLS,
                                max_test_runs=MAX_TEST_RUNS)
    left = [p for p in common.MULTIAGENT_PLACEHOLDERS if p in prompt]
    if left:
        raise EngineError(f"orchestrator.md: placeholders not filled: {', '.join(left)}")
    if TEST_COMMAND not in prompt:
        raise EngineError("orchestrator.md: the test command is not in the prompt ({test_command} missing)")
    agents = json.loads(agents_json(run.prompts / "multiagent"))
    short = "'" + json.dumps({r: {"tools": a["tools"], "model": a["model"]} for r, a in agents.items()}) + "'"
    allowed = (*READ_TOOLS, *EDIT_TOOLS, SPAWN_TOOL, f"Bash({TEST_COMMAND})")
    args = common.claude_args("<prompt>", run.settings["effort"], None, tools=ORCHESTRATOR_TOOLS, allowed=allowed,
                              disallowed=deny_rules(MOUNTS.values()) + tuple(f"Agent({a})" for a in BUILTIN_AGENTS),
                              extra=("--agents", short), safe_mode=SAFE_MODE)
    mounts = tuple(f"-v <{name}>:{path}{'' if name == 'state' else ':ro'}" for name, path in MOUNTS.items())
    common.dry_run(run, args, {"BASH_DEFAULT_TIMEOUT_MS": BASH_TIMEOUT_MS, "BASH_MAX_TIMEOUT_MS": BASH_TIMEOUT_MS},
                   mounts)
    print(f"budget:    {MAX_REFACTORING_CALLS} refactoring calls, {MAX_TEST_RUNS} test runs")
    for role, agent in agents.items():
        print(f"role:      {role} {agent['tools']} - {agent['description']}")
    print("--- orchestrator prompt ---")
    print(prompt)
    return common.EXIT_DONE


def prepare(run: Run, test_command: str | None) -> dict:
    """Agent state folder, config of the test command, the claude arguments and the docker mounts."""
    ws, local = run.ws, run.settings["local"]
    state, config_dir = ws.root / "agent-state", ws.root / "agent-config"
    state.mkdir()
    config_dir.mkdir()
    if local:
        paths = {"code": str(ws.model), "project": str(ws.start), "tests": str(ws.tests), "hashes": str(ws.hashes),
                 "baseline": str(run.baseline), "state": str(state), "scripts": str(common.SCRIPTS)}
        command = test_command or (f"{shlex.quote(sys.executable)} "
                                   f"{shlex.quote(str(common.EXPERIMENTS / 'feedback_tests.py'))} "
                                   f"--config {shlex.quote(str(config_dir / 'config.json'))}")
        hidden = ()
    else:
        paths = {"code": "/work", "project": MOUNTS["start"], "tests": MOUNTS["tests"],
                 "hashes": f"{MOUNTS['config']}/test-hashes.json", "baseline": MOUNTS["baseline"],
                 "state": MOUNTS["state"], "scripts": f"{MOUNTS['engine']}/scripts"}
        shutil.copy2(ws.hashes, config_dir / "test-hashes.json")
        command = test_command or TEST_COMMAND
        hidden = tuple(MOUNTS.values())
    common.write_json(config_dir / "config.json", {**paths, "max_runs": MAX_TEST_RUNS,
                                                   "timeout": run.settings["test_timeout"]})
    allowed = (*READ_TOOLS, *EDIT_TOOLS, SPAWN_TOOL, f"Bash({command})")
    prompt = common.fill_prompt(common.load_prompt(run.prompts, "multiagent/orchestrator.md"),
                                test_command=command, max_refactoring_calls=MAX_REFACTORING_CALLS,
                                max_test_runs=MAX_TEST_RUNS)
    args = common.claude_args(prompt, run.settings["effort"], None, tools=ORCHESTRATOR_TOOLS, allowed=allowed,
                              disallowed=deny_rules(hidden) + tuple(f"Agent({a})" for a in BUILTIN_AGENTS),
                              extra=("--agents", agents_json(run.prompts / "multiagent")),
                              safe_mode=SAFE_MODE)
    volumes = [] if local else [(str(common.REPO), MOUNTS["engine"], True), (str(ws.start), MOUNTS["start"], True),
                                (str(ws.tests), MOUNTS["tests"], True), (str(run.baseline), MOUNTS["baseline"], True),
                                (str(state), MOUNTS["state"], False), (str(config_dir), MOUNTS["config"], True)]
    run.record.update({"test_command": command, "roles_allowed": {r: list(t) for r, t in ROLES.items()},
                       "budget": {"refactoring_calls": MAX_REFACTORING_CALLS, "test_runs": MAX_TEST_RUNS}})
    return {"prompt": prompt, "state": state,
            # the feedback tests run inside the call, so the run lock stays held (W13 does not apply, ADR 005)
            "setup": {"args": args, "tools": INIT_TOOLS, "subagents_allowed": True, "denials_invalid": False,
                      "hold_lock": True,
                      "volumes": volumes,
                      "env": {"BASH_DEFAULT_TIMEOUT_MS": BASH_TIMEOUT_MS, "BASH_MAX_TIMEOUT_MS": BASH_TIMEOUT_MS}}}


def rounds_from(run: Run, state: Path) -> list[dict]:
    """The rounds to measure: every snapshot of the test command that differs from the start and from the round
    before it, then the final ``lms/`` if it differs from the last one (the model may have edited after the last test)."""
    final = run.ws.root / "final-lms"
    shutil.copytree(run.ws.model / "lms", final, ignore=shutil.ignore_patterns("__pycache__"))
    previous = tree_hash(run.ws.start / "lms")
    sources = []
    for snap in sorted((state / "snapshots").glob("*")) if (state / "snapshots").is_dir() else []:
        if not (snap / "lms").is_dir():
            continue
        digest = tree_hash(snap / "lms")
        if digest != previous:
            meta = common.read_json(snap / "meta.json") if (snap / "meta.json").is_file() else {}
            sources.append({"source": f"test run {int(snap.name)}", "lms": snap / "lms", "meta": meta,
                            "feedback": snap / "feedback.txt"})
            previous = digest
    if tree_hash(final) != previous:
        sources.append({"source": "end of the call", "lms": final, "meta": {}, "feedback": None})
    return sources


def utc(timestamp: float | None) -> str:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if timestamp else "?"


def stop_cut(run: Run, state: dict, why: str) -> int:
    """The run stays as it is (work folder, session/, state.json, the calls): status ``limit_cut``, exit code 5."""
    run.record.update({"status": "limit_cut", "stop_reason": why})
    common.write_json(run.out / "state.json", state)
    run.event(f"usage-limit cut, the run is stopped and nothing is deleted: {why}")
    return common.EXIT_LIMIT


def handle_limit(run: Run, call: dict, state: dict, auto_resume: bool) -> int | None:
    """A call was cut by the usage limit. Returns an exit code when the run stops (``limit_cut``), or None after the
    pause: the 5-hour window has reopened and the same session can be continued. The weekly limit never waits."""
    info = common.limit_info(call.get("rate_limit"))
    record = run.record
    state.update({"session_id": call["session_id"] or state["session_id"], "limit_cut_at_call": call["number"],
                  "pending": {"kind": "resume", "prompt": common.CONTINUE_PROMPT}})
    record["limit_kinds"].append(info["kind"] or "unknown")
    record["limit_cuts"].append({"call": call["number"], "kind": info["kind"], "resets_at": info["resets_at"],
                                 "five_hour_util": info["five_hour_util"], "seven_day_util": info["seven_day_util"],
                                 "waited_s": None})
    record["status"] = "limit_cut"
    state.update({k: record[k] for k in ("pauses", "wait_s", "limit_kinds")})
    common.write_json(run.out / "state.json", state)
    run.save()
    if info["kind"] == "seven_day":
        return stop_cut(run, state, f"the weekly limit is full (resets {utc(info['resets_at'])}): no waiting; continue "
                                    f"the same session after that time")
    if not auto_resume:
        return stop_cut(run, state, "--auto-resume is not set")
    if not state["session_id"]:
        return stop_cut(run, state, "the cut call has no session id: it cannot be continued")
    if info["kind"] != "five_hour" or info["resets_at"] is None:
        return stop_cut(run, state, "the last rate_limit_event does not say which window is full or when it resets")
    if record["pauses"] >= common.MAX_PAUSES:
        return stop_cut(run, state, f"{record['pauses']} pauses already (at most {common.MAX_PAUSES})")
    planned = max(0.0, info["resets_at"] + common.RESET_MARGIN_S - common.CLOCK())
    if record["wait_s"] + planned > common.MAX_PAUSE_TOTAL_S:
        return stop_cut(run, state, f"waiting {planned / 3600:.1f} h more would pass {common.MAX_PAUSE_TOTAL_S // 3600} "
                                    f"h of waiting in total")
    lock = run.lock
    held = lock is not None and lock.held
    if held:                # nothing runs while we wait: free the lock for other runs (W13); taken again below
        lock.__exit__()
    run.event(f"5-hour window full: waiting until {utc(info['resets_at'])} + {common.RESET_MARGIN_S // 60} min "
              f"(pause {record['pauses'] + 1} of {common.MAX_PAUSES}); the lock is {'released' if held else 'not held'}")
    waited = common.wait_until(info["resets_at"], common.RESET_MARGIN_S,
                               on_tick=lambda left: run.event(f"still waiting: {int(left // 60)} min left"))
    if held:
        lock.acquire(None)
    record["pauses"] += 1
    record["wait_s"] = round(record["wait_s"] + waited, 1)
    record["limit_cuts"][-1]["waited_s"] = waited
    record["status"] = "running"
    state.update({k: record[k] for k in ("pauses", "wait_s")})
    common.write_json(run.out / "state.json", state)
    run.event(f"waited {waited} s: continuing session {state['session_id']}")
    return None


def execute(run: Run, test_command: str | None, auto_resume: bool = False) -> int:
    run.setup()
    leftovers = [p for p in run.ws.listing() if p.split("/")[0].startswith(".") or p.split("/")[-1] in common.FORBIDDEN_NAMES]
    if leftovers:          # without --safe-mode nothing may be there for Claude Code to load
        raise EngineError(f"the model's folder has files Claude Code would load: {', '.join(leftovers[:5])}")
    prepared = prepare(run, test_command)
    setup = prepared["setup"]
    run.record.update({"auto_resume": auto_resume, "pauses": 0, "wait_s": 0.0, "limit_kinds": [], "limit_cuts": []})
    cut_state = {"session_id": None, "pending": {"kind": "orchestrator", "prompt": prepared["prompt"]},
                 "limit_cut_at_call": None, "pauses": 0, "wait_s": 0.0, "limit_kinds": []}
    common.write_json(run.out / "state.json", cut_state)
    call = run.call(prepared["prompt"], "orchestrator", None, setup)
    while call["status"] == "limit":      # pause, wait for the window, continue the same session with the same settings
        stop = handle_limit(run, call, cut_state, auto_resume)
        if stop is not None:
            return stop
        resumed = {**setup, "args": common.resume_args(setup["args"], common.CONTINUE_PROMPT, cut_state["session_id"])}
        call = run.call(common.CONTINUE_PROMPT, "resume", cut_state["session_id"], resumed)
    cut_state["pending"] = None
    common.write_json(run.out / "state.json", cut_state)
    # the budget and the roles are checked over the streams of all calls (M5)
    parsed = run.parsed_calls()
    denials = [d for p in parsed for d in (p.get("result") or {}).get("permission_denials") or []]
    roles = analyze_roles([u for p in parsed for u in p["uses"]], run.record["test_command"], denials,
                          {k: v for p in parsed for k, v in p["tool_results"].items()})
    run.record["roles"] = roles
    # the totals of the whole run, on the last call (as before, when a run had a single call)
    call["subagent_calls"], call["test_runs"], call["blocked"] = roles["subagent_calls"], roles["test_runs"], roles["blocked"]
    run.save()
    carried = [reason for c in run.record["calls"] for reason in c["invalid"]]        # also those of the cut calls
    invalid = list(dict.fromkeys(carried + roles["invalid"]))
    if invalid or call["status"] != "ok":
        return run.finish("invalid", False, invalid or [f"call status {call['status']}"])

    sources = rounds_from(run, prepared["state"])
    # run_iterative.final() saves run.state as state.json: keep the session and the pauses in it
    run.state = {"best": 0, "best_commit": run.record["start_state_commit"], **cut_state}
    for k, src in enumerate(sources, start=1):
        lms = run.ws.model / "lms"
        shutil.rmtree(lms)
        shutil.copytree(src["lms"], lms)
        entry = run.commit_round(k)
        entry.update({"source": src["source"], "test_run": src["meta"]})
        best = run.state["best"]
        previous = run.out / f"rounds/r{best}" / "analysis" if best else None
        facts, folder = run.measure(entry["state_commit"], entry["code_sha"], f"rounds/r{k}", "feedback", previous)
        if facts["status"] == "invalid":
            return run.finish("invalid", False, facts["problems"] or ["measurement invalid"])
        entry.update({"accepted": facts["round_accepted"] is True, "facts": facts,
                      "feedback_lines": src["meta"].get("feedback_lines", 0)})
        if src["feedback"] and src["feedback"].is_file():
            shutil.copy2(src["feedback"], folder / "feedback.txt")         # what the orchestrator got
        if entry["accepted"]:
            run.state.update({"best": k, "best_commit": entry["state_commit"]})
        else:
            run.event(f"round {k} not kept: {'; '.join(facts['accept_reasons']) or 'not better than the best'}")
        run.save()
    if not sources:
        return run.finish(*common.classify([], None))
    return run_iterative.final(run, f"{len(sources)} round(s) from {roles['test_runs']} test run(s)")


def main(argv: list[str] | None = None, toolkit: common.Toolkit | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_arguments(parser)
    parser.add_argument("--auto-resume", action="store_true",
                        help="after a usage-limit cut of the 5-hour window: wait for its reset and continue the same "
                             "session (at most 3 pauses, 24 h of waiting)")
    parser.add_argument("--test-command", help=argparse.SUPPRESS)       # tests: a stand-in for feedback_tests.py
    args = parser.parse_args(argv)
    run = Run(APPROACH, args, toolkit)
    try:
        if args.dry_run:
            return dry_run(run)
        with common.RunLock(Path(args.lock_file), f"run_multiagent.py {args.run_id}", args.wait, args.poll) as lock:
            run.lock = lock
            return execute(run, args.test_command, args.auto_resume)
    except EngineError as exc:
        print(f"run_multiagent: {exc}", file=sys.stderr)
        if run.record and run.record.get("status") == "running":
            run.record.update({"status": "stopped", "stop_reason": str(exc)})
            run.save()
        return exc.code
    except KeyboardInterrupt:
        if run.record and run.record.get("status") != "limit_cut":      # Ctrl+C while waiting keeps limit_cut
            run.record.update({"status": "aborted"})
            run.save()
        raise


if __name__ == "__main__":
    sys.exit(main())
