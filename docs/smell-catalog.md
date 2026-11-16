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

**Decision.** Primary detectors are Ruff and Pylint rules and our own AST and import-graph scripts, one tool per smell ([`decisions/003`](decisions/003-analyzer-and-success-rule.md)). PyExamine (MSR 2025) is kept as a secondary source because it crashes silently on some files and its output order is unstable; DPy is not in the image. The topic gives us definitions, categories, evidence that thresholds vary, and the group of AI-specific smells below.

## Catalog

The **total smell count** (primary metric) counts only the frozen list of [`decisions/003`](decisions/003-analyzer-and-success-rule.md): S01, S02, S03, S07, S09, S10, S11, S18, S19, S20, S21, S22, S23, each by exactly **one primary tool or rule** (first in the Detection column). Other tools in the column are **secondary**: reported, never added to the total. The same smell at the same place is counted once (key: S-ID, file, enclosing function or class). S04, S05, S08 and S12–S17 are **not measured** (no reliable tool: PyExamine is secondary, DPy is not in the image); S06 is not in the total because duplication is a primary metric of its own.

| ID | Smell | Category (Jerzyk & Madeyski) | Level | AI-specific | Detection (primary · secondary) |
| --- | --- | --- | --- | --- | --- |
| S01 | Long Method | Bloaters | Code | | **Own AST script** (function over 45 lines, docstring excluded) · secondary: PyExamine, Ruff PLR0915 |
| S02 | Large Class / God Class | Bloaters | Design | | **Own AST script** (over 15 methods, `plain` classes only) · secondary: PyExamine |
| S03 | Long Parameter List | Bloaters | Code | | **Ruff PLR0913** (FastAPI route handlers also reported separately) · secondary: PyExamine |
| S04 | Data Clumps | Bloaters | Code | | Not measured · PyExamine (secondary) |
| S05 | Primitive Obsession | Bloaters | Code | | Not measured · PyExamine (secondary) |
| S06 | Duplicate Code | Dispensables | Code | | jscpd (primary metric, not in the smell total) · PyExamine (secondary) |
| S07 | Dead Code (unused imports, variables, functions) | Dispensables | Code | ✓ | **Ruff F401 + F841** (stable run, `--ignore-noqa`) · secondary: Vulture (80 %), Ruff F401 under `--preview`, PyExamine |
| S08 | Speculative Generality (needless abstraction) | Dispensables | Design | ✓ | Not measured · PyExamine (secondary) |
| S09 | Complex Conditional | Obfuscators | Code | | **Ruff PLR0916** (`--preview`, separate run) **+ SIM** · secondary: PyExamine |
| S10 | Deep Nesting | Obfuscators | Code | | **Pylint R1702** · secondary: complexipy (cognitive complexity) |
| S11 | Magic Number | Lexical Abusers | Code | | **Ruff PLR2004** (only numbers in comparisons) |
| S12 | Feature Envy | Couplers | Design | | Not measured · PyExamine (secondary) |
| S13 | Message Chains | Couplers | Design | | Not measured · PyExamine (secondary) |
| S14 | Shotgun Surgery | Change Preventers | Design | | Not measured · PyExamine (secondary) |
| S15 | Divergent Change | Change Preventers | Design | | Not measured · PyExamine (secondary) |
| S16 | Temporary Field | Object-Oriented Abusers | Design | | Not measured · PyExamine (secondary) |
| S17 | Deficient Encapsulation | Object-Oriented Abusers | Design | | Not measured (DPy is not in the image) |
| S18 | Cyclic / Hub-like Dependency | Couplers | Architecture | | **Own import graph** (strongly connected components of size > 1 at file level; primary value includes the function-level model-registration imports of `core/db.py`, the value without them is reported next to it) · secondary: files inside cycles, Pylint R0401, PyExamine |
| S19 | Swallowed / broad exception | Functional Abusers* | Logic | ✓ | **Ruff S110 + BLE001** · secondary: Pylint W0718 |
| S20 | Mutable default argument | Functional Abusers* | Logic (Python) | | **Ruff B006** |
| S21 | Inconsistent / redundant return | Obfuscators* | Logic | | **Ruff RET** · secondary: Pylint R1710 |
| S22 | Disallowed dependency (import of a package outside the fixed library list of LIB-TECH-02, including non-existent packages) | Couplers* | Architecture | ✓ | **Own script** (real `import` nodes by AST; allowed: standard library, `fastapi`, `starlette`, `pydantic_core`, `uvicorn`, `pydantic`, `sqlalchemy`, `lms`) |
| S23 | Bypassed type safety (`Any`, `cast`, blanket `# type: ignore`) | Obfuscators* | Code | ✓ | **Ruff ANN401 + PGH003 + count of `cast(` calls** · secondary: suppression-comment counts |

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

Code that compiles and may pass the tests but is illogical. Detectable by tools: unreachable code (Pylint W0101), unused variables and imports (Ruff F841, F401), simplifiable conditions (Ruff SIM), repeated checks of the same condition, inconsistent return values (Pylint R1710), swallowed exceptions (Ruff S110), mutable default arguments (Ruff B006). The logic smells in the frozen list (S19, S20, S21) are counted in the total smell count; the Pylint messages W0101, R1710 and W0718 are reported as secondary information. Logic problems the tools miss are captured by the rubric in [`metrics.md`](metrics.md#design-and-logic-rubric).

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
