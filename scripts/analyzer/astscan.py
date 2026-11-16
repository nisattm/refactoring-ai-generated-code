"""Own AST script: units, class metrics, imports, ``cast(`` calls, suppression comments.

Everything that Radon, complexipy, Ruff, Pylint and jscpd do not give us (ADR 003, D8, D12, D15).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    ENUM_ROOTS, LARGE_CLASS_METHODS, LONG_FUNCTION_LINES, ORM_ROOTS, ROUTE_METHODS, SCHEMA_ROOTS,
    SUPPRESSION_PATTERNS,
)

_NON_CODE_TOKENS = {
    tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
    tokenize.ENCODING,
}
_NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)
_TRY_NODES = tuple(getattr(ast, name) for name in ("Try", "TryStar") if hasattr(ast, name))


@dataclass
class Unit:
    """A function or method (D15 identity: path, qualified name, kind, running number)."""
    path: str
    qualname: str
    name: str
    kind: str                 # "function" or "method"
    ordinal: int
    lineno: int               # line of ``def``
    end_lineno: int
    nested: bool              # defined inside another function
    params: int
    nesting: int
    doc_lines: int
    sloc: int
    route_handler: bool

    @property
    def id(self) -> str:
        return f"{self.path}::{self.qualname}::{self.kind}::{self.ordinal}"

    @property
    def lines(self) -> int:
        return self.end_lineno - self.lineno + 1


@dataclass
class ClassInfo:
    path: str
    qualname: str
    name: str
    ordinal: int
    lineno: int
    end_lineno: int
    bases: list[str]
    nom: int
    method_ids: list[str]
    lcom4: int
    rfc: int
    refs: set[str]
    kind: str = "plain"
    dit: int = 0
    noc: int = 0
    cbo: int = 0
    fan_in: int = 0

    @property
    def id(self) -> str:
        return f"{self.path}::{self.qualname}::class::{self.ordinal}"


@dataclass
class ImportRow:
    path: str
    lineno: int
    level: int
    module: str               # as written ("" for ``from . import x``)
    names: list[str]
    in_function: bool


@dataclass
class FileScan:
    path: str
    code_lines: int = 0
    suppressions: dict[str, int] = field(default_factory=dict)
    parse_error: str | None = None
    spans: list[tuple[int, int, str]] = field(default_factory=list)   # (start, end, qualname)


@dataclass
class ScanResult:
    files: dict[str, FileScan] = field(default_factory=dict)
    units: list[Unit] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportRow] = field(default_factory=list)
    casts: list[tuple[str, int]] = field(default_factory=list)

    def enclosing(self, path: str, line: int) -> str:
        """Name of the innermost function or class that contains ``line`` (``<module>`` if none)."""
        best = None
        for start, end, qualname in self.files[path].spans if path in self.files else []:
            if start <= line <= end and (best is None or end - start < best[0]):
                best = (end - start, qualname)
        return best[1] if best else "<module>"


def _last_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _last_name(node.value)
    return None


def _nesting_depth(body: list[ast.stmt], depth: int = 0) -> int:
    """Deepest level of nested compound blocks; ``elif`` is not one level deeper; nested defs are separate units."""
    deepest = depth
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(stmt, _NESTING_NODES):
            inner = depth + 1
            deepest = max(deepest, inner)
            blocks: list[list[ast.stmt]] = []
            if isinstance(stmt, ast.If):
                blocks.append(stmt.body)
                orelse = stmt.orelse
                while len(orelse) == 1 and isinstance(orelse[0], ast.If):     # elif chain: same level
                    blocks.append(orelse[0].body)
                    orelse = orelse[0].orelse
                if orelse:
                    blocks.append(orelse)
            elif isinstance(stmt, _TRY_NODES):
                blocks += [stmt.body, *[h.body for h in stmt.handlers], stmt.orelse, stmt.finalbody]
            elif isinstance(stmt, ast.Match):
                blocks += [case.body for case in stmt.cases]
            else:
                blocks += [stmt.body, getattr(stmt, "orelse", [])]
            for block in blocks:
                deepest = max(deepest, _nesting_depth(block, inner))
    return deepest


def _docstring_node(node: ast.AST) -> ast.Expr | None:
    body = getattr(node, "body", None)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[0]
    return None


class _Scanner(ast.NodeVisitor):
    def __init__(self, path: str, code_lines: set[int], result: ScanResult, scan: FileScan):
        self.path = path
        self.code_lines = code_lines
        self.result = result
        self.scan = scan
        self.stack: list[tuple[str, str]] = []        # ("class" | "function", qualname)
        self.ordinals: dict[tuple[str, str], int] = {}

    def _qualname(self, name: str) -> str:
        if not self.stack:
            return name
        kind, parent = self.stack[-1]
        return f"{parent}.{name}" if kind == "class" else f"{parent}.<locals>.{name}"

    def _ordinal(self, qualname: str, kind: str) -> int:
        key = (qualname, kind)
        self.ordinals[key] = self.ordinals.get(key, 0) + 1
        return self.ordinals[key]

    @staticmethod
    def _span(node: ast.AST) -> tuple[int, int]:
        decorators = [d.lineno for d in getattr(node, "decorator_list", [])]
        return min([node.lineno, *decorators]), node.end_lineno

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        in_class = bool(self.stack) and self.stack[-1][0] == "class"
        kind = "method" if in_class else "function"
        qualname = self._qualname(node.name)
        args = node.args
        names = [a.arg for a in (*args.posonlyargs, *args.args)]
        count = len(names) + len(args.kwonlyargs) + (1 if args.vararg else 0) + (1 if args.kwarg else 0)
        if in_class and names and names[0] in ("self", "cls"):
            count -= 1
        doc = _docstring_node(node)
        doc_lines = (doc.end_lineno - doc.lineno + 1) if doc else 0
        doc_range = set(range(doc.lineno, doc.end_lineno + 1)) if doc else set()
        sloc = sum(1 for n in range(node.lineno, node.end_lineno + 1) if n in self.code_lines and n not in doc_range)
        handler = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_METHODS
                      for d in node.decorator_list)
        unit = Unit(self.path, qualname, node.name, kind, self._ordinal(qualname, kind), node.lineno, node.end_lineno,
                    any(k == "function" for k, _ in self.stack), count, _nesting_depth(node.body), doc_lines, sloc,
                    handler)
        self.result.units.append(unit)
        self.scan.spans.append((*self._span(node), qualname))
        self.stack.append(("function", qualname))
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = self._qualname(node.name)
        self.scan.spans.append((*self._span(node), qualname))
        first_class = len(self.result.units)
        self.stack.append(("class", qualname))
        self.generic_visit(node)
        self.stack.pop()
        # direct methods = units created for the class body's own defs
        methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        ids = [u.id for u in self.result.units[first_class:] if u.kind == "method" and u.qualname.rsplit(".", 1)[0] == qualname]
        own = {m.name for m in methods}
        parent = list(range(len(methods)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        attrs: list[set[str]] = []
        called: set[str] = set()
        for index, method in enumerate(methods):
            decorators = {_last_name(d) for d in method.decorator_list}
            self_name = method.args.args[0].arg if method.args.args and "staticmethod" not in decorators else None
            used: set[str] = set()
            for sub in ast.walk(method):
                if isinstance(sub, ast.Call):
                    callee = _last_name(sub.func)
                    if callee and callee not in own:
                        called.add(callee)
                if self_name and isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) \
                        and sub.value.id == self_name:
                    used.add(sub.attr)
            attrs.append(used)
        index_by_name = {m.name: i for i, m in enumerate(methods)}
        for i, used in enumerate(attrs):
            for other_index in (index_by_name[a] for a in used if a in index_by_name):
                parent[find(i)] = find(other_index)
            for j in range(i):
                if (used - own) & (attrs[j] - own):
                    parent[find(i)] = find(j)
        lcom4 = len({find(i) for i in range(len(methods))}) if methods else 0
        refs = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        refs |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr[:1].isupper()}
        bases = [b for b in (_last_name(base) for base in node.bases) if b]
        self.result.classes.append(ClassInfo(
            self.path, qualname, node.name, self._ordinal(qualname, "class"), node.lineno, node.end_lineno, bases,
            len(methods), ids, lcom4, len(methods) + len(called), refs))

    def visit_Import(self, node: ast.Import) -> None:
        self.result.imports.append(ImportRow(self.path, node.lineno, 0, "", [a.name for a in node.names],
                                             any(k == "function" for k, _ in self.stack)))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.result.imports.append(ImportRow(self.path, node.lineno, node.level, node.module or "",
                                             [a.name for a in node.names], any(k == "function" for k, _ in self.stack)))

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "cast") or (
                isinstance(func, ast.Attribute) and func.attr == "cast"
                and isinstance(func.value, ast.Name) and func.value.id in ("typing", "t")):
            self.result.casts.append((self.path, node.lineno))
        self.generic_visit(node)


def _code_lines(source: str, tree: ast.AST) -> tuple[set[int], dict[str, int]]:
    """Lines that hold code (not blank, comment-only or docstring) and the suppression comment counts."""
    lines: set[int] = set()
    suppressions = dict.fromkeys(SUPPRESSION_PATTERNS, 0)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            for name, pattern in SUPPRESSION_PATTERNS.items():
                if re.search(pattern, token.string):
                    suppressions[name] += 1
        elif token.type not in _NON_CODE_TOKENS:
            lines.update(range(token.start[0], token.end[0] + 1))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = _docstring_node(node)
            if doc:
                lines.difference_update(range(doc.lineno, doc.end_lineno + 1))
    return lines, suppressions


def scan_files(pkg: Path, files: list[str]) -> ScanResult:
    """Scan every file; a file that cannot be parsed is recorded in ``FileScan.parse_error``."""
    result = ScanResult()
    for rel in files:
        scan = FileScan(rel)
        result.files[rel] = scan
        try:
            source = (pkg / rel).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
            code_lines, scan.suppressions = _code_lines(source, tree)
        except (SyntaxError, ValueError, tokenize.TokenError, UnicodeDecodeError) as exc:
            scan.parse_error = f"{type(exc).__name__}: {exc}"
            continue
        scan.code_lines = len(code_lines)
        _Scanner(rel, code_lines, result, scan).visit(tree)
    return result


def resolve_class_relations(classes: list[ClassInfo]) -> None:
    """Kind (orm, schema, enum, plain), DIT, NOC, CBO and class fan-in from the project's class names."""
    by_name: dict[str, list[ClassInfo]] = {}
    for cls in classes:
        by_name.setdefault(cls.name, []).append(cls)

    def candidates(name: str, origin: ClassInfo) -> list[ClassInfo]:
        found = by_name.get(name, [])
        same_file = [c for c in found if c.path == origin.path and c is not origin]
        return same_file or [c for c in found if c is not origin]

    memo: dict[str, tuple[str, int]] = {}

    def resolve(cls: ClassInfo, seen: tuple[str, ...] = ()) -> tuple[str, int]:
        if cls.id in memo:
            return memo[cls.id]
        if cls.id in seen:
            return "plain", 0
        kinds: set[str] = set()
        dit = 0
        for base in cls.bases:
            local = candidates(base, cls)
            if local:
                resolved = [resolve(c, (*seen, cls.id)) for c in local]
                kinds.add(resolved[0][0] if len({r[0] for r in resolved}) == 1 else "plain")
                dit = max(dit, 1 + max(r[1] for r in resolved))
            else:
                dit = max(dit, 1)
                if base in ENUM_ROOTS:
                    kinds.add("enum")
                elif base in ORM_ROOTS:
                    kinds.add("orm")
                elif base in SCHEMA_ROOTS:
                    kinds.add("schema")
        kind = next((k for k in ("enum", "orm", "schema") if k in kinds), "plain")
        memo[cls.id] = (kind, dit)
        return memo[cls.id]

    names = set(by_name)
    for cls in classes:
        cls.kind, cls.dit = resolve(cls)
        for base in cls.bases:
            for parent in candidates(base, cls):
                parent.noc += 1
        cls.cbo = len((cls.refs & names) - {cls.name})
    for cls in classes:
        for other in classes:
            if other is not cls and cls.name in other.refs and other.name != cls.name:
                cls.fan_in += 1


def long_functions(units: list[Unit]) -> list[Unit]:
    return [u for u in units if u.lines - u.doc_lines > LONG_FUNCTION_LINES]


def large_classes(classes: list[ClassInfo]) -> list[ClassInfo]:
    return [c for c in classes if c.kind == "plain" and c.nom > LARGE_CLASS_METHODS]
