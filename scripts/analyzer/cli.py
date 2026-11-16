"""Command line of the Code Quality Analyzer: ``python scripts/analyze.py --code <folder with lms/> --out <folder>``.

Exit codes: 0 done · 2 usage error · 4 a tool did not run or its file set did not match (the dependent
metric is ``null`` and the reason is in ``summary.json``).
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import os
import sys
import time
from pathlib import Path

from . import SCHEMA_VERSION, aggregate, build, collect, config, graph as graph_mod, report, secondary as secondary_mod, workspace
from .astscan import resolve_class_relations, scan_files
from .mapping import UNASSIGNED, Mapping
from .tools import ToolFailure, versions

HERE = Path(__file__).resolve().parent


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyze.py", description="Code Quality Analyzer for the LMS package lms/")
    parser.add_argument("--code", type=Path, required=True, help="folder that contains the lms/ package")
    parser.add_argument("--out", type=Path, required=True, help="output folder")
    parser.add_argument("--label", help="name of this measurement (written into every CSV row)")
    parser.add_argument("--with-secondary", action="store_true", help="also write the secondary views (modules_router.csv)")
    parser.add_argument("--image-id", default=os.environ.get("ANALYZER_IMAGE_ID"), help="Docker image ID to record")
    return parser


def _attempt(failures: list[ToolFailure], fn):
    try:
        return fn()
    except ToolFailure as failure:
        failures.append(failure)
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = args.code / "lms"
    if not source.is_dir() or not (source / "__init__.py").is_file():
        print(f"no lms package (lms/__init__.py) in {args.code}", file=sys.stderr)
        return 2
    started_at = dt.datetime.now(dt.timezone.utc)
    clock = time.perf_counter()
    schema = report.load_schema()
    mapping = Mapping()
    out = args.out.resolve()
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    ws = workspace.build(source.resolve())
    try:
        return _run(args, ws, mapping, schema, out, raw, started_at, clock)
    finally:
        ws.close()


def _run(args, ws, mapping: Mapping, schema: dict, out: Path, raw: Path, started_at, clock) -> int:
    failures: list[ToolFailure] = []
    timings: dict[str, float] = {}
    scan = scan_files(ws.pkg, ws.files)
    resolve_class_relations(scan.classes)
    unparsable = sorted(p for p, f in scan.files.items() if f.parse_error)
    if unparsable:
        failures.append(ToolFailure("ast", f"{len(unparsable)} file(s) cannot be parsed", "fileset", unparsable))
    graph = graph_mod.build(ws.pkg.name, ws.files, scan.imports)
    g = build.Gathered(scan, graph, failures=failures)
    if not unparsable:
        expected_cc = {u.path for u in scan.units} | {c.path for c in scan.classes}
        g.radon = _attempt(failures, lambda: collect.collect_radon(ws, raw, timings, expected_cc))
        g.cognitive = _attempt(failures, lambda: collect.collect_complexipy(ws, raw, timings))
        g.ruff = _attempt(failures, lambda: collect.collect_ruff(ws, raw, timings))
        g.pylint = _attempt(failures, lambda: collect.collect_pylint(ws, raw, timings))
        g.jscpd = _attempt(failures, lambda: collect.collect_jscpd(ws, raw, timings))

    units = build.build_units(g, mapping)
    classes = build.build_classes(g, units, mapping)
    files = build.build_files(g, ws.files, mapping)
    smells, available = build.build_smells(g, mapping)
    clones, dup_lines = build.build_duplication(g)
    read_lines = {f: lines for f, (_, lines) in g.jscpd.read.items()} if g.jscpd else {}
    complete = all(available.values())
    counted = [s for s in smells if s["counted"]]

    total_sloc = sum(f["sloc"] or 0 for f in files)
    unassigned_sloc = sum(f["sloc"] or 0 for f in files if f["module_no"] == UNASSIGNED)
    unassigned_pct = 100 * unassigned_sloc / total_sloc if total_sloc else 0.0
    valid = unassigned_pct <= config.UNASSIGNED_INVALID_PCT

    assign = lambda path: (lambda m: (str(m.no), m.name, m.level) if m else (UNASSIGNED, UNASSIGNED, ""))(mapping.assign(path))  # noqa: E731
    modules = aggregate.module_rows(mapping, assign, units, files, smells, dup_lines, read_lines, complete, valid)
    levels = aggregate.level_rows(mapping, modules, assign, units, files, smells, dup_lines, read_lines, complete)
    project = aggregate.stats(units, files, smells, dup_lines, read_lines, complete)
    architecture = aggregate.architecture_rows(graph, mapping)

    # Secondary results (ADR 003): a problem here is reported but does not change the exit code
    secondary_failures: list[ToolFailure] = []
    vulture_rows = pyexamine = None
    if args.with_secondary and not unparsable:
        vulture_rows = _attempt(secondary_failures, lambda: collect.collect_vulture(ws, raw, timings))
        pyexamine = _attempt(secondary_failures, lambda: collect.collect_pyexamine(ws, raw, timings))
        if pyexamine and pyexamine.crashed:
            secondary_failures.append(ToolFailure("pyexamine", f"a detector crashed on {len(pyexamine.crashed)} file(s) "
                                                  "although the exit code was 0", "fileset", list(pyexamine.crashed)))
    layer = secondary_mod.layer_violations(scan) if not unparsable else []
    layer_counts = collections.Counter(v["rule"] for v in layer)
    architecture += [{"kind": f"layer_violation:{v['rule']}", "source": v["path"], "target": v["target"], "value": v["line"],
                      "note": secondary_mod.LAYER_RULES[v["rule"]]} for v in layer]
    r0401 = secondary_mod.r0401_check(g.pylint, graph)

    per_id = collections.Counter(s["s_id"] for s in counted)
    smell_counts = {s: (per_id.get(s, 0) if available[s] else None) for s in config.FROZEN_IDS}
    primary = {
        "mean_cc": project["mean_cc"], "mean_cognitive": project["mean_cognitive"], "mi_weighted": project["mi_weighted"],
        "duplication_pct": g.jscpd.stats["percentage"] if g.jscpd else None,
        "smell_count": project["smells"],
    }
    if unparsable:
        primary = dict.fromkeys(primary)
        smell_counts = dict.fromkeys(smell_counts)

    static = secondary_mod.static_cases(args.code.resolve(), ws, scan, mapping, smell_counts.get("S22"), not unparsable)

    raw_by_rule = collections.Counter(f"{s['tool']}:{s['rule']}" for s in smells if s["s_id"] not in ("S01", "S02", "S18", "S22"))
    plain_classes = collections.Counter(c["class_kind"] for c in classes)
    secondary: dict = {
        "files": len(files), "files_excluded_by_d1": len(ws.excluded), "sloc": total_sloc,
        "loc": sum(f["loc"] or 0 for f in files), "cc_units": sum(1 for u in units if u["cc"] is not None),
        "cognitive_units": sum(1 for u in units if u["cognitive"] is not None), "nested_units": sum(u["nested"] for u in units),
        "classes": len(classes), "classes_by_kind": dict(sorted(plain_classes.items())),
        "mi_plain_mean": project["mi_mean"],
        "duplication_pct_union": project["duplication_pct"], "duplicated_lines_union": project["duplicated_lines"],
        "duplication_pct_of_sloc": 100 * project["duplicated_lines"] / total_sloc if total_sloc and g.jscpd else None,
        "duplicated_lines_jscpd": g.jscpd.stats["duplicatedLines"] if g.jscpd else None,
        "clones": g.jscpd.stats["clones"] if g.jscpd else None,
        "jscpd_files_read": len(g.jscpd.read) if g.jscpd else None,
        "jscpd_token_warnings": g.jscpd.warnings if g.jscpd else None,
        "suppressions": {k: sum(f[k] for f in files) for k in ("noqa", "type_ignore", "pylint_disable", "jscpd_ignore")},
        "raw_findings_by_rule": dict(sorted(raw_by_rule.items())),
        "ruff_f401_preview": sum(1 for f in g.ruff["f401_preview"] if f.rule == "F401") if g.ruff else None,
        "s03_route_handlers": sum(1 for s in counted if s["s_id"] == "S03" and s["route_handler"]),
        "s03_other": sum(1 for s in counted if s["s_id"] == "S03" and not s["route_handler"]),
        "s18_without_function_level_imports": len(graph_mod.sccs(graph.edges_module)),
        "s18_files_in_cycles": sum(len(m) for m in graph_mod.sccs(graph.edges_all)),
        "package_cycles_module_level_sizes": [len(m) for m in graph_mod.sccs(graph_mod.package_edges(graph))],
        "pylint_secondary": dict(sorted(collections.Counter(
            f.rule for f in (g.pylint or []) if f.rule != "R1702").items())),
        "not_measured": config.NOT_MEASURED,
        "modules_not_generated": [m["module_no"] for m in modules if m["status"] == "not generated"],
        "module_stats_valid": valid, "with_secondary": bool(args.with_secondary),
        "layer_violations": {"api_persistence": layer_counts["api_persistence"],
                             "domain_imports_api": layer_counts["domain_imports_api"],
                             "core_imports_domain": layer_counts["core_imports_domain"], "total": len(layer)},
        "r0401_check": r0401, "static_cases": {r["case"]: r["result"] for r in static},
        "vulture": None if vulture_rows is None else {
            "findings": len(vulture_rows), "by_kind": dict(sorted(collections.Counter(r["kind"] for r in vulture_rows).items()))},
        "pyexamine": None if pyexamine is None else {
            "rows": len(pyexamine.rows), "by_type": dict(sorted(collections.Counter(r["type"] for r in pyexamine.rows).items())),
            "by_name": dict(sorted(collections.Counter(r["name"] for r in pyexamine.rows).items())),
            "crashed_files": sorted(pyexamine.crashed)},
    }

    code_git = workspace.git_info(args.code.resolve())
    tool_versions = versions()
    label = args.label or (f"run-{code_git['sha'][:7]}" if code_git["sha"] else "run")
    duration = round(time.perf_counter() - clock, 2)
    summary = {
        "label": label,
        "primary": primary, "smell_counts": smell_counts, "secondary": secondary,
        "frozen_smell_list": config.FROZEN_SMELLS, "unassigned_sloc_pct": unassigned_pct,
        "code_sha": code_git["sha"], "code_dirty": code_git["dirty"], "code_last_change_sha": code_git["last_change_sha"],
        "code_content_hash": ws.content_hash,
        "analyzer_sha": workspace.git_info(HERE)["sha"], "analyzer_dirty": workspace.git_info(HERE)["dirty"],
        "image_id": args.image_id, "tool_versions": tool_versions, "schema_version": SCHEMA_VERSION,
        "started_at": started_at.isoformat(timespec="seconds"), "duration_s": duration, "tool_seconds": timings,
        "failures": [{"tool": f.tool, "kind": f.kind, "reason": f.reason, "files": f.files[:50]} for f in failures],
        "secondary_failures": [{"tool": f.tool, "kind": f.kind, "reason": f.reason, "files": f.files[:50]}
                               for f in secondary_failures],
    }

    project_rows = [{"metric": k, "value": v, "kind": "primary", "note": ""} for k, v in primary.items()]
    project_rows += [{"metric": f"unassigned_sloc_pct", "value": unassigned_pct, "kind": "secondary", "note": ""}]
    listed_elsewhere = {"jscpd_token_warnings", "not_measured", "modules_not_generated"}
    scalars = {**{f"smell_{k}": v for k, v in smell_counts.items()}, **{k: v for k, v in secondary.items() if k not in listed_elsewhere}}
    for metric, value in report.flatten("", scalars):
        if isinstance(value, (int, float)) and not isinstance(value, bool) or value is None:
            project_rows.append({"metric": metric, "value": value, "kind": "secondary", "note": ""})
    long_rows = []
    for u in units:
        for metric in ("cc", "cognitive", "lines", "sloc", "params", "nesting", "halstead_volume"):
            if u[metric] is not None:
                long_rows.append({"scope": "function", "unit": u["unit_id"], "metric": metric, "value": u[metric]})
    for c in classes:
        for metric in ("wmc", "nom", "cbo", "lcom4", "rfc", "dit", "noc"):
            if c[metric] is not None:
                long_rows.append({"scope": "class", "unit": c["unit_id"], "metric": metric, "value": c[metric]})
    for f in files:
        for metric in ("mi", "sloc", "loc", "fan_in", "fan_out"):
            if f[metric] is not None:
                long_rows.append({"scope": "file", "unit": f["path"], "metric": metric, "value": f[metric]})
    long_rows.sort(key=lambda r: (r["scope"], r["unit"], r["metric"]))

    for name, rows in (("functions.csv", units), ("classes.csv", classes), ("files.csv", files), ("smells.csv", smells),
                       ("duplication.csv", clones), ("modules.csv", modules), ("levels.csv", levels),
                       ("project.csv", project_rows), ("architecture.csv", architecture), ("metrics_long.csv", long_rows)):
        report.write_csv(out, name, rows, label, schema)
    report.write_csv(out, "static_cases.csv", static, label, schema)
    if vulture_rows is not None:
        report.write_csv(out, "vulture.csv", vulture_rows, label, schema)
    if pyexamine is not None:
        report.write_csv(out, "pyexamine.csv", pyexamine.rows, label, schema)
    if args.with_secondary:
        router_groups = [("api/reports.py", "API router reports (module 10 and 15-28 reports)", "medium")]

        def router_assign(path: str) -> tuple[str, str, str]:
            return mapping.assign_with_router(path)
        router = aggregate.module_rows(mapping, router_assign, units, files, smells, dup_lines, read_lines, complete,
                                       valid, router_groups)
        report.write_csv(out, "modules_router.csv", router, label, schema)
    report.write_json(out / "tool_versions.json", tool_versions)
    report.write_json(out / "summary.json", summary)

    print(f"{label}: " + ", ".join(f"{k}={'null' if v is None else round(v, 4)}" for k, v in primary.items()))
    for f in failures:
        print(f"FAILED {f.tool} ({f.kind}): {f.reason} {f.files[:5] if f.files else ''}", file=sys.stderr)
    for f in secondary_failures:
        print(f"secondary problem {f.tool} ({f.kind}): {f.reason} {f.files[:5] if f.files else ''}", file=sys.stderr)
    return 4 if failures else 0
