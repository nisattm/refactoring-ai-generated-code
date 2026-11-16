"""Collectors: run one tool, parse its output, check the files it processed (ADR 003, D10, D13)."""

from __future__ import annotations

import ast
import json
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .tools import ToolFailure, run
from .workspace import Workspace

PYLINTRC = Path(__file__).resolve().parent / "pylintrc"


def _rel(path: str, ws: Workspace) -> str:
    try:
        return Path(path).resolve().relative_to(ws.pkg.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _check_files(tool: str, got: set[str], expected: set[str]) -> None:
    missing = sorted(expected - got)
    if missing:
        raise ToolFailure(tool, f"{len(missing)} expected file(s) not processed", "fileset", missing)


def _json(tool: str, text: str, what: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolFailure(tool, f"{what}: output is not JSON ({exc})") from exc


# --- Radon -------------------------------------------------------------------------------------------------

@dataclass
class CcUnit:
    path: str
    name: str
    lineno: int
    endline: int
    complexity: int
    rank: str
    closure: bool


@dataclass
class RadonData:
    raw: dict[str, dict] = field(default_factory=dict)          # file -> loc, lloc, sloc, comments, multi, blank
    mi: dict[str, float] = field(default_factory=dict)
    cc: list[CcUnit] = field(default_factory=list)
    hal_file: dict[str, dict] = field(default_factory=dict)
    hal_units: dict[str, list[tuple[str, dict]]] = field(default_factory=dict)   # file -> [(name, report)] source order


def has_definition(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(tree))


def collect_radon(ws: Workspace, raw: Path, timings: dict, expected_cc: set[str]) -> RadonData:
    data = RadonData()
    expected = set(ws.files)

    def cli(args: list[str], name: str) -> dict:
        proc = run("radon", args, ws.run_dir, raw, name, timings, ok_codes={0})
        parsed = _json("radon", proc.stdout, name)
        broken = sorted(_rel(k, ws) for k, v in parsed.items() if isinstance(v, dict) and "error" in v)
        if broken:
            raise ToolFailure("radon", f"{name}: error in {len(broken)} file(s)", "fileset", broken)
        return {_rel(k, ws): v for k, v in parsed.items()}

    data.raw = cli(["raw", "-s", "-j", str(ws.pkg)], "radon_raw")
    _check_files("radon raw", set(data.raw), expected)
    mi = cli(["mi", "-j", "-s", str(ws.pkg)], "radon_mi")
    _check_files("radon mi", set(mi), expected)
    data.mi = {k: float(v["mi"]) for k, v in mi.items()}
    cc = cli(["cc", "-j", "-s", str(ws.pkg)], "radon_cc")
    _check_files("radon cc", set(cc), expected_cc)

    def flatten(path: str, blocks: list[dict], nested: bool) -> None:
        for block in blocks:
            if block["type"] in ("function", "method"):
                data.cc.append(CcUnit(path, block["name"], block["lineno"], block["endline"], int(block["complexity"]),
                                      block["rank"], nested))
                flatten(path, block.get("closures", []), True)
    for path, blocks in cc.items():
        flatten(path, blocks, False)

    # Halstead through the Python API: the command line keys functions by name and loses duplicates
    from radon.metrics import h_visit
    for rel in ws.files:
        try:
            result = h_visit((ws.pkg / rel).read_text(encoding="utf-8"))
        except Exception as exc:                                  # radon raises on code it cannot parse
            raise ToolFailure("radon hal", f"{rel}: {exc}", "fileset", [rel]) from exc
        data.hal_file[rel] = result.total._asdict()
        data.hal_units[rel] = [(name, report._asdict()) for name, report in result.functions]
    (raw / "radon_hal.json").write_text(json.dumps(
        {f: {"total": data.hal_file[f], "functions": data.hal_units[f]} for f in sorted(data.hal_file)},
        indent=1, sort_keys=True), encoding="utf-8")
    return data


# --- complexipy --------------------------------------------------------------------------------------------

@dataclass
class CogUnit:
    path: str
    name: str            # the method name without its class
    line_start: int
    line_end: int
    complexity: int


def collect_complexipy(ws: Workspace, raw: Path, timings: dict) -> list[CogUnit]:
    try:
        import complexipy
    except ImportError as exc:
        raise ToolFailure("complexipy", f"cannot import: {exc}") from exc
    units: list[CogUnit] = []
    failed: list[str] = []
    for rel in ws.files:
        try:
            result = complexipy.file_complexity(str(ws.pkg / rel))
        except ValueError:
            failed.append(rel)
            continue
        for fn in result.functions:
            units.append(CogUnit(rel, fn.name.split("::")[-1], fn.line_start, fn.line_end, int(fn.complexity)))
    if failed:
        raise ToolFailure("complexipy", f"{len(failed)} file(s) not analyzed", "fileset", sorted(failed))
    (raw / "complexipy.json").write_text(json.dumps(
        [[u.path, u.name, u.line_start, u.line_end, u.complexity] for u in units], indent=1), encoding="utf-8")
    return units


# --- Ruff --------------------------------------------------------------------------------------------------

@dataclass
class Finding:
    tool: str
    rule: str
    path: str
    line: int
    message: str


def _ruff(ws: Workspace, raw: Path, timings: dict, name: str, extra: list[str]) -> list[Finding]:
    proc = run("ruff", ["check", *config.RUFF_COMMON, *extra, str(ws.pkg)], ws.run_dir, raw, name, timings, ok_codes={0, 1})
    out = []
    broken = []
    for item in _json("ruff", proc.stdout or "[]", name):
        path = _rel(item["filename"], ws)
        if item["code"] is None:                                  # syntax error
            broken.append(path)
        else:
            out.append(Finding("ruff", item["code"], path, item["location"]["row"], item["message"]))
    if broken:
        raise ToolFailure("ruff", f"{name}: syntax error in {len(set(broken))} file(s)", "fileset", sorted(set(broken)))
    return sorted(out, key=lambda f: (f.path, f.line, f.rule))


def collect_ruff(ws: Workspace, raw: Path, timings: dict) -> dict:
    """Stable run, the preview run (PLR0916 only) and the F401 preview count; checks ``--show-files``."""
    stable = _ruff(ws, raw, timings, "ruff_stable", ["--select", config.RUFF_STABLE_SELECT])
    preview = _ruff(ws, raw, timings, "ruff_preview", ["--preview", "--select", config.RUFF_PREVIEW_SELECT])
    f401_preview = _ruff(ws, raw, timings, "ruff_f401_preview", ["--preview", "--select", "F401"])
    proc = run("ruff", ["check", "--isolated", "--no-cache", "--show-files", str(ws.pkg)], ws.run_dir, raw,
               "ruff_files", timings, ok_codes={0})
    listed = {_rel(line.strip(), ws) for line in proc.stdout.splitlines() if line.strip()}
    _check_files("ruff", listed, set(ws.files))
    return {"stable": stable, "preview": preview, "f401_preview": f401_preview}


# --- Pylint ------------------------------------------------------------------------------------------------

def collect_pylint(ws: Workspace, raw: Path, timings: dict) -> list[Finding]:
    proc = run("pylint", [f"--rcfile={PYLINTRC}", "--persistent=n", "--output-format=json2", "-j", "1", str(ws.pkg)],
               ws.run_dir, raw, "pylint", timings)
    if proc.returncode >= 32:
        raise ToolFailure("pylint", f"usage error (exit code {proc.returncode})")
    data = _json("pylint", proc.stdout, "pylint")
    broken = sorted({_rel(m["path"], ws) for m in data["messages"]
                     if m["messageId"] == "E0001" or m["messageId"].startswith("F")})
    if broken or proc.returncode & 1:
        raise ToolFailure("pylint", "fatal message or parse error", "fileset", broken)
    return sorted((Finding("pylint", m["messageId"], _rel(m["path"], ws), m["line"], m["message"])
                   for m in data["messages"]), key=lambda f: (f.path, f.line, f.rule))


# --- jscpd -------------------------------------------------------------------------------------------------

@dataclass
class Clone:
    file_a: str
    start_a: int
    end_a: int
    file_b: str
    start_b: int
    end_b: int
    lines: int
    tokens: int


@dataclass
class JscpdData:
    stats: dict
    clones: list[Clone]
    read: dict[str, tuple[int, int]]          # file -> (jscpd tokens, lines)
    warnings: dict[str, dict]


def estimated_tokens(path: Path) -> int:
    significant = {tokenize.NAME, tokenize.NUMBER, tokenize.STRING, tokenize.OP, tokenize.NEWLINE}
    with tokenize.open(path) as handle:
        return sum(1 for t in tokenize.generate_tokens(handle.readline) if t.type in significant)


def collect_jscpd(ws: Workspace, raw: Path, timings: dict) -> JscpdData:
    out_dir = raw / "jscpd"
    proc = run("jscpd", [*config.JSCPD_ARGS, "--reporters", "json,console", "--summary", "--summary-top", "100000",
                         "--no-colors", "--output", str(out_dir), str(ws.pkg)], ws.run_dir, raw, "jscpd", timings,
               ok_codes={0})
    report = out_dir / "jscpd-report.json"
    if not report.exists():
        raise ToolFailure("jscpd", "no JSON report written")
    data = _json("jscpd", report.read_text(encoding="utf-8"), "jscpd report")
    listing = proc.stdout.split("Top files:", 1)[-1].split("Top folders:", 1)[0].splitlines()[2:]
    read: dict[str, tuple[int, int]] = {}
    for line in listing:
        parts = line.split()
        if len(parts) >= 6 and parts[0].isdigit():
            read[_rel(parts[-1], ws) if Path(parts[-1]).is_absolute() else parts[-1]] = (int(parts[0]), int(parts[1]))
    estimates = {f: estimated_tokens(ws.pkg / f) for f in ws.files}
    must = {f for f, n in estimates.items() if n > config.JSCPD_MUST_READ}
    _check_files("jscpd", set(read), must)
    warnings = {f: {"estimated_tokens": n, "read_by_jscpd": f in read}
                for f, n in sorted(estimates.items()) if config.JSCPD_MAY_READ <= n <= config.JSCPD_MUST_READ}
    clones = [Clone(d["firstFile"]["name"], d["firstFile"]["start"], d["firstFile"]["end"], d["secondFile"]["name"],
                    d["secondFile"]["start"], d["secondFile"]["end"], d["lines"], d["tokens"])
              for d in data["duplicates"]]
    clones.sort(key=lambda c: (c.file_a, c.start_a, c.file_b, c.start_b))
    return JscpdData(data["statistics"]["total"], clones, read, warnings)
