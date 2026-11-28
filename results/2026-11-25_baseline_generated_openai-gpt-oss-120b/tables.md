# baseline on the generated set

model `openai/gpt-oss-120b` at `https://api.groq.com/openai/v1`, KB e5a5ae6, run 2026-11-25_baseline_generated_openai-gpt-oss-120b


## overview

| metric | value |
|---|---|
| instances | 55 |
| statuses | {'BASELINE_SAT': 30, 'BASELINE_UNSAT': 25} |
| end-to-end success | 50/55 = 91% [95% CI 80%-96%] |

## plans

| metric | value |
|---|---|
| SAT-claimed plans violating gold | 3/30 = 10% [95% CI 3%-26%] |
| gold violation kinds | {'showtime': 1, 'duration_mismatch': 2, 'horizon': 5} |

## infeasibility

| metric | value |
|---|---|
| precision (UNSAT = positive) | 23/25 = 92% [95% CI 75%-98%] |
| recall (UNSAT = positive) | 23/25 = 92% [95% CI 75%-98%] |
