# M3: development requests through live extraction (2026-11-25)

The 8 hand-written demo requests (`data/examples/demo_requests.json`, not the held-out set) were extracted live
with `gemini-3.5-flash-lite` and compared with their hand-written IRs (canonical tuples, `score_extraction`).

| Request | Final status | Extraction exact? | Difference |
|---|---|---|---|
| Marina Bay evening (feasible, two shows) | SAT, as expected | yes | |
| USS + Night Safari on S$100 (budget conflict) | UNSAT, as expected | yes | |
| Too much for 4 hours and S$30 (two independent conflicts) | UNSAT, as expected | yes | |
| A long dinner leaves no slot for Garden Rhapsody | UNSAT, as expected | yes | |
| Night Safari before the Zoo (opening hours) | UNSAT, as expected | no | "whole day from 8am": no end time extracted (gold 23:55); the default end applied |
| Museum morning from Orchard, back by 5pm | SAT, as expected | yes | |
| Sentosa day (theme park, show, optional luge) | SAT, as expected | yes | |
| A place we do not know (needs clarification) | NEEDS_CLARIFICATION, as expected | no | "this afternoon": no start time extracted (gold 13:00) |

8/8 correct final status, 6/8 exact extraction. Both misses are vague times ("whole day", "this afternoon") left
blank, so the logged defaults were used; neither changed the answer. The PRD asks for 10 such requests; the
team can add two more (vague times are worth covering, see above).
