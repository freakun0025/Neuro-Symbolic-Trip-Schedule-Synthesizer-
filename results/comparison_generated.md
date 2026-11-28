# Comparison on the generated set

Rates are counts with Wilson 95% intervals; '-' = not applicable. Each run's full tables are in results/<run>/tables.md.

| method | model | end-to-end success | claimed plans violating gold | UNSAT precision | UNSAT recall | core = seeded conflict | core one of two seeded | extracted exactly | programs crashed |
|---|---|---|---|---|---|---|---|---|---|
| [oracle](2026-11-25_oracle_generated_z3/tables.md) | `none (gold IR)` | 55/55 = 100%<br>[93%-100%] | 0/30 = 0%<br>[0%-11%] | 25/25 = 100%<br>[87%-100%] | 25/25 = 100%<br>[87%-100%] | 20/20 = 100%<br>[84%-100%] | 5/5 = 100%<br>[57%-100%] | - | - |
| [pipeline](2026-11-25_pipeline_generated_gemini-3.5-flash-lite/tables.md) | `gemini-3.5-flash-lite` | 55/55 = 100%<br>[93%-100%] | 0/30 = 0%<br>[0%-11%] | 25/25 = 100%<br>[87%-100%] | 25/25 = 100%<br>[87%-100%] | 20/20 = 100%<br>[84%-100%] | 5/5 = 100%<br>[57%-100%] | 53/55 = 96%<br>[88%-99%] | - |
| [pipeline_verify](2026-11-25_pipeline_verify_generated_gemini-3.5-flash-lite/tables.md) | `gemini-3.5-flash-lite` | 55/55 = 100%<br>[93%-100%] | 0/30 = 0%<br>[0%-11%] | 25/25 = 100%<br>[87%-100%] | 25/25 = 100%<br>[87%-100%] | 20/20 = 100%<br>[84%-100%] | 5/5 = 100%<br>[57%-100%] | 53/55 = 96%<br>[88%-99%] | - |
| [codegen](2026-11-25_codegen_generated_gemini-3.5-flash-lite/tables.md) | `gemini-3.5-flash-lite` | 38/55 = 69%<br>[56%-80%] | 3/22 = 14%<br>[5%-33%] | 19/25 = 76%<br>[57%-89%] | 19/25 = 76%<br>[57%-89%] | - | - | - | 8/55 = 15%<br>[8%-26%] |
| [baseline](2026-11-25_baseline_generated_gemini-3.5-flash-lite/tables.md) | `gemini-3.5-flash-lite` | 29/55 = 53%<br>[40%-65%] | 1/5 = 20%<br>[4%-62%] | 25/50 = 50%<br>[37%-63%] | 25/25 = 100%<br>[87%-100%] | - | - | - | - |
| [baseline](2026-11-25_baseline_generated_openai-gpt-oss-120b/tables.md) | `openai/gpt-oss-120b` | 50/55 = 91%<br>[80%-96%] | 3/30 = 10%<br>[3%-26%] | 23/25 = 92%<br>[75%-98%] | 23/25 = 92%<br>[75%-98%] | - | - | - | - |
