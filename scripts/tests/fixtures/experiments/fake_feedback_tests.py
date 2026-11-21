"""A stand-in for experiments/feedback_tests.py in the engine tests: same snapshots and budget, no real tests.
The failing feedback cases come from lms/quality.json ("fail": {"feedback": [...]}) of the model's folder."""

import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    config = Path.cwd().parent / "agent-config" / "config.json"           # cwd is the model's folder
    cfg = json.loads(config.read_text())
    state, code = Path(cfg["state"]), Path(cfg["code"])
    counter = state / "runs.txt"
    number = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(number))
    if number > cfg["max_runs"]:
        print("budget used up")
        return 0
    snap = state / "snapshots" / f"{number:02d}"
    snap.mkdir(parents=True)
    shutil.copytree(code / "lms", snap / "lms")
    q_file = code / "lms" / "quality.json"
    fail = (json.loads(q_file.read_text()) if q_file.is_file() else {}).get("fail", {}).get("feedback", [])
    text = "".join(f"{case}: AssertionError: expected 200\n" for case in fail) or "All feedback tests passed."
    (snap / "meta.json").write_text(json.dumps({"run": number, "status": "ok", "feedback_lines": len(fail)}))
    (snap / "feedback.txt").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
