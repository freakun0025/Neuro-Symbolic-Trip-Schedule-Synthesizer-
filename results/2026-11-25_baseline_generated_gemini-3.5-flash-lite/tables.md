# baseline on the generated set

model `gemini-3.5-flash-lite` at `https://generativelanguage.googleapis.com/v1beta/openai`, KB e5a5ae6, run 2026-11-25_baseline_generated_gemini-3.5-flash-lite


## overview

| metric | value |
|---|---|
| instances | 55 |
| statuses | {'BASELINE_UNSAT': 50, 'BASELINE_SAT': 5} |
| end-to-end success | 29/55 = 53% [95% CI 40%-65%] |

## plans

| metric | value |
|---|---|
| SAT-claimed plans violating gold | 1/5 = 20% [95% CI 4%-62%] |
| gold violation kinds | {'opening': 1} |

## infeasibility

| metric | value |
|---|---|
| precision (UNSAT = positive) | 25/50 = 50% [95% CI 37%-63%] |
| recall (UNSAT = positive) | 25/25 = 100% [95% CI 87%-100%] |
