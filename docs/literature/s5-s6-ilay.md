# S5 – Efficiency and S6 – Effect of Prompts and Models

Owner: Aslınur İlay Tekin · Completed from İlay's four sources plus five additional verified sources · 13 October 2026

All bibliographic data below was checked against the publisher page, arXiv or Crossref. Numbers come from the paper's abstract unless another location is given. "Not verified" means the claim must not be presented as a number.

## A. Evidence table

| # | Authors, year | Title | Venue / status | DOI / URL | Models | Language / tasks | What was measured | Key findings (location) | Proposed solution | Limitation / gap for our project |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Huang, Qing, Shang, Cui, Zhang, 2024 | EffiBench: Benchmarking the Efficiency of Automatically Generated Code | NeurIPS 37, Datasets & Benchmarks, pp. 11506–11544 (peer-reviewed) | 10.52202/079017-0367 | 42 LLMs (35 open, 7 closed) | Python; 1,000 efficiency-critical LeetCode problems with human canonical solutions | Execution time, memory usage | GPT-4 code takes on average **3.12×** the execution time of canonical solutions; worst cases **13.89×** execution time and **43.92×** total memory (Abstract) | Benchmark efficiency, not only correctness | Algorithmic puzzles in Python; no database-backed web service |
| 2 | Du, Luu, Ji, Liu, Ng, 2024 | Mercury: A Code Efficiency Benchmark for Code Large Language Models | NeurIPS 37, Datasets & Benchmarks, pp. 16601–16622 (peer-reviewed) | 10.52202/079017-0529 | Several code LLMs | Python; 1,889 tasks | Correctness (Pass) and runtime-weighted correctness (Beyond) | Leading models reach **65%** Pass but **<50%** Beyond: correct code is often not efficient (Abstract) | Direct Preference Optimization improves efficiency more robustly than supervised fine-tuning | Training-side solution; not applicable to commercial agents we use |
| 3 | Coignion, Quinton, Rouvoy, 2024 | A Performance Study of LLM-Generated Code on Leetcode | EASE 2024 (peer-reviewed) | 10.1145/3661167.3661221 | 18 LLMs | Python; LeetCode | Runtime vs. human solutions; effect of temperature | Performance is comparable across LLMs, and generated code is **on average more efficient** than human-written LeetCode code (Abstract); warns about data contamination and LeetCode measurement reliability | New method for measuring generated-code speed | **Contradicts** [1] on direction; shows results depend on benchmark and measurement |
| 4 | Waghjale, Veerendranath, Wang, Fried, 2024 | ECCO: Can We Improve Model-Generated Code Efficiency Without Sacrificing Functional Correctness? | EMNLP 2024, pp. 15362–15376 (peer-reviewed) | 10.18653/v1/2024.emnlp-main.859 | Several LLMs; in-context learning, iterative refinement, fine-tuning | Python; generation and history-based editing | Efficiency and functional correctness | Most methods **reduce functional correctness** while only modestly improving efficiency; execution feedback helps keep correctness; natural-language feedback gives larger efficiency gains (Abstract; no numbers in abstract) | Reproducible efficiency benchmark; feedback-based refinement | Optimizing for speed can break behavior → supports testing before/after every change |
| 5 | Yi, Gay, Leitner, 2025 | Do AI Models Dream of Faster Code? An Empirical Study on LLM-Proposed Performance Improvements in Real-World Software | arXiv:2510.15494 (preprint) | 10.48550/arXiv.2510.15494 | Several LLMs (names not in abstract) | **Java**; 65 tasks from performance-critical open-source projects | Speed-ups validated with developer-written **JMH** benchmarks | LLM solutions are surprisingly capable but **highly volatile** and **lag behind human developers on average**; LLMs struggle to find performance hotspots; algorithmic benchmarks give an overly optimistic picture (Abstract). Number of projects: not verified | Agent systems that profile runtime behavior | Closest to our Java/JMH setup; still optimization tasks, not generated applications |
| 6 | Ouyang, Zhang, Harman, Wang, 2025 | An Empirical Study of the Non-Determinism of ChatGPT in Code Generation | ACM TOSEM 34(2), pp. 1–28 (peer-reviewed) | 10.1145/3697010 | ChatGPT | 829 problems from CodeContests, APPS, HumanEval | Differences between repeated requests with the same prompt | Share of tasks where **no two requests gave equal test output**: **75.76%** (CodeContests), **51.00%** (APPS), **47.56%** (HumanEval); **temperature 0 does not guarantee determinism** (Abstract) | Researchers must account for non-determinism | Function-level tasks; one model |
| 7 | Döderlein, Kouadio, Acher, Khelladi, Combemale, 2025 | Piloting Copilot, Codex, and StarCoder2: Hot temperature, cold prompts, or black magic? | Journal of Systems and Software 230, art. 112562 (peer-reviewed) | 10.1016/j.jss.2025.112562 | Copilot, Codex, StarCoder2 | HumanEval, LeetCode | Pass rate under varied description, context, temperature and number of solutions | Varying inputs raised one-shot success to **79.27%**, vs. defaults of **22.44%** (Codex) and **31.1%** (Copilot); best settings differ per problem; even removing the prompt can work (Abstract) | Automated tuning of inputs | Correctness only; no quality or efficiency metrics |
| 8 | Khojah, Gomes de Oliveira Neto, Mohamad, Leitner, 2025 | The Impact of Prompt Programming on Function-Level Code Generation | IEEE TSE 51(8) (peer-reviewed) | 10.1109/TSE.2025.3587794 | GPT-4o, Llama3, Mistral | Python functions; CodePromptEval, **7,072 prompts**, 5 techniques (few-shot, persona, chain-of-thought, function signature, list of packages) | Correctness, similarity, code quality | Some techniques significantly change the generated code; **combining techniques does not necessarily help**; **trade-off between correctness and quality** (Abstract) | Choose prompt techniques deliberately | Function-level; no multi-step application |
| 9 | Shukla, Joshi, Syed, 2025 | Security Degradation in Iterative AI Code Generation – A Systematic Analysis of the Paradox | arXiv:2506.11022 (preprint; arXiv HTML states acceptance at IEEE ISTAS 2025, not verified) | 10.48550/arXiv.2506.11022 | Not in abstract | 400 code samples, 40 rounds, 4 prompting strategies | Vulnerabilities across iterative "improvement" rounds | **37.6%** increase in critical vulnerabilities after five iterations (Abstract) | Human validation between iterations | Security only; supports limiting follow-up rounds |

Removed from İlay's draft: "four Java projects" for [5] (not in the abstract). ECCO [4] has no numeric result in its abstract, so no numbers are quoted.

### Patterns that cause extra memory or CPU (S5 sub-question)

None of the verified abstracts gives per-pattern frequencies. The following are **hypotheses to test** in our code, not literature findings: unnecessary object creation in loops, repeated computation, unnecessary collection copies, boxing/unboxing, inefficient algorithm choice. Şevval's source Abbassi et al. 2025 (inefficiency taxonomy, 492 snippets) is the reference for categorizing them.

## B. Threats to validity our project must control

| Threat | Literature | How our protocol controls it | Remaining limitation |
| --- | --- | --- | --- |
| Prompt wording changes the result | [7], [8] | Identical prompt text for all three models, frozen after first use | Results hold for our prompt only |
| Same prompt gives different code on repeated runs | [6] | Fixed model and default settings recorded in the log | **One run per model**: differences between models may partly be chance → state as limitation, or repeat P1 if time allows |
| Model and settings drift | [6], [7] | Model name, tool version, reasoning level recorded; no changes during the study | Vendors may update models silently |
| Iterative follow-ups degrade code | [9], [4] | Only four fixed follow-up messages, max 5 per step; business errors never fed back | — |
| Efficiency results depend on benchmark and measurement | [1] vs [3], [5] | JMH with warm-up and repeated forks; same hardware for before/after | Micro-benchmarks of service methods, not full load tests |
| Optimization can break behavior | [4], [5] | Characterization tests, mutation testing (PIT) before every refactoring | — |

## C. Slide drafts

### Slide – Efficiency: memory and execution time

- Correct is not efficient: GPT-4 code averages **3.12×** the runtime of human solutions, up to **43.92×** memory [1]
- Leading models pass **65%** of tasks but fewer than **50%** are also efficient [2]
- Results depend on the benchmark: on LeetCode, one study found generated code faster than human code on average [3]
- Optimizing generated code often costs correctness [4]
- On real Java code with JMH, LLM speed-ups are volatile and behind developers [5]

Speaker notes: Efficiency studies agree that passing tests says nothing about runtime or memory, but they disagree on how large the gap is, because they use different benchmarks and measurement methods. The study closest to us, on real Java projects with JMH, finds that LLMs struggle to locate performance problems. That is why we measure our service methods with JMH before and after refactoring, and protect behavior with tests while doing it.

### Slide – Effect of prompts and models

- The same prompt does not give the same code: in up to **75.76%** of tasks no two answers had equal test output [6]
- Temperature 0 does not guarantee identical output [6]
- Changing prompt, temperature or number of samples moved success from **22–31%** to **79.27%** [7]
- Prompt techniques trade correctness against code quality; combining them does not necessarily help [8]
- Repeated "improve it" rounds increased critical vulnerabilities by **37.6%** after five iterations [9]

Speaker notes: Because LLM output depends on the prompt, the settings and even on chance, we fix everything we can: the same frozen prompt text for all three models, a new session per step, recorded model and settings, and only four standard follow-up messages. One generation per model remains a limitation that we will state openly.

## D. References (IEEE)

[1] D. Huang, Y. Qing, W. Shang, H. Cui, and J. M. Zhang, "EffiBench: Benchmarking the efficiency of automatically generated code," in *Advances in Neural Information Processing Systems*, vol. 37, 2024, pp. 11506–11544, doi: 10.52202/079017-0367.

[2] M. Du, L. A. Tuan, B. Ji, Q. Liu, and S.-K. Ng, "Mercury: A code efficiency benchmark for code large language models," in *Advances in Neural Information Processing Systems*, vol. 37, 2024, pp. 16601–16622, doi: 10.52202/079017-0529.

[3] T. Coignion, C. Quinton, and R. Rouvoy, "A performance study of LLM-generated code on Leetcode," in *Proc. 28th Int. Conf. Evaluation and Assessment in Software Engineering (EASE)*, 2024, doi: 10.1145/3661167.3661221.

[4] S. Waghjale, V. Veerendranath, Z. Wang, and D. Fried, "ECCO: Can we improve model-generated code efficiency without sacrificing functional correctness?," in *Proc. 2024 Conf. Empirical Methods in Natural Language Processing (EMNLP)*, 2024, pp. 15362–15376, doi: 10.18653/v1/2024.emnlp-main.859.

[5] L. Yi, G. Gay, and P. Leitner, "Do AI models dream of faster code? An empirical study on LLM-proposed performance improvements in real-world software," arXiv:2510.15494, 2025. [Preprint].

[6] S. Ouyang, J. M. Zhang, M. Harman, and M. Wang, "An empirical study of the non-determinism of ChatGPT in code generation," *ACM Trans. Softw. Eng. Methodol.*, vol. 34, no. 2, pp. 1–28, 2025, doi: 10.1145/3697010.

[7] J.-B. Döderlein, N. H. Kouadio, M. Acher, D. E. Khelladi, and B. Combemale, "Piloting Copilot, Codex, and StarCoder2: Hot temperature, cold prompts, or black magic?," *J. Syst. Softw.*, vol. 230, Art. no. 112562, 2025, doi: 10.1016/j.jss.2025.112562.

[8] R. Khojah, F. Gomes de Oliveira Neto, M. Mohamad, and P. Leitner, "The impact of prompt programming on function-level code generation," *IEEE Trans. Softw. Eng.*, vol. 51, no. 8, 2025, doi: 10.1109/TSE.2025.3587794.

[9] S. Shukla, H. Joshi, and R. Syed, "Security degradation in iterative AI code generation – A systematic analysis of the paradox," arXiv:2506.11022, 2025. [Preprint].
