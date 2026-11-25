# Neuro-Symbolic Trip & Schedule Synthesizer

AID 851 (Introduction to Machine Reasoning) project. You describe a day out in Singapore in plain English;
you get either a timetable that is **guaranteed to satisfy every extracted constraint**, or the **minimal set of
requirements that conflict** plus the **smallest change** that would fix it.

```
request ─► LLM fills a typed form (Pydantic IR, place = enum of KB ids, retried on invalid output)
        ─► deterministic grounding with the knowledge base (all integers; defaults logged)
        ─► compiler: QF-LIA + Boolean constraints, one named assumption literal per requirement
        ─► Z3 (CDCL(T), the modern form of DPLL(T))
              SAT   ─► Optimize: most optional places, lowest cost, then earliest starts ─► plan
                      ─► independent checker (no Z3, no shared code) must accept it
              UNSAT ─► unsat core ─► deletion-minimised (minimal) core
                      ─► Z3 Optimize: smallest change per core member, on the full problem
        ─► template explanation (an LLM may only rephrase it, under a numbers/names guard)
```

The LLM never plans, never decides feasibility and never proposes fixes. The only place an LLM writes Z3 code
is `nstrip/ablation/codegen.py`, an evaluation-only comparison with Hao et al. (NAACL 2025).

Specs: [context/PRD.md](context/PRD.md) (what), [context/ARCHITECTURE.md](context/ARCHITECTURE.md) (how),
[context/DATA_MODEL_AND_SCAFFOLDING.md](context/DATA_MODEL_AND_SCAFFOLDING.md) (models, folders),
[context/RISKS.md](context/RISKS.md) (pitfalls, viva questions), [context/AGENTS.md](context/AGENTS.md) (rules).

## Quickstart

```bash
uv sync --extra dev            # Python 3.11+, or: pip install -e ".[dev]"
uv run pytest -q               # ~355 tests, offline, ~20 s
uv run nstrip-app              # UI at http://127.0.0.1:7860 (examples work offline via "Re-solve")
```

To use a live LLM, copy `.env.example` to `.env` and set `OPENAI_BASE_URL`, `OPENAI_API_KEY` and
`NSTRIP_MODEL`. Any OpenAI-compatible provider works (OpenAI, Gemini, Groq, OpenRouter, local Ollama);
switching provider is a change to `.env` only. Every LLM call is cached in `data/cache/llm/`, so committed
runs replay offline with `NSTRIP_MODE=cache`.

## Evaluation

```bash
uv run nstrip-gen --seed 851                                  # 50 + 5 two-conflict instances, labels from construction
uv run nstrip-paraphrase --fraction 0.5 --model <other model>  # then review every paraphrase by hand
uv run nstrip-run --method oracle          --set generated    # gold IR -> Z3, no LLM
uv run nstrip-run --method pipeline        --set generated    # LLM extraction -> Z3
uv run nstrip-run --method pipeline_verify --set generated    # + one solver -> LLM verification round on UNSAT
uv run nstrip-run --method baseline        --set generated    # pure LLM planner (NSTRIP_BASELINE_* in .env)
uv run nstrip-run --method baseline        --set generated --role extract   # same, with the extraction model
uv run nstrip-run --method codegen         --set generated    # Hao-style: the LLM writes the Z3 program
uv run nstrip-run --method pipeline        --set heldout      # the team's hand-written set
uv run nstrip-eval --compare generated                        # results/comparison_generated.md
uv run nstrip-stress                                          # solver scaling, n = 3..30
```

Each run writes `results/<run_id>/records.jsonl`, `summary.csv` and `tables.md`; every LLM call is in
`data/cache/llm/`, so `NSTRIP_MODE=cache` replays a run offline with identical results.

Models used (2026-11-25): extraction `gemini-3.5-flash-lite` (Gemini's OpenAI-compatible endpoint); baseline and
codegen `openai/gpt-oss-120b` (Groq) and, for a same-model comparison, the extraction model; paraphrases
`gemini-3.1-flash-lite`. The proposal named gpt-4o-mini / GPT-4o; these were the strongest free-tier models
available (see `context/ARCHITECTURE.md` D26).

**Results on the 55 generated instances:** see [results/comparison_generated.md](results/comparison_generated.md)
for every method with Wilson 95% intervals.
In short:

| Method | Model | Correct (of 55) | Claimed plans violating gold |
|---|---|---|---|
| Oracle (gold IR → Z3) | none | 55 | 0/30 |
| **Pipeline** (LLM → IR → Z3) | gemini-3.5-flash-lite | **55** | **0/30** |
| Pure-LLM planner | openai/gpt-oss-120b | 50 | 3/30 |
| LLM writes the Z3 program (Hao-style) | gemini-3.5-flash-lite | 38 (8 programs crashed) | 3/22 |
| Pure-LLM planner | gemini-3.5-flash-lite | 29 | 1/5 |

Extraction: 53/55 requests extracted exactly (micro F1 1.00 over 1,450 constraint tuples). All cores equal the
seeded conflict (20/20) or one of the two seeded conflicts (5/5). The optional verification round changed 0 of 25
UNSAT answers, so it erased no real conflict.

## Layout

```
data/kb/                 Singapore knowledge base (39 places, SGD, showtimes, source URLs, checked flag)
data/benchmark/          generated instances + manifest; heldout/ is written by the team (see its README)
data/examples/           demo requests with hand-written IRs (used by the UI and tests)
src/nstrip/models/       Pydantic models: IR, grounded problem, plans, diagnoses, benchmark records
src/nstrip/kb/           KB loader, travel times (metric by construction, asserted on load)
src/nstrip/extract/      OpenAI-compatible client + disk cache, prompts, extractor with retries
src/nstrip/ground.py     IR + KB -> ProblemInstance
src/nstrip/encode/       the compiler (tracked constraints, readable forms)
src/nstrip/solve/        feasibility, two-stage optimisation, core minimisation, relaxations
src/nstrip/checker/      independent plan checker (never imports z3 / encode / solve)
src/nstrip/explain/      templates + guarded rephrase
src/nstrip/pipeline.py   the whole pipeline, errors as statuses
src/nstrip/baseline/     pure-LLM planner;  src/nstrip/ablation/  codegen (evaluation only)
src/nstrip/bench/        generator, paraphrase, runner, metrics, stress, brute-force reference solver
src/nstrip/app/          Gradio UI
```

## Limits (say these at the viva)

- The guarantee is about the **extracted** constraints; extraction accuracy is measured, not assumed.
- Single day, single city, one opening window per place, approximate KB values (see `checked` in the CSV).
- Cores are **minimal** (irreducible), not minimum. Relaxations are per member, each re-solved on the full problem.
- Above ~15 places the optional-subset optimisation is not always proven optimal within budget (plans stay valid).
