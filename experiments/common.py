"""Shared engine of the Week 5 experiments (ADR 004, W1-W16): the model's workspace, the measurement tree, the
Claude Code call with its checks, the measurement, the run lock, the tags and the records.

``run_single.py`` and ``run_iterative.py`` are thin loops on top of this module; ``measure.py`` is the measurement
step that runs inside the Docker image (network off). Only the standard library is used here, so the engine runs on
the host (Windows Git Bash, macOS, Linux) and starts one container per step.

Layout of one run (``<out-root>/<approach>/<run-id>/``, default ``results/experiments``)::

    run.json            steps, times, decisions, code hashes, image, version, account label (written after every step)
    state.json          iterative and multi-agent: what is needed to continue after a usage-limit cut (W6)
    calls/call-N/       prompt.md, stream.jsonl, stderr.txt of every Claude Code call (raw/ is not committed)
    rounds/rK/          measurement of round K (analysis/, tests/, repeat1/, repeat2/, compare/, measure.json)
    final/rK/           full measurement (both test sets) of the reported rounds (iterative)

The work folder (``--work-root``, a temporary folder by default) is outside the repository::

    start/dataset/lms/generated   the starting project (git archive of the start ref)
    model/                        what the model sees (W3): lms/, requirements.txt, INTERFACE.md
    state.git/                    git history of model/ (one commit per round), kept outside model/
    session/                      CLAUDE_CONFIG_DIR of the run (one session folder per run, W9)
    tests/, test-hashes.json      the tests of the run (module subset) and their hashes
    measure/rK/                   measurement tree: the starting project with only lms/ replaced
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import getpass
import hashlib
import io
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

EXPERIMENTS = Path(__file__).resolve().parent
REPO = EXPERIMENTS.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cost  # noqa: E402
import test_hashes  # noqa: E402
from analyzer import baseline as baseline_steps  # noqa: E402

GENERATED = "dataset/lms/generated"
DEFAULT_TESTS = "dataset/lms/tests"
DEFAULT_IMAGE = "refactoring-env"
MODEL = cost.MODEL

# --- W9: Claude Code settings. Update from results/check/week5/flags.md (Işıl) -----------------------------------
TOOLS = ("Read", "Edit", "Write", "Glob", "Grep")   # offered with --tools and permitted with --allowedTools
DISALLOWED_TOOLS = ("Task", "Agent")
FIXED_FLAGS = ("--safe-mode", "--permission-mode", "dontAsk", "--output-format", "stream-json", "--verbose")
CLAUDE_ENV = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}
# The context size at which Claude Code compacts its conversation; its value is a run option (--compact-window), so it
# is added to CLAUDE_ENV by Run.claude_env(). The 1,000,000 token window of the model is never reached in scale-m01
# (largest context 661,170 tokens): a smaller window makes the long Refactoring subagent compact earlier.
COMPACT_ENV = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
DEFAULT_COMPACT_WINDOW = 200000
EXPECTED_CLAUDE_VERSION = "2.1.308"      # pinned in the image (generation log); --expected-version overrides
DEFAULT_EFFORT = "high"                   # setting of the refactoring runs is chosen in the pilot (approaches.md)
FORBIDDEN_NAMES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md"}
SUBAGENT_TOOLS = {"Task", "Agent"}
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens", "thinking_tokens")

# --- W4, W5, W6 ------------------------------------------------------------------------------------------------
DONE_MARKER = "REFACTORING_DONE"
MAX_CALLS = 4
MAX_CODE_ROUNDS = 3
WINDOW_LIMIT_PCT = 10.0
# Fixed, neutral sentences for {reverted} (W5). The exact texts are approved in Aslınur's prompt PR; files
# experiments/prompts/reverted.md and accepted.md override these defaults when they exist.
REVERTED_TEXT = "Your previous changes were reverted. Read the files again before you continue."
ACCEPTED_TEXT = "Your previous changes were kept."
PLACEHOLDERS = ("{round}", "{max_rounds}", "{feedback}", "{reverted}")          # Iterative (ADR 004)
MULTIAGENT_PLACEHOLDERS = ("{test_command}", "{max_refactoring_calls}", "{max_test_runs}")

LIMIT_PATTERN = re.compile(r"usage limit|rate.?limit|limit reached|quota|too many requests|\b429\b", re.I)

# Pause and continue after a usage-limit cut (Week 6): wait for the 5-hour window to reopen, then continue the same
# session with a fixed, neutral sentence (no quality hint, no smell name, no metric).
CONTINUE_PROMPT = "The session was interrupted by a usage limit. Continue the task from where you stopped."
MAX_PAUSES = 3
MAX_PAUSE_TOTAL_S = 24 * 3600
RESET_MARGIN_S = 300
SLEEP, CLOCK = time.sleep, time.time        # replaced by the tests

# Exit codes of the runners
EXIT_DONE, EXIT_INVALID, EXIT_USAGE, EXIT_LOCK, EXIT_LIMIT = 0, 1, 2, 3, 5

RUNS_COLUMNS = [
    "run_id", "approach", "repetition", "start_ref", "start_sha", "baseline", "tests_modules", "account",
    "accounts_used", "window_pct_start", "started_at", "finished_at", "duration_s",
    "outcome", "valid", "reasons", "run_successful",
    "calls", "code_rounds", "accepted_rounds", "rejected_rounds", "best_round", "last_round", "best_tag",
    *[f"{m}_{w}" for w in ("start", "best", "best_delta", "r1", "last") for m in
      ("mean_cc", "mean_cognitive", "mi_weighted", "duplication_pct", "smell_count")],
    "regressions_feedback", "regressions_heldout", "api_changed", "api_change_kind", "outside_lms_changes",
    "subagents_spawned", "subagent_attempts", "permission_denials", "files_read", "files_changed", "feedback_lines_max",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "usd_raw", "usd_diff", "usd_lost",
    "claude_s", "measure_s", "claude_code_version", "model", "effort", "image_id", "note",
]
# Files of the starting measurement that the engine and compare.py read (checked before the first Claude call)
BASELINE_FILES = ("summary.json", "tests.csv", "project.csv", "modules.csv", "levels.csv", "functions.csv", "classes.csv")
PRIMARY = ("mean_cc", "mean_cognitive", "mi_weighted", "duplication_pct", "smell_count")


class EngineError(Exception):
    """Stops a run before or outside the experiment itself (usage error, lock, broken input)."""

    def __init__(self, message: str, code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code


def repo_relative(path: Path, repo: Path) -> str:
    """``path`` relative to the repository (``results/baseline/...``) when it is inside it, so that run.json and
    runs.csv are the same on every machine; otherwise the absolute path."""
    try:
        return Path(path).resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        return str(path)


def from_repo(path: str, repo: Path) -> Path:
    """The inverse of ``repo_relative``."""
    return Path(path) if Path(path).is_absolute() else Path(repo) / path


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --- git ----------------------------------------------------------------------------------------------------------

def git(args: list[str], cwd: Path, *, env: dict | None = None, input: bytes | None = None,
        check: bool = True) -> str:
    proc = subprocess.run(["git", "-c", "safe.directory=*", "-c", "core.autocrlf=false", *args], cwd=cwd,
                          input=input, capture_output=True, env={**os.environ, **(env or {})}, check=False)
    if check and proc.returncode != 0:
        raise EngineError(f"git {' '.join(args[:3])} failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout.decode("utf-8", errors="replace").strip()


IDENTITY = {"GIT_AUTHOR_NAME": "experiment engine", "GIT_AUTHOR_EMAIL": "experiments@localhost",
            "GIT_COMMITTER_NAME": "experiment engine", "GIT_COMMITTER_EMAIL": "experiments@localhost"}


def resolve_commit(repo: Path, ref: str) -> str:
    try:
        return git(["rev-parse", "--verify", f"{ref}^{{commit}}"], repo)
    except EngineError:
        raise EngineError(f"unknown git ref: {ref}") from None


def export_project(repo: Path, sha: str, dest: Path) -> Path:
    """``dataset/lms/generated`` of commit ``sha`` exported into ``dest`` (git archive, no checkout)."""
    proc = subprocess.run(["git", "-c", "safe.directory=*", "archive", "--format=tar", sha, GENERATED], cwd=repo,
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise EngineError(f"git archive {sha} {GENERATED} failed: {proc.stderr.decode(errors='replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(dest)
    project = dest / GENERATED
    if not (project / "lms").is_dir():
        raise EngineError(f"no lms/ package in {GENERATED} at {sha}")
    return project


def code_files(folder: Path) -> list[Path]:
    """Files of a code folder, without bytecode caches."""
    return sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and p.suffix not in (".pyc", ".pyo"))


def tag_code(repo: Path, start_sha: str, lms_dir: Path, tag: str, message: str) -> str:
    """A commit on top of ``start_sha`` with only ``dataset/lms/generated/lms`` replaced by ``lms_dir`` and a
    lightweight tag ``tag`` on it (W12). Nothing is checked out; returns the commit SHA."""
    if git(["tag", "-l", tag], repo):
        raise EngineError(f"tag {tag} already exists: use another --run-id")
    with tempfile.TemporaryDirectory(prefix="exp-index-") as tmp:
        env = {**IDENTITY, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(["read-tree", start_sha], repo, env=env)
        # --cached: only the temporary index changes; -f: the checked-out files may differ from the start ref
        git(["rm", "--cached", "-r", "-q", "-f", "--ignore-unmatch", f"{GENERATED}/lms"], repo, env=env)
        files = code_files(lms_dir)
        paths = "\n".join(str(p) for p in files).encode("utf-8")
        blobs = git(["hash-object", "-w", "--no-filters", "--stdin-paths"], repo, input=paths).splitlines()
        info = "".join(f"100644 {blob}\t{GENERATED}/lms/{p.relative_to(lms_dir).as_posix()}\n"
                       for blob, p in zip(blobs, files))
        git(["update-index", "--index-info"], repo, env=env, input=info.encode("utf-8"))
        tree = git(["write-tree"], repo, env=env)
    commit = git(["commit-tree", tree, "-p", start_sha, "-m", message], repo, env=IDENTITY)
    git(["tag", tag, commit], repo)
    return commit


# --- run lock (W13) -----------------------------------------------------------------------------------------------

class RunLock:
    """``.run.lock`` in the repository root, same format as scripts/measure_baseline.sh. Held for the whole run,
    except during a Claude Code call that runs no tests (W13, ADR 004 addendum point 1): ``released()``."""

    def __init__(self, path: Path, what: str, wait: int = 21600, poll: int = 60, log=print):
        self.path, self.what, self.wait, self.poll, self.log = path, what, wait, poll, log
        self.held = False

    def __enter__(self) -> "RunLock":
        return self.acquire(self.wait)

    def acquire(self, wait: int | None) -> "RunLock":
        """Take the lock; ``wait`` seconds at most (None: no limit, used after a call so that its result is kept)."""
        waited = 0
        user = os.environ.get("USER") or os.environ.get("USERNAME") or getpass.getuser()
        text = (f"who={user}@{socket.gethostname()}\nwhat={self.what}\n"
                f"start={dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\npid={os.getpid()}\n")
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if wait is not None and waited >= wait:
                    held = self.path.read_text(encoding="utf-8", errors="replace") if self.path.exists() else ""
                    raise EngineError(f"{self.path} is still held after {waited} s:\n{held}", EXIT_LOCK) from None
                if waited == 0:
                    self.log(f"waiting for {self.path}")
                time.sleep(self.poll)
                waited += self.poll
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.held = True
            return self

    def __exit__(self, *exc) -> None:
        if self.held and self.path.exists() and f"pid={os.getpid()}\n" in self.path.read_text(encoding="utf-8"):
            self.path.unlink()
        self.held = False

    @contextlib.contextmanager
    def released(self):
        """W13: free the lock while Claude Code runs and take it again before the code is tested or measured, so
        that the tests and measurements of two runs never overlap. Yields a dict; ``wait_s`` is the time spent
        waiting for the lock afterwards (another run was measuring)."""
        info = {"released": self.held, "wait_s": 0.0}
        if not self.held:
            yield info
            return
        self.__exit__()
        try:
            yield info
        finally:
            started = time.monotonic()
            self.acquire(None)
            info["wait_s"] = round(time.monotonic() - started, 1)


# --- the model's workspace (W3) -----------------------------------------------------------------------------------

class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.start = root / "start" / GENERATED
        self.model = root / "model"
        self.git_dir = root / "state.git"
        self.session = root / "session"
        self.tests = root / "tests"
        self.hashes = root / "test-hashes.json"
        self.measure_root = root / "measure"

    def _g(self, *args: str, input: bytes | None = None) -> str:
        return git(["--git-dir", str(self.git_dir), "--work-tree", str(self.model), *args], self.model,
                   env=IDENTITY, input=input)

    def create(self, repo: Path, start_sha: str, interface: Path | None, make_interface: Path) -> None:
        if self.model.exists():
            raise EngineError(f"work folder already used: {self.root}")
        export_project(repo, start_sha, self.root / "start")
        self.model.mkdir(parents=True)
        shutil.copytree(self.start / "lms", self.model / "lms", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(self.start / "requirements.txt", self.model / "requirements.txt")
        target = self.model / "INTERFACE.md"
        if interface:
            shutil.copy2(interface, target)
        else:
            if not make_interface.is_file():
                raise EngineError("experiments/make_interface.py is not there yet: pass --interface FILE")
            proc = subprocess.run([sys.executable, str(make_interface), "--requirements",
                                   str(self.start / "REQUIREMENTS.md"), "--out", str(target)],
                                  capture_output=True, text=True, check=False)
            if proc.returncode != 0 or not target.is_file():
                raise EngineError(f"make_interface.py failed: {proc.stderr.strip()}")
        self.session.mkdir()
        git(["init", "-q", "--bare", str(self.git_dir)], self.root)
        git(["--git-dir", str(self.git_dir), "config", "core.bare", "false"], self.root)
        self._g("add", "-A")
        self._g("commit", "-q", "-m", "start")

    def listing(self) -> dict[str, str]:
        return {p.relative_to(self.model).as_posix(): sha256_file(p)
                for p in sorted(self.model.rglob("*")) if p.is_file()}

    def head(self) -> str:
        return self._g("rev-parse", "HEAD")

    def lms_changed(self) -> bool:
        return bool(self._g("status", "--porcelain", "--untracked-files=all", "--", "lms"))

    def commit(self, message: str) -> str:
        self._g("add", "-A")
        self._g("commit", "-q", "--allow-empty", "-m", message)
        return self.head()

    def restore(self, commit: str) -> None:
        """Workspace back to ``commit`` (rejected round, W5; resume after a limit cut, W6)."""
        self._g("reset", "-q", "--hard", commit)
        self._g("clean", "-q", "-f", "-d", "-x")

    def discard_outside_lms(self, before: dict[str, str]) -> dict[str, list[str]]:
        """Undo changes outside lms/ (W3) and return them; ``before`` is the listing at the start of the call."""
        after = self.listing()
        outside = lambda keys: sorted(k for k in keys if not k.startswith("lms/"))  # noqa: E731
        changes = {"changed": outside(k for k in before.keys() & after.keys() if before[k] != after[k]),
                   "added": outside(after.keys() - before.keys()),
                   "removed": outside(before.keys() - after.keys())}
        for rel in changes["added"]:
            (self.model / rel).unlink()
        for rel in changes["changed"] + changes["removed"]:
            self._g("checkout", "HEAD", "--", rel)
        for folder in sorted({p for p in self.model.rglob("*") if p.is_dir()}, reverse=True):
            if not any(folder.iterdir()) and folder.relative_to(self.model).parts[0] != "lms":
                folder.rmdir()
        return changes

    def tree_for(self, commit: str, name: str) -> Path:
        """Measurement tree (W3): the starting project with lms/ taken from ``commit`` of the state repository."""
        dest = self.measure_root / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.start, dest, ignore=lambda d, names: ["lms"] if Path(d) == self.start else [])
        data = subprocess.run(["git", "-c", "safe.directory=*", "--git-dir", str(self.git_dir), "archive",
                               "--format=tar", commit, "lms"], capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(dest)
        return dest


def hidden_or_forbidden(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """New hidden files or folders and new CLAUDE.md / AGENTS.md anywhere in the workspace (W9)."""
    new = sorted(after.keys() - before.keys())
    return [p for p in new if any(part.startswith(".") for part in PurePosixPath(p).parts)
            or PurePosixPath(p).name in FORBIDDEN_NAMES]


def forbidden_writes(written: list[str]) -> list[str]:
    """Edit / Write targets that are CLAUDE.md, AGENTS.md or hidden (also outside the workspace, e.g. ~/.claude),
    from the stream: catches a file that was written and removed again within the same call. --safe-mode does not
    stop the model from writing CLAUDE.md (setup check, Işıl, 20 November 2026)."""
    return sorted({p for p in written if PurePosixPath(p).name in FORBIDDEN_NAMES
                   or any(part.startswith(".") for part in PurePosixPath(p).parts)})


def prepare_tests(tests_src: Path, modules: str | None, ws: Workspace) -> list[str] | None:
    """The run's own copy of the tests (a module subset with --tests-modules) and the hashes of that copy."""
    if modules:
        low, high = baseline_steps.parse_modules(modules)
        stems = baseline_steps.select_stems(tests_src, low, high)
        if not stems:
            raise EngineError(f"no test files for modules {modules}")
        baseline_steps.make_subset(tests_src, stems, ws.tests)
    else:
        stems = None
        shutil.copytree(tests_src, ws.tests, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    write_json(ws.hashes, test_hashes.compute(ws.tests))
    return stems


# --- prompts --------------------------------------------------------------------------------------------------------

def fill_prompt(text: str, **values: Any) -> str:
    """Only the four placeholders are filled; the text itself is never changed (Aslınur's contract)."""
    for key, value in values.items():
        if f"{{{key}}}" not in PLACEHOLDERS + MULTIAGENT_PLACEHOLDERS:
            raise ValueError(f"unknown placeholder {key}")
        text = text.replace(f"{{{key}}}", str(value))
    return text


def load_prompt(prompts: Path, name: str) -> str:
    path = prompts / name
    if not path.is_file():
        raise EngineError(f"prompt file not found: {path} (Aslınur's prompt PR)")
    return path.read_text(encoding="utf-8")


def fixed_sentence(prompts: Path, name: str, default: str) -> str:
    path = prompts / name
    return path.read_text(encoding="utf-8").strip() if path.is_file() else default


# --- the Claude Code call (W9) --------------------------------------------------------------------------------------

def claude_args(prompt: str, effort: str, session_id: str | None, tools: tuple = TOOLS, allowed: tuple | None = None,
                disallowed: tuple = DISALLOWED_TOOLS, extra: tuple = (), safe_mode: bool = True) -> list[str]:
    # --tools only offers the tools; in dontAsk mode a tool also needs --allowedTools, otherwise every Write is
    # denied and the call still ends with subtype "success" (setup check, Işıl, 20 November 2026)
    args = ["-p", prompt, "--model", MODEL, "--effort", effort, "--tools", ",".join(tools),
            "--allowedTools", *(allowed or tools), *(("--disallowedTools", *disallowed) if disallowed else ()),
            *extra, *(f for f in FIXED_FLAGS if safe_mode or f != "--safe-mode")]
    if session_id:
        args += ["--resume", session_id]
    return args


def parse_stream(text: str) -> dict:
    """Facts from a ``--output-format stream-json --verbose`` log: init event, result event, tool uses."""
    init, result, uses, texts, rate_limit, tool_results = None, None, [], [], None, {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init" and init is None:
            init = event
        elif kind == "result":
            result = event
        elif kind == "user":             # tool results: a denied subagent type only shows up here (K6c)
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content")
                    text = content if isinstance(content, str) else " ".join(
                        str(c.get("text") or "") for c in content or [] if isinstance(c, dict))
                    tool_results[block.get("tool_use_id")] = {"is_error": bool(block.get("is_error")), "text": text[:500]}
        elif kind == "rate_limit_event":
            rate_limit = {k: v for k, v in event.items() if k not in ("type", "uuid")}
        elif kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    uses.append({"name": block.get("name"), "input": block.get("input") or {}, "id": block.get("id"),
                                 "parent": event.get("parent_tool_use_id")})     # parent: the subagent's call
                elif block.get("type") == "text":
                    texts.append(block.get("text") or "")
    def paths(*names: str) -> list[str]:
        return sorted({str(u["input"].get("file_path") or u["input"].get("path") or "")
                       for u in uses if u["name"] in names} - {""})
    counts: dict[str, int] = {}
    for u in uses:
        counts[u["name"]] = counts.get(u["name"], 0) + 1
    return {"init": init, "result": result, "tool_counts": counts, "rate_limit": rate_limit, "uses": uses,
            "tool_results": tool_results,
            "files_read": paths("Read"), "files_written": paths("Edit", "Write"),
            "subagent_attempts": sum(counts.get(n, 0) for n in SUBAGENT_TOOLS),
            "final_text": (result or {}).get("result") or (texts[-1] if texts else "")}


def said_done(text: str | None) -> bool:
    """The end marker counts only at the end of the last non-empty line of the final message, as the prompt asks
    (W4); a sentence that only mentions REFACTORING_DONE ("I will not write REFACTORING_DONE yet") does not stop a
    run. Markdown around it (**, `, a final period) is allowed."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return bool(lines) and lines[-1].strip("*_`>#. ").endswith(DONE_MARKER)


def check_call(parsed: dict, stderr: str, expected_version: str | None, tools: tuple = TOOLS,
               subagents_allowed: bool = False, denials_invalid: bool = True) -> tuple[str, list[str]]:
    """Status of a call (``ok``, ``limit`` or ``error``) and the reasons that make the run invalid (W9, W10)."""
    init, result = parsed["init"], parsed["result"]
    invalid: list[str] = []
    if result is None:
        status = "limit" if LIMIT_PATTERN.search(stderr or "") else "error"
        return status, ([] if status == "limit" else ["no result event in the stream (call did not finish)"])
    text = " ".join(str(result.get(k) or "") for k in ("result", "terminal_reason", "subtype"))
    if result.get("is_error") or result.get("subtype") != "success":
        if result.get("api_error_status") == 429 or LIMIT_PATTERN.search(text):
            return "limit", []
        invalid.append(f"call returned an error: {text.strip()[:200]}")
    if init is None:
        invalid.append("no init event: tool list, model and version cannot be checked")
    else:
        offered = sorted(init.get("tools") or [])
        if offered != sorted(tools):
            invalid.append(f"tool list is not exactly {','.join(tools)}: {','.join(offered)}")
        if expected_version and init.get("claude_code_version") != expected_version:
            invalid.append(f"Claude Code version {init.get('claude_code_version')} (expected {expected_version})")
        if "ANTHROPIC" in str(init.get("apiKeySource") or ""):
            invalid.append(f"credential source {init.get('apiKeySource')}: not the account's token")
        if init.get("model") and init.get("model") != MODEL:
            invalid.append(f"model {init.get('model')} (expected {MODEL})")
    summary = cost.summarize(result)
    if summary["valid"] != "true" and summary["note"]:
        invalid += [p for p in summary["note"].split("; ") if not p.startswith("call returned an error")]
    stats = result.get("subagent_stats")
    if not isinstance(stats, dict):
        invalid.append("subagent_stats missing: subagents cannot be checked")
    elif stats.get("spawned") and not subagents_allowed:
        invalid.append(f"{stats.get('spawned')} subagent(s) started")
    denials = result.get("permission_denials")
    if not isinstance(denials, list):
        invalid.append("permission_denials missing: denied tool calls cannot be checked")
    elif denials and denials_invalid:      # Multi-Agent classifies its denials itself (run_multiagent.blocked_or_broken)
        invalid.append(f"{len(denials)} denied tool call(s): {', '.join(denied_tools(denials))}")
    return "ok", invalid


# In a resumed session total_cost_usd and the modelUsage token counts are cumulative (setup check, Işıl,
# 20 November 2026): the value of one call is "this total - the total of the previous call of the same session".
CUMULATIVE = ("usd", "usd_recomputed", "input_tokens", "output_tokens", "cache_write_tokens", "cache_write_1h_tokens",
              "cache_read_tokens", "thinking_tokens", "total_input_tokens")


def per_call(summary: dict, previous: dict | None) -> dict:
    """``summary`` (cost.summarize of a result) with the cumulative fields turned into this call's share. A total
    smaller than the previous one (a new session, e.g. after an account switch) is taken as it is."""
    out = dict(summary)
    if not previous:
        return out
    usd_now, usd_before = summary.get("usd"), previous.get("usd")
    if isinstance(usd_now, (int, float)) and isinstance(usd_before, (int, float)) and usd_now < usd_before:
        return out
    for key in CUMULATIVE:
        now_v, before_v = summary.get(key), previous.get(key)
        if isinstance(now_v, (int, float)) and isinstance(before_v, (int, float)) and now_v >= before_v:
            out[key] = round(now_v - before_v, 6) if isinstance(now_v, float) else now_v - before_v
    return out


def denied_tools(denials: list) -> list[str]:
    return [str(d.get("tool_name") or d.get("name") or "?") if isinstance(d, dict) else str(d) for d in denials]


# --- shell commands of the model (the same rule in every role and every approach) --------------------------------------

# Decision of 24 November 2026 (m01c, before its metrics were seen): read-only shell commands are no reason for an
# invalid run in any role or approach; they are counted and written to run.json. A command that writes, deletes or is
# not on this list makes the run invalid. This widens the decision of 22 November (orchestrator only, K6b).
# Addition of 24 November 2026, 20:35 (m01c, metrics still not seen): `xargs` counts as read-only when the command it
# runs is on the list and has no option that writes; the options of xargs itself (-0, -n, -I, ...) are free. No other
# command is added. Both decisions are copied into the decision record of a run judged again (SHELL_RULE_DECISIONS).
READ_ONLY_COMMANDS = ("find", "wc", "ls", "cat", "head", "tail", "sort", "grep", "uniq")
SHELL_RULE_DECISIONS = (
    {"at": "2026-11-24T20:30:00+03:00", "decision": "Read-only shell commands (find, wc, ls, cat, head, tail, sort, grep, "
     "uniq) are no reason for an invalid run in any role or approach; they are counted and written to run.json. A "
     "command that writes, deletes or is not on the list makes the run invalid."},
    {"at": "2026-11-24T20:35:00+03:00", "decision": "The list was incomplete: xargs counts as read-only when the command "
     "it runs is on the list and has no option that writes (xargs wc -l is valid; xargs rm and xargs sed -i are not); "
     "the options of xargs itself (-0, -n, -I, ...) are free. No other command is added."},
)
_XARGS_VALUE_SHORT = set("nLIsPdEa")        # -n 1, -L 1, -I {}, -s N, -P N, -d C, -E END, -a FILE: the value is the next word
_XARGS_VALUE_LONG = {"--max-args", "--max-chars", "--max-procs", "--delimiter", "--arg-file", "--process-slot-var"}
_FIND_ACTIONS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
_SEPARATORS = {"|", "||", "&&", ";"}


def classify_shell(command: str) -> tuple[bool, str]:
    """``(True, "")`` if ``command`` only chains commands of ``READ_ONLY_COMMANDS`` (pipes, ``&&``, ``||``, ``;``)
    without anything that writes, deletes or runs another program; otherwise ``(False, why)``. Redirections are not
    allowed, except ``2>/dev/null``; substitutions, background jobs and unknown commands (``python``, ``echo``, ...)
    are not either. ``xargs`` is read-only if the command it runs is (``xargs wc -l``; ``xargs rm`` is not). Options that make an allowed command write (``find -delete``/``-exec``/``-fprint*``,
    ``sort -o``) are not allowed, and ``uniq`` takes at most one file (the second would be its output)."""
    if not command.strip():
        return False, "empty command"
    if "`" in command:
        return False, "command substitution"
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as exc:
        return False, f"cannot be parsed ({exc})"
    stages: list[list[str]] = [[]]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _SEPARATORS:
            stages.append([])
        elif token == ">" and tokens[i + 1:i + 2] == ["/dev/null"] and stages[-1][-1:] == ["2"]:
            stages[-1].pop()
            i += 1
        elif token and set(token) <= set("();<>|&"):
            return False, f"'{token}' is not allowed"
        else:
            stages[-1].append(token)
        i += 1
    for stage in (s for s in stages if s):
        name, args, via = stage[0], stage[1:], ""
        if name == "xargs":
            name, args = _xargs_command(args)
            via = "xargs runs "
            if name is None:
                return False, "xargs without a command (it would run echo)"
        problem = _command_problem(name, args)
        if problem:
            return False, via + problem
    return True, ""


def _xargs_command(args: list[str]) -> tuple[str | None, list[str]]:
    """The command xargs runs and its arguments: what is left after the options of xargs itself."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            i += 1
            break
        if not arg.startswith("-") or arg == "-":
            break
        if (len(arg) == 2 and arg[1] in _XARGS_VALUE_SHORT) or arg in _XARGS_VALUE_LONG:
            i += 1                          # the value of the option is the next word
        i += 1
    return (args[i], args[i + 1:]) if i < len(args) else (None, [])


def _command_problem(name: str, args: list[str]) -> str:
    """Why a command of the list is not read-only with these arguments ("" if it is)."""
    if name not in READ_ONLY_COMMANDS:
        return f"'{name}' is not on the list ({', '.join(READ_ONLY_COMMANDS)})"
    if name == "find" and any(a in _FIND_ACTIONS for a in args):
        return "find with an action that writes or runs a program"
    if name == "sort" and any(a == "--output" or a.startswith("--output=") or a.startswith("--compress-program")
                              or (a.startswith("-") and not a.startswith("--") and "o" in a[1:]) for a in args):
        return "sort with an output file or a program"
    if name == "uniq" and sum(1 for a in args if not a.startswith("-")) > 1:
        return "uniq with an output file"
    return ""


def shell_check(uses: list[dict], allowed_command: str | None = None) -> dict:
    """The Bash uses of a stream: ``read_only`` (commands to count) and ``invalid`` (reasons). ``allowed_command``
    (the Multi-Agent test command) is neither."""
    own = " ".join((allowed_command or "").split())
    report: dict[str, list[str]] = {"read_only": [], "invalid": []}
    for use in uses:
        if use.get("name") != "Bash":
            continue
        command = " ".join(str((use.get("input") or {}).get("command") or "").split())
        if own and command == own:
            continue
        ok, why = classify_shell(command)
        (report["read_only"] if ok else report["invalid"]).append(command[:80] if ok else f"{command[:80]} ({why})")
    return report


# --- pause and continue after a usage-limit cut -------------------------------------------------------------------

def limit_info(rate_limit: dict | None) -> dict:
    """Which window ran out and when it opens again, from the last ``rate_limit_event`` of the cut call (the
    ``rate_limit`` of its call record). ``kind`` is ``five_hour``, ``seven_day`` or None when the event does not say.
    Checked only against scale-m01 (a five-hour cut: status ``rejected``, ``rateLimitType`` ``five_hour``, five_hour
    utilization 1 and seven_day 0.49, ``resetsAt`` in epoch seconds); a weekly cut is not verified. The weekly window
    wins when both are full, because waiting for the 5-hour window would not help."""
    info = (rate_limit or {}).get("rate_limit_info") or {}
    windows = info.get("unifiedWindows") or {}

    def window(name: str) -> tuple:
        w = windows.get(name) or {}
        use, resets = w.get("utilization"), w.get("resetsAt")
        return (use if isinstance(use, (int, float)) else None), (resets if isinstance(resets, (int, float)) else None)

    five_use, five_resets = window("five_hour")
    seven_use, seven_resets = window("seven_day")
    rejected = info.get("status") == "rejected"
    full = lambda use: use is not None and use >= 1  # noqa: E731
    if full(seven_use) or (rejected and info.get("rateLimitType") == "seven_day"):
        kind = "seven_day"
    elif full(five_use) or (rejected and info.get("rateLimitType") == "five_hour"):
        kind = "five_hour"
    else:
        kind = None
    resets = {"five_hour": five_resets, "seven_day": seven_resets}.get(kind)
    if resets is None and kind == "five_hour" and isinstance(info.get("resetsAt"), (int, float)):
        resets = info["resetsAt"]
    return {"kind": kind, "resets_at": resets, "five_hour_util": five_use, "seven_day_util": seven_use,
            "five_hour_resets_at": five_resets, "seven_day_resets_at": seven_resets, "status": info.get("status")}


def wait_until(timestamp: float, margin_s: int = RESET_MARGIN_S, on_tick=None, tick_s: int = 600,
               step_s: int = 30) -> float:
    """Sleep until ``timestamp`` (epoch seconds) + ``margin_s``. ``on_tick(seconds_left)`` is called every
    ``tick_s`` seconds (the run records that it is waiting). Wall-clock based, so a sleeping computer does not make it
    wait longer. Returns the seconds waited; Ctrl+C leaves everything as it is."""
    target = timestamp + margin_s
    started = last_tick = CLOCK()
    while True:
        left = target - CLOCK()
        if left <= 0:
            return round(CLOCK() - started, 1)
        if on_tick and CLOCK() - last_tick >= tick_s:
            on_tick(left)
            last_tick = CLOCK()
        SLEEP(min(step_s, left))


def resume_args(args: list[str], prompt: str, session_id: str) -> list[str]:
    """The arguments of a call again with the same flags (``--agents``, tools, permissions), but the prompt replaced
    and ``--resume <session_id>`` added. ``claude_args`` puts ``-p <prompt>`` first."""
    if len(args) < 2 or args[0] != "-p":
        raise EngineError("the Claude Code arguments do not start with -p <prompt>: cannot build the resume call")
    return [args[0], prompt, *args[2:], "--resume", session_id]


# --- measurement --------------------------------------------------------------------------------------------------

class Toolkit:
    """The measurement step. The engine only reads ``compare.json`` and ``measure.json`` from its output."""

    def measure(self, run: "Run", tree: Path, out: Path, label: str, code_sha: str, test_set: str,
                previous_best: Path | None) -> dict:
        raise NotImplementedError

    def format_feedback(self, tests_before: Path, tests_after: Path, repeats: list[Path], log_dir: Path) -> str:
        raise NotImplementedError


class RealToolkit(Toolkit):
    """``experiments/measure.py`` in the Docker image with the network off (or here with ``--local``)."""

    def measure(self, run, tree, out, label, code_sha, test_set, previous_best):
        args = ["--code", tree, "--tests", run.ws.tests, "--hashes", run.ws.hashes, "--baseline", run.baseline,
                "--start-code", run.ws.start, "--out", out, "--label", label, "--code-sha", code_sha,
                "--set", test_set, "--timeout", str(run.settings["test_timeout"])]
        if previous_best:
            args += ["--previous-best", previous_best]
        out.mkdir(parents=True, exist_ok=True)
        if run.settings["local"]:
            cmd = [sys.executable, str(EXPERIMENTS / "measure.py"), *map(str, args)]
        else:
            mapped = [run.container_path(a) if isinstance(a, Path) else a for a in args]
            cmd = ["docker", "run", "--rm", "--network", "none", "-e", f"ANALYZER_IMAGE_ID={run.image_id}",
                   "-v", f"{run.repo_scripts_root}:/work", "-v", f"{run.ws.root}:/exp", "-v", f"{run.out_root}:/out",
                   "-w", "/work", run.settings["image"], "python", "experiments/measure.py", *mapped]
        with (out / "measure.log").open("w", encoding="utf-8") as log:
            code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  check=False).returncode
        return read_measurement(out, code)

    def format_feedback(self, tests_before, tests_after, repeats, log_dir):
        sys.path.insert(0, str(EXPERIMENTS))
        try:
            import feedback  # Aslınur's experiments/feedback.py (W2)
        except ImportError:
            raise EngineError("experiments/feedback.py is not there yet (W2, Aslınur)") from None
        return feedback.format_feedback(tests_before, tests_after, repeats, log_dir)


def read_measurement(out: Path, exit_code: int) -> dict:
    info = read_json(out / "measure.json") if (out / "measure.json").is_file() else {
        "status": "error", "problems": [f"measure.py exited with {exit_code} and wrote no measure.json"]}
    info["exit_code"] = exit_code
    compare_file = out / "compare" / "compare.json"
    info["compare"] = read_json(compare_file) if compare_file.is_file() else None
    return info


def digest(measurement: dict) -> dict:
    """The facts the engine decides on, from one measurement."""
    cmp = measurement.get("compare") or {}
    tests = cmp.get("tests") or {}
    regs = tests.get("regressions") or []
    openapi = cmp.get("openapi") or {}
    primary = cmp.get("primary") or {}
    return {
        "status": measurement.get("status"),
        "problems": measurement.get("problems", []),
        "round_accepted": (cmp.get("round_accepted") or {}).get("value"),
        "run_successful": (cmp.get("run_successful") or {}).get("value"),
        "reasons": (cmp.get("run_successful") or {}).get("reasons", []),
        "accept_reasons": (cmp.get("round_accepted") or {}).get("reasons", []),
        "regressions": tests.get("regression_count", 0),
        "regressions_by_set": {s: sum(1 for r in regs if r.get("set") == s) for s in ("feedback", "heldout")},
        "regression_cases": [r.get("case") for r in regs],
        "api_changed": openapi.get("changed"),
        "api_loads": openapi.get("after_hash") is not None if openapi.get("checked") else None,
        "api_change_kind": measurement.get("api_change_kind"),
        "invalid_metrics": cmp.get("invalid", []),
        "primary": {m: {k: v.get(k) for k in ("before", "after", "delta", "status")} for m, v in primary.items()},
    }


def classify(call_invalid: list[str], facts: dict | None) -> tuple[str, bool, list[str]]:
    """W10: ``invalid`` (infrastructure, the run is repeated) or a valid outcome: ``failed`` (caused by the model),
    ``success``, ``no_improvement`` or ``no_change``."""
    if call_invalid:
        return "invalid", False, call_invalid
    if facts is None:
        return "no_change", True, ["the model changed nothing in lms/"]
    if facts["status"] == "invalid":
        return "invalid", False, facts["problems"]
    failed = []
    if facts["status"] == "timeout":
        failed.append("tests timed out again after one repetition")
    if facts["api_loads"] is False:
        failed.append("the code does not load (OpenAPI schema cannot be built)")
    elif facts["api_changed"]:
        failed.append(f"API changed ({facts.get('api_change_kind') or 'unclassified'})")
    if facts["regressions"]:
        failed.append(f"{facts['regressions']} test regression(s)")
    if facts["invalid_metrics"] or facts["status"] == "not_measurable":
        failed.append("metric(s) not measurable: " + ", ".join(facts["invalid_metrics"] or ["analyzer"]))
    if facts["status"] not in ("ok", "timeout", "not_measurable") and not failed:
        return "invalid", False, facts["problems"] or [f"measurement status {facts['status']}"]
    if failed:
        return "failed", True, failed
    if facts["run_successful"] is True:
        return "success", True, []
    return "no_improvement", True, facts["reasons"]


# --- one run --------------------------------------------------------------------------------------------------------

class Run:
    """Everything one runner needs: settings, workspace, records, calls and measurements."""

    def __init__(self, approach: str, args, toolkit: Toolkit | None = None, log=print):
        self.approach, self.args, self.log = approach, args, log
        self.toolkit = toolkit or RealToolkit()
        self.lock: RunLock | None = None      # set by the runner; released during a call that runs no tests (W13)
        self.repo = Path(args.repo).resolve()
        self.out_root = Path(args.out_root).resolve()
        self.out = self.out_root / approach / args.run_id
        self.baseline = Path(args.baseline).resolve() if args.baseline else None
        self.prompts = Path(args.prompts).resolve()
        self.repo_scripts_root = REPO
        self.settings = {"image": args.image, "local": args.local, "effort": args.effort,
                         "call_timeout": args.call_timeout, "test_timeout": args.test_timeout,
                         "expected_version": args.expected_version or None,
                         "compact_window": getattr(args, "compact_window", DEFAULT_COMPACT_WINDOW),
                         "claude_command": shlex.split(args.claude_command, posix=os.name != "nt") if args.claude_command
                         else ["claude"]}
        self.image_id = ""
        self.ws: Workspace
        self.record: dict = {}
        self.state: dict = {}

    def claude_env(self) -> dict[str, str]:
        """The environment of every Claude Code call: the fixed settings and the compaction window (recorded)."""
        return {**CLAUDE_ENV, COMPACT_ENV: str(self.settings["compact_window"])}

    def parsed_calls(self) -> list[dict]:
        """Every call's stream read again from its folder (a call is parsed when it ends, but the checks over all
        calls of a run, e.g. the roles of a resumed Multi-Agent run, need them all)."""
        return [parse_stream((self.out / "calls" / f"call-{c['number']}" / "stream.jsonl")
                             .read_text(encoding="utf-8", errors="replace")) for c in self.record["calls"]]

    # paths inside the measurement container
    def container_path(self, path: Path) -> str:
        path = Path(path).resolve()
        for root, mount in ((self.ws.root.resolve(), "/exp"), (self.out_root, "/out"), (REPO, "/work")):
            try:
                return str(PurePosixPath(mount) / path.relative_to(root).as_posix())
            except ValueError:
                continue
        raise EngineError(f"{path} is outside the mounted folders")

    # --- setup ---------------------------------------------------------------------------------------------------
    def check_inputs(self) -> None:
        a = self.args
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", a.run_id):
            raise EngineError("--run-id: letters, digits, '.', '_' and '-' only")
        if self.settings["compact_window"] < 1:
            raise EngineError("--compact-window must be a positive number of tokens")
        if a.window_pct is None or a.window_pct > WINDOW_LIMIT_PCT:
            raise EngineError(f"W6: start only when the account's 5-hour window is at most {WINDOW_LIMIT_PCT:g} % "
                              f"(--window-pct, from /usage)")
        missing = [name for name in BASELINE_FILES if not (self.baseline / name).is_file()]
        if missing:
            raise EngineError(f"--baseline {self.baseline} lacks {', '.join(missing)} (compare.py reads them). The detail "
                              f"CSVs of results/baseline/trial/ are not committed: use the folder of the machine that "
                              f"measured it, or measure the start ref again")
        self.check_docker()
        if a.modules:
            baseline_steps.parse_modules(a.modules)

    def check_docker(self) -> None:
        a = self.args
        if a.local:
            return
        if not Path(a.env_file).is_file():
            raise EngineError(f"--env-file {a.env_file} not found (it is passed to docker, never read)")
        if shutil.which("docker") is None:
            raise EngineError("docker not found (use --local only inside the image or in tests)")
        try:
            running = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True,
                                     text=True, timeout=60, check=False).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            running = False
        if not running:     # pilot-i01: Docker Desktop was closed; the first call failed after 0.2 s
            raise EngineError("Docker is not running: start Docker Desktop and wait until the engine runs")

    def setup(self) -> None:
        a = self.args
        self.check_inputs()
        start_sha = resolve_commit(self.repo, a.start_ref)
        summary = read_json(self.baseline / "summary.json")
        if summary.get("code_sha") and summary["code_sha"] != start_sha:
            raise EngineError(f"--baseline was measured on {summary['code_sha'][:12]}, the start ref is {start_sha[:12]}")
        bjson = self.baseline / "baseline.json"
        if bjson.is_file() and (read_json(bjson).get("modules") or None) != (a.modules or None):
            raise EngineError(f"--baseline was measured with modules {read_json(bjson).get('modules')}, "
                              f"--tests-modules is {a.modules}: the test sets would not match")
        if self.out.exists():
            raise EngineError(f"{self.out} already exists: use another --run-id")
        root = Path(a.work_root).resolve() if a.work_root else Path(tempfile.mkdtemp(prefix=f"exp-{a.run_id}-"))
        root.mkdir(parents=True, exist_ok=True)
        self.ws = Workspace(root)
        interface = Path(a.interface).resolve() if a.interface else None
        self.ws.create(self.repo, start_sha, interface, EXPERIMENTS / "make_interface.py")
        stems = prepare_tests(Path(a.tests).resolve(), a.modules, self.ws)
        if not a.local:
            self.image_id = subprocess.run(["docker", "image", "inspect", a.image, "--format", "{{.Id}}"],
                                           capture_output=True, text=True, check=False).stdout.strip() or "unknown"
        self.out.mkdir(parents=True)
        self.record = {
            "approach": self.approach, "run_id": a.run_id, "repetition": a.repetition, "start_ref": a.start_ref,
            "start_sha": start_sha, "start_state_commit": self.ws.head(), "baseline": repo_relative(self.baseline, self.repo),
            "baseline_primary": summary.get("primary"), "tests_modules": a.modules, "test_files": stems,
            "account": a.account, "accounts_used": [a.account], "window_pct_start": a.window_pct,
            "work_root": str(root), "image": a.image, "image_id": self.image_id, "model": MODEL,
            "effort": a.effort, "flags": claude_args("<prompt>", a.effort, None)[2:],
            "env": self.claude_env(), "compact_window": self.settings["compact_window"],
            "expected_version": self.settings["expected_version"],
            "host": {"os": platform.platform(), "python": platform.python_version()},
            "interface_sha256": sha256_file(self.ws.model / "INTERFACE.md"),
            "test_hashes_sha256": sha256_file(self.ws.hashes),
            "started_at": now(), "finished_at": None, "status": "running",
            "calls": [], "rounds": [], "final": {}, "outside_lms_changes": [], "events": [],
        }
        self.save()

    def save(self) -> None:
        write_json(self.out / "run.json", self.record)

    def event(self, text: str) -> None:
        self.record["events"].append({"at": now(), "text": text})
        self.log(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {text}")
        self.save()

    # --- one Claude Code call --------------------------------------------------------------------------------------
    def call(self, prompt: str, kind: str, session_id: str | None, setup: dict | None = None) -> dict:
        """One Claude Code call. ``setup`` (Multi-Agent): ``args`` (the claude arguments), ``tools`` (the expected
        tool list), ``subagents_allowed``, ``volumes`` ([(host, container, read_only)]) and ``env`` (docker only)."""
        setup = setup or {}
        number = len(self.record["calls"]) + 1
        folder = self.out / "calls" / f"call-{number}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "prompt.md").write_text(prompt, encoding="utf-8")
        before = self.ws.listing()
        args = setup.get("args") or claude_args(prompt, self.settings["effort"], session_id)
        extra_env = setup.get("env") or {}
        volumes = [x for host, inside, ro in setup.get("volumes", []) for x in ("-v", f"{host}:{inside}{':ro' if ro else ''}")]
        name = f"exp-{self.args.run_id}-c{number}-{os.getpid()}"
        if self.settings["local"]:
            cmd, env, cwd = [*self.settings["claude_command"], *args], {
                **os.environ, **self.claude_env(), **extra_env, "CLAUDE_CONFIG_DIR": str(self.ws.session)}, self.ws.model
        else:
            cmd = ["docker", "run", "--rm", "--name", name, "--env-file", str(Path(self.args.env_file).resolve()),
                   "-e", "CLAUDE_CONFIG_DIR=/session",
                   *[x for k, v in {**self.claude_env(), **extra_env}.items() for x in ("-e", f"{k}={v}")],
                   "-v", f"{self.ws.model}:/work", "-v", f"{self.ws.session}:/session", *volumes, "-w", "/work",
                   self.settings["image"], "claude", *args]
            env, cwd = None, None
        # W13: the lock is free while Claude Code runs, unless the call runs tests itself (Multi-Agent: hold_lock)
        release = self.lock is not None and not setup.get("hold_lock")
        lock_ctx = self.lock.released() if release else contextlib.nullcontext({"released": False, "wait_s": 0.0})
        self.event(f"call {number} ({kind}) started" + ("; run lock released" if release else ""))
        with lock_ctx as lock_info:
            started = time.monotonic()
            timed_out = False
            with (folder / "stream.jsonl").open("w", encoding="utf-8") as out, \
                    (folder / "stderr.txt").open("w", encoding="utf-8") as err:
                try:
                    code = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env, cwd=cwd,
                                          timeout=self.settings["call_timeout"], check=False).returncode
                except subprocess.TimeoutExpired:
                    timed_out, code = True, None
                    if not self.settings["local"]:
                        subprocess.run(["docker", "kill", name], capture_output=True, check=False)
            wall = round(time.monotonic() - started, 1)
        if lock_info["wait_s"]:
            self.event(f"run lock taken again after waiting {lock_info['wait_s']} s")
        parsed = parse_stream((folder / "stream.jsonl").read_text(encoding="utf-8", errors="replace"))
        stderr = (folder / "stderr.txt").read_text(encoding="utf-8", errors="replace")
        status, invalid = check_call(parsed, stderr, self.settings["expected_version"],
                                     tools=setup.get("tools", TOOLS), subagents_allowed=setup.get("subagents_allowed", False),
                                     denials_invalid=setup.get("denials_invalid", True))
        self.last_parsed = parsed
        if timed_out:
            status, invalid = "error", [f"call timed out after {self.settings['call_timeout']} s"]
        after = self.ws.listing()
        hidden = sorted(set(hidden_or_forbidden(before, after)) | set(forbidden_writes(parsed["files_written"])))
        if hidden:
            invalid.append(f"new hidden file(s) or CLAUDE.md / AGENTS.md: {', '.join(hidden[:10])}")
        shell = shell_check(parsed["uses"]) if setup.get("shell_check", True) else {"read_only": [], "invalid": []}
        invalid += [f"shell command that is not a read-only command of the list: {c}" for c in shell["invalid"]]
        outside = self.ws.discard_outside_lms(before)
        n_outside = sum(len(v) for v in outside.values())
        if n_outside:
            self.record["outside_lms_changes"].append({"call": number, **outside})
        result = parsed["result"] or {}
        summary = cost.summarize(result) if result else {}
        raw = result.get("total_cost_usd") if isinstance(result.get("total_cost_usd"), (int, float)) else None
        same_session = [c for c in self.record["calls"] if c.get("session_id") and
                        c.get("session_id") == result.get("session_id") and c.get("summary_raw")]
        share = per_call(summary, same_session[-1]["summary_raw"] if same_session else None) if summary else {}
        diff = share.get("usd") if isinstance(share.get("usd"), (int, float)) else None
        record = {
            "number": number, "kind": kind, "account": self.args.account, "started_at": now(), "wall_s": wall,
            "lock_released": lock_info["released"], "lock_wait_s": lock_info["wait_s"],
            "exit_code": code, "status": status, "invalid": invalid, "session_in": session_id,
            "session_id": result.get("session_id") or (parsed["init"] or {}).get("session_id"),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "claude_code_version": (parsed["init"] or {}).get("claude_code_version"),
            "api_key_source": (parsed["init"] or {}).get("apiKeySource"),
            "tools": (parsed["init"] or {}).get("tools"), "tool_counts": parsed["tool_counts"],
            "files_read": parsed["files_read"], "files_written": parsed["files_written"],
            "subagent_attempts": parsed["subagent_attempts"],
            "subagents_spawned": (result.get("subagent_stats") or {}).get("spawned"),
            "permission_denials": denied_tools(result.get("permission_denials") or []),
            "terminal_reason": result.get("terminal_reason"), "is_error": result.get("is_error"),
            "num_turns": result.get("num_turns"), "done_marker": said_done(parsed["final_text"]),
            "outside_lms_changes": n_outside, "hidden_files": hidden, "read_only_shell": shell["read_only"],
            "rate_limit": parsed["rate_limit"],
            "usd_raw": raw, "usd_diff": diff, "summary_raw": summary, "summary": share,
            "tokens_raw": {k: summary.get(k) for k in TOKEN_KEYS}, "tokens": {k: share.get(k) for k in TOKEN_KEYS},
        }
        self.record["calls"].append(record)
        if result:
            self.log_cost(record)
        self.event(f"call {number} finished: {status}, {wall} s" + (f"; invalid: {invalid}" if invalid else ""))
        return record

    def log_cost(self, call: dict, accepted: str = "") -> None:
        """One cost-log row per call with this call's share (W16); the cumulative total is in the note."""
        path = Path(self.args.cost_log)
        if not path.parent.is_dir():
            return
        share = dict(call["summary"])
        note = "; ".join(x for x in (share.pop("note", ""), f"account {self.args.account}",
                                      f"session total usd {call['usd_raw']} (tokens and usd are this call's share)") if x)
        stage = {"multiagent": "multi-agent"}.get(self.approach, self.approach)      # the stage names of cost.py
        cost.append_row(path, task=f"{self.approach}/{self.args.run_id}/call-{call['number']}", stage=stage,
                        model=MODEL, **share, run_id=self.args.run_id, repetition=self.args.repetition or "",
                        round=call["number"], role="refactor", accepted=accepted,
                        claude_code_version=call.get("claude_code_version") or "", note=note)

    # --- rounds ----------------------------------------------------------------------------------------------------
    def commit_round(self, k: int) -> dict:
        state_commit = self.ws.commit(f"round {k}")
        tag = f"exp/{self.approach}/{self.args.run_id}/r{k}"
        sha = tag_code(self.repo, self.record["start_sha"], self.ws.model / "lms", tag,
                       f"experiment {self.approach} {self.args.run_id} round {k}")
        entry = {"round": k, "call": len(self.record["calls"]), "state_commit": state_commit, "tag": tag,
                 "code_sha": sha}
        self.record["rounds"].append(entry)
        self.event(f"round {k}: {tag} = {sha[:12]}")
        return entry

    def measure(self, state_commit: str, code_sha: str, name: str, test_set: str,
                previous_best: Path | None) -> tuple[dict, Path]:
        out = self.out / name
        tree = self.ws.tree_for(state_commit, name.replace("/", "-"))
        self.event(f"measurement {name} ({test_set}) started")
        started = time.monotonic()
        measurement = self.toolkit.measure(self, tree, out, f"{self.args.run_id}-{name.replace('/', '-')}",
                                           code_sha, test_set, previous_best)
        facts = digest(measurement)
        facts["wall_s"] = round(time.monotonic() - started, 1)
        facts["folder"] = str(out.relative_to(self.out))
        shutil.rmtree(tree, ignore_errors=True)
        self.event(f"measurement {name}: status {facts['status']}, accepted {facts['round_accepted']}, "
                   f"successful {facts['run_successful']}, regressions {facts['regressions']}")
        return facts, out

    # --- the end -----------------------------------------------------------------------------------------------------
    def finish(self, outcome: str, valid: bool, reasons: list[str], extra: dict | None = None) -> int:
        r = self.record
        r.update(extra or {})
        r.update({"outcome": outcome, "valid": valid, "reasons": reasons, "finished_at": now(), "status": "finished"})
        self.save()
        self.append_runs_row()
        if valid and not self.args.keep_work:
            shutil.rmtree(self.ws.root, ignore_errors=True)
        self.log(f"outcome: {outcome}{' (INVALID, repeat the run)' if not valid else ''}"
                 + (f" — {'; '.join(reasons)}" if reasons else ""))
        return EXIT_DONE if valid else (EXIT_LIMIT if outcome == "discarded_limit" else EXIT_INVALID)

    def append_runs_row(self) -> dict:
        r = self.record
        calls, rounds = r["calls"], r["rounds"]
        best = r.get("best_facts") or {}
        tok = lambda key: sum((c["tokens"].get(key) or 0) for c in calls if c.get("tokens"))  # noqa: E731
        usd = lambda key: round(sum(c[key] for c in calls if c.get(key) is not None), 6)  # noqa: E731
        row = {
            "run_id": r["run_id"], "approach": r["approach"], "repetition": r.get("repetition") or "",
            "start_ref": r["start_ref"], "start_sha": r["start_sha"], "baseline": r["baseline"],
            "tests_modules": r.get("tests_modules") or "", "account": r["account"],
            "accounts_used": ";".join(r["accounts_used"]), "window_pct_start": r["window_pct_start"],
            "started_at": r["started_at"], "finished_at": r["finished_at"],
            "duration_s": round((dt.datetime.fromisoformat(r["finished_at"]) -
                                 dt.datetime.fromisoformat(r["started_at"])).total_seconds()),
            "outcome": r["outcome"], "valid": str(r["valid"]).lower(), "reasons": "; ".join(r["reasons"]),
            "run_successful": "" if best.get("run_successful") is None else str(best["run_successful"]).lower(),
            "calls": sum(1 for c in calls if c["status"] != "limit"), "code_rounds": len(rounds),
            "accepted_rounds": sum(1 for x in rounds if x.get("accepted") is True),
            "rejected_rounds": sum(1 for x in rounds if x.get("accepted") is False),
            "best_round": r.get("best_round", ""), "last_round": rounds[-1]["round"] if rounds else 0,
            "best_tag": r.get("best_tag", ""),
            "regressions_feedback": best.get("regressions_by_set", {}).get("feedback", ""),
            "regressions_heldout": best.get("regressions_by_set", {}).get("heldout", ""),
            "api_changed": "" if best.get("api_changed") is None else str(best["api_changed"]).lower(),
            "api_change_kind": best.get("api_change_kind") or "",
            "outside_lms_changes": sum(c["outside_lms_changes"] for c in calls),
            "subagents_spawned": sum(c.get("subagents_spawned") or 0 for c in calls),
            "subagent_attempts": sum(c.get("subagent_attempts") or 0 for c in calls),
            "permission_denials": sum(len(c.get("permission_denials") or []) for c in calls),
            "files_read": len({f for c in calls for f in c["files_read"]}),
            "files_changed": len({f for c in calls for f in c["files_written"]}),
            "feedback_lines_max": max((x.get("feedback_lines", 0) for x in rounds), default=0),
            "input_tokens": tok("input_tokens"), "output_tokens": tok("output_tokens"),
            "cache_read_tokens": tok("cache_read_tokens"), "cache_write_tokens": tok("cache_write_tokens"),
            "usd_raw": round(sum(max(c["usd_raw"] for c in calls if c.get("session_id") == s and c.get("usd_raw") is not None)
                                 for s in {c.get("session_id") for c in calls if c.get("usd_raw") is not None}), 6),
            "usd_diff": usd("usd_diff"),
            "usd_lost": round(sum(c["usd_diff"] or 0 for c in calls if c["status"] == "limit"), 6),
            "claude_s": round(sum(c["wall_s"] for c in calls), 1),
            # every measurement once: the same folder can be a round, "best", "round1" and "last" at the same time
            "measure_s": round(sum({f["folder"]: f.get("wall_s", 0) for f in [x.get("facts") or {} for x in rounds]
                                    + list(r["final"].values()) if f.get("folder")}.values()), 1),
            "claude_code_version": ";".join(sorted({c["claude_code_version"] for c in calls
                                                    if c.get("claude_code_version")})),
            "model": MODEL, "effort": r["effort"], "image_id": r["image_id"], "note": r.get("note", ""),
        }
        start = r.get("baseline_primary") or {}
        r1 = (r["final"].get("round1") or {}).get("primary") or {}
        last = (r["final"].get("last") or {}).get("primary") or {}
        for m in PRIMARY:
            row[f"{m}_start"] = start.get(m, "")
            row[f"{m}_best"] = (best.get("primary", {}).get(m) or {}).get("after", "")
            row[f"{m}_best_delta"] = (best.get("primary", {}).get(m) or {}).get("delta", "")
            row[f"{m}_r1"] = (r1.get(m) or {}).get("after", "")
            row[f"{m}_last"] = (last.get(m) or {}).get("after", "")
        row = {k: ("" if v is None else v) for k, v in row.items()}
        unknown = set(row) - set(RUNS_COLUMNS)
        if unknown:
            raise ValueError(f"unknown runs.csv columns: {sorted(unknown)}")
        path = Path(self.args.runs_csv) if self.args.runs_csv else self.out_root / "runs.csv"
        new = not path.exists() or path.stat().st_size == 0
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=RUNS_COLUMNS)
            if new:
                writer.writeheader()
            writer.writerow({c: row.get(c, "") for c in RUNS_COLUMNS})
        return row


# --- command line --------------------------------------------------------------------------------------------------

def add_arguments(parser) -> None:
    p = parser.add_argument
    p("--start-ref", required=True, help="git ref of the starting code, e.g. v0-ai-baseline or ce03f54")
    p("--baseline", required=True, help="analysis folder of the starting code (summary.json, tests.csv, flaky.txt)")
    p("--tests-modules", dest="modules", help="only the test files of these modules, e.g. 1-14 (pilot code)")
    p("--account", required=True, help="label of the experiment account (W14); recorded, never a secret")
    p("--run-id", required=True, help="name of the run, e.g. s01; used in the tag exp/<approach>/<run-id>/r<k>")
    p("--window-pct", type=float, help=f"5-hour window of the account in %% from /usage; at most {WINDOW_LIMIT_PCT:g} (W6)")
    p("--repetition", default="", help="repetition number for the statistics (W7)")
    p("--env-file", default=str(REPO / ".env"), help="token file of the account, passed to docker (never read)")
    p("--image", default=DEFAULT_IMAGE)
    p("--effort", default=DEFAULT_EFFORT)
    p("--expected-version", default=EXPECTED_CLAUDE_VERSION, help="Claude Code version the image must report")
    p("--compact-window", type=int, default=DEFAULT_COMPACT_WINDOW,
      help=f"tokens of context at which Claude Code compacts ({COMPACT_ENV}); recorded in run.json "
           f"(default %(default)s)")
    p("--tests", default=str(REPO / DEFAULT_TESTS))
    p("--interface", help="use this INTERFACE.md instead of running experiments/make_interface.py")
    p("--prompts", default=str(EXPERIMENTS / "prompts"))
    p("--out-root", default=str(REPO / "results" / "experiments"))
    p("--runs-csv", help="default <out-root>/runs.csv")
    p("--cost-log", default=str(REPO / "metrics" / "cost-log.csv"))
    p("--work-root", help="work folder outside the repository (default: a new temporary folder)")
    p("--keep-work", action="store_true", help="keep the work folder after a valid run")
    p("--call-timeout", type=int, default=4 * 3600, help="seconds per Claude Code call")
    p("--test-timeout", type=int, default=7200, help="seconds per test set")
    p("--lock-file", default=str(REPO / ".run.lock"))
    p("--wait", type=int, default=21600, help="seconds to wait for the run lock")
    p("--poll", type=int, default=60)
    p("--local", action="store_true", help="no docker: the steps run here (inside the image, or in the tests)")
    p("--claude-command", help="command used instead of `claude` with --local (the fake Claude of the tests)")
    p("--repo", default=str(REPO), help=argparse.SUPPRESS)
    p("--dry-run", action="store_true", help="check the inputs, print the Claude Code command and stop")


def answered_calls(record: dict) -> int:
    """Calls that count for the W4 limit (a call cut by the usage limit is sent again and counts once)."""
    return sum(1 for c in record["calls"] if c["status"] != "limit")


def dry_run(run: Run, args: list[str] | None = None, env: dict | None = None, mounts: tuple = ()) -> int:
    """Check the inputs and print the Claude Code command. A runner with its own command (Multi-Agent) passes its
    arguments, extra environment and extra mounts (``-v <name>:<path>[:ro]``); the default is the Single command."""
    run.check_inputs()
    sha = resolve_commit(run.repo, run.args.start_ref)
    print(f"start:     {run.args.start_ref} = {sha}")
    print(f"baseline:  {run.baseline}")
    print(f"output:    {run.out}")
    print(f"lock:      {run.args.lock_file}")
    print("claude:    docker run --rm --env-file <env-file> -e CLAUDE_CONFIG_DIR=/session "
          + " ".join(f"-e {k}={v}" for k, v in {**run.claude_env(), **(env or {})}.items())
          + " -v <work>/model:/work -v <work>/session:/session " + "".join(f"{m} " for m in mounts)
          + f"-w /work {run.settings['image']} claude "
          + " ".join(args if args is not None else claude_args("<prompt>", run.settings["effort"], None)))
    return EXIT_DONE
