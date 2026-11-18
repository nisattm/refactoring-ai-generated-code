"""Iterative LLM run (ADR 004, W1, W4, W5, W6): rounds in one Claude Code session, the feedback tests and the
acceptance rule after every round that changed code, a rejected round is reverted, and at the end the full
measurement of the best round, round 1 and the last round.

    python experiments/run_iterative.py --start-ref <ref> --baseline <folder> [--tests-modules 1-14]
        --account <label> --run-id <id> --window-pct <0-10> [options]

Rules (W4): at most 4 calls; after call 1 at least one "re-evaluate" call; stop when the last call left no
regression and the model wrote REFACTORING_DONE, or when 3 rounds changed code. A call that changes nothing is
not a round. A round is accepted when compare.py says ``round_accepted`` against the best accepted round so far;
otherwise lms/ goes back to that best round and the next prompt gets the fixed "reverted" sentence (W5) and the
feedback of experiments/feedback.py (W2: confirmed regressions only, never metrics).

Usage-limit cut (W6): the state is saved and the run stops with exit code 5. Continue with another account only
if the setup check verified that this works:

    python experiments/run_iterative.py --resume-run --run-id <id> --account <other> --window-pct <0-10>
        --account-switch-verified [--env-file <its token file>] (other options as in the first start)

The last round is restored and the interrupted prompt is sent again in the same session. Otherwise discard it:
``--discard-run --run-id <id>`` (a row with outcome ``discarded_limit``). The lost cost goes to ``usd_lost``.

Exit code: 0 valid run · 1 invalid run, repeat it · 2 usage error · 3 run lock not free · 5 usage-limit cut.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import EngineError, Run, Workspace  # noqa: E402

APPROACH = "iterative"


def save_state(run: Run) -> None:
    common.write_json(run.out / "state.json", run.state)
    run.save()


def next_prompt(run: Run) -> tuple[str, str]:
    s = run.state
    number = common.answered_calls(run.record) + 1
    if number == 1:
        text = common.load_prompt(run.prompts, "iterative-round-1.md")
        return "round-1", common.fill_prompt(text, round=1, max_rounds=common.MAX_CALLS, feedback="", reverted="")
    text = common.load_prompt(run.prompts, "iterative-round-n.md")
    return "round-n", common.fill_prompt(text, round=number, max_rounds=common.MAX_CALLS,
                                         feedback=s["feedback"], reverted=s["sentence"])


def loop(run: Run) -> int:
    s = run.state
    while True:
        if s.get("pending"):
            kind, prompt = s["pending"]["kind"], s["pending"]["prompt"]
        else:
            kind, prompt = next_prompt(run)
            s["pending"] = {"kind": kind, "prompt": prompt}
            save_state(run)
        call = run.call(prompt, kind, s.get("session_id"))
        if call["status"] == "limit":
            s["limit_cut_at_call"] = call["number"]
            save_state(run)
            run.record["status"] = "limit_cut"
            run.event("usage-limit cut: state saved; continue with --resume-run (verified account switch) "
                      "or --discard-run (W6)")
            return common.EXIT_LIMIT
        if call["invalid"] or call["status"] != "ok":
            return finish_invalid(run, call["invalid"] or [f"call status {call['status']}"])
        s["pending"] = None
        s["session_id"] = call["session_id"] or s.get("session_id")
        regression = False
        if run.ws.lms_changed():
            k = len(run.record["rounds"]) + 1
            entry = run.commit_round(k)
            best = s["best"]
            previous = run.out / f"rounds/r{best}" / "analysis" if best else None
            facts, folder = run.measure(entry["state_commit"], entry["code_sha"], f"rounds/r{k}", "feedback", previous)
            if facts["status"] == "invalid":
                return finish_invalid(run, facts["problems"] or ["measurement invalid"])
            accepted = facts["round_accepted"] is True
            entry.update({"accepted": accepted, "facts": facts})
            regression = bool(facts["regressions"])
            repeats = [folder / f"repeat{n}" / "tests.csv" for n in (1, 2) if (folder / f"repeat{n}" / "tests.csv").is_file()]
            feedback = run.toolkit.format_feedback(run.baseline / "tests.csv", folder / "tests" / "tests.csv",
                                                   repeats, folder / "tests") if (folder / "tests" / "tests.csv").is_file() else ""
            entry["feedback_lines"] = len(feedback.splitlines())
            (folder / "feedback.txt").write_text(feedback, encoding="utf-8")
            if accepted:
                s.update({"best": k, "best_commit": entry["state_commit"],
                          "sentence": common.fixed_sentence(run.prompts, "accepted.md", common.ACCEPTED_TEXT)})
            else:
                run.ws.restore(s["best_commit"])
                s["sentence"] = common.fixed_sentence(run.prompts, "reverted.md", common.REVERTED_TEXT)
                run.event(f"round {k} rejected: lms/ back to round {s['best']} ({'; '.join(facts['accept_reasons'])})")
            s["feedback"] = feedback
        else:
            s.update({"feedback": "", "sentence": ""})
            run.event(f"call {call['number']} changed nothing in lms/ (not a round)")
        save_state(run)
        calls, rounds = common.answered_calls(run.record), len(run.record["rounds"])
        if calls >= common.MAX_CALLS:
            return final(run, f"{common.MAX_CALLS} calls")
        if rounds >= common.MAX_CODE_ROUNDS:
            return final(run, f"{common.MAX_CODE_ROUNDS} rounds changed code")
        if calls >= 2 and call["done_marker"] and not regression:
            return final(run, f"{common.DONE_MARKER} and no regression")


def finish_invalid(run: Run, reasons: list[str]) -> int:
    run.state["pending"] = None
    save_state(run)
    return run.finish("invalid", False, reasons)


def final(run: Run, why: str) -> int:
    """Full measurement (both test sets) of the best round, round 1 and the last round (W1)."""
    s, rounds = run.state, run.record["rounds"]
    run.record["stop_reason"] = why
    run.event(f"stop: {why}")
    if not rounds:
        return run.finish(*common.classify([], None))
    wanted = {"best": s["best"], "round1": 1, "last": rounds[-1]["round"]}
    measured: dict[int, dict] = {}
    for name, k in wanted.items():
        if k == 0:
            continue
        if k not in measured:
            entry = rounds[k - 1]
            facts, _ = run.measure(entry["state_commit"], entry["code_sha"], f"final/r{k}", "both", None)
            measured[k] = facts
        run.record["final"][name] = {**measured[k], "round": k}
    save_state(run)
    if any(f["status"] == "invalid" for f in measured.values()):
        return run.finish("invalid", False, [p for f in measured.values() for p in f["problems"]])
    if s["best"] == 0:
        run.record.update({"best_round": 0, "best_tag": ""})
        return run.finish("no_improvement", True, ["no round was accepted: the best result is the starting code"])
    best = run.record["final"]["best"]
    run.record.update({"best_round": s["best"], "best_tag": rounds[s["best"] - 1]["tag"], "best_facts": best})
    outcome, valid, reasons = common.classify([], best)
    return run.finish(outcome, valid, reasons)


def resume(run: Run, args) -> int:
    run.record = common.read_json(run.out / "run.json")
    run.state = common.read_json(run.out / "state.json")
    if run.record.get("status") != "limit_cut" or not run.state.get("pending"):
        raise EngineError(f"run {args.run_id} is not waiting after a usage-limit cut")
    run.ws = Workspace(Path(run.record["work_root"]))
    if not run.ws.git_dir.is_dir():
        raise EngineError(f"work folder {run.ws.root} is gone: the run cannot continue")
    if args.discard_run:
        cut = run.record["calls"][-1]
        cut["usd_diff"] = cut["usd_diff"] or 0
        return run.finish("discarded_limit", False, ["usage-limit cut, continuing not verified: run discarded (W6)"])
    if not args.account_switch_verified:
        raise EngineError("W6: continue only if the setup check verified that another account can continue the "
                          "session (--account-switch-verified); otherwise use --discard-run")
    if args.window_pct is None or args.window_pct > common.WINDOW_LIMIT_PCT:
        raise EngineError(f"W6: the new account's 5-hour window must be at most {common.WINDOW_LIMIT_PCT:g} %")
    run.record["accounts_used"].append(args.account)
    run.record["status"] = "running"
    run.ws.restore(run.ws.head())
    run.event(f"resumed with account {args.account} (window {args.window_pct} %); last round restored, "
              f"call {run.state['limit_cut_at_call']} sent again")
    return loop(run)


def execute(run: Run) -> int:
    run.setup()
    run.state = {"best": 0, "best_commit": run.record["start_state_commit"], "feedback": "", "sentence": "",
                 "session_id": None, "pending": None}
    save_state(run)
    return loop(run)


def main(argv: list[str] | None = None, toolkit: common.Toolkit | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_arguments(parser)
    parser.add_argument("--resume-run", action="store_true", help="continue a run stopped by a usage-limit cut")
    parser.add_argument("--account-switch-verified", action="store_true",
                        help="the setup check verified that another account can continue a session (W6)")
    parser.add_argument("--discard-run", action="store_true", help="give up a run stopped by a usage-limit cut")
    if argv is None:
        argv = sys.argv[1:]
    if "--resume-run" in argv or "--discard-run" in argv:
        for action in parser._actions:  # the start options are in run.json
            if action.dest in ("start_ref", "baseline"):
                action.required = False
    args = parser.parse_args(argv)
    run = Run(APPROACH, args, toolkit)
    try:
        if args.dry_run:
            return common.dry_run(run)
        with common.RunLock(Path(args.lock_file), f"run_iterative.py {args.run_id}", args.wait, args.poll):
            if args.resume_run or args.discard_run:
                if not (run.out / "state.json").is_file():
                    raise EngineError(f"no saved state in {run.out}")
                run.baseline = Path(common.read_json(run.out / "run.json")["baseline"])
                return resume(run, args)
            return execute(run)
    except EngineError as exc:
        print(f"run_iterative: {exc}", file=sys.stderr)
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
