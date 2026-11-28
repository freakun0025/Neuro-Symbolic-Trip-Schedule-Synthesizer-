# codegen on the generated set

model `gemini-3.5-flash-lite` at `https://generativelanguage.googleapis.com/v1beta/openai`, KB e5a5ae6, run 2026-11-25_codegen_generated_gemini-3.5-flash-lite


## overview

| metric | value |
|---|---|
| instances | 55 |
| statuses | {'CODEGEN_SAT': 22, 'CODEGEN_CRASH': 8, 'CODEGEN_UNSAT': 25} |
| end-to-end success | 38/55 = 69% [95% CI 56%-80%] |

## plans

| metric | value |
|---|---|
| SAT-claimed plans violating gold | 3/22 = 14% [95% CI 5%-33%] |
| gold violation kinds | {'horizon': 2, 'window': 1, 'unknown_location': 1} |

## infeasibility

| metric | value |
|---|---|
| precision (UNSAT = positive) | 19/25 = 76% [95% CI 57%-89%] |
| recall (UNSAT = positive) | 19/25 = 76% [95% CI 57%-89%] |

## codegen

| metric | value |
|---|---|
| programs that crashed / timed out / printed garbage | 8/55 = 15% [95% CI 8%-26%] |
