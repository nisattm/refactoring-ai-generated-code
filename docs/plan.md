# 8-Week Plan

Plan provided by the instructor (October 2026). Status is updated as the project progresses.

## Weeks 1–2 – Literature review and research design ✅

- Review at least 10 academic papers and present them (16 reviewed)
- LLM-based code refactoring, multi-agent systems, sustainable software engineering
- Identify gaps in existing work and the research gap
- Formulate the research questions
- Define the three approaches: Single LLM, Iterative LLM, Multi-Agent
- Research metrics for code quality, functional correctness, performance and resource consumption
- Meeting to evaluate and finalize the metrics

**Instructor feedback (26 October 2026)** and our response:

| Feedback | Response |
| --- | --- |
| Too few metrics | Five-layer metric set: size, complexity, design, duplication, logic ([`metrics.md`](metrics.md)) |
| Design and logic are not examined; code can compile and still be illogical | Design metrics (CBO, LCOM, RFC, WMC…), logic smells and a design/logic review rubric ([`metrics.md`](metrics.md), [`smell-catalog.md`](smell-catalog.md)) |
| Detail memory, CPU and RAM usage | CPU time, peak RSS, allocations and a measurement protocol ([`metrics.md`](metrics.md#resource-measurement-protocol)) |
| Create test cases | Test strategy, feedback vs. held-out tests, coverage and mutation targets ([`testing.md`](testing.md)) |
| Review the GitHub `code-smell` topic | Survey of the topic and a Python smell catalog ([`smell-catalog.md`](smell-catalog.md)) |

## Week 3 – Dataset and complex project

- Prepare software tasks that fit the metrics from Weeks 1–2
- Classify tasks as simple, medium and complex
- Generate Python code for the tasks with the LLM
- Write functional requirements and test scenarios for the generated code
- Start the study with a complex Library Management System
- Store code, generation prompts and tests in the dataset ([`../dataset/`](../dataset/))

## Week 4 – Code Quality Analyzer

- Develop the Code Quality Analyzer module for automatic analysis of Python code
- Set up Ruff, Radon and the duplication tool (plus the tools in [`metrics.md`](metrics.md))
- Compute Cyclomatic Complexity, Maintainability Index and Code Duplication (plus the extended set)
- Measure code quality before refactoring
- Run the tests
- Save analysis results to CSV

## Week 5 – Single LLM and Iterative LLM

- Single LLM: analyze and refactor the code in one call
- Iterative LLM: analyze, improve and re-evaluate the code in several steps
- Standard prompt structures for both approaches
- Rules that preserve existing functionality during refactoring
- Record token consumption, API cost and processing time
- Pilot both approaches

## Week 6 – Multi-Agent

- Analyzer Agent: analyzes code quality problems
- Refactoring Agent: restructures the code to fix the identified problems
- Reviewer Agent: evaluates the refactoring and requests corrections when needed
- Communication and task flow between the agents
- Feedback and correction mechanism based on test results
- Pilot the Multi-Agent system; first comparison of the three approaches

## Week 7 – Main experiments

- Run the three approaches on the dataset
- Same starting code and same test scenarios for every approach
- Quality metrics before and after refactoring
- Functional test results
- Execution time and memory usage of the code
- LLM token consumption, API cost and response times
- Reproducibility and organized storage of results

## Week 8 – Statistical analysis and paper

- Compare Single LLM, Iterative LLM and Multi-Agent
- Analyze changes in complexity, maintainability and duplication
- Evaluate functional correctness and performance
- Compare token consumption, API cost and processing time
- Statistical tests, confidence intervals and effect sizes
- Quality–cost trade-off
- Tables and charts
- Write the paper
