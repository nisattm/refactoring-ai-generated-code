"""Aggregation: module, level and project values (ADR 003, D2, D3, D20) and the architecture rows."""

from __future__ import annotations

from collections.abc import Callable

from . import config
from .graph import Graph, sccs
from .mapping import UNASSIGNED, Mapping

Assign = Callable[[str], tuple[str, str, str]]     # path -> (key, name, level)

COMPLEX_LOW = {2, 3, 4, 5, 6, 7, 13}
COMPLEX_HIGH = set(range(15, 30))


def mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def share(values, threshold: float) -> float | None:
    values = [v for v in values if v is not None]
    return sum(1 for v in values if v > threshold) / len(values) if values else None


def stats(units: list[dict], files: list[dict], smells: list[dict], dup_lines: dict[str, int],
          read_lines: dict[str, int], smells_complete: bool) -> dict:
    cc = [u["cc"] for u in units]
    cog = [u["cognitive"] for u in units]
    sloc = sum(f["sloc"] or 0 for f in files)
    weighted = [(f["mi"], f["sloc"]) for f in files if f["mi"] is not None and f["sloc"] is not None]
    weight = sum(s for _, s in weighted)
    counted = sum(1 for s in smells if s["counted"])
    den = sum(read_lines.get(f["path"], 0) for f in files)
    num = sum(dup_lines.get(f["path"], 0) for f in files)
    cc_known = [v for v in cc if v is not None]
    cog_known = [v for v in cog if v is not None]
    return {
        "files": len(files), "sloc": sloc, "units": len(units),
        "mean_cc": mean(cc), "max_cc": max(cc_known) if cc_known else None,
        "share_cc_high": share(cc, config.CC_HIGH),
        "mean_cognitive": mean(cog), "max_cognitive": max(cog_known) if cog_known else None,
        "share_cognitive_high": share(cog, config.COGNITIVE_HIGH),
        "mi_weighted": sum(m * s for m, s in weighted) / weight if weight else None,
        "mi_mean": mean(m for m, _ in weighted),
        "smells": counted if smells_complete else None,
        "smells_per_ksloc": counted / (sloc / 1000) if smells_complete and sloc else None,
        "duplication_pct": 100 * num / den if den else None, "duplicated_lines": num,
    }


def module_rows(mapping: Mapping, assign: Assign, units: list[dict], files: list[dict], smells: list[dict],
                dup_lines: dict[str, int], read_lines: dict[str, int], smells_complete: bool, valid: bool,
                extra_groups: list[tuple[str, str, str]] | None = None) -> list[dict]:
    """One row per module (``not generated`` when it has no file) plus the ``unassigned`` row."""
    groups = [(str(m.no), m.name, m.level) for m in sorted(mapping.modules.values(), key=lambda m: m.no)]
    groups += extra_groups or []
    groups.append((UNASSIGNED, UNASSIGNED, ""))
    by_key = {key: ([], [], []) for key, _, _ in groups}
    for u in units:
        by_key.setdefault(assign(u["path"])[0], ([], [], []))[0].append(u)
    for f in files:
        by_key.setdefault(assign(f["path"])[0], ([], [], []))[1].append(f)
    for s in smells:
        by_key.setdefault(assign(s["path"])[0], ([], [], []))[2].append(s)
    rows = []
    for key, name, level in groups:
        u, f, s = by_key[key]
        status = "unassigned" if key == UNASSIGNED else ("generated" if f else "not generated")
        row = {"module_no": key, "module_name": name, "level": level, "status": status, "valid": int(valid)}
        if f:
            row.update(stats(u, f, s, dup_lines, read_lines, smells_complete))
        else:
            row.update({k: (0 if k in ("files", "sloc", "units", "duplicated_lines") else None) for k in
                        ("files", "sloc", "units", "mean_cc", "max_cc", "share_cc_high", "mean_cognitive",
                         "max_cognitive", "share_cognitive_high", "mi_weighted", "mi_mean", "smells",
                         "smells_per_ksloc", "duplication_pct", "duplicated_lines")})
            if status == "unassigned":
                row["smells"] = 0
        rows.append(row)
    return rows


LEVEL_METRICS = ("mean_cc", "mean_cognitive", "mi_weighted", "smells_per_ksloc", "duplication_pct")


def level_rows(mapping: Mapping, modules: list[dict], assign: Assign, units: list[dict], files: list[dict],
               smells: list[dict], dup_lines: dict[str, int], read_lines: dict[str, int], smells_complete: bool) -> list[dict]:
    """Level value = mean of the module values (primary); pooled units are secondary (D3)."""
    sets = [("simple", "simple", None), ("medium", "medium", None), ("complex", "complex", None),
            ("complex 2-7 and 13", "complex", COMPLEX_LOW), ("complex 15-29", "complex", COMPLEX_HIGH)]
    rows = []
    for label, level, numbers in sets:
        chosen = [m for m in modules if m["status"] == "generated" and m["level"] == level
                  and (numbers is None or int(m["module_no"]) in numbers)]
        keys = {m["module_no"] for m in chosen}
        note = "descriptive only (2 modules)" if label == "simple" else (
            "sensitivity row" if numbers else "")
        row = {"level": label, "aggregation": "module mean", "modules": len(chosen),
               "files": sum(m["files"] for m in chosen), "sloc": sum(m["sloc"] for m in chosen),
               "smells": sum(m["smells"] for m in chosen if m["smells"] is not None) if smells_complete else None,
               "note": note}
        for metric in LEVEL_METRICS:
            row[metric] = mean(m[metric] for m in chosen)
        rows.append(row)
        pooled = stats([u for u in units if assign(u["path"])[0] in keys], [f for f in files if assign(f["path"])[0] in keys],
                       [s for s in smells if assign(s["path"])[0] in keys], dup_lines, read_lines, smells_complete)
        rows.append({"level": label, "aggregation": "pooled units", "modules": len(chosen), "files": pooled["files"],
                     "sloc": pooled["sloc"], "smells": pooled["smells"], "note": note,
                     **{metric: pooled[metric] for metric in LEVEL_METRICS}})
    return rows


def architecture_rows(graph: Graph, mapping: Mapping) -> list[dict]:
    """Module dependencies (by module number), fan-in/out per module and the import cycles."""
    key = lambda path: (lambda m: str(m.no) if m else UNASSIGNED)(mapping.assign(path))  # noqa: E731
    edges: dict[tuple[str, str], int] = {}
    for (src, dst), count in graph.import_counts.items():
        a, b = key(src), key(dst)
        if a != b:
            edges[(a, b)] = edges.get((a, b), 0) + count
    rows: list[dict] = [{"kind": "module_edge", "source": a, "target": b, "value": n, "note": "imports"}
                        for (a, b), n in sorted(edges.items())]
    fan_in: dict[str, set[str]] = {}
    fan_out: dict[str, set[str]] = {}
    for a, b in edges:
        fan_out.setdefault(a, set()).add(b)
        fan_in.setdefault(b, set()).add(a)
    for module in sorted({*fan_in, *fan_out}):
        rows.append({"kind": "module_fan_in", "source": module, "target": "", "value": len(fan_in.get(module, ())), "note": ""})
        rows.append({"kind": "module_fan_out", "source": module, "target": "", "value": len(fan_out.get(module, ())), "note": ""})
    for index, members in enumerate(sccs(graph.edges_all), 1):
        rows.append({"kind": "file_cycle_all_imports", "source": str(index), "target": "", "value": len(members),
                     "note": ";".join(members)})
    for index, members in enumerate(sccs(graph.edges_module), 1):
        rows.append({"kind": "file_cycle_module_level", "source": str(index), "target": "", "value": len(members),
                     "note": ";".join(members)})
    module_graph = {k: set() for k in {*fan_in, *fan_out}}
    for a, b in edges:
        module_graph[a].add(b)
    for index, members in enumerate(sccs(module_graph), 1):
        rows.append({"kind": "module_cycle", "source": str(index), "target": "", "value": len(members),
                     "note": ";".join(members)})
    return rows
