# DATA MODEL, SCAFFOLDING, FILES & FOLDERS

Package name: `nstrip`. Python ≥ 3.11. All models are Pydantic v2 (`model_config = ConfigDict(extra="forbid", frozen=True)` unless noted).

**Units (everywhere):** time = `int` minutes since midnight (0–1440); duration = `int` minutes; money = `int` whole currency units (USD, as in the proposal example). The only place strings like `"09:30"` or `"$30"` exist is the LLM-facing schema, and validators convert them immediately.

---

## 1. Folder structure

```
nstrip/
├── README.md                     # quickstart, demo instructions
├── AGENTS.md                     # rules for any coding agent
├── CLAUDE.md                     # rules for Claude Code
├── pyproject.toml                # deps pinned; [project.scripts] entry points
├── .env.example                  # OPENAI_API_KEY=, NSTRIP_BACKEND=openai|ollama|cache, NSTRIP_MODEL=
├── .gitignore                    # .env, results/*/scratch, __pycache__ (NOT data/cache)
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── ARCHITECTURE_ESSENTIAL.md
│   ├── DATA_MODEL_AND_SCAFFOLDING.md
│   ├── RISKS.md
│   └── report/                   # LaTeX/Markdown report, figures generated from results/
│
├── data/
│   ├── kb/
│   │   ├── locations.csv         # one row per place (see §3)
│   │   ├── travel_params.json    # {"overhead_min": 10, "speed_kmph": 20}
│   │   └── kb_meta.json          # {"city": "...", "currency": "USD", "curated_on": "YYYY-MM-DD", "version": "<sha>"}
│   ├── benchmark/
│   │   ├── manifest.json         # list of ids, generator seed, kb version, review status
│   │   └── instances/
│   │       └── inst_001.json … inst_050.json
│   ├── examples/
│   │   └── demo_requests.json    # curated requests for the UI + viva rehearsal
│   └── cache/
│       └── llm/                  # <sha256>.json — committed, makes runs reproducible offline
│
├── src/nstrip/
│   ├── __init__.py
│   ├── config.py                 # env + defaults (DEFAULT_DAY_START=540, DEFAULT_DAY_END=1260, SOLVER_TIMEOUT_MS=10000, MAX_RETRIES=3)
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
│   │   ├── llm_client.py         # LLMClient protocol; OpenAIClient; OllamaClient; CacheOnlyClient; DiskCache
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
│   ├── bench/
│   │   ├── __init__.py
│   │   ├── generate.py           # witness-first SAT, seeded-conflict UNSAT
│   │   ├── paraphrase.py         # LLM paraphrase + guard
│   │   ├── run.py                # CLI: --method pipeline|oracle|baseline
│   │   ├── metrics.py            # summary.csv, tables.md
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
│   ├── test_checker_independence.py   # AST import ban
│   ├── test_z3_vs_bruteforce.py  # random n≤6 problems: same SAT/UNSAT; Z3 plans pass checker
│   ├── test_extractor_retry.py   # fake client returns invalid then valid JSON
│   ├── test_rephrase_guard.py
│   └── test_bench_labels.py      # every instance: witness passes checker / seeded conflict holds
│
└── results/
    └── <run_id>/                 # e.g. 2026-11-25_pipeline_gpt-4o-mini
        ├── config.json
        ├── records.jsonl
        ├── summary.csv
        └── tables.md
```

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
**OpenAI strict mode note:** in strict structured outputs every property must be listed as required and nullable fields must be typed `X | None`, with no defaults in the schema. `prompts.py` generates the strict-compatible schema from the model; don't hand-write it.

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
    BUDGET="budget"; HORIZON="horizon"; OPENING="opening"; WINDOW="window"
    MUST_VISIT="must_visit"; PRECEDENCE="precedence"

RELAXABLE = {BUDGET, HORIZON, WINDOW, MUST_VISIT, PRECEDENCE}       # OPENING is a world fact

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

class Relaxation(BaseModel):
    cid: str
    action: Literal["raise_budget", "extend_horizon_end", "widen_window", "drop_must_visit", "drop_precedence"]
    old_value: int | None
    new_value: int | None        # None for drops
    restores_feasibility: bool

class Diagnosis(BaseModel):
    core: list[str]              # cids, minimal
    is_minimal: bool             # False only if a minimisation check timed out
    world_facts: list[str]       # core members of kind OPENING
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
                  "horizon", "opening", "window", "budget", "missing_must_visit", "precedence"]
    detail: str
    location_ids: list[str] = []

class CheckReport(BaseModel):
    ok: bool
    violations: list[Violation]
```

### 2.6 Benchmark — `models/bench.py`

```python
class BenchmarkInstance(BaseModel):
    id: str                                   # "inst_017"
    n_locations: int                          # 3..12
    budget_tightness: Literal["tight", "loose", "none"]
    expected_status: Literal["SAT", "UNSAT"]
    conflict_type: Literal["budget", "horizon", "window", "precedence_window", "precedence_cycle"] | None
    seeded_conflict: list[str] | None         # cids, e.g. ["budget","must_visit:a","must_visit:b"]
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
    method: Literal["pipeline", "oracle", "baseline"]
    backend: str; model: str
    status: Status | Literal["BASELINE_SAT", "BASELINE_UNSAT"]
    extracted_ir: TripRequestIR | None
    plan: Plan | None
    diagnosis: Diagnosis | None
    check_vs_gold: CheckReport | None
    check_vs_extracted: CheckReport | None    # pipeline only; must be ok
    extraction_scores: dict | None            # per-kind tp/fp/fn
    timings_ms: dict[str, float]
```

## 3. Knowledge-base file — `data/kb/locations.csv`

| column | type | example |
|---|---|---|
| id | slug, unique | `museum` |
| name | str | `Government Museum` |
| aliases | `|`-separated | `museum|govt museum` |
| category | str | `museum` |
| cost | int | `20` |
| typical_duration_min | int | `120` |
| open | `HH:MM` | `10:00` |
| close | `HH:MM` | `17:00` |
| lat, lon | float | `12.97, 77.59` |

The loader validates: unique ids, open < close, cost ≥ 0, duration > 0, and `typical_duration_min ≤ close − open`. A test fixture KB (`tiny_kb`) lives in `tests/conftest.py`, not in `data/`.

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

Report micro P/R/F1 per kind, and instance exact match = the sets are equal.

## 5. Example benchmark instance (abbreviated)

```json
{
  "id": "inst_003", "n_locations": 3, "budget_tightness": "tight",
  "expected_status": "UNSAT", "conflict_type": "budget",
  "seeded_conflict": ["budget", "must_visit:museum", "must_visit:cafe"],
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
  "paraphrase_model": "gpt-4o-mini", "paraphrase_guard_passed": true,
  "reviewed_by": "PB", "kb_version": "a1b2c3d", "generator_seed": 851
}
```

## 6. Public function signatures (the contract between modules)

```python
# kb
def load_kb(path: Path = DATA/"kb") -> KB
# extract
def extract(text: str, kb: KB, client: LLMClient, max_retries: int = 3) -> tuple[TripRequestIR | None, int, str | None]
# ground
def ground(ir: TripRequestIR, kb: KB, source: Literal["extracted","gold"]) -> ProblemInstance
# encode
def compile_problem(p: ProblemInstance) -> Encoding   # Encoding: vars, hard: list[BoolRef], tracked: dict[cid, (BoolRef lit, BoolRef φ)]
# solve
def check_feasible(enc: Encoding, timeout_ms: int) -> Literal["sat","unsat","unknown"]
def optimise_plan(enc: Encoding, p: ProblemInstance, timeout_ms: int) -> Plan
def minimise_core(enc: Encoding, timeout_ms: int) -> tuple[list[str], bool, int]
def relax_all(enc: Encoding, p: ProblemInstance, core: list[str], timeout_ms: int) -> list[Relaxation]
# checker
def check_plan(p: ProblemInstance, plan: Plan) -> CheckReport
# explain
def render_plan(p, plan) -> str ; def render_diagnosis(p, d) -> str
def rephrase(text: str, client: LLMClient) -> tuple[str, Literal["template","llm_rephrase"]]
# pipeline
def run_pipeline(text: str | None, kb: KB, client: LLMClient | None, ir: TripRequestIR | None = None) -> PipelineResult
# baseline
def plan_with_llm(text: str, kb: KB, ids: list[str], client: LLMClient) -> BaselineAnswer
```

## 7. `pyproject.toml` (dependencies)

```toml
[project]
name = "nstrip"
requires-python = ">=3.11"
dependencies = [
  "z3-solver>=4.12,<5",
  "pydantic>=2.6,<3",
  "openai>=1.40",
  "ollama>=0.3",
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
2. `kb/*` + `test_kb_metric.py`
3. `encode/compiler.py` + `solve/*` + `test_proposal_example.py`, `test_core_minimality.py`, `test_relax.py`
4. `bench/bruteforce.py` + `test_z3_vs_bruteforce.py`
5. `ground.py` + `extract/*` (fake client in tests) + `pipeline.py`
6. `explain/*`
7. `bench/generate.py`, `paraphrase.py`, `run.py`, `metrics.py`
8. `baseline/pure_llm.py`
9. `app/gradio_app.py`
