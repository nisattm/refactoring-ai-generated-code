"""Serving of the web interface (LIB-UI-GEN-01, LIB-UI-GEN-02) and its screen registry (WEB_INTERFACE.md, section 2)."""

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

import lms
from lms.api import app as app_module

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_index_is_served_at_ui(client):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == (WEB / "index.html").read_text(encoding="utf-8")


def test_ui_without_slash_redirects(client):
    response = client.get("/ui", follow_redirects=False)
    assert response.status_code in (301, 307)
    assert response.headers["location"].endswith("/ui/")


@pytest.mark.parametrize("name,kind", [("app.js", "javascript"), ("style.css", "css"), ("screens/index.js", "javascript")])
def test_files_are_served_by_path(client, name, kind):
    response = client.get(f"/ui/{name}")
    assert response.status_code == 200
    assert kind in response.headers["content-type"]
    assert response.text == (WEB / name).read_text(encoding="utf-8")


def test_unknown_file_is_not_found(client):
    response = client.get("/ui/missing.js")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_path_traversal_is_refused(client):
    response = client.get("/ui/..%2Frequirements.txt")
    assert response.status_code == 404


def test_api_paths_are_unchanged(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/calendar/days/2026-10-29").json() == {
        "date": "2026-10-29",
        "working_day": False,
        "reason": "holiday",
    }
    paths = client.get("/openapi.json").json()["paths"]
    assert not any(path.startswith("/ui") for path in paths)


def test_application_starts_without_web_folder(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "WEB_DIR", tmp_path / "missing")
    client = TestClient(lms.create_app(settings), raise_server_exceptions=False)
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/calendar/days/2026-11-02").status_code == 200
    response = client.get("/ui/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_nothing_is_loaded_from_the_internet():
    for path in WEB.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".js", ".css"}:
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"(?:src|href)=[\"']https?:", text), path
            assert "@import" not in text and "url(http" not in text, path
            assert not re.search(r"import\s[^;]*from\s+[\"']https?:", text), path
            assert not re.search(r"\bimport\(\s*[\"']https?:", text), path


def test_no_browser_dialogs_are_used():
    for path in WEB.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?<![\w.])(alert|confirm|prompt)\(", text), path
        assert "window.alert" not in text and "window.confirm" not in text and "window.prompt" not in text, path


def _section2_screens():
    spec = ROOT / "WEB_INTERFACE.md"
    if not spec.exists():
        pytest.skip("WEB_INTERFACE.md is not in the repository")
    text = spec.read_text(encoding="utf-8")
    section = text.split("## 2. Screens of modules 1–14", 1)[1].split("## 3.", 1)[0]
    rows = re.findall(r"^\| (LIB-UI-[A-Z]+-\d\d) \| \*\*(.+?)\.?\*\*", section, flags=re.MULTILINE)
    assert len(rows) == 31
    return rows


def test_every_screen_of_section_2_has_its_route_and_heading():
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (WEB / "screens").glob("*.js"))
    for requirement, name in _section2_screens():
        route = requirement.removeprefix("LIB-UI-").lower()
        assert f'id: "{route}"' in sources, requirement
        assert f'title: "{name}"' in sources, requirement


def _section3_screens(first, last):
    """Screens of the sections 3.<first> to 3.<last> of WEB_INTERFACE.md."""
    spec = ROOT / "WEB_INTERFACE.md"
    if not spec.exists():
        pytest.skip("WEB_INTERFACE.md is not in the repository")
    text = spec.read_text(encoding="utf-8")
    section = text.split("## 3. Screens of modules 15–29", 1)[1]
    parts = re.split(r"^### 3\.(\d+) ", section, flags=re.MULTILINE)
    rows = []
    for number, body in zip(parts[1::2], parts[2::2]):
        if first <= int(number) <= last:
            rows += re.findall(r"^\| (LIB-UI-[A-Z]+-\d\d) \| \*\*(.+?)\.?\*\*", body, flags=re.MULTILINE)
    return rows


def test_every_screen_of_sections_3_1_to_3_7_has_its_route_and_heading():
    rows = _section3_screens(1, 7)
    assert len(rows) == 47
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (WEB / "screens").glob("*.js"))
    for requirement, name in rows:
        route = requirement.removeprefix("LIB-UI-").lower()
        assert f'id: "{route}"' in sources, requirement
        assert f'title: "{name}"' in sources, requirement


def test_screens_of_modules_15_to_21_are_registered_in_the_menu():
    index = (WEB / "screens" / "index.js").read_text(encoding="utf-8")
    for module in ("Study rooms", "Equipment loans", "Digital resources", "Interlibrary loans", "Staff and shifts", "Events", "Course reserves"):
        assert f'"{module}"' in index
    for name in ("rooms", "equipment", "digital", "ill", "staff", "events", "courses"):
        assert (WEB / "screens" / f"{name}.js").is_file()
        assert (WEB / f"{name}.css").is_file()


def test_every_screen_of_sections_3_8_to_3_14_has_its_route_and_heading():
    rows = _section3_screens(8, 14)
    assert len(rows) == 42
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (WEB / "screens").glob("*.js"))
    for requirement, name in rows:
        route = requirement.removeprefix("LIB-UI-").lower()
        assert f'id: "{route}"' in sources, requirement
        assert f'title: "{name}"' in sources, requirement


def test_screens_of_modules_22_to_28_are_registered_in_the_menu():
    index = (WEB / "screens" / "index.js").read_text(encoding="utf-8")
    modules = {
        "Donations": "donations",
        "Preservation": "preservation",
        "Inventory counts": "inventory",
        "Purchase suggestions": "suggestions",
        "Reading programs": "programs",
        "Announcements and messages": "messaging",
        "Member cards and building access": "access",
    }
    for module, name in modules.items():
        assert f'"{module}"' in index
        assert (WEB / "screens" / f"{name}.js").is_file()
        assert (WEB / f"{name}.css").is_file()
