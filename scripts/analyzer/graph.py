"""Import graph at file level: edges, strongly connected components (S18), fan-in / fan-out, S22 imports."""

from __future__ import annotations

from dataclasses import dataclass, field

from .astscan import ImportRow
from .config import ALLOWED_THIRD_PARTY, STDLIB


def module_name(pkg: str, rel: str) -> str:
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([pkg, *parts])


@dataclass
class Graph:
    pkg: str
    module_of: dict[str, str]                                   # file -> module name
    file_of: dict[str, str]                                     # module name -> file
    edges_all: dict[str, set[str]] = field(default_factory=dict)       # every import, function-level included
    edges_module: dict[str, set[str]] = field(default_factory=dict)    # module-level imports only
    import_counts: dict[tuple[str, str], int] = field(default_factory=dict)


def _resolve(name: str, file_of: dict[str, str]) -> str | None:
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in file_of:
            return file_of[candidate]
        parts.pop()
    return None


def build(pkg: str, files: list[str], imports: list[ImportRow]) -> Graph:
    module_of = {f: module_name(pkg, f) for f in files}
    file_of = {m: f for f, m in module_of.items()}
    graph = Graph(pkg, module_of, file_of, {f: set() for f in files}, {f: set() for f in files})
    for row in imports:
        if row.path not in module_of:
            continue
        own = module_of[row.path]
        if row.level:
            package = own if row.path.endswith("__init__.py") else own.rsplit(".", 1)[0]
            base = package.split(".")
            base = base[:len(base) - (row.level - 1)] if row.level > 1 else base
            root = ".".join(base + ([row.module] if row.module else []))
            candidates = [f"{root}.{n}" for n in row.names] + [root]
        elif row.module:
            candidates = [f"{row.module}.{n}" for n in row.names] + [row.module]
        else:
            candidates = list(row.names)
        for candidate in candidates:
            target = _resolve(candidate, file_of)
            if target and target != row.path:
                graph.edges_all[row.path].add(target)
                graph.import_counts[(row.path, target)] = graph.import_counts.get((row.path, target), 0) + 1
                if not row.in_function:
                    graph.edges_module[row.path].add(target)
    return graph


def sccs(edges: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components of size > 1 (Tarjan), members sorted, components sorted."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []
    counter = [0]

    def visit(start: str) -> None:
        work = [(start, iter(sorted(edges.get(start, ()))))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter[0]
                    counter[0] += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(edges.get(child, ())))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    found.append(sorted(component))

    for node in sorted(edges):
        if node not in index:
            visit(node)
    return sorted(found)


def package_edges(graph: Graph) -> dict[str, set[str]]:
    """Module-level imports between top-level packages (secondary cycle view)."""
    top = lambda f: f.split("/")[0] if "/" in f else "(root)"  # noqa: E731
    result: dict[str, set[str]] = {}
    for src, targets in graph.edges_module.items():
        result.setdefault(top(src), set())
        for dst in targets:
            if top(dst) != top(src):
                result[top(src)].add(top(dst))
                result.setdefault(top(dst), set())
    return result


def fan(graph: Graph) -> dict[str, tuple[int, int]]:
    """File -> (fan-in, fan-out): distinct files that import it / that it imports."""
    fan_in = dict.fromkeys(graph.edges_all, 0)
    for targets in graph.edges_all.values():
        for target in targets:
            fan_in[target] += 1
    return {f: (fan_in[f], len(graph.edges_all[f])) for f in graph.edges_all}


def external_imports(imports: list[ImportRow]) -> list[tuple[str, int, str]]:
    """(file, line, top-level package) of every real import outside the allowed libraries (S22)."""
    found = []
    for row in imports:
        if row.level:
            continue
        tops = [n.split(".")[0] for n in row.names] if not row.module else [row.module.split(".")[0]]
        for top in tops:
            if top not in STDLIB and top not in ALLOWED_THIRD_PARTY:
                found.append((row.path, row.lineno, top))
    return found
