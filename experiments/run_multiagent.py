"""Multi-Agent run (approaches.md, ADR 005 draft M1–M7): one orchestrator call of Claude Code with three subagents
(Analyzer, Refactoring, Reviewer) and one feedback test command; every run of that command keeps a snapshot of
``lms/``, and the engine measures the snapshots as rounds and keeps the best one (W1), as for Iterative.

    python experiments/run_multiagent.py --start-ref <ref> --baseline <folder> [--tests-modules 1-14]
        --account <label> --run-id <id> --window-pct <0-10> [options]

Roles and tools (M2): the orchestrator reads and calls the subagents and the test command; Analyzer and Reviewer
only read; only the Refactoring subagent edits. The test command is ``experiments/feedback_tests.py`` (M3); the tests,
the starting project and the engine are mounted read-only and closed to Read / Glob / Grep (M4). After the call the
stream is checked (M5): at most 3 Refactoring calls and 3 test runs, no other subagent type, no edit by the
orchestrator or a read-only role, no other shell command. A usage-limit cut discards the run (one call, as Single).

The settings marked K1–K7 are the ones the Week 6 setup check verifies; they are constants below.

Exit code: 0 valid run · 1 invalid run, repeat it · 2 usage error · 3 run lock not free · 5 usage-limit cut.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
SPAWN_TOOL = "Agent"                    # K1: the name of the subagent tool in this Claude Code version ("Task"/"Agent")
READ_TOOLS = ("Read", "Glob", "Grep")
EDIT_TOOLS = ("Edit", "Write")
ROLES = {                               # M2; K2: a subagent's ``tools`` are enforced
    "analyzer": READ_TOOLS,
    "refactoring": READ_TOOLS + EDIT_TOOLS,
    "reviewer": READ_TOOLS,
}
# Edit/Write are offered to the session so that the Refactoring subagent can use them (K2); an edit by the
# orchestrator itself is found in the stream and makes the run invalid.
ORCHESTRATOR_TOOLS = READ_TOOLS + EDIT_TOOLS + ("Bash", SPAWN_TOOL)
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


def analyze_roles(uses: list[dict], test_command: str) -> dict:
    """Who did what (M2, M5): subagent calls per role, test runs, and the reasons that make the run invalid."""
    spawns = [u for u in uses if u["name"] in common.SUBAGENT_TOOLS and not u.get("parent")]
    role_of = {u.get("id"): str(u["input"].get("subagent_type") or "") for u in spawns}
    calls: dict[str, int] = {}
    for role in role_of.values():
        calls[role] = calls.get(role, 0) + 1
    invalid = [f"subagent of type '{r}' called {n} time(s): only {', '.join(ROLES)} are allowed"
               for r, n in sorted(calls.items()) if r not in ROLES]
    tests, other_shell = 0, []
    for u in uses:
        parent = u.get("parent")
        if not parent:
            if u["name"] in EDIT_TOOLS:
                invalid.append(f"the orchestrator used {u['name']} itself (only the Refactoring subagent edits)")
            elif u["name"] == "Bash":
                command = " ".join(str(u["input"].get("command") or "").split())
                if command == " ".join(test_command.split()):
                    tests += 1
                else:
                    other_shell.append(command[:80])
            continue
        role = role_of.get(parent)
        if u["name"] in common.SUBAGENT_TOOLS:
            invalid.append(f"a subagent ({role or 'unknown'}) started another subagent")
        elif role in ROLES and u["name"] not in ROLES[role]:
            invalid.append(f"the {role} subagent used {u['name']} (not one of its tools)")
        elif role is None:
            invalid.append(f"a tool call ({u['name']}) of an unknown subagent")
    if other_shell:
        invalid.append(f"shell command(s) other than the test command: {', '.join(other_shell[:3])}")
    if calls.get("refactoring", 0) > MAX_REFACTORING_CALLS:
        invalid.append(f"Refactoring subagent called {calls['refactoring']} times (at most {MAX_REFACTORING_CALLS})")
    if tests > MAX_TEST_RUNS:
        invalid.append(f"test command run {tests} times (at most {MAX_TEST_RUNS})")
    return {"subagent_calls": calls, "test_runs": tests, "invalid": sorted(set(invalid), key=invalid.index)}


def tree_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in common.code_files(folder):
        digest.update(path.relative_to(folder).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


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
                              disallowed=deny_rules(hidden), extra=("--agents", agents_json(run.prompts / "multiagent")))
    volumes = [] if local else [(str(common.REPO), MOUNTS["engine"], True), (str(ws.start), MOUNTS["start"], True),
                                (str(ws.tests), MOUNTS["tests"], True), (str(run.baseline), MOUNTS["baseline"], True),
                                (str(state), MOUNTS["state"], False), (str(config_dir), MOUNTS["config"], True)]
    run.record.update({"test_command": command, "roles_allowed": {r: list(t) for r, t in ROLES.items()},
                       "budget": {"refactoring_calls": MAX_REFACTORING_CALLS, "test_runs": MAX_TEST_RUNS}})
    return {"prompt": prompt, "state": state,
            "setup": {"args": args, "tools": ORCHESTRATOR_TOOLS, "subagents_allowed": True, "volumes": volumes,
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


def execute(run: Run, test_command: str | None) -> int:
    run.setup()
    prepared = prepare(run, test_command)
    call = run.call(prepared["prompt"], "orchestrator", None, prepared["setup"])
    if call["status"] == "limit":
        return run.finish("discarded_limit", False, ["usage-limit cut: Multi-Agent is discarded and done again (W6)"])
    roles = analyze_roles(run.last_parsed["uses"], run.record["test_command"])
    run.record["roles"] = roles
    call["subagent_calls"], call["test_runs"] = roles["subagent_calls"], roles["test_runs"]
    run.save()
    invalid = call["invalid"] + roles["invalid"]
    if invalid or call["status"] != "ok":
        return run.finish("invalid", False, invalid or [f"call status {call['status']}"])

    sources = rounds_from(run, prepared["state"])
    run.state = {"best": 0, "best_commit": run.record["start_state_commit"]}
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
    parser.add_argument("--test-command", help=argparse.SUPPRESS)       # tests: a stand-in for feedback_tests.py
    args = parser.parse_args(argv)
    run = Run(APPROACH, args, toolkit)
    try:
        if args.dry_run:
            return common.dry_run(run)
        with common.RunLock(Path(args.lock_file), f"run_multiagent.py {args.run_id}", args.wait, args.poll):
            return execute(run, args.test_command)
    except EngineError as exc:
        print(f"run_multiagent: {exc}", file=sys.stderr)
        if run.record and run.record.get("status") == "running":
            run.record.update({"status": "stopped", "stop_reason": str(exc)})
            run.save()
        return exc.code
    except KeyboardInterrupt:
        if run.record:
            run.record.update({"status": "aborted"})
            run.save()
        raise


if __name__ == "__main__":
    sys.exit(main())
