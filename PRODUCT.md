# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Course examiners (AID 851, Machine Reasoning) at a viva, watching on a laptop close up while the team types
examiner-made requests live. Secondary: recruiters and peers viewing the public repo / demo.

## Product Purpose
Turn a plain-English one-day Singapore trip request into either a timetable guaranteed to satisfy every
extracted constraint, or the minimal set of conflicting requirements plus the smallest fixes. Success at the
viva: the examiner sees that the LLM only extracted a typed form and that Z3 did the reasoning, with proof on screen.

## Positioning
The LLM never plans. Feasibility, the schedule, the minimal conflict and the fixes all come from Z3, and every plan
is re-verified by an independent checker that shares no code with the solver.

## Operating Context
Gradio app (`src/nstrip/app/gradio_app.py`), run locally with `nstrip-app`. Works offline through the editable IR
and "Re-solve"; live extraction needs an OpenAI-compatible LLM configured in `.env`.

## Capabilities and Constraints
- Must stay in Gradio (theme + CSS + HTML), no separate frontend.
- Keep every current feature: request box, extraction mode, status, answer text, timeline / conflict view,
  apply-fix, editable IR + re-solve, encoded constraints, SMT-LIB, places table, examples.
- Statuses: Feasible, Infeasible, Needs clarification, Extraction failed, Solver timeout, Internal error.
- Wording rules: say "minimal" (not minimum) conflict, "extracted constraints".

## Evidence on Hand
Knowledge base of 39 Singapore places (`data/kb/locations.csv`), 8 demo requests with IRs
(`data/examples/demo_requests.json`), oracle results in `results/`.

## Product Principles
1. Proof over promise: show the verification, not a claim of it.
2. The reasoning is visible: constraints, conflict and fixes are first-class, not hidden.
3. Honest limits: guarantees are about the extracted constraints.
