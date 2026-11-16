"""Compares two analyzer results (and, optionally, two test results) of the LMS (ADR 003, D17-D21).

    python scripts/compare.py --before <analysis folder> --after <analysis folder> --out <folder>
                              [--tests-before tests.csv --tests-after tests.csv]
                              [--tests-after-repeat tests.csv ...] [--flaky <list>]
                              [--previous-best <analysis folder>]
                              [--before-code <folder with lms/> --after-code <folder with lms/>]

``--tests-after-repeat`` (twice, from ``run_tests.py --cases``) is the repetition of D18: a test that
passed at the start and fails after refactoring is a regression only if it fails in both repetitions.
``--before-code`` / ``--after-code`` give the change size (``git diff --no-index``) and the OpenAPI hash
(D21); without them those two checks are not made and a decision that needs them is ``null``.

Writes ``<out>/compare.json`` and ``<out>/compare.csv``. Two separate decisions, each with its reasons:
``round_accepted`` (one Iterative round) and ``run_successful`` (the success definition).

Exit codes: 0 compared · 2 usage error · 3 incompatible inputs (other schema version or other frozen
smell list) · 4 missing data (a file or a baseline value is missing; compare.json says what).
Standard library only; the OpenAPI hash needs the LMS stack (run it in the Docker image).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyzer import workspace  # noqa: E402

COMPARE_VERSION = "1.0"
# metric -> (better direction, threshold of "changed"; ADR 003, D20)
PRIMARY = {
    "mean_cc": ("lower", Decimal("0.01")),
    "mean_cognitive": ("lower", Decimal("0.01")),
    "mi_weighted": ("higher", Decimal("0.1")),
    "duplication_pct": ("lower", Decimal("0.05")),
    "smell_count": ("lower", Decimal("1")),
}
MODULE_METRICS = ("files", "sloc", "units", "mean_cc", "mean_cognitive", "mi_weighted", "smells", "smells_per_ksloc",
                  "duplication_pct")
SLOC_DROP_WARNING = 15.0
LIST_LIMIT = 300
TEST_COLUMNS = ("case", "module", "type", "set", "result")
CSV_COLUMNS = ("kind", "scope", "metric", "before", "after", "delta", "threshold", "status")


class Stop(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- reading ------------------------------------------------------------------------------------------------------

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Stop(4, f"cannot read {path}: {exc}") from exc


def read_csv(path: Path) -> list[dict]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise Stop(4, f"cannot read {path}: {exc}") from exc


def number(text: str | None):
    if text is None or text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return float(text)


class Analysis:
    """One analyzer result folder."""

    def __init__(self, folder: Path):
        if not folder.is_dir():
            raise Stop(2, f"not a folder: {folder}")
        self.folder = folder
        self.summary = read_json(folder / "summary.json")
        for key in ("primary", "schema_version", "frozen_smell_list", "smell_counts"):
            if key not in self.summary:
                raise Stop(4, f"{folder / 'summary.json'} has no field {key!r}")
        self._tables: dict[str, list[dict]] = {}

    def table(self, name: str) -> list[dict]:
        if name not in self._tables:
            self._tables[name] = read_csv(self.folder / name)
        return self._tables[name]

    def info(self) -> dict:
        s = self.summary
        return {"label": s.get("label"), "code_sha": s.get("code_sha"), "code_content_hash": s.get("code_content_hash"),
                "analyzer_sha": s.get("analyzer_sha"), "image_id": s.get("image_id"), "schema_version": s["schema_version"],
                "tool_versions": s.get("tool_versions")}


def read_tests(path: Path) -> dict[tuple[str, str], dict]:
    rows = read_csv(path)
    if rows and not set(TEST_COLUMNS) <= set(rows[0]):
        raise Stop(4, f"{path} lacks columns {sorted(set(TEST_COLUMNS) - set(rows[0]))}")
    return {(r["set"], r["case"]): r for r in rows}


def read_flaky(path: Path | None) -> set[str]:
    if path is None:
        return set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Stop(4, f"cannot read {path}: {exc}") from exc
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


# --- primary metrics (D20) ----------------------------------------------------------------------------------------

def dec(value) -> Decimal:
    """A value rounded to 4 decimals, so that 0.01 differences are exact."""
    return Decimal(str(round(float(value), 4)))


def metric_status(name: str, before, after) -> dict:
    direction, threshold = PRIMARY[name]
    entry = {"before": before, "after": after, "threshold": float(threshold), "direction": direction}
    if before is None:
        return {**entry, "delta": None, "status": "not comparable"}
    if after is None:
        return {**entry, "delta": None, "status": "invalid"}
    delta = dec(after) - dec(before)
    if abs(delta) < threshold:
        status = "same"
    else:
        better = delta < 0 if direction == "lower" else delta > 0
        status = "improved" if better else "worse"
    return {**entry, "delta": float(delta), "status": status}


def primary_table(reference: dict, after: dict) -> dict:
    return {m: metric_status(m, reference["primary"].get(m), after["primary"].get(m)) for m in PRIMARY}


def check_compatible(base: Analysis, other: Analysis, names: str) -> None:
    if base.summary["schema_version"] != other.summary["schema_version"]:
        raise Stop(3, f"{names}: schema versions differ ({base.summary['schema_version']} and "
                      f"{other.summary['schema_version']})")
    if base.summary["frozen_smell_list"] != other.summary["frozen_smell_list"]:
        raise Stop(3, f"{names}: the frozen smell lists differ")


# --- tests (D17-D19) ----------------------------------------------------------------------------------------------

def compare_tests(before: dict, after: dict, repeats: list[dict], flaky: set[str]) -> dict:
    """Regressions, new passes and lost cases per set. A set that the after run did not run is not compared."""
    sets_run = sorted({s for s, _ in after} & {s for s, _ in before})
    sets_not_run = sorted({s for s, _ in before} - {s for s, _ in after})
    out: dict = {"sets_compared": sets_run, "sets_not_run": sets_not_run, "sets": {}, "excluded_flaky": [],
                 "regressions": [], "regressions_confirmed": 0, "regressions_unconfirmed": 0, "recovered_in_repeat": []}
    by_module: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for s in sets_run:
        info = {"before_passed": 0, "after_passed": 0, "baseline_failing": 0, "baseline_failing_still": 0,
                "regressions": 0, "new_passing": 0, "lost": 0, "new_cases": 0}
        for (kind, case), row in sorted(before.items()):
            if kind != s:
                continue
            if case in flaky:
                out["excluded_flaky"].append({"set": s, "case": case})
                continue
            was = row["result"]
            now_row = after.get((s, case))
            now = now_row["result"] if now_row else "missing"
            info["before_passed"] += was == "passed"
            info["after_passed"] += now == "passed"
            info["lost"] += now == "missing"
            if was != "passed":
                info["baseline_failing"] += 1
                info["baseline_failing_still"] += now != "passed"
                info["new_passing"] += now == "passed"
                continue
            if now == "passed":
                continue
            seen = [rep.get((s, case)) for rep in repeats]
            results = [r["result"] if r else None for r in seen]
            if any(r == "passed" for r in results):
                out["recovered_in_repeat"].append({"set": s, "case": case})
                continue
            confirmed = len(repeats) >= 2 and all(r is not None for r in results)
            info["regressions"] += 1
            out["regressions_confirmed" if confirmed else "regressions_unconfirmed"] += 1
            out["regressions"].append({"set": s, "case": case, "before": was, "after": now, "module": row["module"],
                                       "type": row["type"], "confirmed": confirmed, "repeat_results": results})
            by_module[row["module"]] = by_module.get(row["module"], 0) + 1
            by_type[row["type"]] = by_type.get(row["type"], 0) + 1
        info["new_cases"] = sum(1 for (k, c) in after if k == s and (s, c) not in before)
        out["sets"][s] = info
    out["lost_cases"] = [{"set": s, "case": c, "before": before[(s, c)]["result"]} for (s, c) in sorted(before)
                         if s in sets_run and c not in flaky and (s, c) not in after]
    out["lost_cases"] += [{"set": s, "case": c, "before": before[(s, c)]["result"]} for (s, c), r in sorted(after.items())
                          if s in sets_run and r["result"] == "missing" and (s, c) in before and c not in flaky]
    out["new_passing"] = [{"set": s, "case": c} for (s, c), r in sorted(after.items())
                          if s in sets_run and c not in flaky and r["result"] == "passed"
                          and before.get((s, c)) and before[(s, c)]["result"] != "passed"][:LIST_LIMIT]
    out["regression_count"] = out["regressions_confirmed"] + out["regressions_unconfirmed"]
    out["regressions_by_module"] = dict(sorted(by_module.items()))
    out["regressions_by_type"] = dict(sorted(by_type.items()))
    out["repetitions_given"] = len(repeats)
    return out


# --- code: OpenAPI hash, change size (D21) ------------------------------------------------------------------------

OPENAPI_SNIPPET = """
import hashlib, json, sys
sys.path.insert(0, sys.argv[1])
import lms
schema = lms.create_app(lms.Settings(database_url="sqlite://")).openapi()
text = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
print(hashlib.sha256(text.encode("utf-8")).hexdigest())
"""


def openapi_hash(code: Path) -> tuple[str | None, str | None]:
    """SHA-256 of ``create_app(...).openapi()`` with sorted keys, or ``(None, error)``."""
    with tempfile.TemporaryDirectory(prefix="openapi-") as neutral:
        try:
            proc = subprocess.run([sys.executable, "-c", OPENAPI_SNIPPET, str(code.resolve())], cwd=neutral,
                                  capture_output=True, text=True, timeout=600, check=False,
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, str(exc)
    lines = proc.stdout.strip().splitlines()
    if proc.returncode != 0 or not lines or len(lines[-1]) != 64:
        tail = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        return None, tail
    return lines[-1], None


def change_size(before_code: Path, after_code: Path) -> dict:
    """Lines added and removed, files changed, added and removed between the two ``lms/`` (clean copies, D1 files only)."""
    ws_before = workspace.build((before_code / "lms").resolve())
    ws_after = workspace.build((after_code / "lms").resolve())
    root = Path(tempfile.mkdtemp(prefix="changesize-"))
    try:
        shutil.copytree(ws_before.pkg, root / "before" / "lms")
        shutil.copytree(ws_after.pkg, root / "after" / "lms")
        base = ["git", "-c", "core.autocrlf=false", "diff", "--no-index", "--no-renames", "--ignore-cr-at-eol"]
        numstat = subprocess.run([*base, "--numstat", "before", "after"], cwd=root, capture_output=True, text=True, check=False)
        status = subprocess.run([*base, "--name-status", "before", "after"], cwd=root, capture_output=True, text=True, check=False)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        ws_before.close()
        ws_after.close()
    if numstat.returncode not in (0, 1) or status.returncode not in (0, 1):
        raise Stop(4, f"git diff failed: {numstat.stderr.strip() or status.stderr.strip()}")
    added = removed = 0
    for line in numstat.stdout.splitlines():
        a, r, _ = line.split("\t", 2)
        added += int(a) if a.isdigit() else 0
        removed += int(r) if r.isdigit() else 0
    kinds = [line.split("\t", 1)[0] for line in status.stdout.splitlines() if line.strip()]
    return {"lines_added": added, "lines_removed": removed, "files_changed": kinds.count("M"),
            "files_added": kinds.count("A"), "files_removed": kinds.count("D")}


def inventory(before: Analysis, after: Analysis) -> dict:
    """Functions and classes that exist before and not after, by qualified name (a move is not a removal) and by unit id."""
    def names(analysis: Analysis) -> tuple[set, set]:
        rows = [("function", r["qualname"], r["unit_id"]) for r in analysis.table("functions.csv")]
        rows += [("class", r["qualname"], r["unit_id"]) for r in analysis.table("classes.csv")]
        return {(k, q) for k, q, _ in rows}, {u for _, _, u in rows}
    kinds_before, ids_before = names(before)
    kinds_after, ids_after = names(after)
    removed = sorted(kinds_before - kinds_after)
    added = sorted(kinds_after - kinds_before)
    return {"units_before": len(kinds_before), "units_after": len(kinds_after), "removed_by_name": len(removed),
            "added_by_name": len(added), "removed_by_id": len(ids_before - ids_after), "added_by_id": len(ids_after - ids_before),
            "removed_share_pct": round(100 * len(removed) / len(kinds_before), 4) if kinds_before else None,
            "removed": [f"{k} {q}" for k, q in removed[:LIST_LIMIT]], "added": [f"{k} {q}" for k, q in added[:LIST_LIMIT]]}


# --- decisions ----------------------------------------------------------------------------------------------------

def criterion(name: str, ok, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def verdict(criteria: list[dict]) -> dict:
    values = [c["ok"] for c in criteria]
    value = False if False in values else (None if None in values else True)
    return {"value": value, "criteria": criteria,
            "reasons": [f"{c['name']}: {c['detail']}" for c in criteria if c["ok"] is not True]}


def test_criterion(tests: dict | None, require_both_sets: bool) -> dict:
    if tests is None:
        return criterion("tests", None, "tests were not compared")
    if tests["regression_count"]:
        return criterion("tests", False, f"{tests['regression_count']} regression(s) ({tests['regressions_confirmed']} confirmed, "
                         f"{tests['regressions_unconfirmed']} not confirmed by two repetitions)")
    if require_both_sets and tests["sets_not_run"]:
        return criterion("tests", None, f"set(s) not run after refactoring: {', '.join(tests['sets_not_run'])}")
    note = "" if tests["repetitions_given"] >= 2 or not tests["recovered_in_repeat"] else " (repetitions incomplete)"
    return criterion("tests", True, "no regression" + note)


def decide(primary: dict, reference: dict, invalid: list[str], tests: dict | None, openapi: dict) -> tuple[dict, dict]:
    """``round_accepted`` and ``run_successful``.

    ``primary`` compares with the starting result, ``reference`` with the previous best (the starting result if
    there is none). A decision is ``false`` as soon as one criterion fails, ``true`` only if every criterion was
    checked and passed, otherwise ``null``.
    """
    if openapi["checked"]:
        api_ok = not openapi["changed"]
        api_detail = "OpenAPI schema unchanged" if api_ok else "OpenAPI schema changed" + (
            f" ({openapi['error']})" if openapi.get("error") else "")
    else:
        api_ok, api_detail = None, "OpenAPI hash not checked (no --before-code / --after-code)"
    api_c = criterion("openapi", api_ok, api_detail)
    valid = criterion("valid", not invalid, "all primary metrics measured" if not invalid else
                      f"primary metric(s) null after refactoring: {', '.join(invalid)}")

    worse_ref = [m for m, v in reference.items() if v["status"] == "worse"]
    round_accepted = verdict([
        valid, test_criterion(tests, False),
        criterion("primary metrics not worse than the previous best", not worse_ref,
                  "none worse" if not worse_ref else f"worse: {', '.join(worse_ref)}"),
        api_c])
    worse = [m for m, v in primary.items() if v["status"] == "worse"]
    better = [m for m, v in primary.items() if v["status"] == "improved"]
    run_successful = verdict([
        valid, test_criterion(tests, True),
        criterion("no primary metric worse", not worse, "none worse" if not worse else f"worse: {', '.join(worse)}"),
        criterion("at least one primary metric improved", bool(better), f"improved: {', '.join(better) or 'none'}"),
        api_c])
    return round_accepted, run_successful


# --- output -------------------------------------------------------------------------------------------------------

def fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def delta_of(before, after):
    if before is None or after is None:
        return None
    d = dec(after) - dec(before)
    return int(d) if isinstance(before, int) and isinstance(after, int) else float(d)


def csv_rows(before: Analysis, after: Analysis, primary: dict, tests: dict | None) -> list[dict]:
    rows = [{"kind": "primary", "scope": "project", "metric": m, "before": v["before"], "after": v["after"],
             "delta": v["delta"], "threshold": v["threshold"], "status": v["status"]} for m, v in primary.items()]
    ids = sorted(set(before.summary["smell_counts"]) | set(after.summary["smell_counts"]))
    for s in ids:
        b, a = before.summary["smell_counts"].get(s), after.summary["smell_counts"].get(s)
        rows.append({"kind": "smell", "scope": s, "metric": "count", "before": b, "after": a, "delta": delta_of(b, a)})
    secondary_b = {r["metric"]: number(r["value"]) for r in before.table("project.csv") if r["kind"] == "secondary"}
    secondary_a = {r["metric"]: number(r["value"]) for r in after.table("project.csv") if r["kind"] == "secondary"}
    for m in sorted(set(secondary_b) | set(secondary_a)):
        b, a = secondary_b.get(m), secondary_a.get(m)
        rows.append({"kind": "secondary", "scope": "project", "metric": m, "before": b, "after": a, "delta": delta_of(b, a)})
    mods_b = {r["module_no"]: r for r in before.table("modules.csv")}
    mods_a = {r["module_no"]: r for r in after.table("modules.csv")}
    for key in sorted(set(mods_b) | set(mods_a), key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else 0, k)):
        for m in MODULE_METRICS:
            b = number(mods_b.get(key, {}).get(m))
            a = number(mods_a.get(key, {}).get(m))
            if b is not None or a is not None:
                rows.append({"kind": "module", "scope": key, "metric": m, "before": b, "after": a, "delta": delta_of(b, a)})
    lev_b = {(r["level"], r["aggregation"]): r for r in before.table("levels.csv")}
    lev_a = {(r["level"], r["aggregation"]): r for r in after.table("levels.csv")}
    for key in sorted(set(lev_b) | set(lev_a)):
        for m in ("mean_cc", "mean_cognitive", "mi_weighted", "smells_per_ksloc", "duplication_pct"):
            b, a = number(lev_b.get(key, {}).get(m)), number(lev_a.get(key, {}).get(m))
            if b is not None or a is not None:
                rows.append({"kind": "level", "scope": f"{key[0]} ({key[1]})", "metric": m, "before": b, "after": a,
                             "delta": delta_of(b, a)})
    if tests:
        for s, info in tests["sets"].items():
            for m in ("before_passed", "after_passed", "regressions", "new_passing", "lost", "new_cases"):
                rows.append({"kind": "tests", "scope": s, "metric": m, "before": None, "after": info[m], "delta": None})
    return rows


def write_outputs(out: Path, report: dict, rows: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.json").write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out / "compare.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow([fmt(row.get(c)) for c in CSV_COLUMNS])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two analyzer results (ADR 003).")
    parser.add_argument("--before", type=Path, required=True, help="analysis folder of the starting code")
    parser.add_argument("--after", type=Path, required=True, help="analysis folder of the refactored code")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tests-before", type=Path)
    parser.add_argument("--tests-after", type=Path)
    parser.add_argument("--tests-after-repeat", type=Path, action="append", default=[],
                        help="tests.csv of a repetition of the failing cases (give it twice)")
    parser.add_argument("--flaky", type=Path, help="list of flaky case IDs, left out of the comparison")
    parser.add_argument("--previous-best", type=Path, help="analysis folder of the best accepted result so far")
    parser.add_argument("--before-code", type=Path, help="folder with the starting lms/")
    parser.add_argument("--after-code", type=Path, help="folder with the refactored lms/")
    args = parser.parse_args(argv)

    if bool(args.tests_before) != bool(args.tests_after):
        print("--tests-before and --tests-after go together", file=sys.stderr)
        return 2
    if bool(args.before_code) != bool(args.after_code):
        print("--before-code and --after-code go together", file=sys.stderr)
        return 2
    if args.tests_after_repeat and not args.tests_after:
        print("--tests-after-repeat needs --tests-before and --tests-after", file=sys.stderr)
        return 2
    try:
        report = {"compare_version": COMPARE_VERSION, "status": "ok"}
        return _compare(args, report)
    except Stop as stop:
        failure = {"compare_version": COMPARE_VERSION, "status": {2: "usage", 3: "incompatible inputs", 4: "missing data"}[stop.code],
                   "reason": stop.message}
        if stop.code != 2:
            write_outputs(args.out, failure, [])
        print(f"compare: {stop.message}", file=sys.stderr)
        return stop.code


def _compare(args, report: dict) -> int:
    before, after = Analysis(args.before), Analysis(args.after)
    check_compatible(before, after, "before and after")
    best = Analysis(args.previous_best) if args.previous_best else None
    if best:
        check_compatible(best, after, "previous best and after")
    warnings: list[str] = []
    if before.summary.get("tool_versions") != after.summary.get("tool_versions"):
        warnings.append("tool versions differ between before and after")
    if before.summary.get("image_id") != after.summary.get("image_id"):
        warnings.append("Docker image IDs differ between before and after")

    primary = primary_table(before.summary, after.summary)
    broken = [m for m, v in primary.items() if v["status"] == "not comparable"]
    if broken:
        raise Stop(4, f"primary metric(s) null in the starting result: {', '.join(broken)}")
    invalid = [m for m, v in primary.items() if v["status"] == "invalid"]
    reference = primary_table(best.summary, after.summary) if best else primary
    if best and any(v["status"] == "not comparable" for v in reference.values()):
        raise Stop(4, "primary metric(s) null in the previous best result")

    tests = None
    if args.tests_before:
        repeats = [read_tests(p) for p in args.tests_after_repeat]
        tests = compare_tests(read_tests(args.tests_before), read_tests(args.tests_after), repeats, read_flaky(args.flaky))
        if len(repeats) == 1 or (not repeats and tests["regression_count"]):
            warnings.append("regressions are not confirmed: D18 needs two repetitions of the failing tests")

    openapi = {"checked": False, "changed": None, "before_hash": None, "after_hash": None, "error": None}
    change = None
    if args.before_code:
        for folder in (args.before_code, args.after_code):
            if not (folder / "lms").is_dir():
                raise Stop(2, f"no lms/ package in {folder}")
        h_before, err_before = openapi_hash(args.before_code)
        if h_before is None:
            raise Stop(4, f"OpenAPI schema of the starting code cannot be built: {err_before}")
        h_after, err_after = openapi_hash(args.after_code)
        openapi = {"checked": True, "before_hash": h_before, "after_hash": h_after, "error": err_after,
                   "changed": h_after != h_before}      # code that cannot build its schema counts as changed
        change = change_size(args.before_code, args.after_code)

    sloc_b, sloc_a = before.summary.get("secondary", {}).get("sloc"), after.summary.get("secondary", {}).get("sloc")
    drop = round(100 * (sloc_b - sloc_a) / sloc_b, 4) if sloc_b and sloc_a is not None else None
    sloc = {"before": sloc_b, "after": sloc_a, "drop_pct": drop, "warning_above_pct": SLOC_DROP_WARNING,
            "warning": bool(drop is not None and drop > SLOC_DROP_WARNING)}
    if sloc["warning"]:
        warnings.append(f"SLOC dropped by {drop} % (more than {SLOC_DROP_WARNING} %): check that no behavior was deleted")
    if before.summary.get("secondary", {}).get("module_stats_valid") is False or \
            after.summary.get("secondary", {}).get("module_stats_valid") is False:
        warnings.append("module-level statistics are invalid in one of the results (more than 5 % unassigned SLOC)")

    round_accepted, run_successful = decide(primary, reference, invalid, tests, openapi)

    smell_counts = {s: {"before": before.summary["smell_counts"].get(s), "after": after.summary["smell_counts"].get(s)}
                    for s in sorted(set(before.summary["smell_counts"]) | set(after.summary["smell_counts"]))}
    report.update({
        "before": before.info(), "after": after.info(), "previous_best": best.info() if best else None,
        "primary": primary, "primary_vs_previous_best": reference if best else None, "invalid": invalid,
        "smell_counts": smell_counts, "tests": tests, "openapi": openapi, "inventory": inventory(before, after),
        "sloc": sloc, "change_size": change, "round_accepted": round_accepted, "run_successful": run_successful,
        "warnings": warnings,
    })
    write_outputs(args.out, report, csv_rows(before, after, primary, tests))
    print(f"round_accepted={round_accepted['value']} run_successful={run_successful['value']} "
          + " ".join(f"{m}:{v['status']}" for m, v in primary.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
