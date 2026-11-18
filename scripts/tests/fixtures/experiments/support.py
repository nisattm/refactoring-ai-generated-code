"""Test support for the experiment engine: a small git repository, a starting measurement, prompts, the fake
Claude and a fake measurement step (FakeToolkit) that reads ``lms/quality.json`` written by the fake Claude.

``lms/quality.json`` keys: the primary metrics (default: the starting values), ``fail`` ({set: [case IDs]}),
``api`` (true: the OpenAPI schema changed), ``loads`` (false: the code does not load), ``measure_status``.
"""

from __future__ import annotations

import csv
import json
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "experiments"))

import common  # noqa: E402

START = {"mean_cc": 3.0, "mean_cognitive": 2.0, "mi_weighted": 40.0, "duplication_pct": 3.0, "smell_count": 100}
CASES = [("T-A-01-a", "feedback"), ("T-A-02-a", "feedback"), ("T-A-01-b", "heldout")]
HIGHER = {"mi_weighted"}
THRESHOLD = {"mean_cc": 0.01, "mean_cognitive": 0.01, "mi_weighted": 0.1, "duplication_pct": 0.1, "smell_count": 1}


def run_git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def make_project(root: Path) -> dict:
    """A git repository with dataset/lms/generated, a starting measurement, tests, prompts and INTERFACE.md."""
    repo = root / "repo"
    gen = repo / "dataset" / "lms" / "generated"
    (gen / "lms" / "loans").mkdir(parents=True)
    (gen / "lms" / "__init__.py").write_text("")
    (gen / "lms" / "loans" / "__init__.py").write_text("")
    (gen / "lms" / "loans" / "service.py").write_text("def fee(days):\n    return days * 2\n")
    (gen / "requirements.txt").write_text("fastapi\n")
    (gen / "REQUIREMENTS.md").write_text("# Requirements\n")
    (gen / "web").mkdir()
    (gen / "web" / "index.html").write_text("<html></html>\n")
    (gen / "tests").mkdir()
    (gen / "tests" / "test_own.py").write_text("def test_x():\n    assert True\n")
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "t@example.com")
    run_git(repo, "config", "user.name", "t")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "start")
    sha = run_git(repo, "rev-parse", "HEAD")

    baseline = root / "baseline"
    baseline.mkdir()
    (baseline / "summary.json").write_text(json.dumps({"code_sha": sha, "primary": START}))
    write_tests_csv(baseline / "tests.csv", {})
    (baseline / "flaky.txt").write_text("# none\n")

    tests = root / "tests"
    (tests / "feedback").mkdir(parents=True)
    (tests / "conftest.py").write_text("")
    (tests / "feedback" / "test_a.py").write_text("def test_a():\n    pass\n")

    prompts = root / "prompts"
    prompts.mkdir()
    (prompts / "single.md").write_text("Refactor lms/.\n")
    (prompts / "iterative-round-1.md").write_text("Round {round} of {max_rounds}. Refactor lms/.\n")
    (prompts / "iterative-round-n.md").write_text("Round {round} of {max_rounds}.\n{reverted}\n{feedback}\n"
                                                  "Write REFACTORING_DONE when done. Keep {other} braces.\n")
    interface = root / "INTERFACE.md"
    interface.write_text("# Interface\n")
    (root / "metrics").mkdir()
    return {"root": root, "repo": repo, "sha": sha, "baseline": baseline, "tests": tests, "prompts": prompts,
            "interface": interface}


def argv(project: dict, run_id: str, *extra: str) -> list[str]:
    root = project["root"]
    fake = f"{shlex.quote(sys.executable)} {shlex.quote(str(HERE / 'fake_claude.py'))}"
    return ["--start-ref", project["sha"], "--baseline", str(project["baseline"]), "--account", "acc-a",
            "--run-id", run_id, "--window-pct", "5", "--local", "--claude-command", fake,
            "--repo", str(project["repo"]), "--out-root", str(root / "out"), "--cost-log", str(root / "metrics" / "cost-log.csv"),
            "--lock-file", str(root / ".run.lock"), "--tests", str(project["tests"]), "--interface", str(project["interface"]),
            "--prompts", str(project["prompts"]), "--work-root", str(root / f"work-{run_id}"),
            "--expected-version", "9.9.9", "--wait", "0", "--poll", "1", "--keep-work", *extra]


def scenario(monkeypatch, root: Path, calls: list[dict]) -> None:
    path = root / "scenario.json"
    path.write_text(json.dumps(calls))
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", str(path))


def quality(**values) -> str:
    return json.dumps(values)


def write_tests_csv(path: Path, failing: dict, sets=("feedback", "heldout")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case", "module", "table", "type", "set", "result"])
        for case, kind in CASES:
            if kind in sets:
                writer.writerow([case, "1", "a", "Normal", kind, "failed" if case in failing.get(kind, []) else "passed"])


def status(metric: str, before: float, after: float) -> str:
    delta = after - before
    if abs(delta) < THRESHOLD[metric]:
        return "same"
    better = delta > 0 if metric in HIGHER else delta < 0
    return "improved" if better else "worse"


class FakeToolkit(common.Toolkit):
    def __init__(self):
        self.measured: list[dict] = []
        self.feedback_calls: list[tuple] = []

    def measure(self, run, tree, out, label, code_sha, test_set, previous_best):
        q_file = tree / "lms" / "quality.json"
        q = json.loads(q_file.read_text()) if q_file.is_file() else {}
        after = {m: q.get(m, START[m]) for m in START}
        reference = json.loads((previous_best / "summary.json").read_text())["primary"] if previous_best else START
        sets = ("feedback",) if test_set == "feedback" else ("feedback", "heldout")
        fail = {s: q.get("fail", {}).get(s, []) for s in sets}
        (out / "analysis").mkdir(parents=True, exist_ok=True)
        (out / "analysis" / "summary.json").write_text(json.dumps({"primary": after, "code_sha": code_sha}))
        write_tests_csv(out / "tests" / "tests.csv", fail, sets)
        if any(fail.values()):
            write_tests_csv(out / "repeat1" / "tests.csv", fail, sets)
            write_tests_csv(out / "repeat2" / "tests.csv", fail, sets)
        regs = [{"set": s, "case": c, "confirmed": True} for s in sets for c in fail[s]]
        api, loads = bool(q.get("api")), q.get("loads", True)
        primary = {m: {"before": START[m], "after": after[m], "delta": after[m] - START[m],
                       "status": status(m, START[m], after[m])} for m in START}
        vs_ref = {m: status(m, reference[m], after[m]) for m in START}
        ok = not regs and not api and loads
        accepted = ok and "worse" not in vs_ref.values()
        successful = ok and all(v["status"] != "worse" for v in primary.values()) and \
            any(v["status"] == "improved" for v in primary.values())
        reasons = [] if successful else ["fake: not successful"]
        compare = {"primary": primary, "invalid": [],
                   "tests": {"regression_count": len(regs), "regressions": regs, "sets_not_run":
                             [] if test_set == "both" else ["heldout"]},
                   "openapi": {"checked": True, "changed": api or not loads,
                               "after_hash": "x" * 64 if loads else None},
                   "round_accepted": {"value": accepted, "reasons": [] if accepted else ["fake: rejected"]},
                   "run_successful": {"value": None if (successful and test_set != "both") else successful,
                                      "reasons": reasons}}
        (out / "compare").mkdir(parents=True, exist_ok=True)
        (out / "compare" / "compare.json").write_text(json.dumps(compare))
        status_ = q.get("measure_status", "ok")
        (out / "measure.json").write_text(json.dumps({"status": status_, "problems": [] if status_ == "ok" else
                                                      [f"fake {status_}"], "api_change_kind":
                                                      "real API change" if api else None}))
        self.measured.append({"label": label, "set": test_set, "previous_best": previous_best, "code_sha": code_sha,
                              "tree_files": sorted(p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file())})
        return common.read_measurement(out, 0)

    def format_feedback(self, tests_before, tests_after, repeats, log_dir):
        self.feedback_calls.append((tests_before, tests_after, repeats, log_dir))
        with open(tests_after, newline="", encoding="utf-8") as handle:
            failed = [r["case"] for r in csv.DictReader(handle) if r["result"] != "passed"]
        return "".join(f"{case}: AssertionError: expected 200\n" for case in failed if len(repeats) == 2)


def read_runs(root: Path) -> list[dict]:
    with (root / "out" / "runs.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fake_args(root: Path, number: int) -> list[str]:
    return json.loads(next((root).glob("work-*/session/fake-call-%d.json" % number)).read_text())["args"]
