# ARCHITECTURE — ESSENTIAL (one page; full design in ARCHITECTURE.md)

**Project:** Neuro-Symbolic Trip & Schedule Synthesizer (AID 851). Single-day trip planning in **Singapore** (~35–40 places, SGD, some with fixed showtimes).

**Core rule:** the LLM does **semantic extraction** and **rephrasing** only. **All reasoning is symbolic** (Z3).

## Pipeline
```
text → [1] LLM fills TripRequestIR (Pydantic v2; places = enum of KB ids; invalid → retry ≤3)
     → [2] ground with KB → ProblemInstance (ints: minutes, currency units; defaults logged)
     → [3] deterministic compiler → QF-LIA + Bool, one named assumption literal per requirement
     → [4] Z3 Solver.check(assumptions)  (CDCL + LIA theory = DPLL(T))
          SAT   → Optimize: max #optional visits, then min cost; then earliest starts for that order → Plan → independent checker
          UNSAT → core → deletion minimisation (drop each, re-solve) → minimal core
                  → per member: Optimize min δ (budget/horizon/window) or drop (must_visit/precedence)
                    on the FULL problem, flag restores_feasibility; opening hours + showtimes = world facts, not relaxable
     → [5] template explanation → optional LLM rephrase (numbers/names guard)
     → [6] Gradio: IR | defaults | constraints | timeline or conflict
```

## Constraints (cid = name that appears in cores)
| cid | formula |
|---|---|
| `budget` | Σ If(X_i,C_i,0) ≤ B |
| `horizon` | X_i ⇒ S_i ≥ H0 ∧ S_i+D_i ≤ H1 |
| `opening:<id>` | X_i ⇒ S_i ≥ O_i ∧ S_i+D_i ≤ K_i |
| `showtime:<id>` | X_i ⇒ ∨_k S_i = t_k (only for places with showtimes) |
| `window:<id>` | user-stated earliest/latest, same shape |
| `must_visit:<id>` | X_i |
| `precedence:<a>:<b>` | X_a ∧ X_b ⇒ S_a+D_a+T(a,b) ≤ S_b |
| non-overlap (hard, untracked) | X_i ∧ X_j ⇒ P_ij ∨ P_ji, P_ij ↔ S_i+D_i+T(i,j) ≤ S_j |

Emit a constraint only when it applies. The travel matrix must satisfy the triangle inequality (asserted on load).

## Invariants (never break)
1. No LLM output reaches Z3 except through validated `TripRequestIR` → `ProblemInstance`.
2. `nstrip.checker` never imports `z3`, `nstrip.encode` or `nstrip.solve`, and checks only consecutive pairs after sorting.
3. Every pipeline plan passes the checker against its own problem, otherwise `INTERNAL_ERROR`.
4. Unknown place → `NEEDS_CLARIFICATION`; timeout → `SOLVER_TIMEOUT`. Never guess SAT or UNSAT.
5. Cores are "minimal" (irreducible), never called "minimum".
6. Benchmark labels come from a witness plan (SAT) or a seeded arithmetic conflict (UNSAT), never from Z3 alone.
7. LLM calls: temperature 0, disk-cached, base URL + model name logged.
8. `nstrip.ablation` (LLM-written code) is evaluation-only; the pipeline and app never import it.

## Evaluation
- **Methods:**
  - `pipeline`
  - `oracle` (gold IR → Z3)
  - `baseline` (pure LLM, same model and strongest model)
  - `codegen` (Hao-style LLM-writes-Z3 ablation)
- **Metrics:**
  - gold violation rate
  - extraction P/R/F1, exact match and error taxonomy
  - UNSAT precision/recall, core match and minimality
  - core size (raw vs. deletion vs. `smt.core.minimize`)
  - codegen crash rate
  - runtime by n, plus a stress sweep to n = 30
  - end-to-end success
- **Sets:** 50 generated instances (3–12 places, 30 SAT / 20 UNSAT, 6 conflict types) and 15 hand-written held-out instances, reported separately with Wilson CIs.

## Hao et al. (NAACL 2025) in one line
Same idea (the LLM translates, the SMT solver verifies, cores explain), but here the LLM produces a **typed IR, not code** (measured by the `codegen` ablation), we use **minimal cores + Optimize relaxations, not LLM fixes**, an **independent checker** verifies every plan, and **extraction accuracy is measured**.

## Stack
Python 3.11, z3-solver, Pydantic v2, `openai` SDK against any OpenAI-compatible base URL (OpenAI / Gemini / Groq / OpenRouter / local Ollama; models set in `.env`), pandas, numpy, pytest, Gradio.
