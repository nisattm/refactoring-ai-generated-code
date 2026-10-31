# The Three Approaches

Defined in Weeks 1–2 (area B), updated on 29 October 2026 for Claude Code ([`decisions/002`](decisions/002-single-lms-claude-code.md)). The Claude Code mechanics are a proposal and are checked in the pilot.

## Common rules

- **Tool and model:** Claude Code with a Claude Pro subscription, no API. The same model in every run: Claude Sonnet 5.5, selected by its full model ID; the Claude Code version, thinking setting and effort level are fixed and recorded. Output is not deterministic, so every experiment is repeated (Xu et al. 2025, Section 5; Ouyang et al. 2025).
- **Scope:** the **whole LMS project is refactored in one run**, not module by module, because the modules depend on each other (instructor's feedback).
- **Same input:** the same starting code (`v0-ai-baseline`) and the same tests for every run.
- **Tests are fixed by us:** the model can run at most the one fixed feedback test command where its approach allows it (see "Tools allowed per approach"); held-out tests are run only by our runner. Test files are protected ([`testing.md`](testing.md#test-protection)).
- **The same behavior instruction** in every approach: *"Do not change the externally visible behavior of the code (REST API and the fixed service interface); only improve its structure. Do not modify tests."* No other quality hints are given.
- **Same fix budget:** at most 3 code-changing rounds for Iterative and Multi-Agent; 1 for Single.
- **Acceptance rule** (Blyth et al. 2025, Algorithm 1): a round's output is accepted only if all feedback tests pass and the primary metrics are not worse ([`metrics.md`](metrics.md#3-success-definition)); otherwise the previous best version is kept.
- **Final gate:** output that fails the held-out tests at the end counts as a failure and is reported; the starting code is used in the analysis.
- **Logging:** tokens, time, round number, accepted or rejected, for every run ([`metrics.md`](metrics.md#8-cost-of-the-refactoring-llm-side)).

## Rules per approach

| | Single LLM | Iterative LLM | Multi-Agent |
| --- | --- | --- | --- |
| Claude Code mechanism *(pilot)* | One non-interactive run (`claude -p`) with one prompt; no test command allowed | One session; after each round our runner runs the feedback tests and resumes the session (`--resume`) with the result | One `claude -p` session whose main conversation acts only as orchestrator and calls three Claude Code **subagents** (Analyzer, Refactoring, Reviewer); the orchestrator runs the feedback tests with the one allowed test command |
| Roles | — | — | Analyzer (does not change code), Refactoring, Reviewer (approve or reject with reasons) |
| Steps | One message: "find and fix the problems" | Find → fix → check → fix again if needed | Analyzer → Refactoring → Reviewer → (if rejected) Refactoring → Reviewer … |
| Max rounds | 1 | 3 fix rounds | 1 refactoring + at most 2 Reviewer returns = 3 fixes |
| Stopping | — | Tests pass **and** the model reports no remaining problems, or 3 rounds used | Tests pass **and** the Reviewer approves, or 2 returns used |
| Test feedback | No (baseline) | Yes | Yes |
| Output | Refactored project | Refactored project | Refactored project |

## Why 3 rounds

- Blyth et al. (2025, preprint) use at most 10 rounds for cost and time reasons (Section III-D3); most code does not improve after round 3–4 (Section V).
- Self-Refine (Madaan et al., NeurIPS 2023) uses at most 4 rounds (Section 3.1); most of the gain comes in the first rounds (Section 4, Figure 4).
- AgentCoder (Huang et al. 2023, preprint): pass@1 gains shrink with each iteration from 1 to 5 (Table 3).
- Multi-agent refactoring studies use much higher limits: RefAgent 20 rounds for compile and test loops (Sections 3.4–3.5); MANTRA 20 repair attempts (Section 3.3), no limit on its Reviewer loop.
- We also measure cost and work within Pro usage limits, so we use 3. Both approaches get **the same budget**; otherwise differences would come from the number of rounds, not from the approach.

## Fairness rule: test feedback

The instructor's Week 6 plan gives test feedback to Multi-Agent. If Iterative did not get it, we could not tell whether a Multi-Agent advantage comes from the roles or from the test information. RefAgent compares its multi-agent system only with a single-shot single agent (44.5% vs 90% test pass rate, Table 6), so this separation is missing in the literature.

- **Test feedback for both Iterative and Multi-Agent.** The only remaining difference is one conversation versus three roles. Precedents: Blyth et al. 2025 add failing-test information to the next prompt (Section III-C); AgentCoder compares single and separate agents with the same test feedback (71.3% vs 79.9%, Table 7).
- The format is identical in both approaches: failing test name and error message, at most N lines (N set in the pilot).
- To avoid overfitting to the feedback tests, the suite is split into a **feedback set** and a **held-out evaluation set** ([`testing.md`](testing.md)).

## Multi-Agent with Claude Code subagents

Decided on 29 October 2026: the instructor's notes name "subagent", so Multi-Agent uses Claude Code's subagent feature rather than three separate `claude -p` sessions.

- **Definitions:** the three roles are custom subagents defined in the clean project copy, each with its own prompt, allowed tools and the model set explicitly to Claude Sonnet 5.5 (field names verified in the pilot).
- **Roles and tools:** Analyzer reads only (no edit, no shell); Refactoring reads and edits; Reviewer reads only and returns approve/reject with reasons. Only the orchestrator may run the feedback test command.
- **Known trade-off:** each subagent has its own context window, but only its final message returns to the orchestrator. We accept this; it matches how the roles hand over work (issue list → changed code → verdict).
- **Round budget:** the orchestrator prompt states the limit (1 refactoring + at most 2 Reviewer returns). The stream log (`--output-format stream-json`, `parent_tool_use_id`) is checked afterwards; a run that called the Refactoring subagent more than 3 times is invalid.
- **Cost:** tokens of the orchestrator and all subagents are summed; the per-model breakdown in the JSON result covers the whole run.

## Tools allowed per approach

Claude Code is an agent: even one prompt can read files, run commands and retry. Without limits, Single could see test results and the fairness rule would break.

| | Read / search files | Edit files | Feedback test command | Any other shell command |
| --- | --- | --- | --- | --- |
| Single | Yes | Yes | **No** | No |
| Iterative | Yes | Yes | No (our runner runs it between rounds) | No |
| Multi-Agent | Yes (all roles) | Refactoring subagent only | Orchestrator only | No |

Limits are set with `--allowedTools` and the `dontAsk` permission mode, which denies every call not explicitly allowed. The feedback test command is one fixed script that prints the same output format in Iterative and Multi-Agent (failing test name and error message, at most N lines). Held-out tests are never runnable by the model.

## Clean environment per run

Claude Code loads `CLAUDE.md`, hooks, skills, settings and auto memory automatically. The `--bare` mode that skips them requires an API key and does not use the Pro login, so it cannot be used.

- Every run starts in a **fresh Docker container** from the same image, with a **fresh copy of the baseline project**, the same settings file and only the files defined for its approach. No `CLAUDE.md`, hooks, memory or other projects are present.
- Only the Pro login is carried into the container. Whether this works without carrying other state is **not yet verified** (pilot).
- Nothing written by one run is visible to another.

## Model and thinking settings

- **Model check:** the JSON result of every run lists usage per model. A run in which any model other than Claude Sonnet 5.5 appears is invalid and repeated.
- **Thinking:** on Sonnet 5.5 thinking cannot be turned off completely; `disabled` is rejected and the lowest setting is `between_tools` (works only at low, medium and high effort). Thinking tokens count as output tokens. Effort is `high` (`--effort high`), as in the generation (decision of 31 October 2026); the thinking setting is chosen in the pilot. Both are the same in all three approaches.

## Usage limits

Pro has a 5-hour usage window and a weekly limit; exact values are not published. The team considers the limit sufficient because the window resets every 5 hours. The pilot still records how much of the window one run uses, so that runs can be scheduled.

## Open questions (pilot)

| Question | Proposal |
| --- | --- |
| How are token counts collected per run? | `claude -p --output-format json`: it contains `total_cost_usd`, a per-model breakdown, usage and `session_id`; cost figures are client-side estimates (Claude Code documentation). OpenTelemetry as an alternative. |
| Does the Pro login work in a fresh container without other state? | Test in the pilot |
| Subagent definition fields (model, tools) | Verify against the Claude Code subagent documentation in the pilot |
| Is static analysis output given to the LLM? | If yes, identically to all three |
| Does the Reviewer see the original code? | To decide in the pilot |

## Flow

```
Single LLM            Iterative LLM (1 session)            Multi-Agent (3 subagents)

project               project                              project
  │                     │                                    │
  ▼                     ▼                                    ▼
"find and fix"   ┌─► find → fix → check                    Analyzer ──► issue list
  │              │      │                                    │
  ▼              │      ▼                                    ▼
tests (final)    └── tests (fail → retry, max 3)      ┌─► Refactoring agent
                                                       │     │
                                                       │     ▼
                                                       │   Reviewer
                                                       │     │
                                                       │     ▼
                                                       └── tests (reject/fail → back, max 2)
```

## Sources

- Blyth, Licorish, Treude, Wagner (2025). Static Analysis as a Feedback Loop: Enhancing LLM-Generated Code Beyond Correctness. arXiv:2508.14419 (preprint)
- Madaan et al. (2023). Self-Refine: Iterative Refinement with Self-Feedback. NeurIPS 2023
- Huang et al. (2023). AgentCoder: Multi-Agent Code Generation with Effective Testing and Self-optimisation. arXiv:2312.13010 (preprint)
- Oueslati, Lamothe, Khomh (2026). RefAgent: A Multi-agent LLM-based Framework for Automatic Software Refactoring. ICSE 2026. arXiv:2511.03153
- Xu et al. (2025). MANTRA: Enhancing Automated Method-Level Refactoring with Contextual RAG and Multi-Agent LLM Collaboration. arXiv:2503.14340 (preprint)
- Ouyang, Zhang, Harman, Wang (2025). An Empirical Study of the Non-Determinism of ChatGPT in Code Generation. ACM TOSEM 34(2). doi:10.1145/3697010
- Anthropic. Claude Code documentation: Manage costs effectively. https://code.claude.com/docs/en/costs
