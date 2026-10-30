# Scripts

| Script | Week | Purpose |
| --- | --- | --- |
| Code Quality Analyzer | 4 | Runs the tools in [`../docs/metrics.md`](../docs/metrics.md) on a code folder and writes CSV rows per function, class, module, level and project |
| Resource benchmark | 4 | Runs workloads W1–W3 and measures time, CPU and memory with the protocol in [`../docs/metrics.md`](../docs/metrics.md#resource-measurement-protocol) |
| Single / Iterative runner | 5 | Runs the Single (`claude -p`) and Iterative (one Claude Code session) approaches, sends test feedback, logs tokens and time |
| Multi-Agent runner | 6 | Runs the Analyzer → Refactoring → Reviewer flow with Claude Code subagents |
| `gen_tests.py` | 3 | Generates `cases/<module>.md` and the `feedback/` and `heldout/` test files of one module from its case list in `dataset/lms/tests/spec/` (`python scripts/gen_tests.py <spec.py> <tests dir>`), applying the split rule of [`../dataset/lms/tests/README.md`](../dataset/lms/tests/README.md). Exit code 0; a duplicate or malformed case ID stops it with an error (exit code 1) |
| `test_hashes.py` | 3 | SHA-256 of every test file, for test protection ([`../docs/testing.md`](../docs/testing.md#test-protection)): `record <tests> <hashes.json>` stores them, `verify <tests> <hashes.json>` compares. Exit codes: 0 unchanged, 1 a file changed, was added or removed (or the test folder is missing), 2 usage error |
| `run_tests.py` | 3 | Test runner: hashes the tests, runs `feedback/` and `heldout/` in separate pytest processes with the code folder on `PYTHONPATH` (tests outside it), hashes again, writes `<out>/<set>.json` (counts, failed case IDs) and `<out>/run.json` (`python scripts/run_tests.py --code <folder> [--set feedback\|heldout\|both] [--out <dir>] [--baseline <hashes.json>]`). Exit codes: 0 all passed, 1 failures or errors, 2 usage problem, 3 test files changed (invalid run) |
| `cost.py` | 3 | Logs the JSON result of each Claude Code call (`--output-format json`) to `metrics/cost-log.csv`: tokens, time, equivalent cost; marks runs with an error or another model as invalid ([`../docs/cost-tracking.md`](../docs/cost-tracking.md)) |

All runners use Claude Code with the Pro subscription, the fixed model (Claude Sonnet 5.5) and the fixed effort level ([`../docs/approaches.md`](../docs/approaches.md)). No Anthropic API key is used.

The analyzer, the benchmark and the approach runners are added from Week 4. Tests of the scripts: `python -m pytest scripts/tests` inside the container ([`../docs/environment.md`](../docs/environment.md)).
