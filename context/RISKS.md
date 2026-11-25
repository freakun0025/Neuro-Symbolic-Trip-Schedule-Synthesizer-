# RISKS — what will break, what is over-engineered, what to say at the viva

This is a critical review of the proposal **and** of the reply sent to the instructor. Every item has a concrete fix, and most fixes are already built into `ARCHITECTURE.md`. Severity: 🔴 will be attacked at the viva or will produce wrong results · 🟠 likely bug or confusion · 🟡 polish.

---

## Part A — Claims in the document that will break

### R1 🔴 "The encoding itself cannot be wrong"
The reply to the instructor says the typed IR means "the encoding itself cannot be wrong". This is false as stated. The compiler is code we write, and it can have bugs (an off-by-one in a window, a missing transit term, a precedence in the wrong direction). What the typed IR actually buys is that encoding errors are **deterministic and testable** instead of stochastic LLM code errors.
**Fix:** in the report and at the viva, say: *"Encoding errors become deterministic compiler bugs that we unit-test, cross-check against a brute-force solver, and catch at runtime with an independent checker."* The safety net is built in: `test_z3_vs_bruteforce.py`, `test_proposal_example.py`, and the checker run on every pipeline plan (`INTERNAL_ERROR` on failure).

### R2 🔴 The guarantee only covers extracted constraints, so extraction is the real bottleneck
The phrase "every returned plan satisfies all constraints" is true only relative to what the LLM extracted. If the LLM misses "Museum before Café", Z3 will happily return a plan that violates the user's real intent.
**Fix (already in the spec):** measure extraction accuracy, and add the **oracle** run (gold IR → Z3). The headline result becomes "oracle 0 violations; pipeline violations against gold = extraction errors". Never compare the pipeline-vs-extracted number with the baseline-vs-gold number, because that comparison is unfair in our favour. **Always report both methods against gold.**

### R3 🔴 Live demo on examiner queries: places not in the KB
The examiner will say "Taj Mahal", "a good chilli crab place", or a city we didn't curate (we only have Singapore). The proposal promises a "live demo on examiner-provided queries".
**Fix:** (a) the UI always shows the KB place list and the city name; (b) unknown places → `NEEDS_CLARIFICATION` with a clear message, never a silent drop; (c) the editable-IR box (FR-18) lets you fix extraction live; (d) rehearse 15+ varied requests from `demo_requests.json`. Say upfront at the viva: "single city, N places, static data".

### R4 🔴 "I have 4 hours" has no absolute anchor
Opening hours are absolute times (10:00–17:00), but "4 hours" is relative. The proposal's encoding uses `S_i + D_i ≤ MaxTime`, which silently assumes a start of 0, and that is incompatible with opening windows.
**Fix:** the horizon is `[H0, H1]`. If the start is not given, H0 = 09:00, **logged in `assumed_defaults` and shown in the UI**. Also add the missing lower bound `S_i ≥ H0`, which the proposal's formula omits.

### R5 🔴 Pairwise non-overlap with transit is only correct if travel times satisfy the triangle inequality
The proposal's non-overlap constraint requires `S_j ≥ S_i + D_i + T(i,j)` between **every** pair of visits, not just consecutive ones. If T(A,C) > T(A,B) + T(B,C) (common with real taxi data), the encoder demands an impossible gap between A and C and **rejects feasible plans**. The checker (adjacent pairs only) would then disagree with the encoder.
**Fix:** generate travel times from haversine distance + a constant overhead (metric by construction) and assert metric closure (Floyd–Warshall) on load. Write one sentence in the report about why.

### R6 🟠 No start location or return
The proposal's formulas have no origin: the first activity can start at H0 with zero travel. That is fine for the worked example ("travel times ignored here") but unrealistic in general.
**Fix:** optional `start_location` / `return_to_start`, folded into `horizon`. Off by default, so the proposal's formulas remain the default behaviour.

### R7 🟠 No objective means trivial or arbitrary plans
With optional activities, `X_i = False` for all of them is a valid model. Z3 may return an empty day. The proposal's example ("Z3 would simply pick a feasible subset such as Museum + Park") silently assumes it maximises something.
**Fix:** on SAT, use `Optimize`: maximise the number of optional visits, then minimise cost (D8). Say in the report that the plan is optimal **for this objective**, and that the guarantee is about constraint satisfaction, not about "best trip".

### R8 🟠 "Smallest relaxation that restores feasibility" may not exist for a single core member
A request can contain two **independent** conflicts (budget too low **and** a must-visit place closed). Relaxing a member of one core leaves the other conflict, so the claim "restores feasibility" is false.
**Fix:** solve each relaxation on the **full** problem and return `restores_feasibility: bool`. The UI offers "apply and re-diagnose". In the report, say "per-member relaxations, each computed by Z3 Optimize on the full problem" and do not claim a globally minimal relaxation (that would be MaxSMT, see O3).

### R9 🟡 The proposal's worked example lists only one of the drops
The text says "raise the budget to $35 **or drop the Café**". Dropping the Museum (Park + Café = $15) is equally valid, and our relaxer will list it. That is not wrong, but an examiner comparing slides with the output may notice.
**Fix:** state all three relaxations in the report's version of the example (budget → 35, drop Café, drop Museum).

### R10 🟠 "Minimal" vs "minimum" core, and "core matches the seeded conflict"
Deletion gives a **minimal** (irreducible) core, not the smallest one. Separately, an UNSAT instance can have **several** minimal cores, so the core Z3 finds may be a different valid one from the seeded conflict, and the "core matches seeded" metric would then wrongly count it as a failure.
**Fix:** (a) always say "minimal"; (b) report two numbers: *valid minimal core rate* (every returned core is UNSAT and each member is necessary, which should be 100%) and *matches seeded conflict*; (c) the generator should make the seeded conflict the only conflict (check that dropping any one seeded member gives SAT using the oracle). Note: deletion minimisation guarantees minimality, so the proposal's "minimality verified by re-solving with each member dropped" is a **redundant sanity test**, and it should be presented as such rather than as an independent result.

### R11 🟠 Benchmark labels must not come from Z3
If Z3 decides which instances are feasible, "Z3 gets 100% detection" is circular.
**Fix:** SAT label = a witness plan the checker accepts; UNSAT label = a seeded conflict that can be shown by arithmetic. Z3 is only used as a cross-check that must agree.

### R12 🟠 Paraphrasing can change the gold constraints
The LLM paraphrase can drop "Museum before Café", turn $30 into "about thirty", or rename the Café. Then the gold no longer matches the text, and an extraction "error" is actually a benchmark error.
**Fix:** a guard (every number and place name in the template must appear in the paraphrase) plus a manual review of all 50, recorded in `manifest.json`. Fall back to the template text if the guard fails.

### R13 🟠 The baseline comparison must be fair
A pure-LLM baseline that never sees opening hours or the travel matrix will fail for reasons that have nothing to do with reasoning. One that is not allowed to say "infeasible" gets zero detection by design.
**Fix:**
- The baseline gets the **same KB rows** for the instance's places, including showtimes, plus the travel matrix. It uses structured output and may answer `feasible: false`.
- Run it twice:
  1. with the **same model** the pipeline uses for extraction (like-for-like)
  2. with the **strongest model** available on the configured provider (the fairest test of "can a pure LLM do it")
- Log both model strings. The proposal said "GPT-4o family"; if another provider is used, say so in the report as a deviation.

### R14 🟠 Structured-output pitfalls
- We use one OpenAI-compatible client across providers (OpenAI, Gemini, Groq, OpenRouter, local Ollama). Their support for `response_format={"type": "json_schema"}` varies:
  - some enforce it strictly
  - some accept only a subset of JSON Schema (regex patterns, min/max, enums may be ignored)
  - some support only `json_object`
  - OpenAI strict mode additionally needs all properties required and nullable fields written as `X | None`, with no defaults
- **Fix:** try `json_schema`, fall back to `json_object` with the schema in the prompt, and always validate with Pydantic. Retries and fallbacks are counted per model, so a weak provider shows up as more retries, not as silent wrong data.
- Dynamic enums of ~40 ids are fine; enums of thousands would not be (one more reason to stay with one city).
- Small or open models follow schemas much less reliably. Expect more retries and lower extraction accuracy, and **report it per model** instead of hiding it.

### R15 🟠 Reproducibility of LLM numbers
Even at temperature 0, outputs can differ between calls and model snapshots.
**Fix:** disk cache keyed by (base URL, model, prompt, schema hash), committed to git; log the exact model string; the final evaluation is run once and the cache is frozen. Free tiers (Gemini, Groq) have per-minute rate limits, so the runner uses exponential backoff, and the full benchmark is run early once to warm the cache.

### R16 🟠 The "LLM only rephrases" step can introduce wrong numbers
A rephrase like "raise your budget to about $40" breaks the exactness the project is built on.
**Fix:** the template text is authoritative; the rephrase is accepted only if every number and place name in it appears in the template (D13).

### R17 🟡 Statistical weight of 50 instances
With 50 instances, 20 of them UNSAT, one error moves recall by 5 points.
**Fix:** report counts (e.g. 18/20) with Wilson intervals; make no significance claims. The proposal's "we report the measured values as they come out" is the right stance, so keep it.

### R18 🟡 Terminology an examiner may poke at
- "DPLL(T)": correct in spirit; Z3's SMT core is CDCL(T) (modern DPLL(T) with clause learning). Say "CDCL(T), the modern form of DPLL(T)".
- "Tseitin": the `P_ij` proxies are naming, not a full Tseitin transform, and the proposal already says this, which is good.
- `assert_and_track`: we use explicit assumption literals; say it is the same mechanism.
- "Formal verification": what is verified is *constraint satisfaction of the returned plan*, not correctness of the code.

### R19 🟡 Data realism
Fees, hours and durations in a hand-curated KB will be approximate; there is one window per day and no day-of-week or holiday logic.
**Fix:** state this in the limitations section, with the curation date. It does not affect any claim, because all claims are relative to the KB.

### R20 🟡 Ambiguous language that the schema cannot express
"Lunch around 1", "not too late", "cheap", "if there's time, the zoo". Only the last one is supported (as an optional activity).
**Fix:** route vague wishes to `ignored_preferences` and show them, so it is visible what was not encoded. In the report, list this as a deliberate limit of the typed-IR approach (the trade-off with Hao et al.'s code generation).

### R21 🟡 Precedence when one activity is dropped
The proposal's `(X_i ∧ X_j) ⇒ …` makes "Museum before Café" **vacuous** if Café is not scheduled. That is reasonable, but a user might mean "Café only after Museum".
**Fix:** keep the proposal's semantics and document it in one line.

### R22 🟡 Citation
Hao et al. was published at **NAACL 2025** (Hao, Chen, Zhang, Fan). Cite the NAACL version in the final report, not only the arXiv id.

### R23 🔴 The `codegen` ablation executes LLM-written code
**Fix:**
- Run it only in `nstrip.ablation`, only on team-made benchmark instances, never in the UI or on examiner input.
- Use a fresh subprocess (`python -I`, temp working directory, 20 s timeout) and capture stdout and stderr.
- The pipeline and the app must not import `nstrip.ablation` (enforced by the import-ban test).

### R24 🟠 The `codegen` ablation must be fair, and it is not Hao et al.'s system
A weak prompt makes code generation look bad, which would be a strawman.
**Fix:**
- Same model, same KB rows (including the travel matrix and showtimes) and same request text as the pipeline.
- A short API contract and one worked example in the prompt.
- The report says plainly that this is a **single-shot simplification** of Hao et al., not a reproduction. If time allows, add a repair variant with up to 3 rounds of feeding back the error.

### R25 🟠 Showtimes change the search, not just the data
**Measured** (`results/stress.md`, 3 random Singapore problems per cell): up to 12 places the median solve is under 1 s.
From ~15 places the optional-subset optimisation usually hits its 3 s budget, the greedy fallback takes over
(plans valid, `optimal=False`), and solves take several seconds, up to ~30 s at 20–25 places. No feasibility
timeouts occurred. The benchmark stays within 3–12 places, as in the proposal.
`X_i ⇒ ∨_k S_i = t_k` adds real disjunctions. Combined with non-overlap, solve time grows with n, and the showtime cases are the ones most likely to hit the timeout.
**Fix:**
- Keep the solver timeout and the `SOLVER_TIMEOUT` status.
- Report the stress sweep (n = 3…30) with and without showtimes.
- The brute-force cross-check must include showtime places.

### R26 🟡 Singapore data drift
Fees, hours and showtimes change (shows get paused, prices rise).
**Fix:** a `source_url` per row, a `curated_on` date in `kb_meta.json`, and a sentence in the limitations section. Every claim is relative to the KB snapshot, so drift does not affect correctness.

---

## Part B — Over-engineering to avoid (cut list)

| # | Tempting | Why to skip it | Do instead |
|---|---|---|---|
| O1 | Multi-day, multi-city, hotels and flights (full TravelPlanner) | Months of work; not in the proposal; Hao et al. already did it | Single day, single city; cite the scope difference |
| O2 | Live Google Maps / Places APIs | Keys, quotas, non-reproducible results, a demo that can break | Static KB + haversine travel times |
| O3 | Global minimum relaxation (MaxSMT over all soft constraints with a cost model across $ and minutes) | Units cannot be compared; it needs a weighting the team cannot defend | Per-member Optimize relaxations + a `restores_feasibility` flag |
| O4 | Enumerating all MUSes (MARCO), QuickXplain, etc. | Beyond the proposal; deletion is enough at 12 places | Deletion-based minimisation; mention the alternatives in one sentence |
| O5 | Writing our own SAT/DPLL solver or a manual CNF/Tseitin pipeline | Z3 does this; it adds bugs, not marks | Explain DPLL(T) conceptually in the report |
| O6 | A full re-implementation of Hao et al. (multi-step formulation, iterative repair, their prompts) | Doubles the work; not needed to measure difference 1 | **Changed in v1.1:** a *lean* single-shot `codegen` ablation (one prompt, subprocess runner, same checker, about 80 lines) is in scope (D19), because PRD §6 promises the differences are *evaluated*. Anything beyond that is still out. |
| O7 | LangChain or agent frameworks, vector DB, RAG | ~40 places fit in the prompt | The plain `openai` client (any OpenAI-compatible base URL) |
| O8 | Database (SQLite/Postgres), REST API, Docker, auth | Nobody needs them for a course demo | CSV/JSON files, one Gradio process |
| O9 | React or custom front end | Gradio is in the proposal | Gradio Blocks with 4–5 panels |
| O10 | Soft preferences / ratings / "best trip" scoring | Not in the proposal; muddies "all reasoning is symbolic and exact" | `ignored_preferences` list, shown only |
| O11 | Day-of-week hours, multiple windows per place, transport modes | Each one multiplies the encoding and the test matrix | One window, one travel matrix. (Fixed showtimes are the one deliberate exception, D18.) |
| O12 | Fine-tuning the extractor | No data, no time | Few-shot prompt + retry |
| O13 | Provider-specific SDKs or code paths (google-genai, groq, ollama packages) | Each adds failure modes | **One** OpenAI-compatible client; the provider is a base URL in `.env` (D16) |
| O14 | Significance tests, bootstrap studies on n = 50 | Overclaims | Counts + Wilson intervals |
| O15 | A large benchmark (hundreds of instances) | Manual review becomes impossible, so paraphrase errors creep in | 50 generated + 15 held-out instances, all reviewed |

**Things that look like extra engineering but are worth the effort:** the oracle run (≈10 lines, the strongest argument in the report), the brute-force cross-check for n ≤ 7 (catches compiler bugs, ≈40 lines), the checker import ban test (≈15 lines), and the LLM disk cache (saves money and makes runs reproducible).

---

## Part C — Viva questions to rehearse

1. *"If the LLM extracts the wrong constraint, what does your guarantee mean?"* → R2, oracle vs pipeline numbers.
2. *"Isn't your compiler just as error-prone as LLM-generated code?"* → R1: deterministic, tested, brute-force cross-check, runtime checker.
3. *"Is your core the smallest?"* → No, it is minimal (irreducible); the minimum is NP-hard in general; deletion costs ≤ |core| calls.
4. *"Why not let the LLM suggest fixes like Hao et al.?"* → An LLM suggestion is not guaranteed feasible or minimal; ours comes from Optimize and is re-checked.
5. *"What does DPLL(T) actually do here?"* → CDCL enumerates Boolean assignments to X_i, P_ij and the assumption literals; the LIA theory solver (simplex + branch-and-bound) checks the arithmetic; conflicts become learned clauses; the final conflict over assumption literals is the unsat core.
6. *"How do you know a benchmark instance is really infeasible?"* → R11: a seeded arithmetic conflict, cross-checked by Z3.
7. *"Show me a request with two conflicts."* → R8 demo: `restores_feasibility = false`, apply, re-diagnose.
8. *"So is your approach actually better than Hao et al.'s?"* → The `codegen` ablation numbers on the same instances with the same model: crash rate, gold violations, detection. Then the caveat: it is a single-shot simplification, and code generation is more expressive (R24, ARCHITECTURE §9).
9. *"Where does the SAT search actually matter?"* → Showtimes and non-overlap are disjunctions. Walk through Garden Rhapsody at 19:45 ∨ 20:45 against a precedence and a closing time.
10. *"Is the held-out set really independent?"* → Written by each member before seeing the templates, labels backed by a witness or an arithmetic note, and prompts never tuned on it.
