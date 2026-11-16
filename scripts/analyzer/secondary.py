"""Secondary checks (ADR 003): layer violations, the Pylint R0401 cross-check of S18, the static cases of D22."""

from __future__ import annotations

import ast
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .astscan import ImportRow, ScanResult
from .collect import Finding
from .graph import Graph, sccs
from .mapping import Mapping
from .workspace import Workspace

# LIB-TECH-04: the seven pinned versions that must be in requirements.txt
REQUIRED_PINS = {"fastapi": "0.162.0", "uvicorn": "0.54.0", "pydantic": "2.14.2", "sqlalchemy": "2.1.6",
                 "httpx": "0.28.1", "pytest": "9.2.0", "hypothesis": "6.170.13"}
ASYNC_NAMES = {"AsyncSession", "create_async_engine", "async_sessionmaker", "AsyncEngine"}
HEALTH_WAIT_S = 45


# --- layer violations ----------------------------------------------------------------------------------------

LAYER_RULES = {
    "api_persistence": "lms/api imports lms.<package>.models or sqlalchemy (the API layer reaches the database layer)",
    "domain_imports_api": "a domain package or core imports lms.api",
    "core_imports_domain": "core imports a domain package at module level",
}


def _candidates(row: ImportRow) -> list[str]:
    """The dotted names one import statement refers to (``from lms.x import y`` -> lms.x and lms.x.y)."""
    if row.level:
        return []
    if row.module:
        return [row.module, *[f"{row.module}.{n}" for n in row.names if n != "*"]]
    return list(row.names)


def layer_violations(scan: ScanResult) -> list[dict]:
    """One row per import statement and rule: (rule, path, line, target). The root ``lms/__init__.py`` builds the
    application from the API, so it is not a domain package."""
    rows = []
    for row in scan.imports:
        names = _candidates(row)
        if row.path.startswith("api/"):
            hit = next((n for n in names if (n.startswith("lms.") and n.endswith(".models"))
                        or n == "sqlalchemy" or n.startswith("sqlalchemy.")), None)
            if hit:
                rows.append({"rule": "api_persistence", "path": row.path, "line": row.lineno, "target": hit})
        elif row.path != "__init__.py":
            hit = next((n for n in names if n == "lms.api" or n.startswith("lms.api.")), None)
            if hit:
                rows.append({"rule": "domain_imports_api", "path": row.path, "line": row.lineno, "target": hit})
        if row.path.startswith("core/") and not row.in_function:
            hit = next((n for n in names if n.startswith("lms.") and n.split(".")[1] not in ("core", "api")), None)
            if hit:
                rows.append({"rule": "core_imports_domain", "path": row.path, "line": row.lineno, "target": hit})
    return sorted(rows, key=lambda r: (r["rule"], r["path"], r["line"], r["target"]))


# --- Pylint R0401 against S18 -----------------------------------------------------------------------------------

def r0401_check(pylint: list[Finding] | None, graph: Graph) -> dict | None:
    """Do Pylint's ``cyclic-import`` messages and our strongly connected components describe the same cycles?"""
    if pylint is None:
        return None
    members = {f for component in sccs(graph.edges_all) for f in component}
    messages = [f for f in pylint if f.rule == "R0401"]
    named: set[str] = set()
    for message in messages:
        found = re.search(r"\((.*)\)", message.message)
        for module in (found.group(1).split(" -> ") if found else []):
            if module.strip() in graph.file_of:
                named.add(graph.file_of[module.strip()])
    return {"pylint_messages": len(messages), "pylint_files_in_cycles": len(named), "our_files_in_cycles": len(members),
            "agree": (bool(messages) == bool(members)) and named <= members}


# --- static cases of D22 ----------------------------------------------------------------------------------------------

def _row(case: str, requirement: str, result: str, detail: str) -> dict:
    return {"case": case, "requirement": requirement, "result": result, "detail": detail}


def _check_requirements(code_dir: Path) -> dict:
    path = code_dir / "requirements.txt"
    if not path.is_file():
        return _row("T-TECH-04-a", "LIB-TECH-04", "failed", "requirements.txt not found next to lms/")
    pins: dict[str, str] = {}
    problems = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.\-]+)==(\S+)", line)
        if not match:
            problems.append(f"not an exact pin: {line}")
        else:
            pins[match[1].lower().replace("_", "-")] = match[2]
    for name, version in REQUIRED_PINS.items():
        if pins.get(name) != version:
            problems.append(f"{name}: {pins.get(name, 'missing')} instead of {version}")
    return _row("T-TECH-04-a", "LIB-TECH-04", "failed" if problems else "passed",
                "; ".join(problems) if problems else f"{len(REQUIRED_PINS)} pinned versions found, {len(pins)} pins in all")


def _parse(ws: Workspace) -> dict[str, ast.AST]:
    trees = {}
    for rel in ws.files:
        try:
            trees[rel] = ast.parse((ws.pkg / rel).read_text(encoding="utf-8"))
        except (SyntaxError, ValueError):
            continue
    return trees


def _check_sync(scan: ScanResult) -> dict:
    problems = [f"async route handler {u.path}::{u.qualname}" for u in scan.units if u.is_async and u.route_handler]
    for row in scan.imports:
        names = _candidates(row)
        if any(n.startswith("sqlalchemy.ext.asyncio") or n.rsplit(".", 1)[-1] in ASYNC_NAMES for n in names):
            problems.append(f"async SQLAlchemy import {row.path}:{row.lineno}")
    other = sorted({f"{u.path}::{u.qualname}" for u in scan.units if u.is_async and not u.route_handler})
    detail = "; ".join(problems) if problems else "no async route handler and no async SQLAlchemy import"
    if other and not problems:
        detail += f" (async helper(s) that are not routes: {len(other)})"
    return _row("T-TECH-06-a", "LIB-TECH-06", "failed" if problems else "passed", detail)


def _check_randomness(trees: dict[str, ast.AST]) -> dict:
    """Randomness only in the auth package (tokens, salts). The ORDER BY half of the case cannot be checked by a script."""
    problems = []
    for rel, tree in trees.items():
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in ("random", "uuid") or (name == "secrets" and not rel.startswith("auth/")):
                    problems.append(f"import {name} in {rel}:{node.lineno}")
            if isinstance(node, ast.Call) and not rel.startswith("auth/"):
                func = node.func
                if (isinstance(func, ast.Attribute) and func.attr == "urandom") or (isinstance(func, ast.Name) and func.id == "urandom"):
                    problems.append(f"urandom in {rel}:{node.lineno}")
    selects = sum(1 for tree in trees.values() for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and ((isinstance(n.func, ast.Name) and n.func.id == "select") or (isinstance(n.func, ast.Attribute) and n.func.attr == "select")))
    orders = sum(1 for tree in trees.values() for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "order_by")
    note = f"ORDER BY not checked by script (select calls {selects}, order_by calls {orders}: information only)"
    if problems:
        return _row("T-TECH-10-a", "LIB-TECH-10", "failed", "; ".join(sorted(set(problems))[:10]) + "; " + note)
    return _row("T-TECH-10-a", "LIB-TECH-10", "partial", "randomness only in auth/; " + note)


def _check_layout(ws: Workspace, mapping: Mapping) -> dict:
    expected = sorted({prefix.rstrip("/") for prefix, _ in mapping.rows if prefix.endswith("/")})
    missing = [d for d in expected if not (ws.pkg / d / "__init__.py").is_file()]
    return _row("T-TECH-11-a", "LIB-TECH-11", "failed" if missing else "passed",
                f"missing package(s): {', '.join(missing)}" if missing else f"{len(expected)} module packages found")


def _check_server(ws: Workspace) -> dict:
    """Start ``uvicorn lms:create_app --factory`` with the default Settings and ask ``/health``."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ws.pkg.parent), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "lms:create_app", "--factory", "--host", "127.0.0.1",
                             "--port", str(port)], cwd=ws.run_dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    status, detail = None, "server did not answer"
    deadline = time.monotonic() + HEALTH_WAIT_S
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                detail = "server exited: " + ((proc.stderr.read() or "").strip().splitlines() or ["no output"])[-1]
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                    status = response.status
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if status == 200:
        return _row("T-TECH-12-a", "LIB-TECH-12", "passed", "GET /health returned 200")
    return _row("T-TECH-12-a", "LIB-TECH-12", "failed", detail if status is None else f"GET /health returned {status}")


def static_cases(code_dir: Path, ws: Workspace, scan: ScanResult, mapping: Mapping, s22_count: int | None,
                 parsed: bool) -> list[dict]:
    """The six static cases a script can check (LIB-TECH-02, -04, -06, -10, -11, -12); ``partial`` = only the scripted part."""
    rows = [_check_requirements(code_dir), _check_layout(ws, mapping)]
    if parsed:
        rows += [_row("T-TECH-02-a", "LIB-TECH-02", "passed" if s22_count == 0 else "failed",
                      "no import outside the allowed libraries" if s22_count == 0 else f"{s22_count} import(s) outside the allowed libraries"),
                 _check_sync(scan), _check_randomness(_parse(ws)), _check_server(ws)]
    else:
        rows += [_row(c, r, "not checked", "a file cannot be parsed") for c, r in
                 (("T-TECH-02-a", "LIB-TECH-02"), ("T-TECH-06-a", "LIB-TECH-06"), ("T-TECH-10-a", "LIB-TECH-10"),
                  ("T-TECH-12-a", "LIB-TECH-12"))]
    return sorted(rows, key=lambda r: r["case"])
