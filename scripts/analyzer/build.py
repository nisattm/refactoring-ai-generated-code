"""Joins the tool results into rows: functions, classes, files, smells, duplication (ADR 003, D8, D9, D15)."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .astscan import ClassInfo, ScanResult, Unit, large_classes, long_functions
from .collect import CcUnit, CogUnit, Finding, JscpdData, RadonData
from .graph import Graph, external_imports, fan, sccs
from .mapping import UNASSIGNED, Mapping
from .tools import ToolFailure


@dataclass
class Gathered:
    """What the collectors returned; ``None`` for a tool that failed."""
    scan: ScanResult
    graph: Graph
    radon: RadonData | None = None
    cognitive: list[CogUnit] | None = None
    ruff: dict | None = None
    pylint: list[Finding] | None = None
    jscpd: JscpdData | None = None
    failures: list[ToolFailure] = field(default_factory=list)


def _location(mapping: Mapping, path: str) -> dict:
    module = mapping.assign(path)
    if module is None:
        return {"module_no": UNASSIGNED, "module_name": UNASSIGNED, "level": ""}
    return {"module_no": module.no, "module_name": module.name, "level": module.level}


def build_units(g: Gathered, mapping: Mapping) -> list[dict]:
    """One row per function or method (the AST units are the master list), with CC, cognitive, Halstead."""
    cc_by_key: dict[tuple, CcUnit] = {}
    if g.radon:
        cc_by_key = {(c.path, c.name, c.lineno): c for c in g.radon.cc}
        known = {(u.path, u.name, u.lineno) for u in g.scan.units}
        stray = sorted({c.path for k, c in cc_by_key.items() if k not in known})
        lacking = sorted({u.path for u in g.scan.units if (u.path, u.name, u.lineno) not in cc_by_key})
        if stray or lacking:
            g.failures.append(ToolFailure("radon cc", "units differ from the AST units", "fileset", sorted({*stray, *lacking})))
            g.radon = None
            cc_by_key = {}
    cog_by_key = {(c.path, c.name, c.line_end): c for c in g.cognitive or []}
    hal: dict[str, dict] = {}
    if g.radon:
        for path, reports in g.radon.hal_units.items():
            top = sorted((u for u in g.scan.units if u.path == path and not u.nested), key=lambda u: u.lineno)
            if [u.name for u in top] == [n for n, _ in reports]:
                hal.update({u.id: report for u, (_, report) in zip(top, reports)})
    rows = []
    for u in sorted(g.scan.units, key=lambda u: (u.path, u.lineno, u.qualname, u.ordinal)):
        cc = cc_by_key.get((u.path, u.name, u.lineno))
        cog = cog_by_key.get((u.path, u.name, u.end_lineno))
        h = hal.get(u.id)
        rows.append({
            "unit_id": u.id, "path": u.path, "qualname": u.qualname, "kind": u.kind, "nested": int(u.nested),
            **_location(mapping, u.path), "lineno": u.lineno, "end_lineno": u.end_lineno, "lines": u.lines,
            "sloc": u.sloc, "params": u.params, "nesting": u.nesting,
            "cc": cc.complexity if cc else None, "rank": cc.rank if cc else None,
            "cognitive": cog.complexity if cog else None,
            "halstead_volume": h["volume"] if h else None, "halstead_difficulty": h["difficulty"] if h else None,
            "halstead_effort": h["effort"] if h else None, "route_handler": int(u.route_handler),
        })
    if g.cognitive is not None:
        missing = sorted({r["path"] for r in rows if r["cognitive"] is None and not r["nested"]})
        if missing:
            g.failures.append(ToolFailure("complexipy", "units without a cognitive value", "fileset", missing))
            g.cognitive = None
            for r in rows:
                r["cognitive"] = None
    return rows


def build_classes(g: Gathered, units: list[dict], mapping: Mapping) -> list[dict]:
    cc_of = {r["unit_id"]: r["cc"] for r in units}
    rows = []
    for c in sorted(g.scan.classes, key=lambda c: (c.path, c.lineno, c.qualname, c.ordinal)):
        ccs = [cc_of.get(m) for m in c.method_ids]
        rows.append({
            "unit_id": c.id, "path": c.path, "qualname": c.qualname, "class_kind": c.kind, **_location(mapping, c.path),
            "lineno": c.lineno, "end_lineno": c.end_lineno,
            "wmc": sum(ccs) if ccs and None not in ccs else (0 if not ccs else None),
            "nom": c.nom, "cbo": c.cbo, "lcom4": c.lcom4, "rfc": c.rfc, "dit": c.dit, "noc": c.noc,
            "fan_in": c.fan_in, "fan_out": c.cbo,
        })
    return rows


def build_files(g: Gathered, files: list[str], mapping: Mapping) -> list[dict]:
    fans = fan(g.graph)
    rows = []
    for path in files:
        scan = g.scan.files[path]
        raw = g.radon.raw.get(path) if g.radon else None
        hal = g.radon.hal_file.get(path) if g.radon else None
        rows.append({
            "path": path, **_location(mapping, path),
            "loc": raw["loc"] if raw else None, "lloc": raw["lloc"] if raw else None,
            "sloc": raw["sloc"] if raw else scan.code_lines, "comments": raw["comments"] if raw else None,
            "multi": raw["multi"] if raw else None, "blank": raw["blank"] if raw else None,
            "single_comments": raw["single_comments"] if raw else None,
            "mi": g.radon.mi.get(path) if g.radon else None,
            "halstead_volume": hal["volume"] if hal else None, "halstead_effort": hal["effort"] if hal else None,
            "fan_in": fans[path][0], "fan_out": fans[path][1],
            "noqa": scan.suppressions.get("noqa", 0), "type_ignore": scan.suppressions.get("type_ignore", 0),
            "pylint_disable": scan.suppressions.get("pylint_disable", 0),
            "jscpd_ignore": scan.suppressions.get("jscpd_ignore", 0),
            "parse_error": scan.parse_error or "",
        })
    return rows


def _smell_for_rule(rule: str) -> str | None:
    if rule in config.RUFF_SMELL_RULES:
        return config.RUFF_SMELL_RULES[rule]
    for prefix, s_id in config.RUFF_SMELL_PREFIXES.items():
        if rule.startswith(prefix):
            return s_id
    return None


def build_smells(g: Gathered, mapping: Mapping) -> tuple[list[dict], dict[str, bool]]:
    """Smell rows (every finding) with ``counted`` set once per (S-ID, file, unit) (D9), and which S-IDs are available."""
    scan = g.scan
    available = {s: True for s in config.FROZEN_IDS}
    ruff_failed = g.ruff is None
    for s_id in ("S03", "S07", "S09", "S11", "S19", "S20", "S21", "S23"):
        available[s_id] = not ruff_failed
    available["S10"] = g.pylint is not None
    parse_failed = any(f.parse_error for f in scan.files.values())
    for s_id in ("S01", "S02", "S18", "S22"):
        available[s_id] = not parse_failed
    available["S23"] = not ruff_failed and not parse_failed
    rows: list[dict] = []
    handler_lines = {(u.path, u.lineno) for u in scan.units if u.route_handler}

    def add(s_id: str, tool: str, rule: str, path: str, unit: str, line: int, **extra) -> None:
        rows.append({"s_id": s_id, "tool": tool, "rule": rule, "path": path, "unit": unit, "line": line,
                     **_location(mapping, path), "route_handler": extra.get("route_handler", 0)})

    if available["S01"]:
        for u in long_functions(scan.units):
            add("S01", "ast", f"{u.lines - u.doc_lines} lines", u.path, u.qualname, u.lineno)
    if available["S02"]:
        for c in large_classes(scan.classes):
            add("S02", "ast", f"{c.nom} methods", c.path, c.qualname, c.lineno)
    if g.ruff:
        for finding in [*g.ruff["stable"], *g.ruff["preview"]]:
            s_id = _smell_for_rule(finding.rule)
            if s_id:
                add(s_id, "ruff", finding.rule, finding.path, scan.enclosing(finding.path, finding.line), finding.line,
                    route_handler=int(finding.rule == "PLR0913" and (finding.path, finding.line) in handler_lines))
    if g.pylint is not None:
        for finding in g.pylint:
            if config.PYLINT_SMELL_RULES.get(finding.rule):
                add("S10", "pylint", finding.rule, finding.path, scan.enclosing(finding.path, finding.line), finding.line)
    if available["S18"]:
        for members in sccs(g.graph.edges_all):
            add("S18", "ast", f"cycle of {len(members)} files", members[0], g.graph.module_of[members[0]], 1)
        for path, line, top in external_imports(scan.imports):
            add("S22", "ast", f"import {top}", path, scan.enclosing(path, line), line)
    if not parse_failed:
        for path, line in scan.casts:
            add("S23", "ast", "cast(", path, scan.enclosing(path, line), line)
    rows.sort(key=lambda r: (r["s_id"], r["path"], r["line"], r["rule"], r["unit"]))
    seen: set[tuple] = set()
    for row in rows:
        key = (row["s_id"], row["path"], row["unit"])
        row["counted"] = int(key not in seen)
        seen.add(key)
    return rows, available


def build_duplication(g: Gathered) -> tuple[list[dict], dict[str, int]]:
    """Clone rows and the duplicated lines per file (union of the clone ranges, both sides)."""
    rows = []
    ranges: dict[str, list[tuple[int, int]]] = {}
    for index, c in enumerate(g.jscpd.clones if g.jscpd else [], 1):
        rows.append({"clone_id": index, "file_a": c.file_a, "start_a": c.start_a, "end_a": c.end_a, "file_b": c.file_b,
                     "start_b": c.start_b, "end_b": c.end_b, "lines": c.lines, "tokens": c.tokens})
        ranges.setdefault(c.file_a, []).append((c.start_a, c.end_a))
        ranges.setdefault(c.file_b, []).append((c.start_b, c.end_b))
    lines: dict[str, int] = {}
    for path, spans in ranges.items():
        covered: set[int] = set()
        for start, end in spans:
            covered.update(range(start, end + 1))
        lines[path] = len(covered)
    return rows, lines
