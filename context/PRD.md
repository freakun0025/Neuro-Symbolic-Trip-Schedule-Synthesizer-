# PRD — Neuro-Symbolic Trip & Schedule Synthesizer

**Course:** AID 851 — Introduction to Machine Reasoning
**Team:** Aaryan Rajesh Antala (IMT2023548), Kunal Mittal (IMT2023533), Parsania Ramya Parulbhai (IMT2023015), Prakrititz Borah (IMT2023547)
**Status:** Specification v1.0. It follows the submitted proposal and the team's reply to the instructor's feedback, and nothing here should contradict either. Decisions the proposal did not settle are listed in `ARCHITECTURE.md` §10 as D-numbers.

---

## 1. One-line summary

Free-text trip request → the LLM fills a **typed schema** (semantic extraction only) → a **deterministic compiler** turns it into QF-LIA + Boolean constraints, each tracked by name → **Z3** decides SAT or UNSAT → SAT gives a verified timetable. UNSAT gives a **deletion-minimised unsat core** plus **Z3-Optimize relaxations** → the LLM only rephrases the result in plain English.

## 2. Problem

LLMs read travel requests well, but they are unreliable when a request has several hard constraints at once (budget, opening hours, travel time, ordering). SMT solvers reason exactly but need formal input. We split the work so that each component does only what it is good at, and **all reasoning is symbolic**.

## 3. What the instructor asked us to show (must be visible in code, UI and report)

| Instructor point | Our commitment | Where it shows |
|---|---|---|
| "Highlight the algorithmic approach on the neuro-symbolic reasoning part" | A named, staged algorithm: Extract → Validate/Retry → Ground → Compile (tracked) → Solve with DPLL(T) → (SAT: Optimize plan) / (UNSAT: deletion-based core minimisation → per-member Optimize relaxation) → Rephrase | `ARCHITECTURE.md` §4, report §Methodology, UI tab "Encoded constraints" |
| "Explain Hao et al. — where are you using it?" | We adopt their central idea: the LLM translates the request, the SMT solver is the formal verifier that guarantees every constraint, and unsat cores explain infeasibility. We differ in four stated ways (§6). | Report section "Comparison with Hao et al.", `ARCHITECTURE.md` §9 |

## 4. Goals (from proposal §1, unchanged)

- **G1.** Build an LLM → typed IR → Z3 pipeline that turns free-text trip requests into verified itineraries.
- **G2.** Every returned plan satisfies all extracted constraints, and an **independent plan checker** confirms it.
- **G3.** For infeasible requests, isolate a **minimal** conflicting set (unsat core) and suggest the **smallest relaxation** that restores feasibility.
- **G4.** Evaluate against a **pure-LLM baseline**, and measure **extraction accuracy** against gold constraints. The solver's guarantee only holds for the constraints it is given.

## 5. Non-goals (explicitly out of scope)

- Multi-day or multi-city trips, hotels, flights, and the full TravelPlanner setup. We are **single-day, single-city**.
- Live data (Maps APIs, live opening hours). The knowledge base is static and curated by hand.
- Soft preferences such as "I like art" or "something relaxing". These are recorded as `ignored_preferences` and shown to the user, but never encoded.
- Letting the LLM generate solver code, or letting the LLM propose fixes. Both are deliberately excluded (see §6).
- Fine-tuning, RAG or vector databases, agent frameworks, accounts or auth, deployment beyond a local or shared Gradio link.

## 6. Relationship to Hao et al. (NAACL 2025, arXiv:2404.11891) — required report content

**What we use from them.** The LLM is a translator from natural language into a formal problem. An SMT solver (Z3) is the formal verification tool that **guarantees** a returned plan satisfies every encoded constraint. **Unsat cores** explain why a request is infeasible.

**How we differ** (these four points were stated to the instructor and must be implemented and evaluated):

1. **Typed IR instead of solver code.** In Hao et al. the LLM writes the formulation steps and the Z3 code. In ours the LLM fills a Pydantic schema, and the encoding is done by a deterministic, unit-tested compiler. *Report wording (use exactly this register):* "encoding errors become deterministic, testable compiler bugs instead of stochastic LLM code errors". Do **not** write "the encoding cannot be wrong" (see `RISKS.md` R1).
2. **Minimal cores and solver-optimised relaxations.** In Hao et al. the LLM analyses the core and suggests modifications. We shrink the core to a minimal one by deletion, and Z3 Optimize computes the smallest change to each relaxable member.
3. **Independent checker.** A separate Python routine that does not import Z3 or the encoder re-verifies **every** plan, including the baseline's.
4. **Measured extraction accuracy.** The formal guarantee covers only the extracted constraints, so we report how often extraction matches the gold constraints. We also report an **oracle** run (gold IR → Z3) that separates extraction error from solving.

## 7. Users and use cases

- **U1 — Demo user / examiner.** Types a request in the Gradio app and sees the extracted IR, the constraints, and either a timeline or a conflict explanation with relaxations.
- **U2 — Team, as evaluator.** Runs the benchmark script and gets the metric tables for the report.
- **U3 — Team, as developer.** Edits the IR by hand in the UI and re-solves without calling the LLM, to debug.

## 8. Functional requirements

Priority: **P0** = must have for the viva, **P1** = should have, **P2** = only if time remains.

### Extraction
- **FR-1 (P0).** The LLM, using structured output, fills `TripRequestIR` (see `DATA_MODEL_AND_SCAFFOLDING.md`). Location fields are an **enum of knowledge-base ids**, so the LLM cannot invent a place.
- **FR-2 (P0).** Invalid output (schema, enum, or semantic validator failure) is rejected. The Pydantic error text is sent back to the LLM, with at most **3 retries**. After that the status is `EXTRACTION_FAILED`.
- **FR-3 (P0).** Places the user mentions that are not in the knowledge base go into `unresolved_mentions`. If that list is non-empty, the status is `NEEDS_CLARIFICATION` and no plan is produced. Silently dropping a place would break the guarantee.
- **FR-4 (P0).** Defaults that are filled in (for example a 09:00 start when the user only says "4 hours") are recorded in `assumed_defaults` and shown in the UI.
- **FR-5 (P0).** Two backends: OpenAI `gpt-4o-mini` and Ollama `llama3.1:8b`. Temperature is 0. Responses are cached on disk, keyed by a hash of (backend, model, prompt, schema).

### Encoding and solving
- **FR-6 (P0).** A deterministic compiler encodes the grounded problem as QF-LIA plus Boolean constraints. Every user requirement and every world fact (opening hours) gets **one named assumption literal**, which is the `assert_and_track` mechanism. Non-overlap and variable domains are untracked hard constraints.
- **FR-7 (P0).** Feasibility check: `Solver.check(assumptions)`. Z3's core is CDCL SAT with a linear-arithmetic theory solver, i.e. DPLL(T).
- **FR-8 (P0).** On SAT, Z3 `Optimize` picks the plan: first maximise the number of optional activities scheduled, then minimise total cost. This avoids empty plans when everything is optional.
- **FR-9 (P0).** On UNSAT: **deletion-based minimisation**. For each member of the core, re-solve without it. If the result is still UNSAT, drop that member permanently. The result is minimal (irreducible), and `is_minimal = True` is asserted in tests.
- **FR-10 (P0).** Relaxation: for each relaxable core member, solve the **whole** problem with only that member relaxed. Numeric members (budget, horizon end, user time window) get the smallest δ from `Optimize.minimize(δ)`. Boolean members (must-visit, precedence) are dropped and re-checked. Each relaxation reports `restores_feasibility`, because another, independent conflict can remain. World facts (opening hours) are listed as **not relaxable**.
- **FR-11 (P0).** Every solver call has a timeout (default 10 s). On timeout the status is `SOLVER_TIMEOUT`, which is never reported as SAT or UNSAT.

### Verification
- **FR-12 (P0).** The independent checker validates any `Plan` against a `ProblemInstance` (extracted or gold). It **must not import** `z3` or `nstrip.encode`, and a test enforces this.
- **FR-13 (P0).** The pipeline runs the checker on its own plan before returning it. A failure means a compiler bug: status `INTERNAL_ERROR`, and the plan is never shown as valid.

### Explanation
- **FR-14 (P0).** A deterministic template renders the result (plan, core, relaxations) as English. That is the ground-truth text.
- **FR-15 (P1).** The LLM rephrases the template text. A guard checks that every number and place name in the rephrasing appears in the template, and otherwise falls back to the template.

### Interface (Gradio)
- **FR-16 (P0).** Input box with example requests, a backend selector (OpenAI, Ollama, or cache only), and a list of the knowledge-base places.
- **FR-17 (P0).** Panels: extracted IR (JSON), assumed defaults and ignored preferences, encoded constraints (named, readable plus SMT-LIB), and the result, which is either a **timeline** or a **highlighted conflict** (core members, relaxations, explanation).
- **FR-18 (P1).** An editable IR box with a "Re-solve" button that skips the LLM.
- **FR-19 (P1).** An "Apply" button on each relaxation, which edits the IR and re-solves.

### Benchmark and evaluation
- **FR-20 (P0).** A generator produces **50 instances** with 3–12 locations, tight and loose budgets, and both feasible and deliberately infeasible cases, each storing its **gold IR** when generated. Feasible labels come from a **witness plan** that the checker validates. Infeasible labels come from a **seeded conflict** that can be shown by arithmetic. Z3 never produces the labels, because that would be circular.
- **FR-21 (P0).** Request text starts from a template and is partly **paraphrased by an LLM**. Every paraphrase must keep each number and place from the template, otherwise it is regenerated. The team reviews all 50 by hand.
- **FR-22 (P0).** Methods evaluated: `pipeline` (LLM → Z3), `oracle` (gold IR → Z3), `baseline` (pure LLM, GPT-4o family, same knowledge-base rows, allowed to answer "infeasible").
- **FR-23 (P0).** Metrics as in §10. Results are written as JSONL per run, and a summary is generated as CSV and markdown tables for the report.

## 9. Non-functional requirements

- **NFR-1.** Reproducible: pinned dependencies, fixed seeds, LLM cache committed, model names and versions logged per run.
- **NFR-2.** The full test suite runs offline (no API key) in under 60 s.
- **NFR-3.** Solve time is under 2 s per instance at 12 locations on a laptop (expected; measured and reported, not promised).
- **NFR-4.** The demo works offline through Ollama or cached examples if the network is down at the viva.
- **NFR-5.** All times are integer minutes since midnight and all money is integer currency units. No floats reach the solver.

## 10. Evaluation metrics (from proposal §5)

| Metric | Definition | Methods |
|---|---|---|
| Plan violation rate | Share of returned (SAT-claimed) plans that fail the checker against the **gold** problem. The pipeline is also checked against its **extracted** problem, and that must be 0. | pipeline, oracle, baseline |
| Extraction accuracy | Canonical constraint tuples, extracted vs gold: micro precision, recall and F1 per constraint kind, plus per-instance exact match | pipeline |
| Infeasibility detection | Precision and recall with UNSAT as the positive class. Core match: core equals the seeded conflict, and separately the rate of valid minimal cores. Minimality is verified by re-solving with each member dropped. | pipeline, oracle (detection only for baseline) |
| Runtime | Mean and median solve time by number of locations. Extraction latency is reported separately. | pipeline, oracle |
| End-to-end success | Correct SAT/UNSAT status **and** (if SAT) zero gold violations | all |

Counts are reported with Wilson 95% intervals. With n = 50 we make no claims of statistical significance.

**Expected-by-construction result:** the oracle has 0 gold violations, and the pipeline has 0 violations against its extracted constraints. Every pipeline violation against gold is therefore an extraction error, and this is the main argument of the report.

## 11. Deliverables

1. A reproducible Python codebase covering extraction, encoding, diagnosis, the checker, the benchmark and the Gradio app.
2. A report covering goals, methodology (the algorithm, stated as such), data and constraints, the **comparison with Hao et al.**, results, limitations and conclusions.
3. A live demo on examiner-provided queries at the viva.

## 12. Milestones (in order of dependency; dates to be set by the team)

| # | Milestone | Exit criterion |
|---|---|---|
| M1 | Models, knowledge base, checker | Proposal example (Museum/Park/Café) hand-built as a `ProblemInstance`; checker tests pass |
| M2 | Compiler, solve, core, relax | Proposal example returns core {must_visit:museum, must_visit:cafe, budget} and relaxation budget → 35 |
| M3 | Extraction and grounding | 10 hand-written requests extract correctly with both backends |
| M4 | Benchmark generator and runner | 50 instances, labels self-verified; oracle run gives 0 gold violations |
| M5 | Baseline and full evaluation | All metric tables generated |
| M6 | Gradio UI | Demo script rehearsed offline |
| M7 | Report | Hao et al. comparison section written |

## 13. Acceptance criteria for "done"

- The proposal's worked example reproduces exactly as written in the proposal, with the extra drop-Museum relaxation (see `RISKS.md` R9).
- `pytest` is green offline, and the independence test passes.
- Oracle: 0 gold violations, and 100% correct status on the 50 instances.
- The report contains the Hao et al. section and the extraction-accuracy table.
