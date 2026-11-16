"""Clean copy of ``lms/`` in a neutral folder, file inventory, hashes, git information (ADR 003, D1, D24)."""

from __future__ import annotations

import fnmatch
import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import EXCLUDED_DIRS, EXCLUDED_FILE_PATTERNS


@dataclass
class Workspace:
    root: Path                 # temporary folder, removed by ``close``
    pkg: Path                  # root/code/lms: the clean copy that is measured
    run_dir: Path              # root/run: neutral working folder for the tools
    files: list[str]           # measured files, relative to lms/ (posix), sorted
    excluded: list[str]        # files left out by D1
    content_hash: str
    file_hashes: dict[str, str] = field(default_factory=dict)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _is_excluded(rel: Path) -> bool:
    if EXCLUDED_DIRS.intersection(rel.parts[:-1]):
        return True
    return any(fnmatch.fnmatch(rel.name, pattern) for pattern in EXCLUDED_FILE_PATTERNS)


def build(source: Path) -> Workspace:
    """Copy the ``.py`` files of ``source`` (the ``lms`` package) into a temporary folder.

    Line endings are normalized to LF so that a Windows checkout (CRLF) and a Linux one give the same
    hash and the same tool output. Nothing else of the project (config files, ``.gitignore``,
    ``sitecustomize.py``) is copied, so it cannot influence a tool.
    """
    root = Path(tempfile.mkdtemp(prefix="analyzer-"))
    pkg = root / "code" / source.name
    run_dir = root / "run"
    pkg.mkdir(parents=True)
    run_dir.mkdir()
    files: list[str] = []
    excluded: list[str] = []
    hashes: dict[str, str] = {}
    for path in sorted(source.rglob("*.py")):
        rel = path.relative_to(source)
        if "__pycache__" in rel.parts:
            continue
        if _is_excluded(rel):
            excluded.append(rel.as_posix())
            continue
        data = path.read_bytes().replace(b"\r\n", b"\n")
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append(rel.as_posix())
        hashes[rel.as_posix()] = hashlib.sha256(data).hexdigest()
    combined = hashlib.sha256("".join(f"{hashes[f]}  {f}\n" for f in sorted(hashes)).encode()).hexdigest()
    return Workspace(root, pkg, run_dir, sorted(files), sorted(excluded), combined, hashes)


def git_info(folder: Path) -> dict:
    """Commit SHA and dirty flag of the git repository that contains ``folder`` (``None`` if there is none)."""
    def git(*args: str) -> str | None:
        try:
            # core.autocrlf: a Windows checkout has CRLF files, which would otherwise all look modified
            proc = subprocess.run(["git", "-c", "safe.directory=*", "-c", "core.autocrlf=true", "-C", str(folder), *args],
                                  capture_output=True, text=True, check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return proc.stdout.strip() if proc.returncode == 0 else None

    sha = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--", ".") if sha else None
    last_change = git("log", "-1", "--format=%H", "--", ".") if sha else None
    return {"sha": sha, "dirty": bool(status) if status is not None else None, "last_change_sha": last_change or None}
