"""Measurement of one round inside the Docker image (network off): analyzer, tests, the two repetitions of the new
failures (D18), compare.py with every argument, and the classification of an API change (W11).

    python experiments/measure.py --code TREE --tests DIR --hashes FILE --baseline DIR --start-code DIR --out DIR
        --label NAME --code-sha SHA --set feedback|both [--previous-best DIR] [--timeout SECONDS]

Writes into --out: analysis/ (analyze.py), tests/ (run_tests.py), repeat1/ and repeat2/, compare/ (compare.py),
openapi/ (only when the API changed) and measure.json. ``measure.json`` ``status``: ok · invalid (test files
changed: the run is repeated) · timeout (tests timed out again after one repetition) · not_measurable (no
analysis) · error (compare.py failed). Exit code: 0 ok, 3 invalid, 4 any other status, 2 usage error.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

SCHEMA_SNIPPET = """
import json, sys
sys.path.insert(0, sys.argv[1])
import lms
schema = lms.create_app(lms.Settings(database_url="sqlite://")).openapi()
print(json.dumps(schema, sort_keys=True, ensure_ascii=False))
"""

DESCRIPTIVE_KEYS = {"description", "summary", "title", "example", "examples"}


def read_results(path: Path) -> dict[tuple[str, str], str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {(r["set"], r["case"]): r["result"] for r in csv.DictReader(handle)}


def read_flaky(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def new_failures(before: dict, after: dict, flaky: set[str]) -> list[str]:
    """Cases that passed at the start and do not pass now, in the sets that ran (they are repeated twice, D18)."""
    sets = {s for s, _ in after}
    return sorted({case for (s, case), result in before.items()
                   if s in sets and result == "passed" and case not in flaky and after.get((s, case)) != "passed"})


# --- W11: what kind of API change -----------------------------------------------------------------------------------

def _strip(node, drop: set[str]):
    if isinstance(node, dict):
        return {k: _strip(v, drop) for k, v in node.items() if k not in drop}
    if isinstance(node, list):
        return [_strip(v, drop) for v in node]
    return node


def _inline(node, components: dict, seen: tuple = ()):
    """Replace every ``$ref`` by the schema it points to, so that the names of the schemas do not matter."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[1]
            if name in seen or name not in components:
                return {"$ref": "<recursive>"}
            return _inline(components[name], components, seen + (name,))
        return {k: _inline(v, components, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline(v, components, seen) for v in node]
    return node


def api_change_kind(before: dict, after: dict) -> str:
    """``descriptions only`` · ``schema names only`` (e.g. a moved or renamed model class) · ``real API change``."""
    b, a = _strip(before, DESCRIPTIVE_KEYS), _strip(after, DESCRIPTIVE_KEYS)
    if b == a:
        return "descriptions only"
    flat = lambda s: _inline(s.get("paths", {}), s.get("components", {}).get("schemas", {}))  # noqa: E731
    if flat(b) == flat(a):
        return "schema names only"
    return "real API change"


def dump_schema(code: Path, dest: Path) -> dict | None:
    with tempfile.TemporaryDirectory(prefix="schema-") as neutral:
        proc = subprocess.run([sys.executable, "-c", SCHEMA_SNIPPET, str(code.resolve())], cwd=neutral,
                              capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    schema = json.loads(proc.stdout.strip().splitlines()[-1])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(schema, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return schema


# --- steps ----------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("--code", "--tests", "--hashes", "--baseline", "--start-code", "--out"):
        parser.add_argument(name, type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--set", choices=("feedback", "both"), required=True)
    parser.add_argument("--previous-best", type=Path)
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args(argv)
    if not (args.code / "lms").is_dir():
        print(f"no lms/ in {args.code}", file=sys.stderr)
        return 2

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    info: dict = {"label": args.label, "code_sha": args.code_sha, "set": args.set, "steps": [], "problems": [],
                  "status": "ok", "new_failures": [], "api_change_kind": None}

    def step(name: str, cmd: list, ok: tuple[int, ...] = (0,)) -> int:
        started = time.monotonic()
        with (out / f"{name}.log").open("w", encoding="utf-8") as log:
            code = subprocess.run([str(c) for c in cmd], stdout=log, stderr=subprocess.STDOUT, check=False).returncode
        info["steps"].append({"name": name, "exit": code, "seconds": round(time.monotonic() - started, 1)})
        if code not in ok:
            info["problems"].append(f"{name} exited with {code} (see {name}.log)")
        return code

    def finish(status: str | None = None) -> int:
        if status:
            info["status"] = status
        (out / "measure.json").write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"ok": 0, "invalid": 3}.get(info["status"], 4)

    # 1. analyzer (code_sha = the tagged commit of this round)
    step("analyze", [py, SCRIPTS / "analyze.py", "--code", args.code, "--out", out / "analysis", "--label", args.label,
                     "--with-secondary", "--code-sha", args.code_sha])
    if not (out / "analysis" / "summary.json").is_file():
        return finish("not_measurable")

    # 2. tests (the hashes of the run's tests are checked before and after); a timeout is repeated once (W10)
    tests_cmd = [py, SCRIPTS / "run_tests.py", "--code", args.code, "--tests", args.tests, "--set", args.set,
                 "--baseline", args.hashes, "--timeout", str(args.timeout)]
    code = step("tests", [*tests_cmd, "--out", out / "tests"], (0, 1))
    if code == 4:
        code = step("tests-retry", [*tests_cmd, "--out", out / "tests"], (0, 1))
        if code == 4:
            return finish("timeout")
    if code == 3:
        return finish("invalid")
    if code not in (0, 1) or not (out / "tests" / "tests.csv").is_file():
        return finish("error")

    # 3. the cases that passed at the start and fail now run twice more (D18)
    before = read_results(args.baseline / "tests.csv")
    flaky = read_flaky(args.baseline / "flaky.txt")
    failing = new_failures(before, read_results(out / "tests" / "tests.csv"), flaky)
    info["new_failures"] = failing
    repeats = []
    if failing:
        (out / "failing.txt").write_text("\n".join(failing) + "\n", encoding="utf-8")
        for number in (1, 2):
            folder = out / f"repeat{number}"
            code = step(f"repeat{number}", [*tests_cmd, "--out", folder, "--cases", out / "failing.txt"], (0, 1))
            if code == 3:
                return finish("invalid")
            if (folder / "tests.csv").is_file():
                repeats.append(folder / "tests.csv")

    # 4. compare.py with every argument
    cmd = [py, SCRIPTS / "compare.py", "--before", args.baseline, "--after", out / "analysis", "--out", out / "compare",
           "--tests-before", args.baseline / "tests.csv", "--tests-after", out / "tests" / "tests.csv",
           "--before-code", args.start_code, "--after-code", args.code]
    for path in repeats:
        cmd += ["--tests-after-repeat", path]
    if (args.baseline / "flaky.txt").is_file():
        cmd += ["--flaky", args.baseline / "flaky.txt"]
    if args.previous_best:
        cmd += ["--previous-best", args.previous_best]
    if step("compare", cmd) != 0 or not (out / "compare" / "compare.json").is_file():
        return finish("error")

    # 5. W11: the normalized difference of an API change
    report = json.loads((out / "compare" / "compare.json").read_text(encoding="utf-8"))
    openapi = report.get("openapi") or {}
    if openapi.get("changed"):
        b = dump_schema(args.start_code, out / "openapi" / "before.json")
        a = dump_schema(args.code, out / "openapi" / "after.json")
        info["api_change_kind"] = "code does not load" if a is None else (
            "unclassified" if b is None else api_change_kind(b, a))
    return finish()


if __name__ == "__main__":
    sys.exit(main())
