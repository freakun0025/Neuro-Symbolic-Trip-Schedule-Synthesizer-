# CLAUDE.md

Neuro-Symbolic Trip & Schedule Synthesizer (AID 851). Python package `nstrip`.
Read `context/AGENTS.md` for the full rules; this file repeats the essentials so it works on its own.

## What this project is

Free-text single-day trip request in Singapore → the LLM fills a typed Pydantic IR → a deterministic compiler encodes QF-LIA + Boolean constraints with named assumption literals → Z3 (DPLL(T)) → SAT: an Optimize-chosen plan verified by an independent checker / UNSAT: a deletion-minimised core + per-member Z3-Optimize relaxations → template explanation (optional guarded LLM rephrase) → Gradio UI.

**The LLM extracts and rephrases. It never reasons, plans, writes solver code, or proposes fixes.** That boundary is the whole point of the project (and the main difference from Hao et al., NAACL 2025). The only place an LLM writes Z3 code is `nstrip/ablation/codegen.py`, an evaluation-only ablation that exists to measure that difference. The pipeline and app never import it.

## Source of truth

| Question | File |
|---|---|
| What must it do? | `context/PRD.md` |
| How does it work / the algorithm? | `context/ARCHITECTURE.md` (summary: `context/ARCHITECTURE_ESSENTIAL.md`) |
| Exact models, fields, folders, signatures | `context/DATA_MODEL_AND_SCAFFOLDING.md` |
| What will go wrong / what not to build | `context/RISKS.md` |

If the code you are asked to write conflicts with these, say so before writing it.

## Non-negotiables

1. LLM → `TripRequestIR` (validated, retry ≤3) → `ground()` → `ProblemInstance` → `compile_problem()`. There is no other path into Z3.
2. Places are an enum of KB ids; unknown → `NEEDS_CLARIFICATION`.
3. One named assumption literal per requirement/world fact; cids per `models/constraints.py`; emit only applicable constraints.
4. UNSAT → deletion minimisation → "minimal" core → Optimize relaxations on the **full** problem with `restores_feasibility`; opening hours and showtimes never relaxed.
5. `nstrip/checker` never imports `z3` / `encode` / `solve`, and checks consecutive pairs after sorting.
6. A pipeline plan that fails the checker → `INTERNAL_ERROR`.
7. Timeouts → `SOLVER_TIMEOUT`, never a guess.
8. Ints only (minutes, currency units).
9. LLM calls: temperature 0, disk-cached, base URL and model logged. Tests never hit a real LLM. One OpenAI-compatible client; provider = `OPENAI_BASE_URL`, models = `NSTRIP_*_MODEL` in `.env`; no hard-coded model ids.
10. Benchmark labels from a witness plan or a seeded conflict, never from Z3. Never tune prompts on the held-out set.

## Commands

```bash
pip install -e ".[dev]"
pytest -q                     # offline, must stay green
ruff check src tests
nstrip-run --method oracle --set generated     # no LLM needed
nstrip-app
```

## How to work in this repo

- Before changing `encode/` or `solve/`, run `pytest tests/test_proposal_example.py tests/test_core_minimality.py tests/test_relax.py tests/test_showtime.py tests/test_z3_vs_bruteforce.py`; run them again after.
- Follow the build order in `DATA_MODEL_AND_SCAFFOLDING.md` §8; don't start the UI before the checker and solver are tested.
- Add a constraint kind only with all six pieces listed in `AGENTS.md` §5.
- Keep changes small and stage-local. Don't introduce new dependencies without asking.
- Don't build anything in `RISKS.md` Part B (over-engineering list) unless explicitly asked.
- When writing report text or UI copy, use the wording rules in `AGENTS.md` §7 ("minimal", "extracted constraints", "deterministic, testable compiler bugs").

## Regression anchor

`tests/test_proposal_example.py`: 4 h, $30, must-visit Museum ($20, 2 h), Park ($0, 1 h), Café ($15, 1 h), Museum before Café, transit 0 →
UNSAT, minimal core `{budget, must_visit:museum, must_visit:cafe}`, relaxations: budget→35 ✔, drop Café ✔, drop Museum ✔. With Café optional → SAT, plan = Museum + Park.
If this test changes, the change is probably wrong.
