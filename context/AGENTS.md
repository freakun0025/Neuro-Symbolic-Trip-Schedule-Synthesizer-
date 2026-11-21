# AGENTS.md — rules for any coding agent working on this repo

Project: **Neuro-Symbolic Trip & Schedule Synthesizer** (AID 851 course project). Python package `nstrip`.
The specs in `docs/` are the source of truth: `PRD.md` (what), `ARCHITECTURE.md` (how), `DATA_MODEL_AND_SCAFFOLDING.md` (exact models and folders), `RISKS.md` (known pitfalls). If code and spec disagree, stop and flag it; do not quietly "fix" the spec in code.

## 1. The one rule

**The LLM does semantic extraction and rephrasing only. All reasoning is symbolic (Z3).**
Never add code where an LLM decides feasibility, picks the schedule, writes solver code, chooses a relaxation, or fills facts (cost, duration, hours, transit) that the KB has.

## 2. Hard invariants (a PR that breaks one is wrong, even if tests pass)

1. LLM output reaches the solver **only** via `TripRequestIR.model_validate` → `ground()` → `ProblemInstance` → `compile_problem()`.
2. Location fields in the LLM schema are an **enum of KB ids**. Places not in the KB go into `unresolved_mentions` → status `NEEDS_CLARIFICATION`. Never drop or fuzzy-map them silently.
3. Every user requirement and every opening-hours fact is a **named tracked constraint** (assumption literal, cid format in `models/constraints.py`). Non-overlap and domain bounds are untracked hard constraints.
4. Constraints are emitted **only when they apply** (no budget → no `budget` cid).
5. On UNSAT, the core is minimised by **deletion** and called **"minimal"** (never "minimum").
6. Relaxations are computed by **Z3 Optimize on the full problem**, and each one carries `restores_feasibility`. Opening hours are **never** relaxed.
7. `nstrip/checker/` **must not import** `z3`, `nstrip.encode`, or `nstrip.solve`. It checks **consecutive** pairs after sorting, which deliberately differs from the encoder's pairwise check. Do not "refactor" the checker to share code with the encoder.
8. The pipeline runs the checker on its own plan; a failure → `INTERNAL_ERROR`, never a displayed plan.
9. Solver calls always have a timeout; `unknown` → `SOLVER_TIMEOUT`. Never map unknown to SAT or UNSAT.
10. Integers only: minutes since midnight, whole currency units. No floats in `ProblemInstance` or in Z3 terms.
11. LLM calls: temperature 0 (paraphrase generator excepted, and seeded), go through `DiskCache`, and log the model string.
12. Benchmark labels come from a **witness plan** (SAT) or a **seeded arithmetic conflict** (UNSAT). Z3 may cross-check a label, never produce it.
13. Explanation text comes from `explain/templates.py`. An LLM rephrase is used only if the numbers/names guard passes.
14. The travel matrix must be metric (triangle inequality); `load_kb` asserts this. Don't disable the assertion.

## 3. Setup and commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # OPENAI_API_KEY=..., NSTRIP_BACKEND=openai|ollama|cache

pytest -q                       # must pass offline, < 60 s
ruff check src tests

nstrip-gen  --seed 851 --out data/benchmark          # generate 50 instances
nstrip-run  --method oracle   --backend cache         # gold IR → Z3
nstrip-run  --method pipeline --backend openai --model gpt-4o-mini
nstrip-run  --method baseline --backend openai --model gpt-4o-mini
nstrip-eval results/<run_id>                          # summary.csv + tables.md
nstrip-app                                            # Gradio UI
```

## 4. Coding conventions

- Python 3.11, type hints everywhere, Pydantic v2 models with `extra="forbid"`.
- Pure functions per stage; no global mutable state; config via `nstrip.config`.
- Z3: build terms in `encode/`, run solvers in `solve/`. Name every assumption literal with its cid (`z3.Bool(cid)`) so cores print readably.
- Do not use `float` for time or money anywhere. Convert `"HH:MM"` to `int` in validators.
- Errors are statuses in `PipelineResult`, not exceptions that leak to the UI.
- Keep modules small; if a file passes ~300 lines, split it along the stage boundaries in `ARCHITECTURE.md` §3.

## 5. Testing rules

- Every change to `encode/` or `solve/` must keep these green: `test_proposal_example.py`, `test_core_minimality.py`, `test_relax.py`, `test_z3_vs_bruteforce.py`.
- Any new constraint kind needs: a compiler test, a checker test (a violation is detected), a brute-force case, a canonical-tuple entry, a template sentence, and a row in `ARCHITECTURE.md` §4.3.
- Tests never call a real LLM. Use `FakeClient` (scripted responses) or `CacheOnlyClient`.
- `test_checker_independence.py` must stay; do not weaken its import ban.

## 6. Scope guard — do NOT add (see RISKS.md Part B)

Multi-day/multi-city, live map APIs, MaxSMT global relaxation, MUS enumeration, a custom SAT solver, an LLM-writes-Z3-code path, LangChain/agents/RAG/vector DB, databases, Docker, auth, non-Gradio front ends, soft preference scoring, day-of-week hours, more LLM backends, fine-tuning. If a task seems to need one of these, ask first.

## 7. Wording rules (for docstrings, UI text, report drafts)

- "minimal core", not "minimum core".
- "guaranteed to satisfy all **extracted** constraints", never "guaranteed correct".
- "encoding errors are deterministic, testable compiler bugs", never "the encoding cannot be wrong".
- "CDCL(T), the modern form of DPLL(T)" when describing Z3.
- Hao et al. = *Large Language Models Can Solve Real-World Planning Rigorously with Formal Verification Tools*, NAACL 2025 (arXiv:2404.11891).

## 8. Definition of done for any task

- Tests pass offline; new behaviour has a test.
- No invariant in §2 is violated.
- If the change affects the algorithm, models or metrics, update the matching section of `docs/ARCHITECTURE.md` or `docs/DATA_MODEL_AND_SCAFFOLDING.md` in the same change.
