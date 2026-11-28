# pipeline on the generated set

model `gemini-3.5-flash-lite` at `https://generativelanguage.googleapis.com/v1beta/openai`, KB e5a5ae6, run 2026-11-25_pipeline_generated_gemini-3.5-flash-lite


## overview

| metric | value |
|---|---|
| instances | 55 |
| statuses | {'SAT': 30, 'UNSAT': 25} |
| end-to-end success | 55/55 = 100% [95% CI 93%-100%] |

## plans

| metric | value |
|---|---|
| SAT-claimed plans violating gold | 0/30 = 0% [95% CI 0%-11%] |
| solver plans proven optimal (else greedy after timeout) | 29/30 = 97% [95% CI 83%-99%] |
| plans violating their own extracted constraints (must be 0) | 0/30 = 0% [95% CI 0%-11%] |

## infeasibility

| metric | value |
|---|---|
| precision (UNSAT = positive) | 25/25 = 100% [95% CI 87%-100%] |
| recall (UNSAT = positive) | 25/25 = 100% [95% CI 87%-100%] |

## cores

| metric | value |
|---|---|
| core equals the seeded conflict | 20/20 = 100% [95% CI 84%-100%] |
| cores reported minimal | 20/20 = 100% [95% CI 84%-100%] |
| two-conflict instances: core is one of the seeded conflicts | 5/5 = 100% [95% CI 57%-100%] |

## extraction

| metric | value |
|---|---|
| activity P/R/F1 | 1.00 / 1.00 / 1.00 (tp 408, fp 2, fn 2) |
| budget P/R/F1 | 1.00 / 1.00 / 1.00 (tp 38, fp 0, fn 0) |
| cost P/R/F1 | 1.00 / 1.00 / 1.00 (tp 410, fp 0, fn 0) |
| duration P/R/F1 | 1.00 / 1.00 / 1.00 (tp 410, fp 0, fn 0) |
| horizon_end P/R/F1 | 1.00 / 1.00 / 1.00 (tp 55, fp 0, fn 0) |
| horizon_start P/R/F1 | 1.00 / 1.00 / 1.00 (tp 55, fp 0, fn 0) |
| origin P/R/F1 | 1.00 / 1.00 / 1.00 (tp 11, fp 0, fn 0) |
| precedence P/R/F1 | 1.00 / 1.00 / 1.00 (tp 35, fp 0, fn 0) |
| window P/R/F1 | 1.00 / 1.00 / 1.00 (tp 26, fp 0, fn 0) |
| ALL P/R/F1 | 1.00 / 1.00 / 1.00 (tp 1448, fp 2, fn 2) |
| instances extracted exactly | 53/55 = 96% [95% CI 88%-99%] |

## error taxonomy

| metric | value |
|---|---|
| wrong_must_visit | 2 instances, 0 with a wrong final answer |

## runtime (solve ms)

| metric | value |
|---|---|
| n=3 | mean 5, median 6 |
| n=4 | mean 10, median 7 |
| n=5 | mean 552, median 19 |
| n=6 | mean 556, median 24 |
| n=7 | mean 671, median 16 |
| n=8 | mean 222, median 51 |
| n=9 | mean 96, median 37 |
| n=10 | mean 26, median 27 |
| n=11 | mean 114, median 67 |
| n=12 | mean 1148, median 74 |

## runtime (extract ms)

| metric | value |
|---|---|
| all | mean 3, median 2 |
