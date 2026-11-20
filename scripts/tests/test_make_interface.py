"""Tests of experiments/make_interface.py (ADR 004, W3): sections 1–4 of the requirements, verbatim."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "experiments" / "make_interface.py"
sys.path.insert(0, str(REPO / "experiments"))
import make_interface  # noqa: E402

DOC = (
    "# Title\n\n**Status:** draft. Tests are written from this document.\n\n---\n\n"
    "## 1. Purpose\n\nText one.\n\n### 1.1 Sub\n\nMore.\n\n"
    "## 2. Constraints\n\n```text\n## 7. Not a heading inside a fence\n```\n\n"
    "## 3. Rules\n\n| a | b |\n\n"
    "## 4. Interface\n\n```python\ndef create_app(): ...\n```\n\nLast line of 4.\n\n---\n\n"
    "## 5. Module 1\n\nNot copied.\n\n## 6. Module 2\n\nNot copied.\n"
)
EXPECTED = (
    "## 1. Purpose\n\nText one.\n\n### 1.1 Sub\n\nMore.\n\n"
    "## 2. Constraints\n\n```text\n## 7. Not a heading inside a fence\n```\n\n"
    "## 3. Rules\n\n| a | b |\n\n"
    "## 4. Interface\n\n```python\ndef create_app(): ...\n```\n\nLast line of 4.\n"
)


def run(tmp_path: Path, text: str | bytes) -> tuple[int, bytes, str]:
    req, out = tmp_path / "REQUIREMENTS.md", tmp_path / "INTERFACE.md"
    req.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    proc = subprocess.run([sys.executable, str(SCRIPT), "--requirements", str(req), "--out", str(out)],
                          capture_output=True, text=True, check=False)
    return proc.returncode, out.read_bytes() if out.exists() else b"", proc.stderr


def test_copies_sections_1_to_4_only(tmp_path):
    code, out, _ = run(tmp_path, DOC)
    assert code == 0
    assert out.decode("utf-8") == EXPECTED


def test_crlf_line_endings_are_kept(tmp_path):
    code, out, _ = run(tmp_path, DOC.replace("\n", "\r\n"))
    assert code == 0
    assert out == EXPECTED.replace("\n", "\r\n").encode("utf-8")


def test_non_ascii_text_is_kept_byte_for_byte(tmp_path):
    doc = DOC.replace("Text one.", "Öğrenci – 14 gün, 2 TL ≥ 50")
    code, out, _ = run(tmp_path, doc)
    assert code == 0 and "Öğrenci – 14 gün, 2 TL ≥ 50".encode("utf-8") in out


def test_same_input_gives_same_output(tmp_path):
    first = run(tmp_path, DOC)[1]
    second = run(tmp_path, DOC)[1]
    assert first == second


@pytest.mark.parametrize("doc, message", [
    (DOC.replace("## 3. Rules", "## Rules"), "missing section heading(s): ## 3."),
    (DOC.replace("## 5. Module 1", "## Module 1"), "missing section heading(s): ## 5."),
    (DOC.replace("## 6. Module 2", "## 2. Again"), "appears twice"),
    (DOC.replace("## 1. Purpose", "## 9. Purpose").replace("## 6. Module 2", "## 1. Late"), "not in order"),
    (DOC.replace("```\n\nLast", "\n\nLast"), "not closed"),
])
def test_changed_document_fails_loudly(tmp_path, doc, message):
    code, out, err = run(tmp_path, doc)
    assert code == 1 and message in err and out == b""


def test_missing_file_fails(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--requirements", str(tmp_path / "nope.md"),
                           "--out", str(tmp_path / "INTERFACE.md")], capture_output=True, text=True, check=False)
    assert proc.returncode == 1 and not (tmp_path / "INTERFACE.md").exists()


def test_usage_error_exit_code_2():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False)
    assert proc.returncode == 2


@pytest.mark.parametrize("path", ["dataset/lms/requirements.md", "dataset/lms/generated/REQUIREMENTS.md"])
def test_real_requirements(path):
    """The real document: starts with section 1, ends with the last requirement of section 4 (LIB-IF-10)."""
    with (REPO / path).open(encoding="utf-8", newline="") as handle:
        text = handle.read()
    result = make_interface.extract(text)
    assert result.startswith("## 1. Purpose and scope")
    assert "## 4. Fixed service interface" in result and "LIB-IF-10" in result
    assert "## 5." not in result and "Tests are written" not in result
    assert result in text  # verbatim: one contiguous piece of the document
