"""Single LLM run (ADR 004, W8): one Claude Code call → full measurement → comparison with the starting code.

    python experiments/run_single.py --start-ref <ref> --baseline <folder> [--tests-modules 1-14]
        --account <label> --run-id <id> --window-pct <0-10> [options]

Output: results/experiments/single/<run-id>/run.json, one row in results/experiments/runs.csv, the tag
exp/single/<run-id>/r1 and the cost rows in metrics/cost-log.csv. A usage-limit cut discards the run (W6): the row
is written with outcome ``discarded_limit`` and the run is done again from the start with a new --run-id.

Exit code: 0 valid run (any outcome) · 1 invalid run, repeat it (W10) · 2 usage error · 3 run lock not free ·
5 usage-limit cut, run discarded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import EngineError, Run  # noqa: E402

APPROACH = "single"


def execute(run: Run) -> int:
    run.setup()
    prompt = common.load_prompt(run.prompts, "single.md")
    call = run.call(prompt, "single", None)
    if call["status"] == "limit":
        return run.finish("discarded_limit", False, ["usage-limit cut: Single is discarded and done again (W6)"])
    if call["invalid"] or call["status"] != "ok":
        return run.finish("invalid", False, call["invalid"] or [f"call status {call['status']}"])
    if not run.ws.lms_changed():
        return run.finish(*common.classify([], None))
    entry = run.commit_round(1)
    facts, folder = run.measure(entry["state_commit"], entry["code_sha"], "rounds/r1", "both", None)
    entry.update({"accepted": facts["run_successful"], "facts": facts})
    outcome, valid, reasons = common.classify([], facts)
    run.record.update({"best_round": 1, "best_tag": entry["tag"], "best_facts": facts})
    run.record["final"] = {"best": facts, "round1": facts, "last": facts}
    return run.finish(outcome, valid, reasons)


def main(argv: list[str] | None = None, toolkit: common.Toolkit | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_arguments(parser)
    args = parser.parse_args(argv)
    run = Run(APPROACH, args, toolkit)
    try:
        if args.dry_run:
            return common.dry_run(run)
        with common.RunLock(Path(args.lock_file), f"run_single.py {args.run_id}", args.wait, args.poll) as lock:
            run.lock = lock
            return execute(run)
    except EngineError as exc:
        print(f"run_single: {exc}", file=sys.stderr)
        if run.record:
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
