# Scripts

| Script | Week | Purpose |
| --- | --- | --- |
| Code Quality Analyzer | 4 | Runs the tools in [`../docs/metrics.md`](../docs/metrics.md) on a code folder and writes CSV rows per function, class, module, level and project |
| Test runner | 4 | Runs the feedback and held-out test sets, checks test-file hashes and records results |
| Resource benchmark | 4 | Runs workloads W1–W3 and measures time, CPU and memory with the protocol in [`../docs/metrics.md`](../docs/metrics.md#resource-measurement-protocol) |
| Single / Iterative runner | 5 | Runs the Single (`claude -p`) and Iterative (one Claude Code session) approaches, sends test feedback, logs tokens and time |
| Multi-Agent runner | 6 | Runs the Analyzer → Refactoring → Reviewer flow with Claude Code subagents |
| Usage collector | 5 | Collects token counts, time and equivalent cost per run from Claude Code (OpenTelemetry or JSON output; chosen in the pilot) |

All runners use Claude Code with the Pro subscription, the fixed model (Claude Sonnet 5.5) and the fixed effort level ([`../docs/approaches.md`](../docs/approaches.md)). No Anthropic API key is used.

To be added from Week 4.
