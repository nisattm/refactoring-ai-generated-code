# The Three Approaches

Defined in Weeks 1–2 (area B), updated on 29 October 2026 for Claude Code ([`decisions/002`](decisions/002-single-lms-claude-code.md)). The Claude Code mechanics are a proposal and are checked in the pilot.

## Common rules

- **Tool and model:** Claude Code with a Claude Pro subscription, no API. The same model in every run: Claude Sonnet 5.5, selected by its full model ID; the Claude Code version and the effort level are fixed and recorded. Output is not deterministic, so every experiment is repeated (Xu et al. 2025, Section 5; Ouyang et al. 2025).
- **Scope:** the **whole LMS project is refactored in one run**, not module by module, because the modules depend on each other (instructor's feedback).
- **Same input:** the same starting code (`v0-ai-baseline`) and the same tests for every run.
- **Tests are run by our runner**, not chosen by the model. Test files are protected ([`testing.md`](testing.md#test-protection)).
- **The same behavior instruction** in every approach: *"Do not change the externally visible behavior of the code (REST API and the fixed service interface); only improve its structure. Do not modify tests."* No other quality hints are given.
- **Same fix budget:** at most 3 code-changing rounds for Iterative and Multi-Agent; 1 for Single.
- **Acceptance rule** (Blyth et al. 2025, Algorithm 1): a round's output is accepted only if all feedback tests pass and the primary metrics are not worse ([`metrics.md`](metrics.md#3-success-definition)); otherwise the previous best version is kept.
- **Final gate:** output that fails the held-out tests at the end counts as a failure and is reported; the starting code is used in the analysis.
- **Logging:** tokens, time, round number, accepted or rejected, for every run ([`metrics.md`](metrics.md#8-cost-of-the-refactoring-llm-side)).

## Rules per approach

| | Single LLM | Iterative LLM | Multi-Agent |
| --- | --- | --- | --- |
| Claude Code mechanism *(pilot)* | One non-interactive run (`claude -p`) with one prompt; tools for running tests disabled | One session; after each round our runner runs the feedback tests and sends the result as the next message | Claude Code subagents: Analyzer, Refactoring, Reviewer, each with its own context; our runner passes test results |
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

## Fairness in Claude Code

- **Same effort level** in all approaches: Sonnet 5.5 always uses extended thinking, and thinking tokens count toward cost.
- **Same project instructions:** no `CLAUDE.md`, skills or plugins in the working directory other than those defined for the approach; the same settings file for all runs.
- **Fresh session per run;** Multi-Agent subagents do not share history.
- **Usage limits:** Pro has 5-hour and weekly usage limits whose exact values are not published. The pilot measures how much of the limit one run uses; the number of repetitions is set from that.

## Open questions (pilot)

| Question | Proposal |
| --- | --- |
| How are token counts collected per run? | OpenTelemetry export or `claude -p --output-format json`; both tried in the pilot |
| Can test tools be fully disabled for Single? | Restrict allowed tools in the run configuration; verify in the pilot |
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
