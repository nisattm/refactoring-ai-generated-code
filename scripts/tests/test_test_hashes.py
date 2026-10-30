import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_hashes  # noqa: E402


def _tree(root: Path) -> Path:
    (root / "feedback").mkdir(parents=True)
    (root / "conftest.py").write_text("x = 1\n", encoding="utf-8")
    (root / "feedback" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    return root


def test_compute_uses_relative_posix_paths(tmp_path):
    hashes = test_hashes.compute(_tree(tmp_path / "t"))
    assert sorted(hashes) == ["conftest.py", "feedback/test_a.py"]
    assert all(len(h) == 64 for h in hashes.values())


def test_caches_are_ignored(tmp_path):
    root = _tree(tmp_path / "t")
    before = test_hashes.compute(root)
    (root / "feedback" / "__pycache__").mkdir()
    (root / "feedback" / "__pycache__" / "test_a.cpython-314.pyc").write_bytes(b"\0")
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache" / "v").write_text("x", encoding="utf-8")
    assert test_hashes.compute(root) == before


def test_compare_reports_changed_added_removed(tmp_path):
    root = _tree(tmp_path / "t")
    before = test_hashes.compute(root)
    (root / "conftest.py").write_text("x = 2\n", encoding="utf-8")
    (root / "feedback" / "test_b.py").write_text("", encoding="utf-8")
    (root / "feedback" / "test_a.py").unlink()
    diff = test_hashes.compare(before, test_hashes.compute(root))
    assert diff == {"changed": ["conftest.py"], "added": ["feedback/test_b.py"],
                    "removed": ["feedback/test_a.py"]}
    assert not test_hashes.is_unchanged(diff)


def test_cli_record_and_verify(tmp_path):
    root = _tree(tmp_path / "t")
    store = tmp_path / "hashes.json"
    assert test_hashes.main(["record", str(root), str(store)]) == 0
    assert len(json.loads(store.read_text(encoding="utf-8"))) == 2
    assert test_hashes.main(["verify", str(root), str(store)]) == 0
    (root / "conftest.py").write_text("changed\n", encoding="utf-8")
    assert test_hashes.main(["verify", str(root), str(store)]) == 1
