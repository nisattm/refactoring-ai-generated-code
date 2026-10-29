# Measurement Environment (Docker)

All quality analyses, tests, resource measurements and Claude Code runs happen in the same Linux Docker container, so results do not depend on whose laptop was used. A container is also required because memray and mutmut do not run natively on Windows ([`metrics.md`](metrics.md#resource-measurement-protocol)), and because every experiment run must start clean (no Claude Code memory, settings or history from earlier runs).

The image contains Python 3.14, the LMS stack (FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.x, httpx), the measurement tools and Claude Code.

Files: [`../Dockerfile`](../Dockerfile), [`../docker/requirements.in`](../docker/requirements.in), [`../docker/requirements.lock`](../docker/requirements.lock), [`../docker/check-tools.sh`](../docker/check-tools.sh), [`../docker/check-claude.sh`](../docker/check-claude.sh).

## 1. Install Docker (once)

**Windows**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and choose the **WSL 2** backend when asked.
2. Restart, open Docker Desktop, and wait until it says *Engine running*.
3. In a terminal (PowerShell or Git Bash): `docker --version`

**macOS / Linux:** install Docker Desktop (macOS) or Docker Engine (Linux), then `docker --version`.

## 2. Build the image

From the repository root:

```bash
docker build -t refactoring-env .
```

The first build downloads the base images and tools and takes several minutes.

## 3. Check the tools

```bash
docker run --rm refactoring-env check-tools
```

Every line should start with `OK`, and the last line should be `All tools OK`. The script also prints the Python version, CPU, number of cores and RAM: **record these** together with the results.

## 4. Pinning versions (once, by one person)

Before–after comparisons are only valid if every tool has the same version for the whole project ([`metrics.md`](metrics.md)).

**Status (30 October 2026):** done. `docker/requirements.lock` holds the exact versions from the first Python 3.14 build, and the `Dockerfile` pins Python 3.14.10, jscpd 5.4.2 and Claude Code 2.1.308. Everyone builds with `docker build -t refactoring-env .` and gets the same versions.

To pin again (only after a decision to change versions):
1. Empty `docker/requirements.lock`, build, then write the exact versions:
   ```bash
   docker run --rm -v "$PWD:/work" refactoring-env sh -c "pip freeze > docker/requirements.lock"
   ```
   (In Windows PowerShell use `${PWD}` instead of `$PWD`. The file is written inside the container, so its encoding is correct on every system.)
2. In the `Dockerfile`, set `PYTHON_VERSION`, `JSCPD_VERSION` and `CLAUDE_CODE_VERSION` to the values printed by `check-tools`.
3. Open a pull request with both files; everyone rebuilds.

Python version: 3.14 (decision of 29 October). Changing it requires a new lock file (empty `requirements.lock`, build, freeze again) and a decision record. Claude Code's automatic updates are switched off in the image (`DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`).

## 4a. Claude Code with the Pro subscription (once per person)

Claude Code's `--bare` mode does not work with a subscription login, so clean runs come from a fresh container instead. The container gets the Pro login only through a long-lived token in the environment variable `CLAUDE_CODE_OAUTH_TOKEN` ([Claude Code authentication](https://code.claude.com/docs/en/authentication.md#generate-a-long-lived-token): one-year token, Pro or higher, model requests only).

1. Create the token inside the container (no installation on Windows needed):
   ```bash
   docker run --rm -it refactoring-env claude setup-token
   ```
   Open the printed URL in your browser, log in with the Pro account, copy the code shown there and paste it **into the terminal**. The terminal then prints the token, a long line starting with `sk-ant-oat01-`. The token is printed once. The browser code (it contains a `#`) is not the token and does not work in `.env`.
2. In the repository root create a file named `.env` with one line:
   ```
   CLAUDE_CODE_OAUTH_TOKEN=<the token>
   ```
   One line, no spaces around `=`, no quotes. `.env` is in `.gitignore`. **Never commit it or send it to anyone**: the token gives access to the subscription.
3. Check that Claude Code works in a clean container:
   ```bash
   docker run --rm --env-file .env -v "$PWD:/work" refactoring-env check-claude
   ```
   The last line should be `Claude Code + Pro login OK`. The check confirms that the container starts without any `~/.claude` state, that no API key is set, that the token has the expected format (without printing it), and that the test call used only `claude-sonnet-5-5`. A `401 Invalid bearer token` means the token in `.env` is wrong (usually the browser code instead of the token, or a line break inside it). It saves the JSON answer to `docker/claude-sample.json`, which shows the exact fields available for the cost log.

Every experiment run uses `docker run --rm --env-file .env ...`, so each run starts in a new container and nothing local (login state, settings, memory, history) is carried over to the next run. One thing is shared: the prompt cache on Anthropic's servers (up to 1 hour), which changes the token mix of later runs; see [`cost-tracking.md`](cost-tracking.md#things-to-know-when-comparing-approaches).

## 5. Daily use

Mount the repository into the container:

```bash
# macOS, Linux, Git Bash
docker run --rm -it -v "$PWD:/work" refactoring-env

# Windows PowerShell
docker run --rm -it -v "${PWD}:/work" refactoring-env
```

You are now in `/work` (the repository). Examples:

```bash
radon cc -s dataset/lms/generated
analyze_code_quality dataset/lms/generated --format json --output pyexamine.json
python -m pytest dataset/lms/tests/feedback
```

Files you create in `/work` appear in your repository folder.

## 6. Rules for resource measurements

- Run all measurements of a comparison **on the same machine**; record its CPU and RAM (`check-tools` prints them).
- Give the container fixed resources so the operating system does not move work around:
  ```bash
  docker run --rm -it --cpuset-cpus=0,1 --memory=4g -v "$PWD:/work" refactoring-env
  ```
  Keep the same `--cpuset-cpus` and `--memory` values for every run; write them in the results.
- Close other heavy programs; laptops plugged in.
- Timing/CPU runs and memory profiling (memray, tracemalloc) are separate runs ([`metrics.md`](metrics.md#resource-measurement-protocol)).
- On Windows, Docker runs inside a WSL 2 virtual machine. Docker Desktop's resource limits (Settings → Resources) also apply; do not change them during the experiments.

## 7. Tools

| Tool | Purpose | Installed from | Status |
| --- | --- | --- | --- |
| radon, complexipy | Size, CC, MI, Halstead; cognitive complexity | PyPI | in image |
| PyExamine | Code, structural and architectural smells; design metrics | PyPI package `code-quality-analyzer`, command `analyze_code_quality` (installation page of the [PyExamine documentation](https://python-smell.readthedocs.io/en/latest/installation.html); source: [GitHub](https://github.com/KarthikShivasankar/python_smells_detector)) | in image |
| ruff, pylint, vulture | Linters, logic smells, dead code | PyPI | in image |
| jscpd | Duplication | npm | in image |
| pytest, hypothesis, coverage, mutmut | Tests, property-based tests, branch coverage, mutation score | PyPI | in image |
| pyperf, psutil, memray, pytest-memray, codecarbon | Time, CPU, RAM, allocations, energy | PyPI | in image |
| FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.x, httpx | LMS application stack | PyPI | in image |
| Claude Code | Code generation and the three approaches | Native installer, version pinned, auto-update off | in image |
| **DPy** | Design and implementation smells | Designite ([product page](https://www.designite-tools.com/products-dpy)) | **Not in image; not verified** |

### PyExamine configuration

Thresholds are set in a YAML file passed with `--config`; the paper's example uses 45 lines for Long Method and 15 methods for Large Class (Shivashankar & Martini, MSR 2025, Section IV.A). Our thresholds are decided in the metrics meeting and the file is stored in the repository.

### DPy (open item)

DPy is not a PyPI package. The MSR 2025 paper says the replication package contains the tool and usage instructions, and a notebook by one of the authors downloads the tool automatically, but we could not verify the download address, the supported operating systems or the license terms. Next step: download it from the product page, check whether a Linux version and an academic license exist, and add it to the `Dockerfile` if so. Until then, the smells assigned to DPy in [`smell-catalog.md`](smell-catalog.md) (S02, S17, S18) are covered by PyExamine where possible.
