# Scripts

| Script | Week | Purpose |
| --- | --- | --- |
| Code Quality Analyzer | 4 | Runs the tools in [`../docs/metrics.md`](../docs/metrics.md) on a code folder and writes CSV rows per function, class, module, level and project |
| Test runner | 4 | Runs the feedback and held-out test sets, checks test-file hashes and records results |
| Resource benchmark | 4 | Runs workloads W1–W3 and measures time, CPU and memory with the protocol in [`../docs/metrics.md`](../docs/metrics.md#resource-measurement-protocol) |
| Single / Iterative runner | 5 | Runs the Single (`claude -p`) and Iterative (one Claude Code session) approaches, sends test feedback, logs tokens and time |
| Multi-Agent runner | 6 | Runs the Analyzer → Refactoring → Reviewer flow with Claude Code subagents |
| `cost.py` | 3 | Logs the JSON result of each Claude Code call (`--output-format json`) to `metrics/cost-log.csv`: tokens, time, equivalent cost; marks runs with an error or another model as invalid ([`../docs/cost-tracking.md`](../docs/cost-tracking.md)) |

All runners use Claude Code with the Pro subscription, the fixed model (Claude Sonnet 5.5) and the fixed effort level ([`../docs/approaches.md`](../docs/approaches.md)). No Anthropic API key is used.

The other scripts are added from Week 4. Tests of the scripts: `python -m pytest scripts/tests` inside the container ([`../docs/environment.md`](../docs/environment.md)).
