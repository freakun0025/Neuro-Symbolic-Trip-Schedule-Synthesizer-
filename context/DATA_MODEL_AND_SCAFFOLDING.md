# DATA MODEL, SCAFFOLDING, FILES & FOLDERS

Package name: `nstrip`. Python ≥ 3.11. All models are Pydantic v2 (`model_config = ConfigDict(extra="forbid", frozen=True)` unless noted).

**Units (everywhere):** time = `int` minutes since midnight (0–1440); duration = `int` minutes; money = `int` whole currency units (SGD for the Singapore KB; the `tiny_kb` test fixture keeps the proposal's $). The only place strings like `"09:30"` or `"$30"` exist is the LLM-facing schema, and validators convert them immediately.

---

## 1. Folder structure

```
nstrip/
├── README.md                     # quickstart, demo instructions
├── pyproject.toml                # deps pinned; [project.scripts] entry points
├── .env.example                  # see §1.1 (OPENAI_BASE_URL, OPENAI_API_KEY, NSTRIP_MODEL, per-role overrides, NSTRIP_MODE)
├── .gitignore                    # .env, results/*/scratch, __pycache__ (NOT data/cache)
│
├── context/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── ARCHITECTURE_ESSENTIAL.md
│   ├── DATA_MODEL_AND_SCAFFOLDING.md
│   ├── RISKS.md
│   ├── AGENTS.md                 # rules for anyone (human or coding agent) working on the repo
│   ├── CLAUDE.md                 # one-page version of AGENTS.md
│   └── report/                   # LaTeX/Markdown report, figures generated from results/
│
├── data/
│   ├── kb/
│   │   ├── locations.csv         # one row per place (see §3)
│   │   ├── travel_params.json    # {"overhead_min": 10, "speed_kmph": 25}
│   │   └── kb_meta.json          # {"city": "Singapore", "currency": "SGD", "curated_on": "YYYY-MM-DD", "version": "<sha>"}
│   ├── benchmark/
│   │   ├── manifest.json         # list of ids, generator seed, kb version, review status
│   │   ├── instances/
│   │   │   └── inst_001.json … inst_050.json
│   │   └── heldout/
│   │       └── held_001.json … held_015.json   # hand-written, hand-annotated (FR-21b)
│   ├── examples/
│   │   └── demo_requests.json    # curated requests for the UI + viva rehearsal
│   └── cache/
│       └── llm/                  # <sha256>.json — committed, makes runs reproducible offline
│
├── src/nstrip/
│   ├── __init__.py
│   ├── config.py                 # env + defaults (DEFAULT_DAY_START=540, DEFAULT_DAY_END=1260, SOLVER_TIMEOUT_MS=10000, OPTIMISE_TIMEOUT_MS=3000, MAX_RETRIES=3)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── ir.py                 # TripRequestIR, ActivitySpec, PrecedenceSpec, make_ir_model(kb_ids)
│   │   ├── problem.py            # Activity, ProblemInstance
│   │   ├── constraints.py        # ConstraintKind, cid helpers, canonical_tuples(ir_or_problem)
│   │   ├── plan.py               # Visit, Plan, Relaxation, Diagnosis, Status, PipelineResult
│   │   ├── check.py              # Violation, CheckReport
│   │   └── bench.py              # BenchmarkInstance, BaselineAnswer, RunRecord
│   ├── kb/
│   │   ├── __init__.py
│   │   ├── loader.py             # load_kb() -> KB ; validates; builds travel matrix; asserts metric
│   │   └── travel.py             # haversine, build_matrix, floyd_warshall, is_metric
│   ├── extract/
│   │   ├── __init__.py
│   │   ├── prompts.py            # SYSTEM_RULES, FEW_SHOTS, render_prompt()
│   │   ├── llm_client.py         # LLMClient protocol; OpenAICompatClient (any base URL); CacheOnlyClient; FakeClient; DiskCache
│   │   └── extractor.py          # extract(text, kb, client) -> TripRequestIR | ExtractionFailure
│   ├── ground.py                 # ground(ir, kb) -> ProblemInstance
│   ├── encode/
│   │   ├── __init__.py
│   │   └── compiler.py           # compile_problem(problem) -> Encoding
│   ├── solve/
│   │   ├── __init__.py
│   │   ├── solver.py             # check_feasible, optimise_plan
│   │   ├── core.py               # minimise_core (deletion)
│   │   └── relax.py              # relax_member, relax_all
│   ├── checker/
│   │   ├── __init__.py
│   │   └── checker.py            # check_plan(problem, plan) -> CheckReport   (NO z3 imports)
│   ├── explain/
│   │   ├── __init__.py
│   │   ├── templates.py          # render_plan, render_diagnosis
│   │   └── rephrase.py           # rephrase(text, client) with numbers/names guard
│   ├── pipeline.py               # run_pipeline(text|ir, kb, client) -> PipelineResult
│   ├── baseline/
│   │   ├── __init__.py
│   │   └── pure_llm.py           # plan_with_llm(text, kb_subset, client) -> BaselineAnswer
│   ├── ablation/
│   │   ├── __init__.py
│   │   └── codegen.py            # Hao-style: LLM writes Z3 code → subprocess (timeout) → Plan | UNSAT | CRASH
│   ├── bench/
│   │   ├── __init__.py
│   │   ├── generate.py           # witness-first SAT, seeded-conflict UNSAT
│   │   ├── paraphrase.py         # LLM paraphrase + guard
│   │   ├── run.py                # CLI: --method pipeline|oracle|baseline|codegen --set generated|heldout
│   │   ├── metrics.py            # summary.csv, tables.md, error taxonomy, core-size table, Wilson CIs
│   │   ├── stress.py             # solver-only scaling sweep n = 3..30 (with/without showtimes)
│   │   └── bruteforce.py         # exhaustive solver for n ≤ 7 (tests only; no z3)
│   └── app/
│       ├── __init__.py
│       └── gradio_app.py         # python -m nstrip.app.gradio_app
│
├── tests/
│   ├── conftest.py               # fixtures: tiny_kb (Museum/Park/Café, transit 0, open 00:00–24:00)
│   ├── test_models_validation.py
│   ├── test_kb_metric.py
│   ├── test_ground_defaults.py
│   ├── test_compiler_emits.py    # only applicable constraints emitted; cids stable
│   ├── test_proposal_example.py  # THE regression test (core + relaxations exactly)
│   ├── test_core_minimality.py   # every returned core: drop any member → SAT
│   ├── test_relax.py             # budget δ exact; restores_feasibility false with 2 conflicts
│   ├── test_checker.py           # hand-made bad plans → each violation kind detected
│   ├── test_checker_independence.py   # AST import ban (checker ↛ z3/encode/solve; pipeline/app ↛ ablation)
│   ├── test_showtime.py          # disjunction encoded; checker flags off-slot start; showtime clash → core has showtime:<id>
│   ├── test_codegen_runner.py    # subprocess runner parses plan / UNSAT / crash / timeout (canned code, no LLM)
│   ├── test_z3_vs_bruteforce.py  # random n≤6 problems: same SAT/UNSAT; Z3 plans pass checker
│   ├── test_extractor_retry.py   # fake client returns invalid then valid JSON
│   ├── test_rephrase_guard.py
│   ├── test_bench_labels.py      # every instance: witness passes checker / seeded conflict holds; held-out labels
│   ├── test_llm_client.py        # cache replay, provider fallback json_schema -> json_object, env roles
│   ├── test_pipeline.py          # end-to-end with FakeClient; statuses; checker disagreement -> INTERNAL_ERROR
│   ├── test_bench_run.py         # run_one for every method with scripted clients; metrics helpers
│   └── test_app.py               # demo examples' expected statuses; one-click fixes; rendering
│
└── results/
    └── <run_id>/                 # e.g. 2026-11-28_pipeline_generated_<model>
        ├── config.json           # base URL, model strings per role, KB version, git sha
        ├── records.jsonl
        ├── summary.csv
        └── tables.md
```

### 1.1 LLM configuration (`.env`)

The `openai` SDK reads `OPENAI_BASE_URL` and `OPENAI_API_KEY` itself, so switching provider is a change to `.env` only.

```bash
# provider: pick one base URL
OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# OPENAI_BASE_URL=https://api.groq.com/openai/v1
# OPENAI_BASE_URL=https://openrouter.ai/api/v1
# OPENAI_BASE_URL=http://localhost:11434/v1          # local Ollama
OPENAI_API_KEY=...

NSTRIP_MODEL=<default model id>                      # used by every role unless overridden
NSTRIP_EXTRACT_MODEL=                                 # optional per-role overrides:
NSTRIP_BASELINE_MODEL=                                #   EXTRACT, BASELINE, CODEGEN, PARAPHRASE, REPHRASE
NSTRIP_CODEGEN_MODEL=
# NSTRIP_<ROLE>_BASE_URL / NSTRIP_<ROLE>_API_KEY      # optional: run one role on a different provider
NSTRIP_MODE=live                                      # live | cache  (cache = never call the network)
```
`config.py` resolves each role in this order: role override, then the default model, then error. Model ids change between providers and over time, so verify them on setup and never hard-code them in source.

## 2. Core models

### 2.1 LLM-facing IR — `models/ir.py`

```python
TimeStr = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]   # "HH:MM"

class ActivitySpec(BaseModel):
    location_id: LocationId                 # dynamic Enum of KB ids (see make_ir_model)
    must_visit: bool                        # "want/must/need" → True ; "maybe/if time" → False
    duration_min: int | None = None         # user override; None → KB typical_duration_min
    cost: int | None = None                 # user override; None → KB cost
    earliest_start: TimeStr | None = None   # user window ("not before 3pm")
    latest_end: TimeStr | None = None       # user window ("done by 5pm")

class PrecedenceSpec(BaseModel):
    before: LocationId
    after: LocationId

class TripRequestIR(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    day_start: TimeStr | None = None
    day_end: TimeStr | None = None
    duration_limit_min: int | None = None   # "I have 4 hours" → 240
    budget: int | None = None               # "$30" → 30 ; decimals rounded DOWN by validator
    start_location: LocationId | None = None
    return_to_start: bool = False
    activities: list[ActivitySpec]
    precedences: list[PrecedenceSpec] = []
    unresolved_mentions: list[str] = []     # places mentioned but not in KB  → NEEDS_CLARIFICATION
    ignored_preferences: list[str] = []     # vague/soft wishes ("something artsy") → shown, never encoded

    # model_validator(mode="after"):
    #  - activity location_ids unique
    #  - precedence endpoints ∈ activities; before ≠ after
    #  - earliest_start < latest_end when both set; day_start < day_end when both set
    #  - all ints ≥ 0; duration_limit_min ≤ 1440
```

`make_ir_model(kb_ids: list[str]) -> type[TripRequestIR]` builds the model with `LocationId = Literal[*kb_ids]` (or a dynamic `Enum`) so the JSON schema sent to the LLM contains the allowed ids.
**Structured-output note:** providers differ in how much of JSON Schema they enforce. OpenAI strict mode, for example, needs every property listed as required, nullable fields typed `X | None`, and no defaults. `prompts.py` generates the schema from the model (never hand-written). The client tries `json_schema` and falls back to `json_object` with the schema in the prompt. Pydantic validation afterwards is the only authority.

### 2.2 Grounded problem — `models/problem.py`

```python
class Activity(BaseModel):
    id: str                  # KB id
    name: str
    must_visit: bool
    duration: int            # D_i
    cost: int                # C_i
    open: int                # O_i (KB)
    close: int               # K_i (KB)
    showtimes: list[int]     # KB only, never from the LLM; [] = no fixed start times
    user_earliest: int | None
    user_latest: int | None

class ProblemInstance(BaseModel):
    horizon_start: int       # H0
    horizon_end: int         # H1
    budget: int | None       # B
    start_location: str | None
    return_to_start: bool
    activities: list[Activity]
    precedences: list[tuple[str, str]]
    transit: dict[str, dict[str, int]]     # restricted to relevant ids (+ start_location)
    assumed_defaults: list[str]            # human-readable, e.g. "day start assumed 09:00"
    source: Literal["extracted", "gold"]
```

### 2.3 Constraint ids — `models/constraints.py`

```python
class ConstraintKind(StrEnum):
    BUDGET="budget"; HORIZON="horizon"; OPENING="opening"; SHOWTIME="showtime"; WINDOW="window"
    MUST_VISIT="must_visit"; PRECEDENCE="precedence"

RELAXABLE = {BUDGET, HORIZON, WINDOW, MUST_VISIT, PRECEDENCE}       # OPENING, SHOWTIME are world facts

def cid(kind, *ids) -> str          # "budget", "opening:museum", "precedence:museum:cafe"
def parse_cid(s) -> tuple[ConstraintKind, tuple[str, ...]]
```

### 2.4 Results — `models/plan.py`

```python
class Status(StrEnum):
    SAT="SAT"; UNSAT="UNSAT"; NEEDS_CLARIFICATION="NEEDS_CLARIFICATION"
    EXTRACTION_FAILED="EXTRACTION_FAILED"; SOLVER_TIMEOUT="SOLVER_TIMEOUT"; INTERNAL_ERROR="INTERNAL_ERROR"

class Visit(BaseModel):
    location_id: str; start: int; end: int

class Plan(BaseModel):
    visits: list[Visit]          # sorted by start
    total_cost: int
    optimal: bool = True         # False if Optimize timed out and a merely feasible model was used

class Relaxation(BaseModel):
    cid: str
    action: Literal["raise_budget", "extend_horizon_end", "widen_window", "drop_must_visit", "drop_precedence"]
    old_value: int | None
    new_value: int | None        # None for drops
    restores_feasibility: bool

class Diagnosis(BaseModel):
    core: list[str]              # cids, minimal
    raw_core_size: int           # size of Z3's unsat_core() before minimisation (core-size metric)
    is_minimal: bool             # False only if a minimisation check timed out
    world_facts: list[str]       # core members of kind OPENING or SHOWTIME
    relaxations: list[Relaxation]
    solver_calls: int

class PipelineResult(BaseModel):
    status: Status
    ir: TripRequestIR | None
    problem: ProblemInstance | None
    constraints_readable: list[str]      # "budget: 20·X_museum + 15·X_cafe ≤ 30"
    smtlib: str | None                   # solver.sexpr()
    plan: Plan | None
    diagnosis: Diagnosis | None
    explanation: str                     # template text (or guarded rephrase)
    explanation_source: Literal["template", "llm_rephrase"]
    timings_ms: dict[str, float]         # extract, ground, compile, solve, minimise, relax, check
    llm_attempts: int
    error: str | None
```

### 2.5 Checker — `models/check.py`

```python
class Violation(BaseModel):
    kind: Literal["unknown_location", "duplicate", "duration_mismatch", "overlap_or_transit",
                  "horizon", "opening", "showtime", "window", "budget", "missing_must_visit", "precedence"]
    detail: str
    location_ids: list[str] = []

class CheckReport(BaseModel):
    ok: bool
    violations: list[Violation]
```

### 2.6 Benchmark — `models/bench.py`

```python
class BenchmarkInstance(BaseModel):
    id: str                                   # "inst_017" | "held_004"
    set: Literal["generated", "heldout"]
    n_locations: int                          # 3..12
    budget_tightness: Literal["tight", "loose", "none"]
    expected_status: Literal["SAT", "UNSAT"]
    conflict_type: Literal["budget", "horizon", "window", "precedence_window",
                           "precedence_cycle", "showtime_clash", "other"] | None   # "other" = held-out only
    seeded_conflict: list[str] | None         # cids, e.g. ["budget","must_visit:a","must_visit:b"]
    conflict_note: str | None                 # held-out UNSAT: one-line arithmetic argument
    gold_ir: TripRequestIR
    witness_plan: Plan | None                 # SAT only; must pass checker
    request_template: str
    request_text: str                         # paraphrased (or template on fallback)
    paraphrase_model: str | None
    paraphrase_guard_passed: bool
    reviewed_by: str | None                   # team member initials
    kb_version: str
    generator_seed: int

class BaselineAnswer(BaseModel):
    feasible: bool
    visits: list[Visit]                       # empty if infeasible
    reason: str

class RunRecord(BaseModel):
    run_id: str; instance_id: str
    method: Literal["pipeline", "oracle", "baseline", "codegen"]
    base_url: str; model: str
    status: Status | Literal["BASELINE_SAT", "BASELINE_UNSAT", "BASELINE_FAILED", "CODEGEN_SAT", "CODEGEN_UNSAT", "CODEGEN_CRASH"]
    extracted_ir: TripRequestIR | None
    plan: Plan | None
    diagnosis: Diagnosis | None
    check_vs_gold: CheckReport | None
    check_vs_extracted: CheckReport | None    # pipeline only; must be ok
    extraction_scores: dict | None            # per-kind tp/fp/fn
    error_classes: list[str] | None           # taxonomy labels for this instance's extraction errors
    codegen_stderr: str | None                # codegen only: truncated traceback on crash
    core_sizes: dict[str, int] | None         # oracle UNSAT: raw, minimal, z3_minimize, calls
    error: str | None                         # pipeline error text, baseline reason or failure
    timings_ms: dict[str, float]
```

## 3. Knowledge-base file — `data/kb/locations.csv`

| column | type | example |
|---|---|---|
| id | slug, unique | `national_museum` |
| name | str | `National Museum of Singapore` |
| aliases | `|`-separated | `national museum|museum of singapore` |
| category | str | `museum` · `theme_park` · `attraction` · `show` · `nature` · `food` · `shopping` |
| cost | int (SGD) | `15` (food: typical meal per person) |
| typical_duration_min | int | `120` |
| open | `HH:MM` | `10:00` |
| close | `HH:MM`, or `24:00` for open until midnight or later | `19:00` |
| showtimes | `|`-separated `HH:MM`, may be empty | `19:45|20:45` (Garden Rhapsody) |
| lat, lon | float | `1.2966, 103.8485` |
| source_url | str | official page the values came from |
| checked | `yes` / `no` | `yes` = cross-checked on `curated_on`; `no` = still to verify against `source_url` |

The loader validates:
- unique ids, ids match `^[a-z0-9_]+$` (no `:`, so cids stay parseable), open < close, cost ≥ 0, duration > 0, `typical_duration_min ≤ close − open`
- for every showtime t: `open ≤ t` and `t + typical_duration_min ≤ close`
- the travel matrix is metric. Places at identical coordinates (e.g. Garden Rhapsody at Supertree Grove) get transit 0; every other pair gets the overhead.

Values are an approximate snapshot; `kb_meta.json.curated_on` records the date. A test fixture KB (`tiny_kb`) lives in `tests/conftest.py`, not in `data/`.

## 4. Canonical constraint tuples (extraction accuracy)

Both gold and extracted IR are first **grounded** (`ground(ir, kb)`), and the tuples are computed from the resulting `ProblemInstance`. This way, an LLM that restates a KB value as an "override" (e.g. writes `cost: 20` for a museum whose KB cost is already 20) is not penalised. The tuples are then compared as sets (exact match, no numeric tolerance).

| kind | tuple |
|---|---|
| activity | `("activity", id, must_visit)` |
| budget | `("budget", B)` |
| horizon | `("horizon_start", H0)`, `("horizon_end", H1)` (after default resolution) |
| window | `("window", id, earliest, latest)` |
| precedence | `("precedence", a, b)` |
| effective facts | `("duration", id, d)`, `("cost", id, c)` (after override/KB merge) |
| origin | `("origin", id, return_to_start)` |

Showtimes and opening hours come only from the KB, so they are identical for gold and extracted problems and are not scored.

Report micro P/R/F1 per kind, and instance exact match = the sets are equal.

## 5. Example benchmark instance (abbreviated)

This example uses the proposal's Museum/Park/Café ids for readability. Real instances use Singapore KB ids and SGD.

```json
{
  "id": "inst_003", "set": "generated", "n_locations": 3, "budget_tightness": "tight",
  "expected_status": "UNSAT", "conflict_type": "budget",
  "seeded_conflict": ["budget", "must_visit:museum", "must_visit:cafe"], "conflict_note": null,
  "gold_ir": {
    "schema_version": "1.0", "day_start": null, "day_end": null,
    "duration_limit_min": 240, "budget": 30, "start_location": null, "return_to_start": false,
    "activities": [
      {"location_id": "museum", "must_visit": true,  "duration_min": 120, "cost": 20, "earliest_start": null, "latest_end": null},
      {"location_id": "park",   "must_visit": true,  "duration_min": 60,  "cost": 0,  "earliest_start": null, "latest_end": null},
      {"location_id": "cafe",   "must_visit": true,  "duration_min": 60,  "cost": 15, "earliest_start": null, "latest_end": null}
    ],
    "precedences": [{"before": "museum", "after": "cafe"}],
    "unresolved_mentions": [], "ignored_preferences": []
  },
  "witness_plan": null,
  "request_template": "I have 4 hours and $30, and want the Museum ($20, 2 h), Park (free, 1 h) and Café ($15, 1 h), Museum before Café.",
  "request_text": "Got about four hours and thirty dollars. I'd like to hit the Museum ($20, 2 hours), the Park (free, 1 hour) and the Café ($15, 1 hour) — Museum has to come before the Café.",
  "paraphrase_model": "<configured paraphrase model>", "paraphrase_guard_passed": true,
  "reviewed_by": "PB", "kb_version": "a1b2c3d", "generator_seed": 851
}
```

## 6. Public function signatures (the contract between modules)

```python
# kb
def load_kb(path: Path = DATA/"kb") -> KB
# extract
def extract(text: str, kb: KB, client: LLMClient, max_retries: int = 3) -> tuple[TripRequestIR | None, int, str | None]   # up to 1 + max_retries calls
# ground
def ground(ir: TripRequestIR, kb: KB, source: Literal["extracted","gold"]) -> ProblemInstance
# encode
def compile_problem(p: ProblemInstance) -> Encoding   # Encoding: problem, X, S, P (order vars), hard, tracked: dict[cid, Tracked(lit, phi, readable)]
# solve  (Encoding carries its ProblemInstance, so no separate p argument)
def solve(p: ProblemInstance, timeout_ms: int) -> tuple[Status, Plan | None, Diagnosis | None]   # nstrip.solve
def check_feasible(enc: Encoding, timeout_ms: int) -> Literal["sat","unsat","unknown"]
def optimise_plan(enc: Encoding, timeout_ms: int) -> Plan   # falls back to the feasible model, optimal=False
def minimise_core(enc: Encoding, timeout_ms: int) -> tuple[list[str], int, bool, int]   # core, raw_size, is_minimal, calls
def relax_all(enc: Encoding, core: list[str], timeout_ms: int) -> list[Relaxation]
# checker
def check_plan(p: ProblemInstance, plan: Plan) -> CheckReport
# explain
def render_plan(p, plan, currency="SGD") -> str ; def render_diagnosis(p, d, currency="SGD") -> str
def rephrase(text: str, client: LLMClient, names: list[str]) -> tuple[str, Literal["template","llm_rephrase"]]   # names = place names the guard checks
# pipeline
def run_pipeline(text: str | None, kb: KB, client: LLMClient | None, ir: TripRequestIR | None = None) -> PipelineResult
# baseline
def plan_with_llm(text: str, kb: KB, ids: list[str], client: LLMClient) -> BaselineAnswer
# ablation (evaluation only)
def run_codegen(text: str, kb: KB, ids: list[str], client: LLMClient, timeout_s: int = 20) -> tuple[Plan | None, Literal["SAT","UNSAT","CRASH"], str | None]
# llm client
def make_client(role: Literal["extract","baseline","codegen","paraphrase","rephrase"], model: str | None = None, live: bool | None = None) -> LLMClient   # reads §1.1 env
```

## 7. `pyproject.toml` (dependencies)

```toml
[project]
name = "nstrip"
requires-python = ">=3.11"
dependencies = [
  "z3-solver>=4.12,<5",
  "pydantic>=2.6,<3",
  "openai>=1.40",                 # the only LLM client; any OpenAI-compatible base URL (incl. local Ollama /v1)
  "pandas>=2.1",
  "numpy>=1.26",
  "gradio>=4.40",
  "python-dotenv>=1.0",
]
[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5"]

[project.scripts]
nstrip-gen   = "nstrip.bench.generate:main"
nstrip-run   = "nstrip.bench.run:main"
nstrip-eval  = "nstrip.bench.metrics:main"
nstrip-app   = "nstrip.app.gradio_app:main"
```
Pin exact versions in a lock file (`uv lock` or `pip freeze > requirements.lock`) before running the final evaluation.

## 8. Build order (scaffold → working)

1. `models/*` + `tests/conftest.py::tiny_kb` + `checker` + `test_checker.py`
2. `kb/*` + `data/kb/locations.csv` (Singapore) + `test_kb_metric.py`
3. `encode/compiler.py` + `solve/*` + `test_proposal_example.py`, `test_core_minimality.py`, `test_relax.py`, `test_showtime.py`
4. `bench/bruteforce.py` (incl. showtimes) + `test_z3_vs_bruteforce.py`
5. `ground.py` + `extract/*` (fake client in tests) + `pipeline.py`
6. `explain/*`
7. `bench/generate.py`, `paraphrase.py`, `run.py`, `metrics.py`; team writes `heldout/` in parallel from step 2 on
8. `baseline/pure_llm.py`, `ablation/codegen.py` + `test_codegen_runner.py`, `bench/stress.py`
9. `app/gradio_app.py`
