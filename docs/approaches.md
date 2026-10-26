# The Three Approaches

Proposal from Weeks 1–2 (area B). Values marked *proposal* are finalized in the metrics and design meeting and recorded in [`decisions/`](decisions/).

## Common rules

- Same model and version, same temperature setting where the model allows it; every experiment is repeated because output is not deterministic (Xu et al. 2025, Section 5; Ouyang et al. 2025).
- Same starting code and same tests. Tests are run by our program, not by the LLM.
- The same instruction in every system prompt: *"Do not change the externally visible behavior of the code; only improve its structure. Return the complete code in a single code block."*
- Same fix budget: at most 3 code-changing calls for Iterative and Multi-Agent; 1 for Single.
- **Acceptance rule** (Blyth et al. 2025, Algorithm 1): a round's output is accepted only if all tests pass and the metrics are not worse; otherwise the previous best version is kept.
- **Final gate:** output that fails the tests at the end counts as a failure and is reported; the starting code is used in the analysis.
- Every call is logged: input and output tokens, time, round number, accepted or rejected.

## Rules per approach

| | Single LLM | Iterative LLM | Multi-Agent |
| --- | --- | --- | --- |
| Conversations | 1 | 1 (history kept) | 3 separate conversations, no shared history |
| Roles | — | — | Analyzer (does not change code), Refactoring, Reviewer (approve or reject with reasons) |
| Steps | One message: "find and fix the problems" | Find → fix → check → fix again if needed | Analyzer → Refactoring → Reviewer → (if rejected) Refactoring → Reviewer … |
| Max rounds | 1 | 3 fix rounds *(proposal)* | 1 refactoring + at most 2 Reviewer returns = 3 fixes *(proposal)* |
| Stopping | — | Tests pass **and** the model reports no remaining problems, or 3 rounds used | Tests pass **and** the Reviewer approves, or 2 returns used |
| Test feedback | No (baseline) | Yes *(proposal a)* | Yes *(proposal a)* |
| Output | Refactored code | Refactored code | Refactored code |

## Why 3 rounds

- Blyth et al. (2025, preprint) use at most 10 rounds for cost and time reasons (Section III-D3); most code does not improve after round 3–4 (Section V).
- Self-Refine (Madaan et al., NeurIPS 2023) uses at most 4 rounds (Section 3.1); most of the gain comes in the first rounds (Section 4, Figure 4).
- AgentCoder (Huang et al. 2023, preprint): pass@1 gains shrink with each iteration from 1 to 5 (Table 3).
- Multi-agent refactoring studies use much higher limits: RefAgent 20 rounds for compile and test loops (Sections 3.4–3.5); MANTRA 20 repair attempts (Section 3.3), no limit on its Reviewer loop.
- We also measure cost, so we propose 3. Both approaches get **the same budget**; otherwise differences would come from the number of rounds, not from the approach.

## Fairness rule: test feedback

The instructor's Week 6 plan gives test feedback to Multi-Agent. If Iterative did not get it, we could not tell whether a Multi-Agent advantage comes from the roles or from the test information. RefAgent compares its multi-agent system only with a single-shot single agent (44.5% vs 90% test pass rate, Table 6), so this separation is missing in the literature.

- **(a) Proposal: test feedback for both Iterative and Multi-Agent.** The only remaining difference is one conversation versus three roles. Precedents: Blyth et al. 2025 add failing-test information to the next prompt (Section III-C); AgentCoder compares single and separate agents with the same test feedback (71.3% vs 79.9%, Table 7).
- **(b) No test feedback for either.** Simpler, but contradicts the Week 6 plan.
- The format is identical in both approaches: failing test name and error message, at most N lines.
- To avoid overfitting to the feedback tests, the test suite is split into a **feedback set** and a **held-out evaluation set** ([`testing.md`](testing.md)).

## Open questions for the meeting

| # | Question | Proposal |
| --- | --- | --- |
| 7 | API or Claude Code? | API with our own Python orchestration: we control what each agent sees and get token usage per call. MANTRA orchestrates with LangGraph (Section 4); AgentCoder's test executor is a Python script (Section 3). |
| 8 | Iterative: max rounds and stopping | 3 fix rounds; stop when tests pass and the model reports no remaining problems |
| 9 | Reviewer: max returns | 2 (3 fixes in total, equal to Iterative) |
| 10 | Which approaches get test feedback? | Iterative and Multi-Agent (option a) |
| — | Is static analysis output given to the LLM? | If yes, identically to all three |
| — | Does the Reviewer see the original code? | To decide |

## Flow

```
Single LLM            Iterative LLM (1 conversation)      Multi-Agent (3 conversations)

code                  code                                 code
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
