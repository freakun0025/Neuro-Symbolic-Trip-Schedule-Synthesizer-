# ARCHITECTURE — Neuro-Symbolic Trip & Schedule Synthesizer

This file is the authoritative technical design. `ARCHITECTURE_ESSENTIAL.md` is a one-page summary of it, and the exact field-level schemas are in `DATA_MODEL_AND_SCAFFOLDING.md`.

---

## 1. Design principle

> **The LLM is used only for semantic extraction and for rephrasing. All reasoning is symbolic.**

| Concern | Done by | Never done by |
|---|---|---|
| Understanding free text | LLM (structured output) | — |
| Mapping place names to knowledge-base ids | LLM, restricted to an enum of KB ids | free-text fuzzy matching after the fact |
| Filling missing facts (cost, duration, hours, transit) | Deterministic grounding from the KB | LLM |
| Encoding into logic | Deterministic compiler | LLM (this is the main difference from Hao et al.) |
| Deciding feasibility, choosing the plan | Z3 Solver / Optimize | LLM |
| Explaining infeasibility | Minimal core (deletion) + Z3 Optimize relaxations | LLM |
| Verifying the plan | Independent Python checker | Z3 or the encoder |
| Wording the answer | Template; LLM rephrase is optional and guarded | — |

## 2. Pipeline

```
 request text
     │
 [1] EXTRACT   LLM + structured output ──► TripRequestIR (Pydantic v2)
     │          invalid → feed validation error back, retry ≤3 → EXTRACTION_FAILED
     │          unresolved_mentions ≠ ∅ → NEEDS_CLARIFICATION
 [2] GROUND    IR + KB ──► ProblemInstance (all ints, all facts filled, assumed_defaults logged)
     │
 [3] COMPILE   ProblemInstance ──► Encoding {vars, hard constraints, tracked: cid → (literal, formula)}
     │
 [4] SOLVE     Solver.check(assumption literals)    [DPLL(T): CDCL + LIA theory]
     ├── SAT ──► [4a] Optimize (max optional visits, then min cost) ──► Plan
     │            └─► [5] CHECK (independent) ── fail → INTERNAL_ERROR
     ├── UNSAT ─► [4b] MINIMISE core by deletion ──► [4c] RELAX each member (Optimize / drop)
     └── UNKNOWN/timeout ──► SOLVER_TIMEOUT
     │
 [6] EXPLAIN   template text ──► (optional) LLM rephrase with number/name guard
     │
 [7] UI        Gradio: IR | defaults | constraints | timeline or conflict view
```

Each stage is a pure function from typed input to typed output, so any stage can be tested on its own, and the oracle evaluation enters at [2] with the gold IR.

## 3. Modules

| Module | Responsibility | May import |
|---|---|---|
| `nstrip.models` | All Pydantic models (IR, ProblemInstance, Plan, Diagnosis, CheckReport, RunRecord) | pydantic only |
| `nstrip.kb` | Load and validate the KB CSVs; build the travel matrix; assert metric closure | models, pandas |
| `nstrip.extract` | Prompt, LLM clients (OpenAI, Ollama), disk cache, retry loop | models, kb |
| `nstrip.ground` | IR + KB → ProblemInstance; defaults | models, kb |
| `nstrip.encode` | ProblemInstance → Encoding (Z3 terms) | models, z3 |
| `nstrip.solve` | feasibility, optimisation, core minimisation, relaxation | models, encode, z3 |
| `nstrip.checker` | Independent plan verification | models, kb — **not z3, not encode, not solve** |
| `nstrip.explain` | Templates; guarded LLM rephrase | models, extract.llm_client |
| `nstrip.pipeline` | Orchestrates [1]–[6]; returns `PipelineResult` | everything above |
| `nstrip.baseline` | Pure-LLM planner | models, kb, extract.llm_client |
| `nstrip.bench` | generate, paraphrase, run, metrics, tables | everything |
| `nstrip.app` | Gradio UI | pipeline |

## 4. The neuro-symbolic algorithm (what the instructor asked to highlight)

### 4.1 Extraction (neural, constrained)

```
function EXTRACT(text, kb, backend):
    schema ← TripRequestIR with LocationId := Enum(kb.ids)      # dynamic enum
    prompt ← SYSTEM_RULES + kb.place_list() + FEW_SHOTS + text
    for attempt in 1..3:
        raw ← backend.structured_call(prompt, schema, temperature=0)   # cached
        try: ir ← TripRequestIR.model_validate(raw); return ir
        except ValidationError as e: prompt ← prompt + "Your output was invalid: " + e
    return EXTRACTION_FAILED
```
The validators check: ids are in the KB, times are "HH:MM" and within 00:00–23:59, earliest < latest, precedence endpoints are among the activities, there is no self-precedence, and numbers are non-negative.

### 4.2 Grounding (symbolic, deterministic)

- For each activity, the duration and cost come from the user override if given, otherwise from the KB.
- `[O_i, K_i]` = KB opening hours. The user window, if stated, is a separate constraint.
- Horizon: `H0` = `day_start` or **09:00** (default, logged). `H1` = the earlier of `day_end` and `H0 + duration_limit_min`. If neither is given, `H1` = **21:00** (default, logged).
- `T(i,j)` comes from the KB travel matrix, which is guaranteed metric (triangle inequality), see §6.
- The budget is `None` if not stated, and then no budget constraint is emitted.

### 4.3 Encoding (QF-LIA + Boolean)

Variables per activity i: `X_i : Bool` (scheduled), `S_i : Int` (start, minutes). `D_i`, `C_i`, `O_i`, `K_i`, `T(i,j)` are integer constants.

| cid (name in core) | Formula | Tracked | Relaxable via |
|---|---|---|---|
| `budget` | Σ If(X_i, C_i, 0) ≤ B | yes | raise B by min δ |
| `horizon` | ∀i: X_i ⇒ (S_i ≥ H0 + T(o,i)\* ∧ S_i + D_i + T(i,o)\*\* ≤ H1) | yes | extend H1 by min δ |
| `opening:<id>` | X_i ⇒ (S_i ≥ O_i ∧ S_i + D_i ≤ K_i) | yes (world fact) | **not relaxable** |
| `window:<id>` | X_i ⇒ (S_i ≥ E_i ∧ S_i + D_i ≤ L_i) (user-stated) | yes | widen to min δ (L_i + δ; E_i − δ) |
| `must_visit:<id>` | X_i | yes | drop (make optional) |
| `precedence:<a>:<b>` | (X_a ∧ X_b) ⇒ S_a + D_a + T(a,b) ≤ S_b | yes | drop |
| `nonoverlap:<i>:<j>` | (X_i ∧ X_j) ⇒ (P_ij ∨ P_ji), with P_ij ↔ (S_i + D_i + T(i,j) ≤ S_j) | **no** (hard) | — |
| domain | 0 ≤ S_i ≤ 1440 | **no** (hard) | — |

\* only if `start_location` is set; \*\* only if `return_to_start` is true.

**Tracking mechanism.** For each tracked cid we create `a_cid = Bool(cid)`, add `Implies(a_cid, φ_cid)`, and call `check(*assumptions)`. This is exactly what `assert_and_track` does internally. We use explicit assumption literals because core minimisation and relaxation need to switch members on and off without rebuilding the solver.

**Proxy variables `P_ij`** name each disjunct, in the spirit of a Tseitin encoding. Z3 does its own CNF conversion, so this is a modelling and readability choice that lets us display the chosen order, not a requirement.

Constraints are emitted **only when they apply** (proposal: "it will depend on the context what statements are required"). There is no budget constraint without a budget, no precedence constraint without a stated order, and so on.

### 4.4 Solve (DPLL(T))

```
function SOLVE(enc, timeout):
    s ← Solver(); s.set(timeout); s.add(enc.hard); s.add(Implies(a_c, φ_c) for c in enc.tracked)
    r ← s.check(*enc.assumptions)
    if r = sat:     return OPTIMISE_PLAN(enc)
    if r = unsat:   core ← MINIMISE(s, s.unsat_core()); return DIAGNOSE(core)
    return SOLVER_TIMEOUT
```

### 4.5 Plan selection on SAT

```
function OPTIMISE_PLAN(enc):
    o ← Optimize(); o.add(enc.hard); o.add(φ_c for every tracked c)     # all tracked are hard here
    o.maximize(Σ If(X_i,1,0) for optional i)        # objective 1 (lexicographic)
    o.minimize(Σ If(X_i,C_i,0))                      # objective 2
    if o.check() = sat: m ← o.model() else m ← s.model()   # fallback: any feasible model
    return Plan(visits = sorted [(i, S_i, S_i+D_i) | m(X_i)])
```

### 4.6 Core minimisation by deletion (UNSAT)

```
function MINIMISE(s, core):
    C ← list(core)                                   # assumption literals
    for c in copy(C):
        if c ∉ C: continue                           # already removed by a shrink below
        r ← s.check(*(C \ {c}))
        if r = unsat: C ← [x for x in s.unsat_core() if x in C \ {c}]   # also shrink by the new core
        elif r = unknown: mark is_minimal=False; continue
        # r = sat → c is necessary, keep it
    return C, is_minimal
```
- Cost: at most |core| solver calls.
- The result is **minimal** (irreducible: removing any member makes it SAT). It is **not** necessarily the **minimum** (smallest) core. The report must say "minimal", never "minimum".
- Untracked hard constraints (non-overlap, domains) are always present, so a core is "minimal relative to the physics of the schedule".

### 4.7 Relaxation with Z3 Optimize

For each `c ∈ C` with a relaxable kind:
```
function RELAX(enc, c):
    o ← Optimize(); o.add(enc.hard); o.add(φ_x for x in tracked if x ≠ c)   # FULL problem, not just the core
    match kind(c):
      budget:      δ ≥ 0; o.add(Σ… ≤ B + δ); o.minimize(δ)
      horizon:     δ ≥ 0; o.add(horizon with H1 + δ); o.minimize(δ)
      window:      δe, δl ≥ 0; o.add(window with E−δe, L+δl); o.minimize(δe+δl)
      must_visit:  (nothing added: the activity becomes optional)
      precedence:  (nothing added)
    r ← o.check()
    return Relaxation(cid=c, kind, old, new, restores_feasibility = (r = sat))
```
- Relaxing one member resolves **this** conflict. If there are other, independent conflicts, `restores_feasibility = False`, and the UI says "this alone is not enough — apply and re-diagnose".
- `opening:<id>` members are reported as **world facts**: "Museum is open 10:00–17:00". They appear in the explanation but get no relaxation.
- Relaxations are **not ranked** against each other (different units). They are listed in core order.

### 4.8 Worked example (proposal §2, regression test `test_proposal_example`)

Request: 4 h, $30, want Museum ($20, 2 h), Park (free, 1 h), Café ($15, 1 h), Museum before Café, transit 0.

- Tracked: `budget`, `horizon`, `must_visit:museum`, `must_visit:park`, `must_visit:cafe`, `precedence:museum:cafe` (+ `opening:*`, all wide open in this fixture).
- 20 + 0 + 15 = 35 > 30 → UNSAT.
- Minimal core: `{budget, must_visit:museum, must_visit:cafe}`. Park costs 0 and drops out during minimisation.
- Relaxations: budget → 35 ✔; drop must_visit:cafe ✔ (Museum + Park, $20); drop must_visit:museum ✔ (Park + Café, $15).
- If Café is optional instead: SAT. The optimiser cannot add Café (20 + 15 > 30), so the plan is Museum + Park.

### 4.9 Explanation

The template is rendered from `Diagnosis` and `Plan`. For example: "Your must-visit places Museum ($20) and Café ($15) cost $35 in total, which is more than your budget of $30. Options: raise the budget to $35, or drop Café, or drop Museum." The optional LLM rephrase must preserve every number and place name in the template (a regex set-inclusion check), otherwise the template is shown.

## 5. Independent checker

The checker's input is a `ProblemInstance` and a `Plan`, and its output is a `CheckReport` (a list of violations). The algorithm is deliberately **different** from the encoding:

1. Every visit is a known activity with no duplicates, and `end − start == D_i`.
2. **Sort visits by start**. For each **consecutive** pair: `next.start ≥ prev.end + T(prev,next)`. The encoder checks all pairs; the checker checks only adjacent ones.
3. First and last visit against the horizon (and origin and return, if set).
4. Opening windows, user windows, budget sum, all must-visits present, precedences where both are present.

Under a metric travel matrix (§6), adjacent checks are equivalent to the encoder's pairwise constraints. Without one, the checker is *weaker* (it accepts some plans the encoder would reject), never stronger, so a checker failure on a Z3 plan always means a compiler bug.

A test (`test_checker_independence`) parses the checker's AST and fails on any import of `z3`, `nstrip.encode` or `nstrip.solve`.

## 6. Knowledge base

- **One city**, about 25–30 places, curated by hand (the team chooses; Bengaluru is suggested for the viva audience). Each place has: id, name, aliases, category, cost, typical duration, one opening window per day, and lat/lon.
- Travel time: `T(i,j) = OVERHEAD + ceil(haversine_km(i,j) / SPEED_KMPH · 60)`, with `T(i,i) = 0`. The loader runs Floyd–Warshall and **asserts** that the matrix equals its own shortest-path closure (triangle inequality). This is what makes pairwise non-overlap with transit correct (see `RISKS.md` R5).
- Values are approximate. The report says so, with the date they were curated.

## 7. Benchmark

- **50 instances**: n ∈ {3,…,12}, 5 per n → 3 feasible + 2 infeasible per n (30 SAT / 20 UNSAT overall). Budgets are tight or loose, alternating.
- **SAT label**: the generator first builds a **witness schedule** (a random subset and order, times placed greedily), then sets the constraints around it (loose: budget = witness cost × 1.5; tight: budget within 10%). The witness must pass the checker.
- **UNSAT label**: the generator starts from a SAT instance and **seeds exactly one conflict** that can be shown infeasible by arithmetic, then records `seeded_conflict` (a cid set). There are 5 conflict types, 4 instances each:
  1. budget < Σ must-visit costs
  2. horizon < Σ must-visit durations + minimum transit chain
  3. must-visit window shorter than the duration, or outside the horizon
  4. precedence a→b where a opens after b closes
  5. precedence cycle a→b→a
  The generator then **checks with the oracle** that Z3 also says UNSAT. A disagreement is a bug in either the generator or the compiler, and must be fixed, not ignored.
- **Text**: template sentence → LLM paraphrase (gpt-4o-mini, temperature 0.7, seeded) → guard: every number and place name in the template must appear in the paraphrase, otherwise retry (max 5) and fall back to the template. Manual review of all 50, recorded in `manifest.json`.
- The gold IR is stored with every instance, and the KB version hash is stored too.

## 8. Evaluation runner

`python -m nstrip.bench.run --method {pipeline,oracle,baseline} --backend …` writes one `RunRecord` per instance to `results/<run_id>/records.jsonl`. `python -m nstrip.bench.metrics results/<run_id>` writes `summary.csv` and `tables.md`.

- **pipeline**: text → extract → ground → solve. The plan is checked against the **extracted** problem (must be 0) and against the **gold** problem (the reported number).
- **oracle**: gold IR → ground → solve. This isolates the symbolic half, and gold violations are expected to be 0.
- **baseline**: text + the same KB rows (places in the instance plus their travel matrix) → LLM → `BaselineAnswer {feasible, visits, reason}` with structured output. Checked against gold. The baseline is **allowed to say infeasible**, so it is scored on detection too.
- **Extraction accuracy**: both the gold and the extracted IR are converted to canonical tuples (`DATA_MODEL_AND_SCAFFOLDING.md` §4), then micro P/R/F1 per kind and exact match per instance.

## 9. Comparison with Hao et al. (for the report)

| Aspect | Hao et al. (NAACL 2025) | This project |
|---|---|---|
| LLM output | Formulation steps + **Z3 Python code** | **Typed IR** (Pydantic), filled by structured output |
| Encoding | Written by the LLM | **Deterministic compiler**, unit-tested |
| Solver role | Formal verifier and planner | Same (Z3, DPLL(T)) |
| Infeasible queries | Unsat core → **LLM** analyses it and proposes modifications, then re-solves | Core **minimised by deletion** → **Z3 Optimize** computes the smallest numeric change, or a drop, per member |
| Plan verification | Solver's guarantee + benchmark evaluator | Solver's guarantee + **our own independent checker**, applied to the baseline too |
| Extraction faithfulness | Not measured separately | **Measured** against gold constraints, plus an oracle ablation |
| Scope | TravelPlanner (multi-day, multi-city), an unseen international dataset, other domains | Single-day, single-city, own benchmark of 50 with gold constraints |

Points the report should be honest about: their scope and scale are much larger; our compiler supports only the constraint kinds in §4.3, while their code generation can in principle express new constraint types (they report zero-shot generalisation to unseen constraints). This trade-off is **expressiveness vs. reliability of the encoding**, and the report should state it plainly.

## 10. Decisions log (choices the proposal did not fix — team to confirm)

| ID | Decision | Why |
|---|---|---|
| D1 | Single-day, single-city scope | Keeps the encoding as in the proposal; avoids TravelPlanner-scale engineering |
| D2 | Integer minutes since midnight; integer currency units (USD as in the proposal example) | QF-LIA, no floats |
| D3 | Location ids are a dynamic enum in the schema | The LLM cannot invent places; entity resolution becomes part of measured extraction |
| D4 | Unknown places → `NEEDS_CLARIFICATION`, no plan | Never silently weaken the user's request |
| D5 | Default horizon 09:00–21:00; "N hours" anchors at 09:00 unless a start is given; defaults logged | The proposal's "4 hours" needs an absolute anchor because opening hours are absolute |
| D6 | `X_i` as `Bool` instead of an Int in {0,1} | Cleaner; equivalent to the proposal's formulation |
| D7 | Assumption literals instead of literal `assert_and_track` calls | Same mechanism, needed to toggle members during minimisation and relaxation |
| D8 | SAT plan = lexicographic max optional visits, then min cost | Otherwise the solver may return an empty or arbitrary plan |
| D9 | Opening hours tracked but not relaxable | They explain conflicts but cannot be changed by the user |
| D10 | Relaxation is solved on the full problem, with a `restores_feasibility` flag | Multiple independent conflicts exist |
| D11 | Optional `start_location` / `return_to_start` folded into `horizon` | Realistic, cheap; off by default (matches the proposal's formulas) |
| D12 | Oracle method added to the evaluation | Cleanly attributes gold violations to extraction |
| D13 | Template-first explanation, guarded LLM rephrase | "LLM only rephrases" must not introduce wrong numbers |
| D14 | One opening window per place per day, no day of week | Simplicity; stated as a limitation |
