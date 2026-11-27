# AGENTS.md — rules for anyone (human or coding agent) working on this repo

Project: **Neuro-Symbolic Trip & Schedule Synthesizer** (AID 851 course project). Python package `nstrip`.
The specs in `context/` are the source of truth: `PRD.md` (what), `ARCHITECTURE.md` (how), `DATA_MODEL_AND_SCAFFOLDING.md` (exact models and folders), `RISKS.md` (known pitfalls). If code and spec disagree, stop and flag it; do not quietly "fix" the spec in code.

## 1. The one rule

**The LLM does semantic extraction and rephrasing only. All reasoning is symbolic (Z3).**
Never add code where an LLM decides feasibility, picks the schedule, writes solver code, chooses a relaxation, or fills facts (cost, duration, hours, showtimes, transit) that the KB has.
**Single exception:** `nstrip/ablation/codegen.py`, the Hao-style ablation that exists only to be *measured* against the pipeline. It is evaluation-only and must never be imported by `pipeline`, `app`, or anything they import.

## 2. Hard invariants (a PR that breaks one is wrong, even if tests pass)

1. LLM output reaches the solver **only** via `TripRequestIR.model_validate` → `ground()` → `ProblemInstance` → `compile_problem()`.
2. Location fields in the LLM schema are an **enum of KB ids**. Places not in the KB go into `unresolved_mentions` → status `NEEDS_CLARIFICATION`. Never drop or fuzzy-map them silently.
3. Every user requirement and every world fact (opening hours, showtimes) is a **named tracked constraint** (assumption literal, cid format in `models/constraints.py`). Non-overlap and domain bounds are untracked hard constraints.
4. Constraints are emitted **only when they apply** (no budget → no `budget` cid).
5. On UNSAT, the core is minimised by **deletion** and called **"minimal"** (never "minimum").
6. Relaxations are computed by **Z3 Optimize on the full problem**, and each one carries `restores_feasibility`. Opening hours and showtimes are **never** relaxed.
7. `nstrip/checker/` **must not import** `z3`, `nstrip.encode`, or `nstrip.solve`. It checks **consecutive** pairs after sorting, which deliberately differs from the encoder's pairwise check. Do not "refactor" the checker to share code with the encoder.
8. The pipeline runs the checker on its own plan; a failure → `INTERNAL_ERROR`, never a displayed plan.
9. Solver calls always have a timeout; `unknown` → `SOLVER_TIMEOUT`. Never map unknown to SAT or UNSAT.
10. Integers only: minutes since midnight, whole currency units. No floats in `ProblemInstance` or in Z3 terms.
11. LLM calls: temperature 0 (paraphrase generator excepted, and seeded), go through `DiskCache`, and log the base URL and model string. There is **one** OpenAI-compatible client. The provider is chosen by `OPENAI_BASE_URL` and the models by `NSTRIP_*_MODEL` in `.env`. No provider-specific SDKs or branches, and no model ids hard-coded in source.
12. Benchmark labels come from a **witness plan** (SAT) or a **seeded arithmetic conflict** (UNSAT). Z3 may cross-check a label, never produce it.
13. Explanation text comes from `explain/templates.py`. An LLM rephrase is used only if the numbers/names guard passes.
14. The travel matrix must be metric (triangle inequality); `load_kb` asserts this. Don't disable the assertion.
15. `codegen` runs generated code only in a subprocess (`python -I`, temp cwd, timeout), only on team-made benchmark instances, never from the UI.
16. Optional verification (`extract.verify`, FR-27) is still **extraction**: the LLM sees the request, its own IR and the *user* requirements in the minimal conflict (plain sentences, no KB facts), and may only return a corrected IR, which goes through invariant 1 again. One round, every changed field logged, off by default. It must never be shown world facts or asked to make the day feasible; its "real conflicts erased" rate is reported.

## 3. Setup and commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # OPENAI_BASE_URL, OPENAI_API_KEY, NSTRIP_MODEL (+ per-role overrides), NSTRIP_MODE=live|cache

pytest -q                       # must pass offline, < 60 s
ruff check src tests

nstrip-gen  --seed 851 --out data/benchmark          # generate 50 instances
nstrip-run  --method oracle   --set generated         # gold IR → Z3 (no LLM)
nstrip-run  --method pipeline --set generated         # models come from .env
nstrip-run  --method baseline --set generated [--model <strongest>]
nstrip-run  --method codegen  --set generated         # Hao-style ablation
nstrip-run  --method pipeline --set heldout           # repeat any method on the held-out set
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
- `test_checker_independence.py` must stay; do not weaken its import ban (checker ↛ z3/encode/solve; pipeline/app ↛ ablation).
- Never tune prompts on `data/benchmark/heldout/`.

## 6. Scope guard — do NOT add (see RISKS.md Part B)

Multi-day/multi-city, live map APIs, MaxSMT global relaxation, MUS enumeration, a custom SAT solver, an LLM-writes-Z3-code path **outside `nstrip/ablation/`**, LangChain/agents/RAG/vector DB, databases, Docker, auth, non-Gradio front ends, soft preference scoring, day-of-week hours, provider-specific LLM SDKs, fine-tuning. If a task seems to need one of these, ask first.

## 7. Wording rules (for docstrings, UI text, report drafts)

- "minimal core", not "minimum core".
- "guaranteed to satisfy all **extracted** constraints", never "guaranteed correct".
- "encoding errors are deterministic, testable compiler bugs", never "the encoding cannot be wrong".
- "CDCL(T), the modern form of DPLL(T)" when describing Z3.
- Hao et al. = *Large Language Models Can Solve Real-World Planning Rigorously with Formal Verification Tools*, NAACL 2025 (arXiv:2404.11891).

## 8. Definition of done for any task

- Tests pass offline; new behaviour has a test.
- No invariant in §2 is violated.
- If the change affects the algorithm, models or metrics, update the matching section of `context/ARCHITECTURE.md` or `context/DATA_MODEL_AND_SCAFFOLDING.md` in the same change.
