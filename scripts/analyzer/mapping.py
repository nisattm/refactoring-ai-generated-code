"""File → module → level mapping (ADR 003, D2, D3): an explicit file, longest path prefix wins."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNASSIGNED = "unassigned"


@dataclass(frozen=True)
class Module:
    no: int
    name: str
    level: str


class Mapping:
    def __init__(self, modules_csv: Path = HERE / "modules.csv", routers_csv: Path = HERE / "api_routers.csv"):
        self.rows: list[tuple[str, Module]] = []
        self.modules: dict[int, Module] = {}
        with modules_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                module = Module(int(row["module_no"]), row["module_name"], row["level"])
                self.modules[module.no] = module
                self.rows.append((row["prefix"], module))
        self.rows.sort(key=lambda r: -len(r[0]))
        self.routers: dict[str, str] = {}
        with routers_csv.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                self.routers[row["api_file"]] = row["module_no"]

    def assign(self, path: str) -> Module | None:
        """Module of a path relative to ``lms/`` (``core/db.py``), or ``None`` for an unassigned file."""
        for prefix, module in self.rows:
            if prefix.endswith("/"):
                if path.startswith(prefix):
                    return module
            elif path == prefix:
                return module
        return None

    def assign_with_router(self, path: str) -> tuple[str, str, str]:
        """Secondary view "module + its own router": ``(key, name, level)``.

        ``api/<package>.py`` goes to the module of the package, ``api/reports.py`` is a row of its
        own, every other file keeps its normal module.
        """
        target = self.routers.get(path)
        if target == "reports":
            return "api/reports.py", "API router reports (module 10 and 15-28 reports)", "medium"
        if target is not None:
            module = self.modules[int(target)]
            return str(module.no), module.name, module.level
        module = self.assign(path)
        if module is None:
            return UNASSIGNED, UNASSIGNED, UNASSIGNED
        return str(module.no), module.name, module.level
