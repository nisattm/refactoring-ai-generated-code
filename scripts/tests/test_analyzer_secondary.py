"""Secondary results of the analyzer (ADR 003): layer violations, R0401 cross-check, D22 static cases, Vulture, PyExamine.

Most tests run without the measurement tools; the last ones use the sample project and need the Docker image.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "analyzer" / "sample"
sys.path.insert(0, str(SCRIPTS))

from analyzer import collect, secondary, workspace  # noqa: E402
from analyzer.astscan import scan_files  # noqa: E402
from analyzer.collect import Finding  # noqa: E402
from analyzer.graph import build as build_graph  # noqa: E402
from analyzer.mapping import Mapping  # noqa: E402
from analyzer.tools import ToolFailure  # noqa: E402


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = root / "lms" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(text), encoding="utf-8")
    return root / "lms"


def scanned(tmp_path: Path, files: dict[str, str]):
    pkg = write_tree(tmp_path, files)
    return scan_files(pkg, sorted(files))


# --- layer violations -----------------------------------------------------------------------------------------

def test_layer_rule_1_api_reaches_persistence(tmp_path):
    scan = scanned(tmp_path, {
        "api/a.py": """
            from lms.catalog.models import Book, Copy
            from lms.catalog import models
            import lms.members.models
            from sqlalchemy.orm import Session
            import sqlalchemy as sa
            from lms.core.db import get_session
            from lms.catalog.service import find
            from fastapi import APIRouter
        """})
    rows = secondary.layer_violations(scan)
    assert [r["rule"] for r in rows] == ["api_persistence"] * 5
    assert [r["line"] for r in rows] == [2, 3, 4, 5, 6]                    # get_session and services are not violations


def test_layer_rule_2_nothing_below_the_api_imports_it(tmp_path):
    scan = scanned(tmp_path, {
        "__init__.py": "from lms.api.app import build\n",                        # the root assembles the app: allowed
        "loans/service.py": "from lms.api.errors import ApiError\nimport lms.api\n",
        "core/x.py": "from lms import api\n",
        "api/app.py": "from lms.api import errors\n"})                          # inside the API layer: allowed
    rows = secondary.layer_violations(scan)
    assert [(r["rule"], r["path"]) for r in rows] == [
        ("domain_imports_api", "core/x.py"), ("domain_imports_api", "loans/service.py"),
        ("domain_imports_api", "loans/service.py")]


def test_layer_rule_3_core_does_not_import_domain_at_module_level(tmp_path):
    scan = scanned(tmp_path, {
        "core/db.py": """
            from lms.core import clock
            from lms.loans import models
            import lms.auth.models

            def create_schema():
                import lms.catalog.models
                from lms.members import models as member_models
        """,
        "core/clock.py": ""})
    rows = secondary.layer_violations(scan)
    assert [(r["rule"], r["line"]) for r in rows] == [("core_imports_domain", 3), ("core_imports_domain", 4)]


def test_relative_imports_are_not_layer_violations(tmp_path):
    scan = scanned(tmp_path, {"api/a.py": "from .models import X\nfrom .. import api\n"})
    assert secondary.layer_violations(scan) == []


# --- R0401 against S18 -----------------------------------------------------------------------------------------

def graph_of(tmp_path, files):
    scan = scanned(tmp_path, files)
    return build_graph("lms", sorted(files), scan.imports)


def test_r0401_agrees_with_the_components(tmp_path):
    graph = graph_of(tmp_path, {"__init__.py": "", "a.py": "from lms import b\n", "b.py": "from lms import a\n", "c.py": ""})
    findings = [Finding("pylint", "R0401", "a.py", 1, "Cyclic import (lms.a -> lms.b)")]
    check = secondary.r0401_check(findings, graph)
    assert check == {"pylint_messages": 1, "pylint_files_in_cycles": 2, "our_files_in_cycles": 2, "agree": True}


def test_r0401_disagrees_when_only_one_side_sees_a_cycle(tmp_path):
    graph = graph_of(tmp_path, {"__init__.py": "", "a.py": "from lms import b\n", "b.py": "", "c.py": ""})
    assert secondary.r0401_check([], graph)["agree"] is True
    findings = [Finding("pylint", "R0401", "a.py", 1, "Cyclic import (lms.a -> lms.c)")]
    assert secondary.r0401_check(findings, graph)["agree"] is False
    assert secondary.r0401_check(None, graph) is None


# --- static cases of D22 ----------------------------------------------------------------------------------------

PINS = "fastapi==0.162.0\nuvicorn==0.54.0\npydantic==2.14.2\nsqlalchemy==2.1.6\nhttpx==0.28.1\npytest==9.2.0\nhypothesis==6.170.13\n"


def test_requirements_must_hold_the_seven_pins_exactly(tmp_path):
    (tmp_path / "requirements.txt").write_text(PINS + "annotated-types==0.8.0\nSQLAlchemy_x==1.0\n", encoding="utf-8")
    assert secondary._check_requirements(tmp_path)["result"] == "passed"
    (tmp_path / "requirements.txt").write_text(PINS.replace("2.14.2", "2.14.3") + "click>=8\n", encoding="utf-8")
    row = secondary._check_requirements(tmp_path)
    assert row["result"] == "failed" and "pydantic: 2.14.3 instead of 2.14.2" in row["detail"] and "not an exact pin: click>=8" in row["detail"]
    (tmp_path / "requirements.txt").write_text(PINS.replace("httpx==0.28.1\n", ""), encoding="utf-8")
    assert "httpx: missing" in secondary._check_requirements(tmp_path)["detail"]
    (tmp_path / "requirements.txt").unlink()
    assert secondary._check_requirements(tmp_path)["result"] == "failed"


def test_layout_lists_missing_module_packages(tmp_path):
    mapping = Mapping()
    pkg = write_tree(tmp_path, {"__init__.py": "", **{f"{d}/__init__.py": "" for d in
                                                    ("core", "auth", "members")}})
    ws = workspace.build(pkg)
    try:
        row = secondary._check_layout(ws, mapping)
    finally:
        ws.close()
    assert row["result"] == "failed" and "printing" in row["detail"] and "core" not in row["detail"].split(": ")[1].split(", ")


def test_layout_passes_with_all_29_packages(tmp_path):
    mapping = Mapping()
    dirs = sorted({p.rstrip("/") for p, _ in mapping.rows if p.endswith("/")})
    pkg = write_tree(tmp_path, {"__init__.py": "", **{f"{d}/__init__.py": "" for d in dirs}})
    ws = workspace.build(pkg)
    try:
        assert secondary._check_layout(ws, mapping) == {
            "case": "T-TECH-11-a", "requirement": "LIB-TECH-11", "result": "passed", "detail": f"{len(dirs)} module packages found"}
    finally:
        ws.close()
    assert len(dirs) == 29


def test_sync_check_finds_async_routes_and_async_sqlalchemy(tmp_path):
    ok = scanned(tmp_path / "ok", {"api/a.py": "async def helper():\n    return 1\n\n@router.get('/x')\ndef route():\n    return 1\n"})
    row = secondary._check_sync(ok)
    assert row["result"] == "passed" and "async helper" in row["detail"]
    bad = scanned(tmp_path / "bad", {
        "api/a.py": "@router.get('/x')\nasync def route():\n    return 1\n",
        "core/db.py": "from sqlalchemy.ext.asyncio import AsyncSession\nfrom sqlalchemy.ext.asyncio import create_async_engine as c\n"})
    row = secondary._check_sync(bad)
    assert row["result"] == "failed" and "async route handler api/a.py::route" in row["detail"] and "core/db.py:1" in row["detail"]


def test_randomness_only_in_auth(tmp_path):
    counter = iter(range(100))

    def check(files):
        pkg = write_tree(tmp_path / f"case{next(counter)}", files)
        ws = workspace.build(pkg)
        try:
            return secondary._check_randomness(secondary._parse(ws))
        finally:
            ws.close()
    good = check({"auth/tokens.py": "import secrets\nimport os\n\ndef token():\n    return secrets.token_hex(8) + os.urandom(2).hex()\n",
                  "loans/s.py": "from sqlalchemy import select\n\ndef f(s):\n    return select(1).order_by(1)\n"})
    assert good["result"] == "partial" and "select calls 1, order_by calls 1" in good["detail"]
    assert check({"loans/s.py": "import random\n"})["result"] == "failed"
    assert check({"loans/s.py": "from uuid import uuid4\n", "a.py": ""})["result"] == "failed"
    assert check({"loans/s.py": "import secrets\n", "a.py": "", "b.py": ""})["result"] == "failed"
    assert check({"loans/s.py": "import os\nx = os.urandom(4)\n", "a.py": "", "b.py": "", "c.py": ""})["result"] == "failed"


def test_server_check_starts_uvicorn_with_the_factory(tmp_path):
    pytest.importorskip("uvicorn")
    app = ("async def _app(scope, receive, send):\n"
           "    if scope['type'] == 'http':\n"
           "        status = 200 if scope['path'] == '/health' else 404\n"
           "        await send({'type': 'http.response.start', 'status': status, 'headers': []})\n"
           "        await send({'type': 'http.response.body', 'body': b'{}'})\n\n"
           "def create_app():\n    return _app\n")
    pkg = write_tree(tmp_path / "good", {"__init__.py": app})
    ws = workspace.build(pkg)
    try:
        assert secondary._check_server(ws)["result"] == "passed"
    finally:
        ws.close()
    pkg = write_tree(tmp_path / "bad", {"__init__.py": "def create_app():\n    raise RuntimeError('no settings')\n"})
    ws = workspace.build(pkg)
    try:
        row = secondary._check_server(ws)
    finally:
        ws.close()
    assert row["result"] == "failed"


# --- Vulture and PyExamine collectors with fake tools ---------------------------------------------------------

def fake_tool(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def make_ws(tmp_path) -> workspace.Workspace:
    return workspace.build(write_tree(tmp_path / "src", {"__init__.py": "", "core/a.py": "x = 1\n"}))


def test_vulture_output_is_parsed_and_sorted(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    try:
        tool = fake_tool(tmp_path / "vulture", f"""
            print("{ws.pkg}/core/a.py:9: unused variable 'y' (100% confidence)")
            print("{ws.pkg}/__init__.py:3: unused import 'json' (90% confidence)")
            raise SystemExit(3)
        """)
        monkeypatch.setenv("ANALYZER_CMD_VULTURE", str(tool))
        raw = tmp_path / "raw"
        raw.mkdir()
        rows = collect.collect_vulture(ws, raw, {})
        assert [(r["path"], r["line"], r["kind"], r["confidence"]) for r in rows] == [
            ("__init__.py", 3, "unused import", 90), ("core/a.py", 9, "unused variable", 100)]
        fake_tool(tmp_path / "vulture", "print('what is this')\n")
        with pytest.raises(ToolFailure):
            collect.collect_vulture(ws, raw, {})
        fake_tool(tmp_path / "vulture", "raise SystemExit(2)\n")
        with pytest.raises(ToolFailure):
            collect.collect_vulture(ws, raw, {})
    finally:
        ws.close()


def test_pyexamine_rows_are_normalized_and_crashes_are_found(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    try:
        tool = fake_tool(tmp_path / "pyex", f"""
            import csv, sys
            out = sys.argv[sys.argv.index('--output') + 1]
            with open(out, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Type', 'Name', 'Description', 'File', 'Module/Class', 'Line Number', 'Severity'])
                w.writerow(['Code', 'Speculative Generality',
                            "Class 'K' has 3 unused parameters: source, cls, handler in {ws.pkg}/core/a.py",
                            '{ws.pkg}/core/a.py', 'K', '39', 'medium'])
                w.writerow(['Code', 'Data Clumps', 'Parameters a, b appear together',
                            '{ws.pkg}/core/a.py, {ws.pkg}/__init__.py', 'f, g', '', 'low'])
            print("2026 - ERROR - Unexpected error analyzing {ws.pkg}/core/a.py: Error in detect_middle_man: max() empty", file=sys.stderr)
        """)
        monkeypatch.setenv("ANALYZER_CMD_ANALYZE_CODE_QUALITY", str(tool))
        raw = tmp_path / "raw"
        raw.mkdir()
        data = collect.collect_pyexamine(ws, raw, {})
        assert data.crashed == {"core/a.py": "Error in detect_middle_man: max() empty"}
        first, second = data.rows
        assert first["name"] == "Data Clumps" and first["path"] == "__init__.py, core/a.py" and first["line"] is None
        assert second["description"] == "Class 'K' has 3 unused parameters: cls, handler, source in core/a.py"
        assert second["path"] == "core/a.py" and second["line"] == 39
        assert "/tmp" not in json.dumps(data.rows)
    finally:
        ws.close()


def test_pyexamine_word_lists_are_sorted():
    ws = SimpleNamespace(pkg=Path("/tmp/x/lms"))
    assert collect._normalize("has 3 different method prefixes: m3, m1, m2 in /tmp/x/lms/a.py", ws) ==         "has 3 different method prefixes: m1, m2, m3 in a.py"
    assert collect._normalize("Parameters a, b appear together across files in: g (b.py), f (a.py), h (c.py)", ws) ==         "Parameters a, b appear together across files in: f (a.py), g (b.py), h (c.py)"
    assert collect._files_cell("/tmp/x/lms/b.py, /tmp/x/lms/a.py", ws) == "a.py, b.py"
    assert collect._files_cell("api/z.py, api/a.py", ws) == "api/a.py, api/z.py"


def test_pyexamine_without_a_report_is_a_failure(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    try:
        monkeypatch.setenv("ANALYZER_CMD_ANALYZE_CODE_QUALITY", str(fake_tool(tmp_path / "pyex", "print('nothing')\n")))
        raw = tmp_path / "raw"
        raw.mkdir()
        with pytest.raises(ToolFailure):
            collect.collect_pyexamine(ws, raw, {})
    finally:
        ws.close()


# --- on the sample project (needs the Docker image) -------------------------------------------------------------

needs_tools = pytest.mark.skipif(shutil.which("ruff") is None or shutil.which("jscpd") is None,
                                 reason="measurement tools are not installed (run inside the Docker image)")


def analyze(out: Path, *extra: str, env: dict | None = None, code: Path = SAMPLE):
    return subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"), "--code", str(code), "--out", str(out), "--label", "s", *extra],
                          capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False)


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def sample_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("secondary")
    proc = analyze(out, "--with-secondary")
    assert proc.returncode == 0, proc.stderr
    return out


@needs_tools
def test_sample_secondary_files_and_summary(sample_out):
    summary = json.loads((sample_out / "summary.json").read_text(encoding="utf-8"))
    sec = summary["secondary"]
    assert sec["layer_violations"] == {"api_persistence": 0, "domain_imports_api": 0, "core_imports_domain": 0, "total": 0}
    assert sec["r0401_check"]["agree"] is True and sec["r0401_check"]["pylint_messages"] >= 1
    assert sec["pyexamine"]["rows"] >= 1 and sec["pyexamine"]["by_name"]["Long Parameter List"] == 2
    # Vulture honors `# noqa`: the suppressed `import json  # noqa: F401` of the sample is not reported
    assert sec["vulture"] == {"findings": 0, "by_kind": {}} and rows(sample_out / "vulture.csv") == []
    descriptions = " ".join(r["description"] for r in rows(sample_out / "pyexamine.csv"))
    assert "m01, m02, m03" in descriptions and "list_loans (api/loans.py), too_many (loans/service.py)" in descriptions
    assert "/tmp" not in (sample_out / "pyexamine.csv").read_text()


@needs_tools
def test_sample_static_cases(sample_out):
    cases = {r["case"]: r for r in rows(sample_out / "static_cases.csv")}
    assert {c: r["result"] for c, r in cases.items()} == {
        "T-TECH-02-a": "failed",      # the sample imports `requests`
        "T-TECH-04-a": "failed",      # no requirements.txt
        "T-TECH-06-a": "passed", "T-TECH-10-a": "partial", "T-TECH-11-a": "failed", "T-TECH-12-a": "failed"}
    assert "1 import" in cases["T-TECH-02-a"]["detail"] and "not found" in cases["T-TECH-04-a"]["detail"]


@needs_tools
def test_layer_violations_are_architecture_rows(tmp_path):
    code = tmp_path / "code"
    shutil.copytree(SAMPLE, code)
    (code / "lms" / "api" / "bad.py").write_text("from lms.loans.models import Loan\nfrom sqlalchemy.orm import Session\n", encoding="utf-8")
    out = tmp_path / "o"
    assert analyze(out, code=code).returncode == 0
    layer = [r for r in rows(out / "architecture.csv") if r["kind"].startswith("layer_violation")]
    assert [(r["kind"], r["source"], r["target"], r["value"]) for r in layer] == [
        ("layer_violation:api_persistence", "api/bad.py", "lms.loans.models", "1"),
        ("layer_violation:api_persistence", "api/bad.py", "sqlalchemy.orm", "2")]
    assert json.loads((out / "summary.json").read_text())["secondary"]["layer_violations"]["total"] == 2
    assert not (out / "vulture.csv").exists() and (out / "static_cases.csv").exists()     # no --with-secondary: no extra tools


@needs_tools
def test_a_missing_secondary_tool_does_not_change_the_exit_code(tmp_path):
    out = tmp_path / "o"
    proc = analyze(out, "--with-secondary", env={"ANALYZER_CMD_VULTURE": str(tmp_path / "no-such-vulture")})
    assert proc.returncode == 0 and "secondary problem vulture" in proc.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert [f["tool"] for f in summary["secondary_failures"]] == ["vulture"] and summary["failures"] == []
    assert summary["secondary"]["vulture"] is None and summary["primary"]["smell_count"] == 19
    assert not (out / "vulture.csv").exists() and (out / "pyexamine.csv").exists()


@needs_tools
def test_a_pyexamine_crash_is_reported_but_exit_code_stays_0(tmp_path):
    out = tmp_path / "o"
    tool = fake_tool(tmp_path / "pyex", """
        import csv, sys
        out = sys.argv[sys.argv.index('--output') + 1]
        with open(out, 'w', newline='') as handle:
            csv.writer(handle).writerow(['Type', 'Name', 'Description', 'File', 'Module/Class', 'Line Number', 'Severity'])
        print("x - ERROR - Unexpected error analyzing /anything/lms/core/util.py: boom", file=sys.stderr)
    """)
    proc = analyze(out, "--with-secondary", env={"ANALYZER_CMD_ANALYZE_CODE_QUALITY": str(tool)})
    assert proc.returncode == 0
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["secondary"]["pyexamine"]["crashed_files"] == ["/anything/lms/core/util.py"] or \
        summary["secondary"]["pyexamine"]["crashed_files"] == ["core/util.py"]
    assert summary["secondary_failures"][0]["kind"] == "fileset"
