# Neuro-Symbolic Trip & Schedule Synthesizer

AID 851, Introduction to Machine Reasoning — project report (DRAFT, to be edited by the team)

---

## 1. Goals

A user describes a one-day trip in Singapore in plain English: a time window, a budget, the places they must see,
the places they would like to see if there is time, and orderings or time windows ("lunch at Maxwell after 12:30",
"the museum before the café"). The system must return either

- a timetable that is **guaranteed to satisfy every extracted constraint**, verified a second time by an
  independent checker, or
- if no such timetable exists, the **minimal set of requirements that conflict** together with the **smallest
  change** to each that would remove the conflict.

The goals from the proposal:

1. Keep all reasoning symbolic. The LLM only translates language into a typed form; feasibility, the schedule, the
   conflict and the fixes come from the SMT solver Z3.
2. Make infeasibility explainable: a minimal unsatisfiable core, not just "no plan".
3. Verify every plan independently of the solver.
4. Measure the approach against a pure-LLM planner on a benchmark with known answers, and measure the
   extraction step separately, since the guarantee only covers what was extracted.

## 2. Approach in one picture

```
request ─► LLM fills a typed form (Pydantic IR; places = enum of KB ids; retried on invalid output)
        ─► grounding with the knowledge base (deterministic; all integers; defaults logged)
        ─► compiler: QF-LIA + Boolean constraints, one named assumption literal per requirement
        ─► Z3 (CDCL(T), the modern form of DPLL(T))
              SAT   ─► Z3 Optimize picks the plan ─► independent checker must accept it
              UNSAT ─► unsat core ─► deletion-minimised (minimal) core
                      ─► Z3 Optimize: smallest change per core member, re-solved on the full problem
        ─► template explanation (an LLM may only reword it, under a numbers/names guard)
```

The **neural** part is the first arrow only. Everything after the form is validated is symbolic and deterministic.

## 3. Methodology

### 3.1 Extraction (neural, constrained)

The LLM receives the request, the list of knowledge-base (KB) places (id and name only), the JSON schema of the
intermediate representation (IR) and two worked examples, and must return a filled `TripRequestIR`:
day start and end (or a duration), budget, start location and whether to return there, the activities with a
`must_visit` flag and optional duration override and time window, precedences, and two lists for what it could
not encode (`unresolved_mentions` for places not in the KB, `ignored_preferences` for wishes like "somewhere
quiet").

- Place fields are an **enumeration of KB ids**, so the model cannot invent a place.
- The output is validated by Pydantic (types, enum, times within the day, earliest < latest, precedence endpoints
  among the activities, no self-precedence). On failure the error text is sent back and the model retries, at most
  3 times; then the status is `EXTRACTION_FAILED`.
- A mentioned place that is not in the KB stops the pipeline with `NEEDS_CLARIFICATION` and a "did you mean"
  suggestion. Nothing is dropped silently.
- The LLM never supplies facts the KB has (prices, durations, hours, showtimes, travel times).

### 3.2 Grounding (symbolic, deterministic)

The IR is joined with the KB into a `ProblemInstance` in integers: minutes since midnight and whole Singapore
dollars. Duration and cost come from the KB unless the user overrides them. The horizon is `[H0, H1]` with
`H0 = day_start` (default 09:00) and `H1 = min(day_end, H0 + duration)` (default 21:00); every default used is
logged and shown to the user.

Travel time between places `i` and `j` is `T(i,j) = 10 + ⌈haversine_km(i,j) / 25 · 60⌉` minutes (0 for the same
place). This is a metric (triangle inequality holds), and the loader asserts it with Floyd–Warshall. Metricity is
what makes the pairwise non-overlap encoding below correct.

### 3.3 Encoding (QF-LIA + Boolean)

For each candidate activity `i`: `X_i : Bool` (scheduled) and `S_i : Int` (start minute). `D_i`, `C_i`, `O_i`,
`K_i`, `T(i,j)` are integer constants.

| Name in the core | Constraint | Kind |
|---|---|---|
| `budget` | Σ If(X_i, C_i, 0) ≤ B | user requirement |
| `horizon` | X_i ⇒ S_i ≥ H0 + T(o,i) ∧ S_i + D_i (+ T(i,o)) ≤ H1 | user requirement |
| `must_visit:i` | X_i | user requirement |
| `window:i` | X_i ⇒ S_i ≥ E_i ∧ S_i + D_i ≤ L_i | user requirement |
| `precedence:a:b` | (X_a ∧ X_b) ⇒ S_a + D_a + T(a,b) ≤ S_b | user requirement |
| `opening:i` | X_i ⇒ S_i ≥ O_i ∧ S_i + D_i ≤ K_i | world fact |
| `showtime:i` | X_i ⇒ ∨_k (S_i = t_k) | world fact |
| (untracked) | (X_i ∧ X_j) ⇒ P_ij ∨ P_ji, with P_ij ↔ S_i + D_i + T(i,j) ≤ S_j | physics of a schedule |
| (untracked) | 0 ≤ S_i ≤ 1440 | domain |

Each user requirement and world fact is guarded by its own **assumption literal** `a_c` (`Implies(a_c, φ_c)`,
then `check(a_1, …, a_n)`), the mechanism behind Z3's `assert_and_track`. That is what lets Z3 name, in an unsat
core, *which* requirements conflict. Constraints are emitted only when they apply (no budget stated, no budget
constraint). The proxies `P_ij` name each side of the non-overlap disjunction, in the spirit of a Tseitin encoding,
so the chosen order can be read back from the model.

**Why this is DPLL(T).** Z3 decides this formula with CDCL over the Boolean structure (the `X_i`, the `P_ij`, the
assumption literals and the showtime disjuncts) and a linear-integer-arithmetic theory solver for the atoms
(`S_i + D_i + T ≤ S_j`). Example (demo request "A long dinner leaves no slot for Garden Rhapsody", run on the real
KB): dinner at Lau Pa Sat lasts 90 min and must lie within 19:30–21:00, so it occupies exactly 19:30–21:00;
Garden Rhapsody (15 min) is open 19:30–21:15 with shows at 19:45 and 20:45; the two are 14 min apart. Both are
must-visits, so unit propagation sets `X_show` and `X_dinner` true, which activates the non-overlap clause
`P_show,dinner ∨ P_dinner,show`. Whichever order literal the SAT search decides, the arithmetic solver finds a
contradiction: show first needs `S_show + 15 + 14 ≤ S_dinner = 19:30` with `S_show ≥ 19:30`; dinner first needs
`21:00 + 14 + 15 ≤ 21:15`. The theory conflict comes back as a learned clause and the formula is UNSAT. Z3's
statistics for this call: 1 conflict, 18 propagations. Note that the core, both must-visits, the dinner window
and the show's **opening hours**, does not contain the showtimes: the opening window alone already makes it
impossible, which the minimal core shows precisely. Showtime disjunctions do cause branching on larger instances.

### 3.4 Plan selection when the request is satisfiable

1. *What to visit.* Z3 `Optimize`, lexicographically: maximise the number of optional places, then minimise total
   cost. Choosing the best subset of optional places is an orienteering problem; on one 12-place instance the
   exact optimum took ~9.5 s, so this stage has a 3 s budget, after which a greedy Z3-checked fallback is used and
   the plan is labelled "valid, not proven optimal" (1 instance in the benchmark).
2. *Order and times.* With the places fixed, minimise the sum of start times (no arbitrary gaps), then break ties
   lexicographically by start time, so **the same request always gives the same plan**. Up to 8 chosen places the
   visit order is searched as well; for larger plans stage 1's order is kept and only compacted. (Without the tie-break we
   observed four different plans in six runs of one request, all optimal for stage 1.)

### 3.5 Diagnosis when the request is unsatisfiable

**Minimal core by deletion.** Z3's `unsat_core()` is a set of assumption literals that is unsatisfiable together
with the hard constraints, but not necessarily minimal. We shrink it: for each member `c`, re-check without it; if
still UNSAT, drop `c` (and shrink to the new core); if SAT, `c` is necessary. The result is **minimal**
(irreducible: removing any member makes the rest satisfiable) in at most |core| solver calls. It is not
necessarily the *minimum* core.

**Smallest fixes with Optimize.** For each relaxable member of the minimal core, the **whole** problem (not just
the core) is re-solved with only that member relaxed:

- budget: `Σ … ≤ B + δ`, minimise δ ≥ 0
- horizon: end at `H1 + δ`, minimise δ
- user window: widen by `δ_e + δ_l`, minimise
- must-visit or precedence: drop it

Each fix records whether it **restores feasibility** on its own. With two independent conflicts, a fix to one is
reported as "not enough on its own". Opening hours and showtimes are facts about the world: they are shown in the
conflict ("Universal Studios closes at 19:00") but never offered as a fix.

### 3.6 Independent checker

Every plan the pipeline returns is checked by a separate module that never imports Z3, the compiler or the solver
(enforced by a test that parses its imports). It uses a different algorithm: sort visits by start time and check
only **consecutive** pairs for travel time, then hours, showtimes, windows, budget, must-visits and precedences.
Under a metric travel matrix this is equivalent to the encoder's pairwise constraints. A plan Z3 produced that
fails the checker is reported as `INTERNAL_ERROR` (a compiler bug), never shown as valid. The same checker scores
the baseline's and the code-generation method's plans against the gold constraints.

### 3.7 Optional: solver → LLM verification round

When the answer is UNSAT, the LLM can be shown the request again together with the *user* requirements in the
minimal conflict, in plain words ("you must visit Universal Studios", "your budget is S$100"; never the KB facts),
and asked only whether each matches what the user wrote. It may return a corrected form, which goes through
validation, grounding and the solver again. One round, every changed field logged, off by default. The risk is
that the LLM "fixes" a real conflict to make the day possible, so its rate of erased real conflicts is measured
(§5).

### 3.8 Explanation

The text shown to the user comes from deterministic templates over the plan or the diagnosis. An LLM may reword it
only if every number and place name in the template survives (otherwise the template is shown).

## 4. Data, facts and constraints

### 4.1 Knowledge base

39 Singapore places (theme parks, attractions, shows with fixed showtimes, museums, nature and zoo, hawker centres,
shopping), each with id, name, aliases, category, admission in SGD, typical duration, one opening window, showtimes
if any, coordinates and a source URL. Values are a hand-curated snapshot from official pages (2026-11-25); 18 rows
were checked against their source, the rest are marked approximate (`checked` column). **[Team: update the count
after verifying the remaining rows.]**

### 4.2 Benchmark (generated, 55 instances)

- **50 instances** as in the proposal: n = 3…12 places, 5 per n, 30 feasible and 20 infeasible, tight / loose /
  no budget, 24 with a show.
- **Labels never come from Z3.** A feasible instance is built around a *witness* schedule that the checker accepts;
  an infeasible one starts from a feasible draft and *seeds* one conflict that is infeasible by arithmetic (six
  types: budget, horizon, window, precedence vs. opening hours, precedence cycle, showtime clash). Z3 is then used
  only to cross-check that the seeded conflict is the instance's unique minimal core.
- **5 extra two-conflict instances** (inst_051–055) each carry two seeded conflicts, cross-checked to be the
  instance's only two minimal cores. Without them, "the core equals the seeded conflict" would hold by construction.
- **Text**: every request is rendered from templates; 22 of 55 are paraphrased by an LLM (a different model from
  the extractor) under a guard that every number and place name survives. Six paraphrases passed the guard but
  changed the meaning (e.g. an optional place reworded as "I'm planning to spend 450 minutes at …") and were
  reverted to the template; one of them was found only from the first evaluation run.

### 4.3 Held-out set (15 instances)

**[Team: written by the four members without looking at the generator's templates; see
`data/benchmark/heldout/README.md`. Report its results as a separate column.]**

## 5. Results

All numbers are on the 55 generated instances (30 feasible, 25 infeasible), with Wilson 95% intervals. Full tables:
`results/comparison_generated.md` and `results/<run>/tables.md`. Every LLM call is cached, so each run replays
offline with identical results.

### 5.1 End to end

| Method | Model | Correct answer | Claimed plans violating the gold constraints | UNSAT precision / recall |
|---|---|---|---|---|
| Oracle (gold IR → Z3) | none | 55/55 (93–100%) | 0/30 | 25/25 / 25/25 |
| **Pipeline** (LLM → IR → Z3) | gemini-3.5-flash-lite | **55/55** (93–100%) | **0/30** | 25/25 / 25/25 |
| Pipeline + verification round | gemini-3.5-flash-lite | 55/55 | 0/30 | 25/25 / 25/25 |
| Pure-LLM planner | openai/gpt-oss-120b | 50/55 (80–96%) | 3/30 (3–26%) | 23/25 / 23/25 |
| Pure-LLM planner | gemini-3.5-flash-lite | 29/55 (40–65%) | 1/5 | 25/50 / 25/25 |
| LLM writes the Z3 program (Hao-style) | gemini-3.5-flash-lite | 38/55 (56–80%) | 3/22 (5–33%) | 19/25 / 19/25 |

*A "correct answer" is the right feasible/infeasible status and, if feasible, a plan with zero violations against
the gold constraints.*

- With a small extraction model, the pipeline returned **no invalid plan** and found every infeasible request.
- A much larger model planning on its own was right on 50/55, but 3 of its 30 plans broke a real constraint
  (ending after the day ended, a wrong duration, a show at a time it does not run), and it missed 2 infeasible
  requests. Presented to a user, those plans look as confident as the correct ones.
- The same small model planning on its own declared 50 of 55 requests infeasible, mostly with false reasons
  (for example "the total cost of Singapore Zoo and Flower Dome and Cloud Forest exceeds the budget of S$101", for a request whose valid plan costs S$95).
- **[Team: add the `gpt-oss-120b` codegen row when that run finishes; it needs a second day of free-tier quota.]**

### 5.2 Extraction

Over 1,450 canonical constraint tuples (places, must-visit flags, costs, durations, horizon, windows,
precedences, start location, budget), micro precision, recall and F1 were all 1.00 (2 false positives, 2 false
negatives); **53/55 requests were extracted exactly.** Both errors were a wrong must-visit flag (inst_007, inst_021),
and neither changed the final answer: both still received a plan that satisfies every gold constraint. Earlier in the evaluation, one more paraphrase
that had itself changed the meaning (§4.2) was "mis-extracted" in exactly the direction the text suggested; this
is the extraction-gap risk the oracle comparison is designed to expose. Extraction took a mean of 3.1 s (median
1.9 s) per request on the live API.

### 5.3 Infeasibility and cores

- All 20 single-conflict cores equal the seeded conflict, all are minimal, and on all 5 two-conflict instances the
  core is one of the two seeded conflicts, through the pipeline as well as the oracle.
- Core size (oracle, 25 UNSAT instances): Z3's raw core 3.68 members on average, after deletion 3.28 (4.64 solver
  calls on average). Z3's built-in `smt.core.minimize` also reaches 3.28 here, so on this benchmark deletion
  matches it; deletion additionally *certifies* minimality, which the built-in option does not.

### 5.4 Verification round (solver → LLM)

On the 25 UNSAT answers the LLM re-read the request against the conflict and changed nothing (0/25), so it
**erased no real conflict**. It also had no false UNSAT to correct in the final runs. In an earlier run its one
chance (the paraphrase in §5.2) was not corrected either, because the text genuinely read as required. The feature
is safe on this benchmark but showed no benefit; it stays off by default.

### 5.5 Runtime

Solving took a median of tens of milliseconds per instance up to 12 places. 29/30 feasible plans are proven
optimal; one 12-place instance hit the 3 s budget for choosing optional places and used the greedy fallback
(valid, labelled "not proven optimal").

Solver-only scaling (`results/stress.md`; synthetic requests with n candidate places, 5 per row, no LLM):

| n | median solve, without / with shows | plans proven optimal |
|---|---|---|
| 6 | 0.02 s / 0.39 s | 10/10 |
| 9 | 0.16 s / 0.94 s | 10/10 |
| 12 | 0.97 s / 2.3 s | 8/10 |
| 15 | 7.8 s / 3.7 s | 2/10 |
| 20–30 | 0.3–8.5 s (max 47 s) | 3/18 feasible |

Feasibility itself is never the bottleneck and no instance timed out. The cost grows in choosing the *best* subset
of optional places (an orienteering problem): above ~12 places Z3 often cannot prove the optimum within its 3 s
budget and the greedy fallback supplies a valid plan. This is why the benchmark stops at 12 places, as in the
proposal.

## 6. Relation to Hao et al. (NAACL 2025)

**Where we use their idea.** Hao et al.'s central idea is that an SMT solver acts as the *formal verification
tool* for an LLM-based planner. We use it at three points:

1. **Feasibility as a proof.** Z3's `sat` answer comes with a model that satisfies every encoded constraint, so the
   returned plan is correct by construction for the extracted constraints (§3.3–3.4); `unsat` is a proof that no
   plan exists (§3.5).
2. **Infeasibility as an explanation.** As in their work, the unsat core says *why*; we additionally minimise it
   and let Z3 Optimize, not the LLM, compute the fixes (§3.5).
3. **A second, independent verification** of every plan by a checker that shares no code with the solver (§3.6),
   which also lets us verify the plans of methods that have no solver: the pure-LLM baseline.

And we test their approach directly: the `codegen` method re-implements "the LLM writes the Z3 program" on our
benchmark, so the difference between their encoding step and ours is measured (§5).

Hao et al. also use an LLM to translate travel requests into constraints and Z3 to plan and verify, and on
infeasible requests they read the unsat core and ask the LLM to propose modifications. Our design differs in four
places, and the third is measured directly:

| Aspect | Hao et al. | This project |
|---|---|---|
| What the LLM writes | Formulation steps and Z3 Python code | A typed form (Pydantic IR) |
| Encoding | Written by the LLM | Deterministic, unit-tested compiler |
| Infeasible requests | LLM analyses the core and proposes fixes | Core minimised by deletion; Z3 Optimize computes the smallest change per member |
| Head-to-head | — | `codegen` method: the LLM writes the Z3 program for the same requests, same KB rows, same checker |

The trade-off is **expressiveness vs. reliability of the encoding**: code generation can in principle express a
constraint type our compiler does not know, while a typed IR turns encoding errors into deterministic, testable
compiler bugs instead of stochastic LLM code errors. Their scope (multi-day, multi-city, an unseen international
dataset) is far larger than ours, and our `codegen` method is a single-shot re-implementation with a simple
prompt, not their system.

## 7. Limitations and threats to validity

- **The guarantee covers the extracted constraints.** If extraction is wrong, the plan is correct for the wrong
  problem; that is why extraction accuracy is measured separately.
- **Template-heavy benchmark text.** 33 of 55 requests keep generator phrasing; the held-out set is the check on
  this.
- **Single day, single city, one opening window per place**, approximate KB values.
- **Cores are minimal, not minimum**; relaxations are per member, not a global optimum over combinations.
- **Optional-subset optimisation is not always proven optimal** above ~12–15 places within the time budget (plans
  stay valid).
- **Models.** Extraction used `gemini-3.5-flash-lite`; the baseline and code-generation runs used
  `openai/gpt-oss-120b` (Groq) and the extraction model. The proposal named gpt-4o-mini and the GPT-4o family;
  these were the strongest models available on the free tiers we had.
- **Small n.** All rates carry Wilson 95% intervals; we make no significance claims.

## 8. Conclusions and future work

**[Team: write after reading §5.]** Directions we did not build: MaxSMT soft preferences ("prefer museums"),
enumerating alternative minimal cores (MARCO), self-consistency voting in extraction, multi-day trips, meal windows,
and repair rounds for the code-generation method.

## References

- Y. Hao, Y. Chen, Y. Zhang, C. Fan. *Large Language Models Can Solve Real-World Planning Rigorously with
  Formal Verification Tools.* NAACL 2025. arXiv:2404.11891.
- L. de Moura, N. Bjørner. *Z3: An Efficient SMT Solver.* TACAS 2008.
- J. Marques-Silva, M. Janota, A. Belov. *Minimal Sets over Monotone Predicates in Boolean Formulae.* CAV 2013
  (deletion-based MUS extraction).
- E. B. Wilson. *Probable Inference, the Law of Succession, and Statistical Inference.* JASA 22 (1927).
