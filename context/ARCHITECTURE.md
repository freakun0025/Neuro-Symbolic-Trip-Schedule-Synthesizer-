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
| `nstrip.extract` | Prompt, one OpenAI-compatible LLM client (provider = base URL), disk cache, retry loop | models, kb |
| `nstrip.ground` | IR + KB → ProblemInstance; defaults | models, kb |
| `nstrip.encode` | ProblemInstance → Encoding (Z3 terms) | models, z3 |
| `nstrip.solve` | feasibility, optimisation, core minimisation, relaxation | models, encode, z3 |
| `nstrip.checker` | Independent plan verification | models, kb — **not z3, not encode, not solve** |
| `nstrip.explain` | Templates; guarded LLM rephrase | models, extract.llm_client |
| `nstrip.pipeline` | Orchestrates [1]–[6]; returns `PipelineResult` | everything above |
| `nstrip.baseline` | Pure-LLM planner | models, kb, extract.llm_client |
| `nstrip.ablation` | `codegen` method: the LLM writes Z3 code, run in a subprocess (evaluation only) | models, kb, extract.llm_client — **never imported by pipeline or app** |
| `nstrip.bench` | generate, paraphrase, run, metrics, tables | everything |
| `nstrip.app` | Gradio UI | pipeline (not ablation) |

## 4. The neuro-symbolic algorithm (what the instructor asked to highlight)

### 4.1 Extraction (neural, constrained)

```
function EXTRACT(text, kb, backend):
    schema ← TripRequestIR with LocationId := Enum(kb.ids)      # dynamic enum
    prompt ← SYSTEM_RULES + kb.place_list() + FEW_SHOTS + text
    for attempt in 1..1+MAX_RETRIES:                                  # MAX_RETRIES = 3 (FR-2)
        raw ← backend.structured_call(prompt, schema, temperature=0)   # cached
        try: ir ← TripRequestIR.model_validate(raw); return ir
        except ValidationError as e: prompt ← prompt + "Your output was invalid: " + e
    return EXTRACTION_FAILED
```
The validators check: ids are in the KB, times are "HH:MM" and within 00:00–23:59, earliest < latest, precedence endpoints are among the activities, there is no self-precedence, and numbers are non-negative.

**`structured_call` across providers.** All providers are reached through the `openai` SDK with a configurable `base_url`.
- The call first asks for `response_format={"type": "json_schema", ...}`. If the provider rejects that, it falls back to `{"type": "json_object"}` with the JSON schema placed in the prompt.
- The KB-id enum is part of the schema either way.
- **Pydantic validation after the call is the only authority**, so provider differences in schema enforcement only change how many retries happen, never what reaches the solver.
- Retries and fallbacks are counted and reported per model.

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
| `showtime:<id>` | X_i ⇒ ∨_k (S_i = t_k), over the KB showtimes of place i (emitted only if it has any) | yes (world fact) | **not relaxable** |
| `window:<id>` | X_i ⇒ (S_i ≥ E_i ∧ S_i + D_i ≤ L_i) (user-stated) | yes | widen to min δ (L_i + δ; E_i − δ) |
| `must_visit:<id>` | X_i | yes | drop (make optional) |
| `precedence:<a>:<b>` | (X_a ∧ X_b) ⇒ S_a + D_a + T(a,b) ≤ S_b | yes | drop |
| `nonoverlap:<i>:<j>` | (X_i ∧ X_j) ⇒ (P_ij ∨ P_ji), with P_ij ↔ (S_i + D_i + T(i,j) ≤ S_j) | **no** (hard) | — |
| domain | 0 ≤ S_i ≤ 1440 | **no** (hard) | — |

\* only if `start_location` is set; \*\* only if `return_to_start` is true.

**Tracking mechanism.** For each tracked cid we create `a_cid = Bool(cid)`, add `Implies(a_cid, φ_cid)`, and call `check(*assumptions)`. This is exactly what `assert_and_track` does internally. We use explicit assumption literals because core minimisation and relaxation need to switch members on and off without rebuilding the solver.

**Showtimes** add a real disjunction over discrete start times. Together with the non-overlap disjunctions, they are where the CDCL search does its branching. The report's DPLL(T) explanation should use a showtime example, e.g. Garden Rhapsody at 19:45 ∨ 20:45 against dinner at Lau Pa Sat.

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
    # stage 1: WHAT to visit
    o ← Optimize(); o.set(OPTIMISE_TIMEOUT = 3 s); o.add(enc.hard); o.add(φ_c for every tracked c)   # all hard
    o.maximize(Σ If(X_i,1,0) for optional i)        # objective 1 (lexicographic, Z3's default priority)
    o.minimize(Σ If(X_i,C_i,0))                      # objective 2
    if o.check() = sat: m ← o.model(); optimal ← True
    else:                                            # timed out: greedy, every step a fast feasibility check
        keep ← []; for optional i, cheapest first: if SAT(assumptions + keep + X_i): keep += X_i
        m ← model of SAT(assumptions + keep); optimal ← False
    # stage 2: ORDER and WHEN, with the chosen places fixed
    tries ← ([], ORDER) if |chosen| ≤ 8 else (ORDER,)           # ORDER = {P_ij = m(P_ij) for chosen i, j}
    for extra in tries:                                          # free order first; stage 1's order on timeout
        o2 ← same constraints + {X_i = m(X_i)} + extra
        o2.minimize(Σ S_i for chosen i)              # start as early as possible: no arbitrary gaps
        o2.minimize(S_i) for chosen i in id order     # lexicographic tie-break: the same request → the same plan
        if o2.check() = sat: m ← o2.model(); break
    return Plan(visits = sorted [(i, S_i, S_i+D_i) | m(X_i)], optimal)
```
Choosing the best subset of optional places is an orienteering problem. On one 12-place benchmark instance
(2 must-visits, 10 optional, 11-hour day) stage 1 needs ~9.5 s whatever the encoding (arithmetic objective,
`add_soft` MaxSAT, an implied capacity constraint). Z3's best-so-far model on timeout had 0 optional places.
The greedy fallback reached the true optimum (6 optional) in 2.2 s. So stage 1 has its own 3 s budget, and
plans from the fallback are valid (the checker runs on every plan) but flagged `optimal=False`, which the
explanation says.
Why two stages: minimising start times over *all* orders is a routing problem. As a third objective in one
`Optimize` it timed out (> 30 s) on a 12-place Singapore trip, while feasibility took 39 ms and stage 1 took
~0.3 s. With the *places* fixed (stage 1 done), choosing the order is small for small plans: ≤ 0.6 s on every
benchmark instance. Stage 2 therefore searches all orders when at most 8 places are chosen (a count, not a timer,
so the result stays deterministic) and otherwise compacts stage 1's order (D24). Stage 2 never changes
which places are visited, so the stage-1 choice stays optimal.

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
- `opening:<id>` and `showtime:<id>` members are reported as **world facts**: "Museum is open 10:00–17:00", "Garden Rhapsody starts only at 19:45 or 20:45". They appear in the explanation but get no relaxation.
- Relaxations are **not ranked** against each other (different units). They are listed in core order.

### 4.8 Worked example (proposal §2, regression test `test_proposal_example`)

Request: 4 h, $30, want Museum ($20, 2 h), Park (free, 1 h), Café ($15, 1 h), Museum before Café, transit 0.
This runs on the `tiny_kb` test fixture, which uses the proposal's own places and dollar amounts, not on the Singapore KB.

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
4. Opening windows, showtimes (the start is a member of the listed times), user windows, budget sum, all must-visits present, precedences where both are present.

Under a metric travel matrix (§6), adjacent checks are equivalent to the encoder's pairwise constraints. Without one, the checker is *weaker* (it accepts some plans the encoder would reject), never stronger, so a checker failure on a Z3 plan always means a compiler bug.

A test (`test_checker_independence`) parses the checker's AST and fails on any import of `z3`, `nstrip.encode` or `nstrip.solve`.

## 6. Knowledge base

- **Singapore**, about 35–40 places curated by hand, money in **SGD** (whole dollars). Singapore was chosen for the variety of constraint shapes, stable official fee and hours pages, and compact geography (about 25 km across). Categories:
  - **theme parks**: Universal Studios Singapore, Adventure Cove. Long and expensive, so they produce budget and horizon conflicts.
  - **attractions**: Gardens by the Bay domes, Singapore Flyer, Marina Bay Sands SkyPark
  - **shows with fixed showtimes**: Garden Rhapsody, Spectra, Wings of Time, Night Safari shows
  - **museums**: National Museum, ArtScience Museum, Asian Civilisations Museum
  - **nature and zoo**: Botanic Gardens (free), Singapore Zoo, Night Safari
  - **food**: Lau Pa Sat, Maxwell Food Centre, Chinatown Complex
- Each place has: id, name, aliases, category, cost, typical duration, one opening window per day, optional showtimes, lat/lon, and a source URL.
- Travel time: `T(i,j) = OVERHEAD + ceil(haversine_km(i,j) / SPEED_KMPH · 60)`, with `T(i,i) = 0`. Parameters: `OVERHEAD = 10` min and `SPEED_KMPH = 25` (an MRT/taxi average), stored in `travel_params.json`. This formula is metric by construction: haversine is a metric, ceil is subadditive, and a constant overhead only adds slack. The loader runs Floyd–Warshall and **asserts** that the matrix equals its own shortest-path closure (triangle inequality). This is what makes pairwise non-overlap with transit correct (see `RISKS.md` R5).
- Values are approximate. The report says so, with the date they were curated.

## 7. Benchmark

- **50 generated instances**: n ∈ {3,…,12}, 5 per n → 3 feasible + 2 infeasible per n (30 SAT / 20 UNSAT overall). Budgets are tight or loose, alternating. At least a third of the instances include a place with showtimes.
- **SAT label**: the generator first builds a **witness schedule** (a random subset and order, times placed greedily), then sets the constraints around it (loose: budget = witness cost × 1.5; tight: budget within 10%). The witness must pass the checker.
- **UNSAT label**: the generator starts from a SAT instance and **seeds exactly one conflict** that can be shown infeasible by arithmetic, then records `seeded_conflict` (a cid set). There are 6 conflict types (20 instances: 4, 4, 3, 3, 3, 3):
  1. budget < Σ must-visit costs
  2. horizon < Σ must-visit durations + minimum transit chain
  3. must-visit window shorter than the duration, or outside the horizon
  4. precedence a→b where a opens after b closes
  5. precedence cycle a→b→a
  6. showtime clash: every showtime of must-visit show s falls outside the horizon, or s must precede a place whose closing time is before (earliest showtime + D_s + T)
  The generator then **checks with the oracle** that Z3 also says UNSAT. A disagreement is a bug in either the generator or the compiler, and must be fixed, not ignored.
- **Text**: template sentence → LLM paraphrase (the configured paraphrase model, temperature 0.7, seeded where the provider supports it) → guard: every number and place name in the template must appear in the paraphrase, otherwise retry (max 5) and fall back to the template. Manual review of all 50, recorded in `manifest.json`.
- The gold IR is stored with every instance, and the KB version hash is stored too.
- **Held-out set** (`data/benchmark/heldout/`, 15 instances):
  - Written by the four team members (about 4 each) **before** looking at the generator templates, in free phrasing. At least 5 must be infeasible and at least 4 must use a show.
  - Each has a hand-written gold IR and an expected status. SAT needs a hand-written witness plan that passes the checker; UNSAT needs a one-line arithmetic argument stored in `conflict_note`.
  - The oracle cross-checks every label, as for the generated set. Never tune prompts on this set.

## 8. Evaluation runner

`python -m nstrip.bench.run --method {pipeline,oracle,baseline,codegen} --set {generated,heldout} [--model …]` writes one `RunRecord` per instance to `results/<run_id>/records.jsonl`. `python -m nstrip.bench.metrics results/<run_id>` writes `summary.csv` and `tables.md`.

- **pipeline**: text → extract → ground → solve. The plan is checked against the **extracted** problem (must be 0) and against the **gold** problem (the reported number).
- **oracle**: gold IR → ground → solve. This isolates the symbolic half, and gold violations are expected to be 0.
- **baseline**: text + the same KB rows (places in the instance plus their travel matrix) → LLM → `BaselineAnswer {feasible, visits, reason}` with structured output. Checked against gold. The baseline is **allowed to say infeasible**, so it is scored on detection too.
- **codegen** (ablation, Hao-style; see §8.1): text + the same KB rows → the LLM writes Z3 Python code → a subprocess prints a plan or `UNSAT`. Checked against gold.
- **Extraction accuracy**: both the gold and the extracted IR are converted to canonical tuples (`DATA_MODEL_AND_SCAFFOLDING.md` §4), then micro P/R/F1 per kind and exact match per instance.
- **Error taxonomy**: every tuple mismatch is mapped to a class (wrong number, missed or extra activity, wrong must-visit flag, reversed or missing precedence, wrong window, unresolved place). For each class, the runner records whether the instance's final answer was wrong.
- **Core size**: for each oracle UNSAT instance, the runner records |raw core|, |deletion core| and the number of solver calls, and also |core| with Z3's `smt.core.minimize=true`.
- **Stress sweep** (`python -m nstrip.bench.stress`): synthetic problems with n = 3…30, solver only, with and without showtimes; reports median solve time.

### 8.1 `codegen` ablation (Hao-style, evaluation only)

```
function CODEGEN(text, kb_rows, client):
    prompt ← SYSTEM_CODEGEN + kb_rows (table, incl. showtimes + travel matrix) + text
             + contract: "write a Python program using z3 that prints exactly one line:
                          a JSON list of {location_id, start, end}, or the word UNSAT"
    code ← client.chat(prompt, temperature=0)                       # cached like every call
    out ← run `python -I -c code` in a subprocess, cwd = temp dir, timeout 20 s, no network needed
    parse out → Plan | UNSAT | CRASH (exception, timeout, unparseable)
```
- Same model, same KB rows and same request text as `pipeline`, so the only difference is IR + compiler vs. LLM-written code.
- No retry on crash by default, matching a single-shot pipeline extraction. A second run with up to 3 repair rounds (error fed back) is a P2 variant, because Hao et al. also iterate.
- Runs **only** on benchmark instances generated or written by the team. Never in the UI, never on examiner input.

## 9. Comparison with Hao et al. (for the report)

| Aspect | Hao et al. (NAACL 2025) | This project |
|---|---|---|
| LLM output | Formulation steps + **Z3 Python code** | **Typed IR** (Pydantic), filled by structured output |
| Encoding | Written by the LLM | **Deterministic compiler**, unit-tested |
| Solver role | Formal verifier and planner | Same (Z3, DPLL(T)) |
| Infeasible queries | Unsat core → **LLM** analyses it and proposes modifications, then re-solves | Core **minimised by deletion** → **Z3 Optimize** computes the smallest numeric change, or a drop, per member |
| Plan verification | Solver's guarantee + benchmark evaluator | Solver's guarantee + **our own independent checker**, applied to the baseline too |
| Extraction faithfulness | Not measured separately | **Measured** against gold constraints, plus an oracle ablation |
| Head-to-head on the same instances | — | `codegen` ablation: a Hao-style LLM-writes-Z3 method vs. our typed IR, same model, same checker |
| Scope | TravelPlanner (multi-day, multi-city), an unseen international dataset, other domains | Single-day, single-city, own benchmark of 50 with gold constraints |

Points the report should be honest about: their scope and scale are much larger; our compiler supports only the constraint kinds in §4.3, while their code generation can in principle express new constraint types (they report zero-shot generalisation to unseen constraints). This trade-off is **expressiveness vs. reliability of the encoding**, and the report should state it plainly. The `codegen` ablation measures the reliability side on our benchmark. It does not reproduce their system, because our version is single-shot with a simple prompt, and the report must say so.

## 10. Decisions log (choices the proposal did not fix — team to confirm)

| ID | Decision | Why |
|---|---|---|
| D1 | Single-day, single-city scope | Keeps the encoding as in the proposal; avoids TravelPlanner-scale engineering |
| D2 | Integer minutes since midnight; integer currency units (SGD for the Singapore KB; the `tiny_kb` fixture keeps the proposal's $) | QF-LIA, no floats |
| D3 | Location ids are a dynamic enum in the schema | The LLM cannot invent places; entity resolution becomes part of measured extraction |
| D4 | Unknown places → `NEEDS_CLARIFICATION`, no plan | Never silently weaken the user's request |
| D5 | Default horizon 09:00–21:00 (midnight if the day starts after 21:00); "N hours" anchors at the given start, else counts back from a given end, else 09:00; defaults logged | The proposal's "4 hours" needs an absolute anchor because opening hours are absolute |
| D6 | `X_i` as `Bool` instead of an Int in {0,1} | Cleaner; equivalent to the proposal's formulation |
| D7 | Assumption literals instead of literal `assert_and_track` calls | Same mechanism, needed to toggle members during minimisation and relaxation |
| D8 | SAT plan = lexicographic max optional visits, then min cost; then, with that choice and order fixed, earliest start times (§4.5) | Otherwise the solver may return an empty or arbitrary plan, or one with idle gaps; a single 3-objective Optimize timed out at 12 places |
| D9 | Opening hours tracked but not relaxable | They explain conflicts but cannot be changed by the user |
| D10 | Relaxation is solved on the full problem, with a `restores_feasibility` flag | Multiple independent conflicts exist |
| D11 | Optional `start_location` / `return_to_start` folded into `horizon` | Realistic, cheap; off by default (matches the proposal's formulas) |
| D12 | Oracle method added to the evaluation | Cleanly attributes gold violations to extraction |
| D13 | Template-first explanation, guarded LLM rephrase | "LLM only rephrases" must not introduce wrong numbers |
| D14 | One opening window per place per day, no day of week | Simplicity; stated as a limitation |
| D15 | City = **Singapore**, ~35–40 places, SGD | Variety of constraint shapes (theme parks, fixed-time shows, free parks, hawker centres); official fee and hours pages; compact |
| D16 | One OpenAI-compatible client; provider via base URL, model per role via env | Keeps the provider open (OpenAI, Gemini, Groq, OpenRouter, local Ollama) with no provider-specific code |
| D17 | Baseline and extraction models are whatever the configured provider offers; the exact model strings are logged and reported | The proposal named gpt-4o-mini / GPT-4o; any other model is a stated deviation, not a hidden one |
| D18 | Fixed showtimes as a non-relaxable world fact `showtime:<id>` | Adds a real disjunction; needs all six pieces (AGENTS.md §5) |
| D19 | `codegen` ablation (Hao-style) in `nstrip.ablation`, evaluation only | PRD §6 promises the differences are *evaluated*; difference 1 cannot be measured without it |
| D20 | Held-out hand-written set of 15, reported separately | Removes "our generator, our phrasing" circularity from the headline numbers |
| D21 | Error taxonomy and a core-size comparison (raw vs. deletion vs. `smt.core.minimize`) | Cheap; turns "extraction is the bottleneck" and "minimisation is needed" into numbers |
| D22 | Stage-1 plan optimisation has its own 3 s budget (`OPTIMISE_TIMEOUT_MS`); on timeout a greedy, Z3-checked plan is returned with `optimal=False` (§4.5) | Choosing the optional subset is an orienteering problem: one 12-place instance needed ~9.5 s for the exact optimum, the greedy fallback found the same optimum in 2.2 s |
| D23 | Demo examples (`data/examples/demo_requests.json`) carry a hand-written IR and expected status | The UI works fully offline through Re-solve; the examples double as a regression test on the real KB (`tests/test_app.py`) |
| D24 | Stage 2 chooses the visit order itself (when ≤ 8 places are chosen) and breaks ties lexicographically by start time (§4.5) | Stage 1 has many tied models; Z3 returned a different order run to run (4 different plans in 6 runs of one demo). Now one request → one plan; regression test `test_plan_deterministic.py` |
| D25 | 5 extra two-conflict UNSAT instances (FR-20b), generated from their own RNG stream | The original 50 are unchanged; scores "core = one of the seeded conflicts" without the single-conflict construction bias |
| D26 | Models (2026-11-25): extraction `gemini-3.5-flash-lite` (Gemini, OpenAI-compatible endpoint); baseline and codegen `openai/gpt-oss-120b` (Groq) plus a same-model run on the extraction model; paraphrases `gemini-3.1-flash-lite` | Proposal named gpt-4o-mini / GPT-4o; these were the strongest models on the free tiers available. The Gemini 2.5 family is closed to new keys and Gemini Pro has no free quota. Stated deviation |
| D27 | Paraphrases reviewed after generation: 5 of 28 passed the numbers/names guard but changed meaning and were reverted to the template; paraphrase instructions tightened afterwards. A 6th (inst_037: "I'm planning to spend 450 minutes at Universal Studios" for an optional place) was missed in review and found from the first pipeline run, where both extraction and verification read it as required; it was reverted too and every method re-run (22/55 paraphrased) | The guard checks numbers and names, not must vs. optional or added commentary. Prompt change made before any extraction run |
| D28 | Optional solver → LLM verification round (FR-27, AGENTS invariant 16) | Phase-6 improvement: the one pipeline error was a must-visit misread as required-vs-optional, which produced a false UNSAT; the conflict points the LLM at exactly that field |
