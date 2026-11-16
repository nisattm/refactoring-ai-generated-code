"""Running the external tools: one function, raw output saved, failures as ``ToolFailure``."""

from __future__ import annotations

import importlib.metadata as md
import os
import subprocess
import time
from pathlib import Path


class ToolFailure(Exception):
    """A tool did not run, or did not process the files it should have (ADR 003, D13). Exit code 4."""

    def __init__(self, tool: str, reason: str, kind: str = "tool", files: list[str] | None = None):
        super().__init__(f"{tool}: {reason}")
        self.tool = tool
        self.reason = reason
        self.kind = kind          # "tool" (did not run) or "fileset" (processed != expected)
        self.files = files or []


def command(tool: str) -> str:
    """Executable of a tool; ``ANALYZER_CMD_<TOOL>`` overrides it (used by the tests)."""
    return os.environ.get(f"ANALYZER_CMD_{tool.upper()}", tool)


def run(tool: str, args: list[str], cwd: Path, raw: Path, name: str, timings: dict, ok_codes: set[int] | None = None):
    """Run ``tool`` with ``args``; save stdout and stderr to ``raw/<name>.out|err``."""
    cmd = [command(tool), *args]
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False)
    except OSError as exc:
        raise ToolFailure(tool, f"cannot run {cmd[0]!r}: {exc}") from exc
    timings[name] = round(time.perf_counter() - started, 2)
    (raw / f"{name}.out").write_text(proc.stdout, encoding="utf-8")
    (raw / f"{name}.err").write_text(proc.stderr, encoding="utf-8")
    if ok_codes is not None and proc.returncode not in ok_codes:
        last = (proc.stderr.strip().splitlines() or [""])[-1]
        raise ToolFailure(tool, f"exit code {proc.returncode}: {last}")
    return proc


def versions() -> dict:
    """Versions of the measurement tools (``tool_versions.json``)."""
    import sys

    def dist(name: str) -> str | None:
        try:
            return md.version(name)
        except md.PackageNotFoundError:
            return None

    jscpd = None
    try:
        jscpd = subprocess.run([command("jscpd"), "--version"], capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        pass
    return {
        "python": sys.version.split()[0],
        "radon": dist("radon"), "complexipy": dist("complexipy"), "ruff": dist("ruff"),
        "pylint": dist("pylint"), "vulture": dist("vulture"), "code-quality-analyzer": dist("code-quality-analyzer"),
        "jscpd": jscpd or None,
    }
