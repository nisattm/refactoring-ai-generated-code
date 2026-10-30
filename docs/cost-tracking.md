# Cost Tracking

Every Claude Code call of the experiment (generation, pilot and the three approaches) is written as one row to [`../metrics/cost-log.csv`](../metrics/cost-log.csv). Claude Code runs with the $20 Pro subscription, so no money is charged per call. We record tokens and time, and Claude Code's own **equivalent cost** (`total_cost_usd`): what the same tokens would cost at API list prices. This answers RQ3 (is the extra cost worth the quality?). What is measured and why: [`metrics.md`](metrics.md#8-cost-of-the-refactoring-llm-side).

## How a call is logged

Each call runs in a fresh container ([`environment.md`](environment.md#4a-claude-code-with-the-pro-subscription-once-per-person)) with JSON output:

```bash
claude -p "<prompt>" --model claude-sonnet-5-5 --output-format json > result.json
python scripts/cost.py log result.json --task lms --stage single --run-id lms-single-r1 --repetition 1
```

[`../scripts/cost.py`](../scripts/cost.py) reads the JSON, sums the tokens of all models and subagents (field `modelUsage`), checks the run and appends one row. The exit code is `2` for an invalid run; the row is still written so that failed calls are counted in the cost.

A run is **invalid** (`valid = false`) when the call returned an error (`is_error`, for example HTTP 401), when `modelUsage` is missing, or when any model other than `claude-sonnet-5-5` appears (decision of 29 October). Invalid runs are repeated.

The JSON fields were checked on a real call: [`../docker/claude-sample.json`](../docker/claude-sample.json) (Claude Code 2.1.308, 29 October 2026).

## Columns

The first nine columns are required by the Week 3 task file.

| Column | Meaning | Source in the JSON | Example |
| --- | --- | --- | --- |
| `date` | Time the row was written (ISO 8601 with offset) | automatic | `2026-11-02T14:05:31+03:00` |
| `task` | Task id | argument | `lms` |
| `stage` | `check`, `pilot`, `generation`, `single`, `iterative` or `multi-agent` | argument | `iterative` |
| `model` | Model required for the run | argument | `claude-sonnet-5-5` |
| `input_tokens` | Uncached input tokens | sum of `modelUsage.*.inputTokens` | `2` |
| `output_tokens` | Output tokens | sum of `modelUsage.*.outputTokens` | `4` |
| `usd` | Equivalent cost estimated by Claude Code (list prices) | `total_cost_usd` | `0.0229907` |
| `duration_s` | Wall-clock time of the call | `duration_ms` / 1000 | `2.3` |
| `note` | Problems found by the check, plus free text | automatic + argument | |
| `run_id` | One id per run of one approach | argument | `lms-iter-r3` |
| `repetition` | Repetition number (1…N) | argument | `3` |
| `round` | Fix round in Iterative / Multi-Agent (1–3); empty otherwise | argument | `2` |
| `role` | Multi-Agent role if the call is logged per role; empty otherwise | argument | `reviewer` |
| `cache_write_tokens` | Tokens written to the prompt cache | sum of `cacheCreationInputTokens` | `5456` |
| `cache_write_1h_tokens` | Part of the writes with 1-hour lifetime; empty if the split is not available | `usage.cache_creation` | `5456` |
| `cache_read_tokens` | Tokens read from the prompt cache | sum of `cacheReadInputTokens` | `11227` |
| `thinking_tokens` | Extended-thinking tokens | sum of `thinkingTokens` | `0` |
| `total_input_tokens` | `input_tokens` + `cache_write_tokens` + `cache_read_tokens` | computed | `16685` |
| `usd_recomputed` | Equivalent cost recomputed with the price table below (check of `usd`) | computed | `0.0229907` |
| `api_duration_s` | Time spent waiting for the model | `duration_api_ms` / 1000 | `1.465` |
| `num_turns` | Agent turns of the call | `num_turns` | `1` |
| `subagents_spawned` | Subagents started (Multi-Agent) | `subagent_stats.spawned` | `0` |
| `models_used` | All models in the call, `;`-separated | keys of `modelUsage` | `claude-sonnet-5-5` |
| `valid` | `true` / `false`, see above | computed | `true` |
| `session_id` | Claude Code session, for finding the transcript | `session_id` | |
| `accepted` | Was this round's output accepted? ([`approaches.md`](approaches.md)) | argument | `true` |
| `tool_s` | Time spent running tests or analyzers between rounds | argument | `4.21` |
| `wait_s` | Time spent waiting for usage limits (recorded, not compared) | argument | `0` |
| `claude_code_version` | `claude --version` | automatic | `2.1.308` |
| `price_date` | Date the price table was checked | automatic | `2026-10-29` |

## Price table

USD per 1 million tokens, list prices from the [Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing), checked on 2026-10-29.

| Model | Input | Output | Cache write (5 min) | Cache write (1 h) | Cache read |
| --- | --- | --- | --- | --- | --- |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | 2.00 | 10.00 | 2.50 | 4.00 | 0.10 |

On the sample call, this table reproduces `total_cost_usd` exactly (2 × 2.00 + 4 × 10.00 + 5456 × 4.00 + 11227 × 0.10 = 22 990.7 per million = 0.0229907 USD), and the JSON states `"costBasis": "list"`. `total_cost_usd` is a client-side estimate, not a bill. Because token counts are stored, costs can be recomputed if prices change.

## Things to know when comparing approaches

- **Fixed overhead per call.** Even a one-word answer used about 16 700 input tokens (Claude Code's system prompt and tool definitions). Every subagent pays this again, so Multi-Agent has a real extra cost; report the overhead with the results.
- **The prompt cache is shared between containers.** A fresh container still read 11 227 tokens from the cache: the cache is on the server and lasts up to 1 hour. The first run in a time window pays the cache write; later runs read cheaply. Therefore: keep the cache columns, alternate or randomize the order of the approaches between repetitions, and report both `total_input_tokens` and `usd`.
- **Resumed sessions.** With `--resume` (Iterative rounds), the JSON figures are the running total of the conversation. Log every call as usual; per-round values are the differences between consecutive rows of the same `session_id` ([`metrics.md`](metrics.md#8-cost-of-the-refactoring-llm-side)).
- **Plan usage.** The Pro plan's 5-hour and weekly usage is not in the JSON. If needed, note it from the `/usage` screen before and after a run in `note`.

## Reported in the analysis

- Per call, per run and per approach: tokens (uncached, cache write, cache read, output), equivalent cost and time.
- Per approach: median and spread over repetitions.
- **Cost per successful refactoring:** total equivalent cost of an approach ÷ number of successful refactorings (definition in [`metrics.md`](metrics.md#3-success-definition)).
- Generation and pilot cost are reported separately from the experiment.
- Invalid and repeated calls are included in the cost.
