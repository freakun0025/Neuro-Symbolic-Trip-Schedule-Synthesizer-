# Held-out set (FR-21b): written by the team, not by the generator

15 requests, about 4 per team member. This set exists to measure extraction on phrasing that did not come
from our own templates, so:

- Write your requests **before** reading `src/nstrip/bench/generate.py` or the generated instances.
- Write the way a real traveller would: informal, out of order, "around lunch", "S$100-ish", typos are fine.
- Use places from `data/kb/locations.csv` (you may also mention one place that is *not* in it, to test
  `NEEDS_CLARIFICATION`).
- At least 5 must be infeasible, and at least 4 must involve a show (Garden Rhapsody, Spectra, Wings of Time).
- **Never tune prompts on this set.** Run it once, at the end.

## One file per request: `held_001.json` ... `held_015.json`

Copy `TEMPLATE.json.example`, then fill:

| field | what to write |
|---|---|
| `id` | `held_001` ... |
| `request_text` / `request_template` | your request, both the same |
| `gold_ir` | the IR a perfect extractor would produce (KB ids, "HH:MM" times, whole SGD) |
| `expected_status` | `SAT` or `UNSAT` |
| `witness_plan` | SAT only: a plan you worked out by hand (minutes since midnight) |
| `conflict_note` | UNSAT only: one line of arithmetic, e.g. "USS S$83 + Night Safari S$56 = 139 > budget 120" |
| `n_locations` | number of activities in `gold_ir` |
| `reviewed_by` | your initials |
| `kb_version` | from `python -c "from nstrip.kb.loader import load_kb; print(load_kb().version)"` |

`tests/test_bench_labels.py` checks every file: SAT witnesses must pass the independent checker, UNSAT
labels must have a `conflict_note`, and Z3 must agree with every label. If Z3 disagrees with your
label, recheck your arithmetic first, then the compiler.

Run: `python -m nstrip.bench.run --method pipeline --set heldout` (and the other methods).
