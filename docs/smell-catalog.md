# Python Code Smell Catalog

Smells we look for in Claude-generated Python code, how we detect them, and where they come from. Categories follow the taxonomy of Jerzyk & Madeyski (2023). Thresholds are in [`metrics.md`](metrics.md#2-thresholds). Observed counts are added after code generation (Week 3–4).

## Survey of the GitHub `code-smell` topic

[github.com/topics/code-smell](https://github.com/topics/code-smell) lists 22 repositories; 20 are shown on the page (first reviewed 26 October 2026, re-checked 29 October 2026).

| Repository | What it does | Relevance for us |
| --- | --- | --- |
| [Luzkan/smells](https://github.com/Luzkan/smells) | Catalog of 56 code smells, backed by Jerzyk & Madeyski (2023, Springer) | Source of our categories and definitions |
| [bhvbhushan/vibecop](https://github.com/bhvbhushan/vibecop) | Deterministic linter for AI-generated code (tree-sitter / ast-grep); examples: god functions, hallucinated packages, trivial assertions, empty tests, unpinned LLM models | Source of AI-specific smells. The page gives conflicting detector counts (22 in the description, 16 + 7 + 4 + 8 = 35 by category); Python support is suggested by a topic tag but **not verified**. May be tried in the pilot. |
| [BaryshevRS/stopslop](https://github.com/BaryshevRS/stopslop) | Cognitive complexity, god classes/modules, copy-pasted blocks, dead code; 0–100 "slop" score | JavaScript/TypeScript only; **not usable** for our Python code. Confirms which smells are typical of AI code. |
| [alonsarias/pureslop](https://github.com/alonsarias/pureslop) | Satirical spec that makes an AI agent write bad code: over-commenting, over-abstraction, swallowed errors, deep nesting, casting away type safety | List of typical AI-code patterns. Never used in generation (no quality steering in prompts). |
| [Yihao-Xu-777/python-code-smell-detector](https://github.com/Yihao-Xu-777/python-code-smell-detector) | AST-based; 5 smells: Long Method (> 30 lines), too many parameters, deep nesting, magic number, broad exception | Shows that thresholds differ between tools (PyExamine example: 45 lines); hence our fixed thresholds |
| [bluebear-io/nikui](https://github.com/bluebear-io/nikui) | Hotspot score = smell weight × Git churn; LLM finds SOLID violations, silent failures, god objects | Not applicable: generated code has no Git history. LLM semantic review is similar to our rubric. |
| [labd2m/ExSmell-Gold](https://github.com/labd2m/ExSmell-Gold), ExSmell-Train | Elixir benchmark: half smelly, half smell-free examples | Different language; method idea only |
| andreeaneacsu33/long-parameter-list, rudra496/codevista, gitstq/CodeRefactor-Pilot (Python); huanweide/litdoctor (JavaScript) | Small single-purpose or AI-assisted detectors (0–6 stars) | No peer-reviewed evaluation; not used |
| Others (C#, T-SQL, PHP, notes, translations) | Not Python detectors | Not used |

**Decision.** Primary detectors are the peer-reviewed PyExamine and DPy (MSR 2025) plus Ruff and Pylint rules. The topic gives us definitions, categories, evidence that thresholds vary, and the group of AI-specific smells below.

## Catalog

| ID | Smell | Category (Jerzyk & Madeyski) | Level | AI-specific | Detection |
| --- | --- | --- | --- | --- | --- |
| S01 | Long Method | Bloaters | Code | | PyExamine (line threshold); Ruff PLR0915 |
| S02 | Large Class / God Class | Bloaters | Design | | PyExamine (NOM, WMC); DPy |
| S03 | Long Parameter List | Bloaters | Code | | PyExamine; Ruff PLR0913 |
| S04 | Data Clumps | Bloaters | Code | | PyExamine |
| S05 | Primitive Obsession | Bloaters | Code | | PyExamine |
| S06 | Duplicate Code | Dispensables | Code | | jscpd; PyExamine |
| S07 | Dead Code (unused imports, variables, functions) | Dispensables | Code | ✓ | Vulture; PyExamine; Ruff F401, F841 |
| S08 | Speculative Generality (needless abstraction) | Dispensables | Design | ✓ | PyExamine |
| S09 | Complex Conditional | Obfuscators | Code | | PyExamine; Ruff PLR0916, SIM |
| S10 | Deep Nesting | Obfuscators | Code | | Pylint R1702; complexipy |
| S11 | Magic Number | Lexical Abusers | Code | | Ruff PLR2004 |
| S12 | Feature Envy | Couplers | Design | | PyExamine |
| S13 | Message Chains | Couplers | Design | | PyExamine |
| S14 | Shotgun Surgery | Change Preventers | Design | | PyExamine |
| S15 | Divergent Change | Change Preventers | Design | | PyExamine |
| S16 | Temporary Field | Object-Oriented Abusers | Design | | PyExamine |
| S17 | Deficient Encapsulation | Object-Oriented Abusers | Design | | DPy |
| S18 | Cyclic / Hub-like Dependency | Couplers | Architecture | | PyExamine; DPy |
| S19 | Swallowed / broad exception | Functional Abusers* | Logic | ✓ | Ruff S110, BLE001; Pylint W0718 |
| S20 | Mutable default argument | Functional Abusers* | Logic (Python) | | Ruff B006 |
| S21 | Inconsistent / redundant return | Obfuscators* | Logic | | Pylint R1710; Ruff RET |
| S22 | Disallowed dependency (import of a package not in `requirements.txt`, including non-existent packages) | Couplers* | Architecture | ✓ | Our script: imports compared with the allowed package list |
| S23 | Bypassed type safety (`Any`, `cast`, blanket `# type: ignore`) | Obfuscators* | Code | ✓ | Ruff ANN401, PGH003; count of `cast(` calls (rule codes verified during setup) |

\* Not in the catalog directly; the category is our assignment.

## AI-specific smells

Patterns reported as typical of AI-generated code in the GitHub topic (vibecop, stopslop, pureslop). They are not a separate measurement; the ✓ column marks them so that results can also be reported for this group.

| Pattern | Measured by |
| --- | --- |
| Over-commenting | Comment ratio (Radon raw, [`metrics.md`](metrics.md)) |
| Unused imports and dead code | S07 |
| Needless abstraction | S08 |
| Swallowed errors | S19 |
| Hallucinated or disallowed packages | S22 |
| Casting away type safety | S23 |

Trivial assertions and empty tests (vibecop) are not counted as smells: tests are written by the team, and the model may not change them ([`testing.md`](testing.md#test-protection)).

## Logic smells

Code that compiles and may pass the tests but is illogical. Detectable by tools: unreachable code (Pylint W0101), unused variables and imports (Ruff F841, F401), simplifiable conditions (Ruff SIM), repeated checks of the same condition, inconsistent return values (Pylint R1710), swallowed exceptions (Ruff S110), mutable default arguments (Ruff B006). Their total is the "logic smell count" metric. Logic problems the tools miss are captured by the rubric in [`metrics.md`](metrics.md#design-and-logic-rubric).

## Observed smells (after generation)

Filled after the LMS code is generated. This table shows that the generated code actually contains the smells the metrics measure; expected smells per module are listed in [`../dataset/README.md`](../dataset/README.md).

| ID | Smell | Module | Location | Detected by | Value | Approach that fixed it |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## Sources

- M. Jerzyk, L. Madeyski. Code Smells: A Comprehensive Online Catalog and Taxonomy. In: Developments in Information and Knowledge Management Systems for Business Applications, Springer, 2023, pp. 543–576. doi:10.1007/978-3-031-25695-0_24 · [luzkan.github.io/smells](https://luzkan.github.io/smells/)
- K. Shivashankar, A. Martini. PyExamine: A Comprehensive, Un-Opinionated Smell Detection Tool for Python. MSR 2025. arXiv:2501.18327
- A. Boloori, T. Sharma. DPy: Code Smells Detection Tool for Python. MSR 2025 Data and Tool Showcase Track
- M. Fowler. Refactoring: Improving the Design of Existing Code, 2nd ed., Addison-Wesley, 2018
- GitHub repositories listed in the survey table (accessed 29 October 2026)
