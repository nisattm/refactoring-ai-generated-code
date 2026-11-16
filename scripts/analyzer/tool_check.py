"""Tool check of the Code Quality Analyzer (PR 1): runs every measurement tool on a clean copy of
a package in a neutral working folder and records version, exit code, time, output size and the
number of files processed against the number expected.

    python scripts/analyzer/tool_check.py --code <folder with the package> --pkg lms --out <folder>
    python scripts/analyzer/tool_check.py --code scripts/tests/fixtures/analyzer/poscontrol --pkg pkg --out <folder> --control

Run it inside the Docker image with ``--network none``. With ``--control`` the package is the
positive-control project and the result lists how often every rule of the frozen smell list fired.
Writes ``<out>/check.json`` and the raw tool output in ``<out>/raw/`` (not committed).
Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import collections
import csv
import importlib.metadata as md
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUFF_STABLE = "PLR0913,F401,F841,SIM,PLR2004,S110,BLE001,B006,RET,ANN401,PGH003"
RUFF_PREVIEW = "PLR0916"
# jscpd reads a file only from --min-tokens (50) tokens, and counts them in its own way. Our estimate
# with the Python tokenizer (names, numbers, strings, operators, NEWLINE) can be a few tokens off, so
# a file above JSCPD_MUST_READ tokens must be in jscpd's list of read files (ADR 003, D13), and a
# file between JSCPD_MAY_READ and JSCPD_MUST_READ tokens only gives a warning.
SIGNIFICANT = {tokenize.NAME, tokenize.NUMBER, tokenize.STRING, tokenize.OP, tokenize.NEWLINE}
JSCPD_MUST_READ = 60
JSCPD_MAY_READ = 40


def run(name: str, cmd: list[str], cwd: Path, raw: Path, results: dict) -> subprocess.CompletedProcess:
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    seconds = round(time.perf_counter() - started, 2)
    (raw / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (raw / f"{name}.err").write_text(proc.stderr, encoding="utf-8")
    results[name] = {"cmd": " ".join(cmd), "exit_code": proc.returncode, "seconds": seconds,
                     "stdout_bytes": len(proc.stdout.encode()), "stderr_bytes": len(proc.stderr.encode())}
    return proc


def fileset(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def has_definition(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(tree))


def token_count(path: Path) -> int:
    with tokenize.open(path) as handle:
        return sum(1 for t in tokenize.generate_tokens(handle.readline) if t.type in SIGNIFICANT)


def rel(path: str, base: Path) -> str:
    try:
        return Path(path).resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def count_by(items, key) -> dict:
    return dict(sorted(collections.Counter(key(i) for i in items).items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code", type=Path, required=True, help="folder that contains the package")
    parser.add_argument("--pkg", default="lms", help="package folder name inside --code")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pylintrc", type=Path, default=HERE / "pylintrc")
    parser.add_argument("--control", action="store_true", help="positive-control project: count rule hits")
    args = parser.parse_args(argv)

    source = (args.code / args.pkg).resolve()
    if not source.is_dir():
        print(f"package not found: {source}", file=sys.stderr)
        return 2
    out = args.out.resolve()
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="toolcheck-"))
    code = work / "code"
    run_dir = work / "run"
    run_dir.mkdir()
    shutil.copytree(source, code / args.pkg, ignore=shutil.ignore_patterns("__pycache__"))
    pkg = code / args.pkg
    files = fileset(pkg)
    expected = {f.relative_to(pkg).as_posix() for f in files}

    res: dict = {}
    check: dict = {"package": args.pkg, "python": sys.version.split()[0], "files_expected": len(expected),
                   "tools": res, "versions": {}, "files": {}, "findings": {}}
    for dist in ("radon", "complexipy", "ruff", "pylint", "vulture", "code-quality-analyzer"):
        check["versions"][dist] = md.version(dist)
    check["versions"]["jscpd"] = subprocess.run(["jscpd", "--version"], capture_output=True, text=True).stdout.strip()

    # Radon
    p = run("radon_raw", ["radon", "raw", "-s", "-j", str(pkg)], run_dir, raw, res)
    raw_d = json.loads(p.stdout)
    p = run("radon_cc", ["radon", "cc", "-j", "-s", str(pkg)], run_dir, raw, res)
    cc_d = json.loads(p.stdout)
    p = run("radon_mi", ["radon", "mi", "-j", "-s", str(pkg)], run_dir, raw, res)
    mi_d = json.loads(p.stdout)
    p = run("radon_hal", ["radon", "hal", "-j", "-f", str(pkg)], run_dir, raw, res)
    hal_d = json.loads(p.stdout)
    with_defs = {f.relative_to(pkg).as_posix() for f in files if has_definition(f)}
    check["files"]["radon_raw"] = [len(raw_d), len(expected)]
    check["files"]["radon_mi"] = [len(mi_d), len(expected)]
    check["files"]["radon_hal"] = [len(hal_d), len(expected)]
    check["files"]["radon_cc"] = [len(cc_d), len(with_defs)]  # radon cc leaves out files without a def or class
    kinds: collections.Counter = collections.Counter()
    closures = 0

    def walk(blocks, nested):
        nonlocal closures
        for b in blocks:
            if b["type"] in ("function", "method"):
                kinds["method" if b["type"] == "method" else "function"] += 1
                closures += nested
            else:
                kinds["class"] += 1
            walk(b.get("closures", []), 1)
    for blocks in cc_d.values():
        walk([b for b in blocks], 0)
    check["findings"]["radon_cc_units"] = {
        "top_level_function_entries": kinds["function"], "top_level_method_entries": kinds["method"],
        "class_entries": kinds["class"], "closures_nested": closures,
        "units_without_closures": kinds["function"] + kinds["method"] - closures,
    }
    sloc = {rel(k, pkg): v["sloc"] for k, v in raw_d.items()}
    mi = {rel(k, pkg): v["mi"] for k, v in mi_d.items()}
    total_sloc = sum(sloc.values())
    check["findings"]["radon"] = {
        "sloc": total_sloc, "loc": sum(v["loc"] for v in raw_d.values()),
        "mi_mean": round(sum(mi.values()) / len(mi), 4) if mi else None,
        "mi_sloc_weighted": round(sum(mi[k] * sloc[k] for k in mi) / total_sloc, 4) if total_sloc else None,
        "mi_equal_100": sum(1 for v in mi.values() if v == 100),
    }

    # complexipy: Python API, one file at a time
    import complexipy
    started = time.perf_counter()
    cog = [complexipy.file_complexity(str(f)) for f in files]
    functions = [fn for c in cog for fn in c.functions]
    res["complexipy_api"] = {"cmd": "complexipy.file_complexity(<file>) per file", "exit_code": 0,
                             "seconds": round(time.perf_counter() - started, 2)}
    check["files"]["complexipy"] = [len(cog), len(expected)]
    check["findings"]["complexipy"] = {
        "units": len(functions),
        "mean": round(sum(fn.complexity for fn in functions) / len(functions), 4) if functions else None,
    }

    # Ruff: stable rules in one run, the preview rule in its own run (--preview changes F401 itself)
    common = ["--isolated", "--ignore-noqa", "--no-cache", "--output-format", "json"]
    p = run("ruff_stable", ["ruff", "check", *common, "--select", RUFF_STABLE, str(pkg)], run_dir, raw, res)
    stable = json.loads(p.stdout)
    p = run("ruff_preview", ["ruff", "check", *common, "--preview", "--select", RUFF_PREVIEW, str(pkg)], run_dir, raw, res)
    preview = json.loads(p.stdout)
    p = run("ruff_preview_all", ["ruff", "check", *common, "--preview", "--select", f"{RUFF_STABLE},{RUFF_PREVIEW}", str(pkg)],
            run_dir, raw, res)
    preview_all = json.loads(p.stdout)
    p = run("ruff_files", ["ruff", "check", "--isolated", "--no-cache", "--show-files", str(pkg)], run_dir, raw, res)
    check["files"]["ruff"] = [len([line for line in p.stdout.splitlines() if line.strip()]), len(expected)]
    fam = lambda d: "SIM" if d["code"].startswith("SIM") else "RET" if d["code"].startswith("RET") else d["code"]  # noqa: E731
    check["findings"]["ruff_stable_by_code"] = count_by(stable, lambda d: d["code"])
    check["findings"]["ruff_stable_by_family"] = count_by(stable, fam)
    check["findings"]["ruff_preview_only_PLR0916"] = len(preview)
    check["findings"]["ruff_preview_all_by_family"] = count_by(preview_all, fam)
    p = run("ruff_noqa_respected", ["ruff", "check", "--isolated", "--no-cache", "--output-format", "json", "--select", "F401", str(pkg)],
            run_dir, raw, res)
    check["findings"]["ruff_F401_without_ignore_noqa"] = len(json.loads(p.stdout))

    # Pylint
    p = run("pylint", ["pylint", f"--rcfile={args.pylintrc}", "--persistent=n", "--output-format=json2", "-j", "1", str(pkg)],
            run_dir, raw, res)
    pyl = json.loads(p.stdout)
    check["findings"]["pylint_by_message"] = count_by(pyl["messages"], lambda m: f'{m["messageId"]} {m["symbol"]}')
    # Pylint gives no list of the modules it processed (json2 and --verbose were tried), and
    # ``modulesLinted`` is files + 3 (it changes with new packages), so the check is: no fatal
    # message, no parse error (E0001) and no fatal bit in the exit code.
    broken = [m for m in pyl["messages"] if m["messageId"] == "E0001" or m["messageId"].startswith("F")]
    check["files"]["pylint_fatal_or_parse_errors"] = [len(broken) + (1 if p.returncode & 1 else 0), 0]
    check["findings"]["pylint_modules_linted_info"] = pyl["statistics"]["modulesLinted"]
    check["findings"]["pylint_modules_with_messages"] = len({m["path"] for m in pyl["messages"]})

    # Vulture
    run("vulture", ["vulture", "--min-confidence", "80", str(pkg)], run_dir, raw, res)
    check["findings"]["vulture_80"] = len([ln for ln in (raw / "vulture.out").read_text().splitlines() if ln.strip()])

    # jscpd: files of fewer than 50 tokens are not read
    # ``--summary`` with the console reporter lists every file jscpd read, with its own token count
    p = run("jscpd", ["jscpd", "--min-lines", "5", "--min-tokens", "50", "--pattern", "**/*.py", "--no-gitignore",
                      "--reporters", "json,console", "--summary", "--summary-top", "100000", "--no-colors",
                      "--output", str(raw / "jscpd"), str(pkg)], run_dir, raw, res)
    report = json.loads((raw / "jscpd" / "jscpd-report.json").read_text(encoding="utf-8"))
    total = report["statistics"]["total"]
    listing = p.stdout.split("Top files:", 1)[-1].split("Top folders:", 1)[0].splitlines()[2:]
    read = {line.split()[-1]: int(line.split()[0]) for line in listing if line.strip()}
    counts = {f.relative_to(pkg).as_posix(): token_count(f) for f in files}
    must = {f for f, n in counts.items() if n > JSCPD_MUST_READ}
    check["files"]["jscpd"] = [len(must & set(read)), len(must)]
    check["findings"]["jscpd_files_read"] = [len(read), total["sources"]]
    check["findings"]["jscpd_warnings"] = {
        f: {"estimated_tokens": n, "read_by_jscpd": f in read, "jscpd_tokens": read.get(f)}
        for f, n in sorted(counts.items()) if JSCPD_MAY_READ <= n <= JSCPD_MUST_READ}
    check["findings"]["jscpd"] = {"clones": total["clones"], "duplicated_lines": total["duplicatedLines"],
                                  "lines": total["lines"], "percentage": round(total["percentage"], 4)}

    # PyExamine: bundled thresholds file given explicitly; it exits 0 even when a detector crashed
    # (importing the package would create code_analysis.log in the current folder, so it is only located)
    spec = importlib.util.find_spec("code_quality_analyzer")
    config = Path(spec.submodule_search_locations[0]) / "code_quality_config.yaml"
    csv_path = raw / "pyexamine.csv"
    p = run("pyexamine", ["analyze_code_quality", str(pkg), "--config", str(config), "--output", str(csv_path)],
            run_dir, raw, res)
    crashed = sorted({rel(m, pkg) for m in re.findall(r"Unexpected error analyzing (\S+?):", p.stderr)})
    rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8")))) if csv_path.exists() else []
    # The CSV lists only files that have a finding and the log names no processed files, so the only
    # coverage check is: no detector crashed (0 crashed files expected).
    seen = {rel(r["File"], pkg) for r in rows if r.get("File")}
    check["files"]["pyexamine_crashed_files"] = [len(crashed), 0]
    check["findings"]["pyexamine_files_with_findings"] = len(seen)
    check["findings"]["pyexamine"] = {"rows": len(rows), "by_type": count_by(rows, lambda r: r["Type"]),
                                      "silent_crashes_exit_code_0": len(crashed), "crashed_files": crashed}

    if args.control:
        s = check["findings"]
        stable_codes = s["ruff_stable_by_code"]
        pylint_msgs = s["pylint_by_message"]
        hit = lambda n: n > 0  # noqa: E731
        check["control"] = {
            "S03 PLR0913": stable_codes.get("PLR0913", 0), "S07 F401": stable_codes.get("F401", 0),
            "S07 F841": stable_codes.get("F841", 0), "S09 PLR0916 (preview)": s["ruff_preview_only_PLR0916"],
            "S09 SIM": s["ruff_stable_by_family"].get("SIM", 0),
            "S10 R1702": pylint_msgs.get("R1702 too-many-nested-blocks", 0),
            "S11 PLR2004": stable_codes.get("PLR2004", 0), "S19 S110": stable_codes.get("S110", 0),
            "S19 BLE001": stable_codes.get("BLE001", 0), "S20 B006": stable_codes.get("B006", 0),
            "S21 RET": s["ruff_stable_by_family"].get("RET", 0), "S23 ANN401": stable_codes.get("ANN401", 0),
            "S23 PGH003": stable_codes.get("PGH003", 0),
            "secondary W0718": pylint_msgs.get("W0718 broad-exception-caught", 0),
            "secondary R1710": pylint_msgs.get("R1710 inconsistent-return-statements", 0),
            "secondary W0101": pylint_msgs.get("W0101 unreachable", 0),
            "cross-check R0401": pylint_msgs.get("R0401 cyclic-import", 0),
            "jscpd clones": s["jscpd"]["clones"],
            "F401 only with --ignore-noqa": stable_codes.get("F401", 0) - s["ruff_F401_without_ignore_noqa"],
        }
        check["control_passed"] = all(hit(v) for k, v in check["control"].items())

    verdicts = {name: (got == want) for name, (got, want) in check["files"].items()}
    check["files_match"] = verdicts
    (out / "check.json").write_text(json.dumps(check, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({"files_match": verdicts, "control_passed": check.get("control_passed")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
