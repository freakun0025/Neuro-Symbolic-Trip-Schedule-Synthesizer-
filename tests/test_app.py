"""UI helpers (no browser): demo examples, rendering, and one-click fixes."""

import json

import pytest

from nstrip.app.gradio_app import (
    EXAMPLES,
    apply_relaxation,
    build,
    constraints_html,
    fix_choices,
    timeline_html,
    verdict_html,
)
from nstrip.extract.extractor import ir_model
from nstrip.kb.loader import load_kb
from nstrip.models.plan import Status
from nstrip.pipeline import run_pipeline

KB = load_kb()
IR = ir_model(tuple(KB.ids))
DEMOS = json.loads(EXAMPLES.read_text())


@pytest.mark.parametrize("ex", DEMOS, ids=lambda e: e["title"][:40])
def test_demo_examples_give_their_expected_status(ex):
    assert run_pipeline(None, KB, ir=IR.model_validate(ex["ir"])).status == ex["expect"]


def solve(title_start):
    ex = next(e for e in DEMOS if e["title"].startswith(title_start))
    return run_pipeline(None, KB, ir=IR.model_validate(ex["ir"]))


def test_every_offered_fix_applies_and_restoring_ones_make_it_feasible():
    for title in ("USS + Night", "Too much for 4 hours", "A long dinner", "Night Safari before"):
        r = solve(title)
        assert r.status == Status.UNSAT
        for _, n in fix_choices(r, KB):
            fix = r.diagnosis.relaxations[n]
            again = run_pipeline(None, KB, ir=apply_relaxation(r.ir, fix, r.problem.horizon_start, KB))
            if fix.restores_feasibility:
                assert again.status == Status.SAT, (title, fix)


def test_budget_fix_sets_the_exact_amount():
    r = solve("USS + Night")
    fix = next(x for x in r.diagnosis.relaxations if x.action == "raise_budget")
    assert apply_relaxation(r.ir, fix, r.problem.horizon_start, KB).budget == 139  # 83 + 56


def test_timeline_and_constraints_render():
    r = solve("Marina Bay")
    html = timeline_html(r, KB)
    assert "Garden Rhapsody" in html and "Spectra" in html and "ns-bar" in html
    table = constraints_html(solve("USS + Night"))
    assert '<tr class="core"><td><span class=ns-hatch></span></td><td><code>budget</code>' in table
    assert "<code>horizon" in table


def test_verdict_shows_the_proof():
    sat, unsat = verdict_html(solve("Marina Bay"), KB), verdict_html(solve("USS + Night"), KB)
    assert "Feasible" in sat and "0 violations" in sat
    assert "Infeasible" in unsat and "minimal" in unsat
    assert "No plan yet" in verdict_html(None, KB)


def test_app_builds():
    assert build(KB) is not None
