"""The feedback test command of the Multi-Agent orchestrator (approaches.md, ADR 005 draft M3, M4, M6).

    python /engine/experiments/feedback_tests.py [--config /exp-config/config.json]

The orchestrator may run this one command and nothing else in the shell. Every run:

1. counts itself; beyond ``max_runs`` it prints a fixed sentence and runs nothing (M5);
2. keeps a snapshot of the model's ``lms/`` (``<state>/snapshots/<n>/lms``): the engine later measures every snapshot
   as a round and keeps the best one (W1, M6);
3. runs the feedback tests in a copy of the starting project with only ``lms/`` replaced (W3), repeats the cases that
   passed at the start and fail now twice (D18);
4. prints the text of ``experiments/feedback.py`` (W2: confirmed regressions only, test ID and short error, never
   metrics) or a fixed sentence when there is no regression, exactly what Iterative gets between rounds.

The config (written by the engine, read-only for the model) holds the paths: ``code`` (the model's folder), ``project``
(the starting project), ``tests``, ``hashes``, ``baseline`` (``tests.csv``, ``flaky.txt``), ``state`` (snapshots,
writable), ``scripts`` (``run_tests.py``), ``max_runs`` and ``timeout``. Exit code 0 except for a broken config (2).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import feedback  # noqa: E402  (W2 text, Aslınur)
import measure  # noqa: E402  (new_failures, read_results, read_flaky)

DEFAULT_CONFIG = "/exp-config/config.json"
# Fixed, neutral sentences (to be approved with the Multi-Agent prompts, as W5)
NO_REGRESSION_TEXT = "All feedback tests that passed at the start still pass."
BUDGET_TEXT = "The feedback tests can be run at most {max_runs} times in this task; they were not run again."
ERROR_TEXT = "The feedback tests could not be run."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        state, code = Path(cfg["state"]), Path(cfg["code"])
    except (OSError, ValueError, KeyError) as exc:
        print(f"feedback_tests: broken config {args.config}: {exc}", file=sys.stderr)
        return 2

    counter = state / "runs.txt"
    number = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(number))
    if number > int(cfg.get("max_runs", 3)):
        print(BUDGET_TEXT.format(max_runs=cfg.get("max_runs", 3)))
        return 0

    snap = state / "snapshots" / f"{number:02d}"
    snap.mkdir(parents=True)
    shutil.copytree(code / "lms", snap / "lms", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    meta = {"run": number, "at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "status": "ok"}

    text = ERROR_TEXT
    with tempfile.TemporaryDirectory(prefix="feedback-tree-") as tmp:
        tree = Path(tmp) / "project"
        project = Path(cfg["project"])
        shutil.copytree(project, tree, ignore=lambda d, names: ["lms"] if Path(d) == project else [])
        shutil.copytree(snap / "lms", tree / "lms")
        base = [sys.executable, str(Path(cfg["scripts"]) / "run_tests.py"), "--code", str(tree), "--tests", cfg["tests"],
                "--set", "feedback", "--baseline", cfg["hashes"], "--timeout", str(cfg.get("timeout", 7200))]

        def run(out: Path, *extra: str) -> int:
            with (snap / f"{out.name}.log").open("w", encoding="utf-8") as log:
                return subprocess.run([*base, "--out", str(out), *extra], stdout=log, stderr=subprocess.STDOUT,
                                      check=False).returncode

        code_tests = run(snap / "tests")
        meta["tests_exit"] = code_tests
        after_csv = snap / "tests" / "tests.csv"
        if code_tests not in (0, 1) or not after_csv.is_file():
            meta["status"] = "invalid" if code_tests == 3 else "error"
        else:
            baseline = Path(cfg["baseline"])
            failing = measure.new_failures(measure.read_results(baseline / "tests.csv"), measure.read_results(after_csv),
                                           measure.read_flaky(baseline / "flaky.txt"))
            meta["new_failures"] = failing
            repeats = []
            if failing:
                (snap / "failing.txt").write_text("\n".join(failing) + "\n", encoding="utf-8")
                for n in (1, 2):
                    run(snap / f"repeat{n}", "--cases", str(snap / "failing.txt"))
                    if (snap / f"repeat{n}" / "tests.csv").is_file():
                        repeats.append(snap / f"repeat{n}" / "tests.csv")
            body = feedback.format_feedback(baseline / "tests.csv", after_csv, repeats, snap / "tests")
            meta["feedback_lines"] = len(body.splitlines())
            meta["regressions_confirmed"] = bool(body)
            text = body or NO_REGRESSION_TEXT
    (snap / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (snap / "feedback.txt").write_text(text + "\n", encoding="utf-8")        # what the orchestrator got
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
