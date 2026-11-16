# Metrics Results

Cost log of the Claude Code calls (`cost-log.csv`, written by [`../scripts/cost.py`](../scripts/cost.py)). The metric definitions are in [`../docs/metrics.md`](../docs/metrics.md).

**Analyzer results are not stored here.** The Code Quality Analyzer ([`../scripts/`](../scripts/)) writes one folder per measurement to `results/baseline/<trial|final>/<label>/` ([`../docs/decisions/003`](../docs/decisions/003-analyzer-and-success-rule.md), D23): CSV files, `summary.json`, `tool_versions.json`; the raw tool output in `raw/` is not committed. The final baseline is `results/baseline/final/v0-ai-baseline/`.

| Folder (planned) | Content |
| --- | --- |
| `../results/baseline/` | Metrics and test results of the generated code before refactoring (Week 4) |
| `pilot/` | Pilot runs of the three approaches (Weeks 5–6) |
| `experiments/` | Main experiment results, one row per approach × repetition × module (plus project totals) (Week 7); the exact location is fixed when the runners are written |

Before and after values are always measured with the same tool and version, in the same environment.
