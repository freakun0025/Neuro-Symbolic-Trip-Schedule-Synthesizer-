# oracle on the generated set

model `None` at `None`, KB e5a5ae6, run 2026-11-25_oracle_generated_z3


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
| mean raw core size | 3.72 |
| mean minimal core size | 3.36 |
| mean z3_minimize core size | 3.28 |
| mean solver calls to minimise | 4.68 |

## runtime (solve ms)

| metric | value |
|---|---|
| n=3 | mean 7, median 6 |
| n=4 | mean 10, median 7 |
| n=5 | mean 366, median 20 |
| n=6 | mean 548, median 24 |
| n=7 | mean 636, median 16 |
| n=8 | mean 227, median 69 |
| n=9 | mean 92, median 45 |
| n=10 | mean 27, median 27 |
| n=11 | mean 123, median 76 |
| n=12 | mean 1188, median 72 |
