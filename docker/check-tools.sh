#!/usr/bin/env bash
# Checks that every measurement tool is installed and runs on a small sample.
# Usage inside the container: check-tools
# Prints one line per tool: OK / FAIL, and the environment info to record.
set -u

fails=0
check() {  # check <name> <command...>
    local name=$1; shift
    if out=$("$@" 2>&1); then
        printf 'OK    %-22s %s\n' "$name" "$(printf '%s' "$out" | head -n 1)"
    else
        printf 'FAIL  %-22s %s\n' "$name" "$(printf '%s' "$out" | tail -n 1)"
        fails=$((fails + 1))
    fi
}

echo "== Environment (record in generation-log / metrics)"
python - <<'PY'
import os, platform, sys
print("python   ", sys.version.split()[0])
print("platform ", platform.platform())
print("machine  ", platform.machine())
print("cpus     ", os.cpu_count())
try:
    import psutil
    print("ram_gb   ", round(psutil.virtual_memory().total / 2**30, 1))
except Exception as exc:  # psutil is checked below as well
    print("ram_gb    unknown:", exc)
PY
grep -m1 'model name' /proc/cpuinfo 2>/dev/null | sed 's/^/cpu       /'

# Sample code with a few smells (long condition, magic number, mutable default, unused import, duplicate block)
tmp=$(mktemp -d)
mkdir -p "$tmp/pkg" "$tmp/tests"
cat > "$tmp/pkg/__init__.py" <<'PY'
PY
cat > "$tmp/pkg/sample.py" <<'PY'
import os


def fee(days, kind, history=[]):
    history.append(days)
    if days > 0 and kind == "student" and days < 100 and len(history) > 0 or days > 365:
        return days * 0.5
    if days > 0:
        return days * 1.0
    return 0


class Report:
    def total(self, items):
        s = 0
        for i in items:
            if i > 0:
                if i < 1000:
                    s += i
        return s

    def total_again(self, items):
        s = 0
        for i in items:
            if i > 0:
                if i < 1000:
                    s += i
        return s
PY
cat > "$tmp/pkg/api.py" <<'PY'
# Minimal version of the LMS stack: FastAPI + Pydantic v2 + SQLAlchemy 2.x + SQLite
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))


class BookIn(BaseModel):
    title: str


engine = create_engine("sqlite:///./lms_check.db")
Base.metadata.create_all(engine)
app = FastAPI()


@app.post("/books", status_code=201)
def add_book(book: BookIn) -> dict:
    with Session(engine) as s:
        row = Book(title=book.title)
        s.add(row)
        s.commit()
        return {"id": row.id, "title": row.title}
PY
cat > "$tmp/tests/test_api.py" <<'PY'
from fastapi.testclient import TestClient
from pkg.api import app


def test_add_book():
    r = TestClient(app).post("/books", json={"title": "Dune"})
    assert r.status_code == 201 and r.json()["title"] == "Dune"
PY
cat > "$tmp/tests/test_sample.py" <<'PY'
from hypothesis import given, strategies as st
from pkg.sample import Report, fee


def test_fee():
    assert fee(2, "standard") == 2.0


@given(st.lists(st.integers(min_value=1, max_value=999)))
def test_total(xs):
    assert Report().total(xs) == sum(xs)
PY
# mutmut 3 needs to know which code to mutate
cat > "$tmp/setup.cfg" <<'CFG'
[mutmut]
source_paths=pkg/
CFG

echo
echo "== Tools"
cd "$tmp" || exit 1
export PYTHONPATH="$tmp"
check radon               radon cc -s pkg
check complexipy          complexipy pkg
check pyexamine           analyze_code_quality pkg --type code
check ruff                ruff check --select F401,B006,PLR2004,SIM --exit-zero pkg
check pylint              pylint --exit-zero --disable=C pkg
check vulture             bash -c 'vulture pkg || [ $? -eq 3 ]'   # exit 3 = dead code found
check jscpd               jscpd --min-lines 3 --min-tokens 10 --silent pkg
check pytest+hypothesis   python -m pytest -q
check coverage            bash -c 'coverage run --branch -m pytest -q && coverage report'
check mutmut              bash -c 'mutmut --help >/dev/null && python -c "import importlib.metadata as m; print(m.version(\"mutmut\"))"'
check pyperf              python -m pyperf timeit --fast -q -s 'from pkg.sample import fee' 'fee(3, "student")'
check psutil              python -c 'import psutil; print(psutil.__version__, psutil.Process().memory_info().rss)'
check memray              bash -c 'memray run -q -o m.bin -m pytest -q && memray stats m.bin | head -n 3'
check pytest-memray       python -m pytest -q --memray
check codecarbon          python -c 'import codecarbon; print(codecarbon.__version__)'
check lms-stack           python -c 'import fastapi, pydantic, sqlalchemy, uvicorn, httpx, sqlite3; print("fastapi", fastapi.__version__, "pydantic", pydantic.VERSION, "sqlalchemy", sqlalchemy.__version__, "sqlite", sqlite3.sqlite_version)'
check uvicorn             bash -c 'timeout 5 uvicorn pkg.api:app --port 8765 >/dev/null 2>&1 & sleep 3; python -c "import httpx; r = httpx.post(\"http://127.0.0.1:8765/books\", json={\"title\": \"x\"}); print(r.status_code); assert r.status_code == 201"'
check node                node --version
check claude-code         claude --version

echo
echo "== CodeCarbon inside Docker (does it measure, or only estimate?)"
python - <<'PY' 2>&1 | grep -v -i "^\s*$" | tail -n 15
import logging
from codecarbon import EmissionsTracker
t = EmissionsTracker(save_to_file=False, log_level="info", measure_power_secs=1)
t.start()
sum(i * i for i in range(30_000_000))
kg = t.stop()
print(f"RESULT emissions_kg={kg}")
PY

echo
echo "== Python package versions"
python - <<'PY'
from importlib.metadata import version, PackageNotFoundError
for p in ["radon", "complexipy", "code-quality-analyzer", "ruff", "pylint", "vulture",
          "pytest", "hypothesis", "coverage", "mutmut", "pyperf", "psutil", "memray",
          "pytest-memray", "codecarbon", "fastapi", "uvicorn", "pydantic",
          "sqlalchemy", "httpx"]:
    try:
        print(f"{p:24} {version(p)}")
    except PackageNotFoundError:
        print(f"{p:24} NOT INSTALLED")
PY
printf '%-24s %s\n' jscpd "$(jscpd --version 2>/dev/null)"
printf '%-24s %s\n' claude-code "$(claude --version 2>/dev/null)"

rm -rf "$tmp"
echo
if [ "$fails" -eq 0 ]; then echo "All tools OK"; else echo "$fails tool(s) FAILED"; fi
exit "$fails"
