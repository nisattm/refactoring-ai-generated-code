# S1 – Prior Studies and S2 – Problems in AI-Generated Code

Owner: Fatima Zehra Öktem · Corrected and verified version · 13 October 2026

Every number below was checked against the paper (abstract, introduction or the section given). Corrections to the original draft are listed at the end.

## 1. Search method

**Databases:** Google Scholar, ACM Digital Library, IEEE Xplore.

**Search strings:**

1. "code quality" AND ("ChatGPT" OR "GitHub Copilot") AND empirical AND "software engineering"
2. "GitHub Copilot" AND ("code smells" OR "maintainability") AND ("Java" OR "Python")
3. "LLM-generated code" AND ("technical debt" OR "static analysis")
4. ("code refactoring" OR "refactoring") AND ("Large Language Models" OR "LLMs") AND empirical
5. ("functional correctness" OR "pass@1") AND ("code quality" OR "smells") AND "ChatGPT"
6. "evaluating code generation" AND ("GPT-4" OR "Claude" OR "Gemini") AND benchmark
7. "security vulnerabilities" AND "GitHub Copilot" AND (CWE OR CodeQL)
8. ("maintainability" OR "technical debt") AND ("LLM-generated code" OR "AI-assisted") AND "Java"
9. ("iterative prompting" OR "software evolution") AND "AI-generated code" AND maintainability
10. "Cited by" follow-up of the key papers found with 1–9

**Inclusion:** 2021–2026; peer-reviewed software engineering or security venues (ICSE, FSE, ASE, MSR, TOSEM, TSE, IEEE S&P, SCAM, EMSE, JSS) or widely cited arXiv preprints, marked as such; empirical studies that measure correctness, smells, maintainability, security or refactoring with tools.

**Exclusion:** developer-opinion surveys without code analysis; blog posts; studies without a reproducible benchmark or prompt description.

## 2. Evidence table

| # | Authors, year | Title | Venue / status | DOI | Models | Language / tasks | Tools | Key findings (location) | Limitation / gap for our project |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Yetiştiren, Özsoy, Ayerdem, Tüzün, 2023 | Evaluating the Code Quality of AI-Assisted Code Generation Tools: An Empirical Study on GitHub Copilot, Amazon CodeWhisperer, and ChatGPT | arXiv:2304.10778 (preprint) | 10.48550/arXiv.2304.10778 | ChatGPT, Copilot, CodeWhisperer | Python; 164 HumanEval problems | Unit tests; SonarQube (security, bugs, code smells) | Correct code: ChatGPT **65.2%**, Copilot **46.3%**, CodeWhisperer **31.1%**; average technical debt from code smells **8.9 / 9.1 / 5.6 minutes** (Abstract); SonarQube is the only quality tool (Section 3) | Single Python functions; no layered application, no requirement changes |
| 2 | Liu, Le-Cong, Widyasari, Tantithamthavorn, Li, Le, Lo, 2024 | Refining ChatGPT-Generated Code: Characterizing and Mitigating Code Quality Issues | ACM TOSEM 33(5) (peer-reviewed) | 10.1145/3643674 | ChatGPT (GPT-3.5, March 2023) | Java and Python; 2,033 LeetCode tasks, 4,066 programs | LeetCode tests; PMD and Checkstyle (Java); Pylint and Flake8 (Python) | 2,756 of 4,066 programs correct; **Java 69%**, Python 66% pass rate (Table 1); 1,930 programs with maintainability issues (Abstract); among passing programs, **53% of Java and 37% of Python** had style/maintainability issues (Introduction); feedback-based self-repair improved quality by **more than 20%** (Abstract) | LeetCode functions; no object-oriented design, no IDE refactoring |
| 3 | Nguyen, Nadi, 2022 | An Empirical Evaluation of GitHub Copilot's Code Suggestions | MSR 2022 (peer-reviewed) | 10.1145/3524842.3528470 | Copilot | Java, Python, JavaScript, C; 33 LeetCode questions, 132 solutions | LeetCode tests; SonarQube cyclomatic and cognitive complexity | Correctness: **Java 57%** (highest), **JavaScript 27%** (lowest); low complexity, no notable difference between languages; some suggestions could be simplified or call undefined helper methods (Abstract) | Very small sample; method-level |
| 4 | Pearce, Ahmad, Tan, Dolan-Gavitt, Karri, 2022 | Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code Contributions | IEEE S&P 2022 (peer-reviewed) | 10.1109/SP46215.2022.9833571 | Copilot | **C, Python, Verilog**; 89 CWE scenarios, 1,689 programs | CodeQL plus manual review | About **40%** of programs vulnerable (Abstract); 39.33% of top-ranked and 40.73% of all options (Discussion) | Security only; no design smells or refactoring |
| 5 | Shukla, Joshi, Syed, 2025 | Security Degradation in Iterative AI Code Generation – A Systematic Analysis of the Paradox | arXiv:2506.11022 (preprint) | 10.48550/arXiv.2506.11022 | Not in abstract | 400 samples, 40 iterative rounds, 4 prompting strategies | Vulnerability analysis | **37.6%** more critical vulnerabilities after five "improvement" iterations (Abstract) | Security only; supports the claim that repeated changes degrade code |

## 3. S1 – What prior studies exist

- Most studies evaluate OpenAI models (ChatGPT, Codex) and GitHub Copilot; direct comparisons of current Claude, GPT and Gemini coding agents under identical prompts are rare. [1]–[4]
- Python dominates; Java appears mainly at LeetCode level. [1]–[3]
- Almost all studies generate single functions or algorithms (HumanEval, LeetCode); we found no study that generates a layered Spring Boot application (controller, service, repository) end to end. [1]–[3]
- Correctness is studied far more than maintainability; only some studies measure smells or technical debt with tools. [1], [2]

## 4. S2 – Problems found

- **Correctness varies widely:** 31–69% of generated solutions are correct, depending on tool, language and benchmark. [1]–[3]
- **Working code still smells:** 53% of passing Java solutions had style or maintainability issues. [2]
- **Technical debt per function:** about 6–9 minutes of SonarQube remediation effort on small functions. [1]
- **Security:** about 40% of Copilot programs in high-risk scenarios were vulnerable. [4]
- **Repeated changes can make code worse:** critical vulnerabilities rose 37.6% after five iterative rounds. [5]

**Our position:** existing work stays at function level and rarely refactors. We generate the same four-feature Spring Boot REST API with three agents, apply two change requests (DT1, DT2) to observe how the code degrades, then refactor under test protection and compare metrics.

## 5. Slide drafts

### Slide – Survey method

- Google Scholar, ACM DL, IEEE Xplore; 10 search strings plus "Cited by" follow-up
- 2021–2026, peer-reviewed venues (TOSEM, MSR, IEEE S&P, NeurIPS…) and marked preprints
- Only empirical studies that measure code with tools (SonarQube, PMD, CodeQL, JMH…)
- Excluded: opinion surveys, blog posts, non-reproducible studies

Speaker notes: We did not collect papers at random. We searched three databases with fixed search strings and kept only studies that measure generated code with tools, because our own project is measurement-based.

### Slide – Prior work at a glance

| Study | Models | Code | Finding |
| --- | --- | --- | --- |
| Yetiştiren 2023 | ChatGPT, Copilot, CodeWhisperer | 164 Python functions | 31–65% correct, ~9 min debt each |
| Liu 2024 | ChatGPT | 4,066 Java/Python programs | 53% of passing Java code smells |
| Nguyen & Nadi 2022 | Copilot | 132 solutions, 4 languages | Java 57% correct |
| Pearce 2022 | Copilot | 1,689 C/Python/Verilog programs | ~40% vulnerable |

Speaker notes: All four studies work on small, isolated functions. None generates a complete layered application, and none applies refactoring under a test safety net. That is the space our project fills.

### Slide – Problems found in AI-generated code

- Correctness varies: 31–69% depending on tool and language [1]–[3]
- Passing tests ≠ clean code: 53% of passing Java solutions had maintainability issues [2]
- Security: ~40% of generated programs vulnerable in high-risk scenarios [4]
- Repeated "improvements" increased critical vulnerabilities by 37.6% [5]

Speaker notes: The key message is that working AI-generated code is not necessarily good code. That is why we first lock behavior with tests and only then refactor.

## 6. References (IEEE)

[1] B. Yetiştiren, I. Özsoy, M. Ayerdem, and E. Tüzün, "Evaluating the code quality of AI-assisted code generation tools: An empirical study on GitHub Copilot, Amazon CodeWhisperer, and ChatGPT," arXiv:2304.10778, 2023. [Preprint].

[2] Y. Liu, T. Le-Cong, R. Widyasari, C. Tantithamthavorn, L. Li, X.-B. D. Le, and D. Lo, "Refining ChatGPT-generated code: Characterizing and mitigating code quality issues," *ACM Trans. Softw. Eng. Methodol.*, vol. 33, no. 5, 2024, doi: 10.1145/3643674.

[3] N. Nguyen and S. Nadi, "An empirical evaluation of GitHub Copilot's code suggestions," in *Proc. 19th Int. Conf. Mining Software Repositories (MSR)*, 2022, pp. 1–5, doi: 10.1145/3524842.3528470.

[4] H. Pearce, B. Ahmad, B. Tan, B. Dolan-Gavitt, and R. Karri, "Asleep at the keyboard? Assessing the security of GitHub Copilot's code contributions," in *Proc. IEEE Symp. Security and Privacy (S&P)*, 2022, pp. 754–768, doi: 10.1109/SP46215.2022.9833571.

[5] S. Shukla, H. Joshi, and R. Syed, "Security degradation in iterative AI code generation – A systematic analysis of the paradox," arXiv:2506.11022, 2025. [Preprint].

## 7. Corrections to the original draft

| Original claim | Correction | Source checked |
| --- | --- | --- |
| Yetiştiren used Bandit for security | Only SonarQube was used | Paper, Section 3 |
| Liu: Java first-attempt correctness ~57% | Java 69% (57% is the Nguyen & Nadi Copilot figure) | Liu, Table 1 |
| Liu: feedback raised correctness to 88.3% | No 88.3% in the paper; abstract says quality improved by more than 20% | Liu, Abstract |
| Liu tools: CheckStyle, Flake8, SonarQube, SpotBugs | PMD and Checkstyle (Java), Pylint and Flake8 (Python) | Liu, Abstract/Section 3 |
| Nguyen & Nadi: Python 42%, C 27%, smells in 28.8% | Only Java 57% and JavaScript 27% are reported in the abstract; no smell percentage | MSR 2022 abstract |
| Pearce: C, Python, HTML/JS | C, Python, Verilog | Pearce, Section 3 |
| "95%+ of benchmarks", "zero studies", "none explore" | Replaced with "almost all / we found no study"; absolute claims cannot be proven | — |
| Correctness range 46–65% vs 46–57% | Unified to 31–69% with sources | [1]–[3] |
| "Evolution fragility" without a source | Supported with Shukla et al. 2025 [5] | arXiv abstract |
