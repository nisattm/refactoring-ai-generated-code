"""Unit tests of the analyzer without the external tools: mapping, AST scan, graph, workspace (ADR 003)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from analyzer import graph as graph_mod  # noqa: E402
from analyzer import workspace  # noqa: E402
from analyzer.astscan import resolve_class_relations, scan_files  # noqa: E402
from analyzer.mapping import Mapping  # noqa: E402


def scan(tmp_path: Path, files: dict[str, str]):
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(text), encoding="utf-8")
    result = scan_files(tmp_path, sorted(files))
    resolve_class_relations(result.classes)
    return result


# --- mapping (D2, D3) ------------------------------------------------------------------------------------------

def test_mapping_prefixes_and_levels():
    m = Mapping()
    assert m.assign("__init__.py").no == 1
    assert m.assign("core/db.py").no == 1 and m.assign("core/db.py").level == "simple"
    assert m.assign("api/reports.py").no == 14                      # api/ is entirely module 14
    assert m.assign("printing/jobs.py").no == 29
    assert m.assign("search/query.py").level == "simple"
    assert m.assign("notifications/x.py").level == "medium"
    assert m.assign("rooms/bookings.py").level == "complex"
    assert m.assign("newfolder/x.py") is None                       # unassigned
    assert m.assign("loans_extra/x.py") is None                     # a prefix must end at the folder boundary


def test_mapping_has_29_modules_with_the_level_split_of_the_dataset():
    m = Mapping()
    levels = {n: mod.level for n, mod in m.modules.items()}
    assert sorted(levels) == list(range(1, 30))
    assert sorted(n for n, lv in levels.items() if lv == "simple") == [1, 9]
    assert sorted(n for n, lv in levels.items() if lv == "medium") == [8, 10, 11, 12, 14]
    assert sum(1 for lv in levels.values() if lv == "complex") == 22


def test_mapping_router_view():
    m = Mapping()
    assert m.assign_with_router("api/calendar.py")[0] == "1"
    assert m.assign_with_router("api/users.py")[0] == "2"
    assert m.assign_with_router("api/transfers.py")[0] == "11"
    assert m.assign_with_router("api/dataexchange.py")[0] == "13"
    assert m.assign_with_router("api/reports.py")[0] == "api/reports.py"        # a row of its own
    assert m.assign_with_router("api/app.py")[0] == "14"
    assert m.assign_with_router("nope/x.py")[0] == "unassigned"


# --- AST scan (D4, D12, D15) -----------------------------------------------------------------------------------

def test_unit_identity_ignores_line_numbers_and_counts_same_names(tmp_path):
    source = """
        def f():
            return 1

        def g():
            def inner():
                return 2
            return inner

        class A:
            def f(self):
                return 3

        def f():          # a second definition with the same name
            return 4
    """
    first = scan(tmp_path / "one", {"m.py": source})
    shifted = scan(tmp_path / "two", {"m.py": "# comment\n\n\n" + textwrap.dedent(source)})
    ids = [u.id for u in first.units]
    assert ids == [u.id for u in shifted.units]
    assert "m.py::f::function::1" in ids and "m.py::f::function::2" in ids
    assert "m.py::g.<locals>.inner::function::1" in ids and "m.py::A.f::method::1" in ids
    assert {u.id for u in first.units if u.nested} == {"m.py::g.<locals>.inner::function::1"}


def test_nesting_depth_does_not_count_elif_as_deeper(tmp_path):
    result = scan(tmp_path, {"m.py": """
        def flat(x):
            if x == 1:
                return 1
            elif x == 2:
                return 2
            elif x == 3:
                return 3
            else:
                return 4

        def deep(x):
            for i in x:
                while i:
                    try:
                        with open(i) as f:
                            return f
                    except OSError:
                        pass
    """})
    depth = {u.name: u.nesting for u in result.units}
    assert depth == {"flat": 1, "deep": 4}


def test_parameters_and_route_handler_flag(tmp_path):
    result = scan(tmp_path, {"m.py": """
        @router.get("/x")
        def route(a, b, *args, c=1, **kw):
            return a

        class K:
            def method(self, a):
                return a

            @staticmethod
            def static(a, b):
                return a
    """})
    by_name = {u.name: u for u in result.units}
    assert by_name["route"].params == 5 and by_name["route"].route_handler
    assert by_name["method"].params == 1 and not by_name["method"].route_handler      # self is not counted
    assert by_name["static"].params == 2


def test_function_length_and_sloc_leave_out_the_docstring(tmp_path):
    result = scan(tmp_path, {"m.py": '''
        def f():
            """One.

            Two.
            """
            # a comment

            x = 1
            return x
    '''})
    unit = result.units[0]
    assert unit.lines == 9 and unit.doc_lines == 4 and unit.sloc == 3        # def line, x = 1, return x


def test_class_kinds_dit_noc_cbo_lcom4(tmp_path):
    result = scan(tmp_path, {
        "m.py": """
            import enum
            from pydantic import BaseModel
            from sqlalchemy.orm import DeclarativeBase

            class Base(DeclarativeBase):
                pass

            class Row(Base):
                pass

            class Color(enum.Enum):
                RED = 1

            class Item(BaseModel):
                name: str

            class Special(Item):
                pass

            class Plain:
                def __init__(self):
                    self.a = 1
                    self.b = 2

                def one(self):
                    return self.a

                def two(self):
                    return self.a + 1

                def three(self):
                    return self.b

                def four(self):
                    return Row()
        """})
    classes = {c.name: c for c in result.classes}
    assert {n: c.kind for n, c in classes.items()} == {
        "Base": "orm", "Row": "orm", "Color": "enum", "Item": "schema", "Special": "schema", "Plain": "plain"}
    assert classes["Base"].dit == 1 and classes["Row"].dit == 2 and classes["Special"].dit == 2
    assert classes["Base"].noc == 1 and classes["Item"].noc == 1 and classes["Plain"].noc == 0
    assert classes["Plain"].nom == 5
    # __init__ shares a and b with one/two/three, so only four() is left alone: two components
    assert classes["Plain"].lcom4 == 2
    assert classes["Plain"].cbo == 1                                   # names the project class Row
    assert classes["Row"].fan_in == 1


def test_suppression_comments_and_casts_are_counted(tmp_path):
    result = scan(tmp_path, {"m.py": """
        import typing
        from typing import cast

        a = cast(int, 1)  # noqa: F401
        b = typing.cast(int, 2)  # type: ignore
        c = 3  # pylint: disable=invalid-name
        d = 4  # not a suppression
    """})
    sup = result.files["m.py"].suppressions
    assert sup == {"noqa": 1, "type_ignore": 1, "pylint_disable": 1, "jscpd_ignore": 0}
    assert len(result.casts) == 2


def test_unparsable_file_is_recorded(tmp_path):
    result = scan(tmp_path, {"bad.py": "def (:\n", "good.py": "x = 1\n"})
    assert result.files["bad.py"].parse_error and result.files["good.py"].parse_error is None


# --- import graph (S18, S22) -----------------------------------------------------------------------------------

def make_graph(tmp_path, files):
    result = scan(tmp_path, files)
    names = sorted(files)
    return result, graph_mod.build("lms", names, result.imports)


def test_cycles_with_and_without_function_level_imports(tmp_path):
    result, g = make_graph(tmp_path, {
        "__init__.py": "",
        "a.py": "from lms import b\n",
        "b.py": "def f():\n    from lms import a\n    return a\n",
        "c.py": "from lms import d\n",
        "d.py": "from lms import c\n",
    })
    assert graph_mod.sccs(g.edges_all) == [["a.py", "b.py"], ["c.py", "d.py"]]
    assert graph_mod.sccs(g.edges_module) == [["c.py", "d.py"]]


def test_relative_imports_and_fan(tmp_path):
    result, g = make_graph(tmp_path, {
        "__init__.py": "",
        "pkg/__init__.py": "",
        "pkg/x.py": "from . import y\nfrom .. import top\n",
        "pkg/y.py": "",
        "top.py": "",
    })
    # `from . import y` also imports the package pkg/__init__.py, `from .. import top` also lms/__init__.py
    assert g.edges_all["pkg/x.py"] == {"pkg/y.py", "pkg/__init__.py", "top.py", "__init__.py"}
    fans = graph_mod.fan(g)
    assert fans["pkg/y.py"] == (1, 0) and fans["top.py"][0] == 1


def test_external_imports_use_real_import_nodes_only(tmp_path):
    result, g = make_graph(tmp_path, {"m.py": '''
        import os
        import json as j
        import requests
        from numpy.linalg import norm
        from fastapi import APIRouter
        from starlette.requests import Request
        import pydantic_core
        from lms.core import x
        from . import sibling

        TEXT = "import notreal"         # a string, not an import
        # import commented
    '''})
    found = sorted(top for _, _, top in graph_mod.external_imports(result.imports))
    assert found == ["numpy", "requests"]


# --- workspace (D1, D24) ---------------------------------------------------------------------------------------

def make_lms(root: Path, crlf: bool = False) -> Path:
    pkg = root / "lms"
    for rel, text in {
        "__init__.py": "x = 1\n", "core/a.py": "y = 2\n", "core/test_a.py": "z = 3\n", "conftest.py": "",
        "web/w.py": "w = 1\n", "tests/t.py": "t = 1\n", "core/__pycache__/a.cpython-314.pyc.py": "",
    }.items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode())
    return pkg


def test_workspace_excludes_by_d1_and_normalizes_line_endings(tmp_path):
    lf = workspace.build(make_lms(tmp_path / "lf"))
    crlf = workspace.build(make_lms(tmp_path / "crlf", crlf=True))
    try:
        assert lf.files == ["__init__.py", "core/a.py"]
        assert lf.excluded == ["conftest.py", "core/test_a.py", "tests/t.py", "web/w.py"]
        assert lf.content_hash == crlf.content_hash                       # CRLF and LF checkouts give one hash
        assert (crlf.pkg / "core" / "a.py").read_bytes() == b"y = 2\n"
        assert not (lf.pkg / "web").exists()
    finally:
        lf.close()
        crlf.close()


def test_content_hash_changes_with_the_content(tmp_path):
    pkg = make_lms(tmp_path)
    one = workspace.build(pkg)
    (pkg / "core" / "a.py").write_text("y = 3\n", encoding="utf-8")
    two = workspace.build(pkg)
    try:
        assert one.content_hash != two.content_hash
    finally:
        one.close()
        two.close()


@pytest.mark.parametrize("name", ["modules.csv", "api_routers.csv", "pylintrc", "schema.json"])
def test_analyzer_data_files_exist(name):
    assert (SCRIPTS / "analyzer" / name).is_file()
