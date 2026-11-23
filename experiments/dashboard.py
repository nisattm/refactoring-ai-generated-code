"""Experiment dashboard: a local, read-only web page that shows the Single, Iterative and Multi-Agent runs while
they run and after they finish.

    python experiments/dashboard.py [--root results/experiments] [--port 8765]

Then open http://localhost:8765. The page reloads its data every few seconds. It only reads what the engine writes
(``run.json``, the ``stream.jsonl`` of a running call, the round folders, ``.run.lock``); it never changes a file and
never talks to Claude. It listens on 127.0.0.1 only. Standard library only, so it runs on the host (Windows, macOS,
Linux) without Docker.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[1]
APPROACHES = ("single", "iterative", "multiagent")
PRIMARY = ("mean_cc", "mean_cognitive", "mi_weighted", "duplication_pct", "smell_count")
HIGHER_IS_BETTER = {"mi_weighted"}
CASES_DIR = REPO / "dataset" / "lms" / "tests" / "cases"
CASE_ID = re.compile(r"T-[A-Z0-9]+(?:-[A-Za-z0-9]+)+")
SETS = ("feedback", "heldout")
MESSAGE_CHARS = 1500
SKIP_DIRS = {"calls", "rounds", "final", "analysis", "tests", "compare", "raw", "openapi", "repeat1", "repeat2"}
TAIL_BYTES = 400_000


# --- reading the engine's files ----------------------------------------------------------------------------------

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def find_runs(root: Path) -> dict[str, Path]:
    """``key -> run folder`` for every run.json the engine wrote under ``root`` (key: path relative to root)."""
    runs: dict[str, Path] = {}
    if not root.is_dir():
        return runs
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        if "run.json" in files:
            record = read_json(Path(folder) / "run.json")
            if isinstance(record, dict) and "approach" in record and "run_id" in record:
                runs[Path(folder).relative_to(root).as_posix()] = Path(folder)
    return runs


def group_of(key: str, approach: str) -> str:
    """``pilot`` for results/experiments/pilot/<approach>/<run>, empty for the real runs."""
    parts = PurePosixPath(key).parts
    return "/".join(parts[:parts.index(approach)]) if approach in parts else ""


def tail_events(stream: Path, limit: int = 25) -> dict:
    """The last tool uses and text of a stream-json log that is still being written."""
    try:
        with stream.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return {"actions": [], "text": "", "bytes": 0}
    actions, last_text = [], ""
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                data = block.get("input") or {}
                target = data.get("file_path") or data.get("path") or data.get("pattern") or ""
                actions.append({"tool": block.get("name"), "target": short_path(str(target))})
            elif block.get("type") == "text" and (block.get("text") or "").strip():
                last_text = block["text"].strip()
    return {"actions": actions[-limit:], "text": last_text[-600:], "bytes": size}


def short_path(path: str) -> str:
    return re.sub(r"^/work/", "", path)


def rel_folder(value: str | None) -> str:
    """A measurement folder of run.json (``final\\r1`` on Windows) as a POSIX path relative to the run folder."""
    return str(value or "").replace("\\", "/").strip("/")


def repo_path(value: str | None) -> Path | None:
    """A path recorded in run.json: relative to the repository, or absolute on the computer that ran the run (early
    pilot runs). An absolute path that does not exist here is mapped to the repository from its ``results/`` part."""
    if not value:
        return None
    path = Path(str(value).replace("\\", "/"))
    if not path.is_absolute() and not re.match(r"^[A-Za-z]:/", path.as_posix()):
        return REPO / path
    if path.exists():
        return path
    parts = PurePosixPath(path.as_posix()).parts
    return REPO.joinpath(*parts[parts.index("results"):]) if "results" in parts else None


def test_modules(folder: Path) -> dict[str, str]:
    """Case ID -> module, from the tests.csv of a measurement folder."""
    path = folder / "tests" / "tests.csv"
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return {row["case"]: row.get("module", "") for row in csv.DictReader(handle)}
    except (OSError, KeyError, csv.Error):
        return {}


def read_cases_csv(path: Path) -> dict[str, dict]:
    """Case ID -> row of a tests.csv written by run_tests.py (case, module, table, type, set, result)."""
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return {row["case"]: row for row in csv.DictReader(handle) if row.get("case")}
    except (OSError, KeyError, csv.Error):
        return {}


_CATALOG: dict[str, dict] = {}


def case_catalog(cases_dir: Path = CASES_DIR) -> dict[str, dict]:
    """Case ID -> what the test checks, from the case tables ``dataset/lms/tests/cases/*.md`` (title, requirement,
    type, input, expected). Read once per folder."""
    key = str(cases_dir)
    if key in _CATALOG:
        return _CATALOG[key]
    catalog: dict[str, dict] = {}
    for md in sorted(cases_dir.glob("*.md")) if cases_dir.is_dir() else []:
        try:
            lines = md.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        title = next((line.lstrip("# ").removeprefix("Test cases: ").strip() for line in lines if line.startswith("# ")),
                     md.stem)
        for line in lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else []
            if len(cells) >= 6 and CASE_ID.fullmatch(cells[0]):
                catalog[cells[0]] = {"area": title, "requirement": cells[1], "type": cells[2], "input": cells[3],
                                     "expected": cells[4]}
    _CATALOG[key] = catalog
    return catalog


def junit_messages(folder: Path) -> dict[str, str]:
    """Case ID -> failure or error text from the JUnit reports in ``folder`` (``<set>.junit.xml``). These reports are
    not committed, so they exist only on the computer that ran the measurement."""
    messages: dict[str, str] = {}
    for name in SETS:
        path = folder / f"{name}.junit.xml"
        if not path.is_file():
            continue
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        for case in root.iter("testcase"):
            for child in case:
                if child.tag in ("failure", "error"):
                    cid = case_id_of(case.get("name") or "")
                    text = (child.get("message") or "").strip()
                    body = (child.text or "").strip()
                    if body and body not in text:
                        text = (text + "\n\n" + body).strip()
                    if cid and cid not in messages:
                        messages[cid] = text[:MESSAGE_CHARS]
                    break
    return messages


def case_id_of(test_name: str) -> str:
    """``test_t_loan_05_c[x]`` -> ``T-LOAN-05-c`` (same rule as scripts/run_tests.py)."""
    name = test_name.split("[", 1)[0]
    if not name.startswith("test_t_"):
        return name
    parts = name[len("test_t_"):].split("_")
    if parts and len(parts[-1]) == 1 and parts[-1].isalpha() and len(parts) >= 3:
        return "T-" + "-".join(p.upper() for p in parts[:-1]) + "-" + parts[-1]
    return "T-" + "-".join(p.upper() for p in parts)


def read_text(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def window_used(record: dict) -> dict:
    """5-hour window at the start (given by the operator) and after the last call (rate_limit_event)."""
    end = None
    for call in record.get("calls", []):
        info = ((call.get("rate_limit") or {}).get("rate_limit_info") or {})
        five = ((info.get("unifiedWindows") or {}).get("five_hour") or {}).get("utilization")
        if isinstance(five, (int, float)):
            end = round(five * 100, 1)
    start = record.get("window_pct_start")
    return {"start": start, "end": end,
            "used": round(end - start, 1) if isinstance(end, (int, float)) and isinstance(start, (int, float)) else None}


def metrics_of(facts: dict | None) -> dict:
    """``metric -> {after, delta, status}``; status is compare.py's verdict with its thresholds (D17)."""
    return {m: {k: (v or {}).get(k) for k in ("after", "delta", "status")}
            for m, v in ((facts or {}).get("primary") or {}).items()}


# --- one run -----------------------------------------------------------------------------------------------------

def summary(key: str, folder: Path) -> dict | None:
    record = read_json(folder / "run.json")
    if not isinstance(record, dict):
        return None
    calls, rounds = record.get("calls", []), record.get("rounds", [])
    best = record.get("best_facts") or {}
    start = record.get("baseline_primary") or {}
    deltas = {m: (best.get("primary", {}).get(m) or {}).get("delta") for m in PRIMARY}
    events = record.get("events", [])
    status = {m: (best.get("primary", {}).get(m) or {}).get("status") for m in PRIMARY}
    return {
        "key": key, "run_id": record["run_id"], "approach": record["approach"], "group": group_of(key, record["approach"]),
        "status": record.get("status"), "outcome": record.get("outcome"), "valid": record.get("valid"),
        "reasons": record.get("reasons", []), "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"), "start_ref": record.get("start_ref"),
        "start_sha": (record.get("start_sha") or "")[:12],
        "account": record.get("account"), "calls": sum(1 for c in calls if c.get("status") != "limit"),
        "rounds": len(rounds), "accepted": sum(1 for r in rounds if r.get("accepted") is True),
        "usd": round(sum(c.get("usd_diff") or 0 for c in calls), 4),
        "claude_s": round(sum(c.get("wall_s") or 0 for c in calls), 1),
        "window": window_used(record), "start_metrics": {m: start.get(m) for m in PRIMARY},
        "best_metrics": {m: (best.get("primary", {}).get(m) or {}).get("after") for m in PRIMARY},
        "deltas": deltas, "metric_status": status, "current": events[-1]["text"] if events else "",
        "regressions": best.get("regressions"), "tests_modules": record.get("tests_modules"),
    }


def detail(key: str, folder: Path) -> dict | None:
    record = read_json(folder / "run.json")
    if not isinstance(record, dict):
        return None
    out = summary(key, folder) or {}
    calls = record.get("calls", [])
    rounds = []
    for entry in record.get("rounds", []):
        facts = entry.get("facts") or {}
        mfolder = folder / (rel_folder(facts.get("folder")) or f"rounds/r{entry.get('round')}")
        modules = test_modules(mfolder) if facts.get("regression_cases") else {}
        rounds.append({
            "round": entry.get("round"), "call": entry.get("call"), "tag": entry.get("tag"),
            "source": entry.get("source"),
            "accepted": entry.get("accepted"), "status": facts.get("status"), "problems": facts.get("problems", []),
            "regressions": [{"case": c, "module": modules.get(c, "")} for c in facts.get("regression_cases", [])],
            "accept_reasons": facts.get("accept_reasons", []), "api_changed": facts.get("api_changed"),
            "api_change_kind": facts.get("api_change_kind"),
            "metrics": {m: {k: v for k, v in (val or {}).items()} for m, val in (facts.get("primary") or {}).items()},
            "feedback": read_text(mfolder / "feedback.txt"), "wall_s": facts.get("wall_s"),
        })
    final = {}
    for name, facts in (record.get("final") or {}).items():
        mfolder = folder / rel_folder(facts.get("folder"))
        modules = test_modules(mfolder) if facts.get("regression_cases") else {}
        final[name] = {"round": facts.get("round"), "run_successful": facts.get("run_successful"),
                       "reasons": facts.get("reasons", []), "metrics": metrics_of(facts),
                       "regressions": [{"case": c, "module": modules.get(c, "")} for c in facts.get("regression_cases", [])],
                       "regressions_by_set": facts.get("regressions_by_set"), "api_changed": facts.get("api_changed")}
    live = None
    if record.get("status") in ("running", "limit_cut"):
        started = [int(m.group(1)) for e in record.get("events", [])
                   if (m := re.match(r"call (\d+) \(.*\) started", e.get("text", "")))]
        running_call = max(started) if started else None
        if running_call and running_call > len(calls):
            live = {"call": running_call, **tail_events(folder / "calls" / f"call-{running_call}" / "stream.jsonl")}
        else:
            live = {"call": None, "actions": [], "text": "", "bytes": 0}
    out.update({
        "calls_detail": [{
            "number": c.get("number"), "kind": c.get("kind"), "status": c.get("status"), "invalid": c.get("invalid", []),
            "wall_s": c.get("wall_s"), "usd": c.get("usd_diff"), "turns": c.get("num_turns"),
            "files_read": len(c.get("files_read") or []), "files_written": len(c.get("files_written") or []),
            "written": [short_path(p) for p in (c.get("files_written") or [])][:60],
            "done_marker": c.get("done_marker"), "denials": c.get("permission_denials") or [],
            "subagents": c.get("subagents_spawned"), "outside": c.get("outside_lms_changes"),
        } for c in calls],
        "rounds_detail": rounds, "final": final, "events": record.get("events", [])[-60:],
        "stop_reason": record.get("stop_reason"), "best_round": record.get("best_round"),
        "best_tag": record.get("best_tag"), "tests_modules": record.get("tests_modules"),
        "model": record.get("model"), "effort": record.get("effort"), "live": live,
        "roles": record.get("roles"), "budget": record.get("budget"),
    })
    return out


def measurements(record: dict) -> list[dict]:
    """The measurement folders of a run, newest decision first: the final checks (feedback and held-out tests) and
    the round checks (feedback tests only)."""
    found: dict[str, dict] = {}
    names = {"best": "best result", "round1": "round 1", "last": "last round"}
    for name, facts in (record.get("final") or {}).items():
        folder = rel_folder(facts.get("folder"))
        if not folder:
            continue
        entry = found.setdefault(folder, {"folder": folder, "kind": "final", "round": facts.get("round"),
                                          "roles": [], "regressions": facts.get("regression_cases") or []})
        entry["roles"].append(names.get(name, name))
    for entry in record.get("rounds") or []:
        facts = entry.get("facts") or {}
        folder = rel_folder(facts.get("folder")) or f"rounds/r{entry.get('round')}"
        found.setdefault(folder, {"folder": folder, "kind": "round", "round": entry.get("round"), "roles": [],
                                  "regressions": facts.get("regression_cases") or [], "accepted": entry.get("accepted")})
    for entry in found.values():
        sets = "feedback and held-out tests" if entry["kind"] == "final" else "feedback tests"
        if entry["kind"] == "final":
            what = f"Final check of round {entry['round']}" if entry["round"] else "Final check"
        else:
            what = f"Round {entry['round']}"
        roles = f" ({', '.join(entry['roles'])})" if entry["roles"] else ""
        entry["label"] = f"{what}{roles}: {sets}"
    return sorted(found.values(), key=lambda e: (e["kind"] != "final", "best result" not in e["roles"],
                                                 -(e["round"] or 0)))


STATUS_ORDER = ("regression", "failed_unconfirmed", "missing", "still_failing", "fixed", "passed", "skipped")


def tests_view(folder: Path, measurement: str | None = None, cases_dir: Path = CASES_DIR) -> dict | None:
    """Every test case of one measurement of a run: its result at the start and after refactoring, what it checks
    and, where the JUnit report is on this computer, why it failed."""
    record = read_json(folder / "run.json")
    if not isinstance(record, dict):
        return None
    options = measurements(record)
    chosen = next((m for m in options if m["folder"] == measurement), options[0] if options else None)
    out = {"measurements": options, "selected": chosen["folder"] if chosen else None, "cases": [], "counts": {},
           "messages_here": False, "start_known": False}
    if not chosen:
        return out
    mfolder = (folder / chosen["folder"]).resolve()
    if folder.resolve() not in mfolder.parents:
        return None
    after = read_cases_csv(mfolder / "tests" / "tests.csv")
    baseline = repo_path(record.get("baseline"))
    start = read_cases_csv(baseline / "tests.csv") if baseline else {}
    flaky = set()
    if baseline and (baseline / "flaky.txt").is_file():
        flaky = {line.split()[0] for line in read_text(baseline / "flaky.txt", 200_000).splitlines()
                 if line.strip() and not line.startswith("#")}
    messages = junit_messages(mfolder / "tests")
    for name in ("repeat1", "repeat2"):
        for cid, text in junit_messages(mfolder / name).items():
            messages.setdefault(cid, text)
    regressions = set(chosen.get("regressions") or [])
    catalog = case_catalog(cases_dir)
    cases = []
    for cid, row in after.items():
        before = (start.get(cid) or {}).get("result")
        result = row.get("result") or ""
        ok_now = result == "passed"
        if cid in regressions:
            status = "regression"
        elif result == "missing":
            status = "missing"
        elif result == "skipped":
            status = "skipped"
        elif ok_now:
            status = "fixed" if before and before != "passed" else "passed"
        elif before == "passed":
            status = "failed_unconfirmed"
        else:
            status = "still_failing"
        info = catalog.get(cid, {})
        cases.append({"case": cid, "module": row.get("module", ""), "table": row.get("table", ""),
                      "type": row.get("type", ""), "set": row.get("set", ""), "start": before, "after": result,
                      "status": status, "flaky": cid in flaky, "message": messages.get(cid, ""), **info})
    cases.sort(key=lambda c: (STATUS_ORDER.index(c["status"]), c["set"], c["case"]))
    counts: dict[str, dict] = {}
    for c in cases:
        bucket = counts.setdefault(c["set"], {"total": 0, **{k: 0 for k in STATUS_ORDER}})
        bucket["total"] += 1
        bucket[c["status"]] += 1
    out.update({"cases": cases, "counts": counts, "messages_here": bool(messages) or not any(
        c["status"] in ("regression", "failed_unconfirmed", "still_failing") for c in cases), "start_known": bool(start)})
    return out


def compare_approaches(summaries: list[dict]) -> dict:
    """Per approach: runs, valid runs, successes, mean change of the primary metrics, cost, time, window."""
    table = {}
    for approach in APPROACHES:
        runs = [s for s in summaries if s["approach"] == approach and s["status"] == "finished"]
        valid = [s for s in runs if s["valid"]]
        mean = lambda values: round(sum(values) / len(values), 4) if values else None  # noqa: E731
        table[approach] = {
            "runs": len(runs), "valid": len(valid),
            "success": sum(1 for s in valid if s["outcome"] == "success"),
            "outcomes": {o: sum(1 for s in runs if s["outcome"] == o) for o in
                         ("success", "no_improvement", "no_change", "failed", "invalid", "discarded_limit")},
            # a valid run that kept no round keeps the starting code: its change is 0, not "unknown"
            "deltas": {m: mean([s["deltas"][m] if isinstance(s["deltas"].get(m), (int, float)) else 0.0
                                for s in valid if s["status"] == "finished" and (
                                    isinstance(s["deltas"].get(m), (int, float)) or not s["accepted"])])
                       for m in PRIMARY},
            "usd": mean([s["usd"] for s in valid]), "claude_min": mean([s["claude_s"] / 60 for s in valid]),
            "window_used": mean([s["window"]["used"] for s in valid if isinstance(s["window"]["used"], (int, float))]),
        }
    return table


def lock_info(lock: Path) -> dict | None:
    try:
        text = lock.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    return {"what": fields.get("what", ""), "start": fields.get("start", "")}


# --- web server --------------------------------------------------------------------------------------------------

class Dashboard:
    def __init__(self, root: Path, lock: Path, cases_dir: Path = CASES_DIR):
        self.root, self.lock, self.cases_dir = root, lock, cases_dir

    def runs(self, include: str) -> dict:
        found = find_runs(self.root)
        summaries = [s for key, folder in found.items() if (s := summary(key, folder))]
        if include == "real":
            summaries = [s for s in summaries if not s["group"]]
        elif include == "pilot":
            summaries = [s for s in summaries if s["group"]]
        summaries.sort(key=lambda s: s.get("started_at") or "", reverse=True)
        return {"runs": summaries, "compare": compare_approaches(summaries), "lock": lock_info(self.lock),
                "root": str(self.root)}

    def run(self, key: str) -> dict | None:
        folder = find_runs(self.root).get(key)
        return detail(key, folder) if folder else None

    def tests(self, key: str, measurement: str | None) -> dict | None:
        folder = find_runs(self.root).get(key)
        return tests_view(folder, measurement, self.cases_dir) if folder else None


def handler_for(board: Dashboard):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            pass

        def send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                self.send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif url.path == "/api/runs":
                data = board.runs((query.get("include") or ["all"])[0])
                self.send(200, json.dumps(data).encode("utf-8"), "application/json")
            elif url.path == "/api/tests":
                data = board.tests((query.get("key") or [""])[0], (query.get("m") or [None])[0])
                if data is None:
                    self.send(404, b'{"error": "unknown run"}', "application/json")
                else:
                    self.send(200, json.dumps(data).encode("utf-8"), "application/json")
            elif url.path == "/api/run":
                data = board.run((query.get("key") or [""])[0])
                if data is None:
                    self.send(404, b'{"error": "unknown run"}', "application/json")
                else:
                    self.send(200, json.dumps(data).encode("utf-8"), "application/json")
            else:
                self.send(404, b"not found", "text/plain")

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(REPO / "results" / "experiments"), help="folder the engine writes to")
    parser.add_argument("--lock-file", default=str(REPO / ".run.lock"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the page in the browser")
    args = parser.parse_args(argv)
    board = Dashboard(Path(args.root).resolve(), Path(args.lock_file).resolve())
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(board))
    url = f"http://localhost:{args.port}"
    print(f"Experiment dashboard on {url} (reading {board.root}); stop with Ctrl+C")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


PAGE = (Path(__file__).resolve().parent / "dashboard.html").read_text(encoding="utf-8") \
    if (Path(__file__).resolve().parent / "dashboard.html").is_file() else "<p>dashboard.html is missing</p>"

if __name__ == "__main__":
    sys.exit(main())
