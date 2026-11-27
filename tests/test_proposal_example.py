"""THE regression anchor (CLAUDE.md): if this test changes, the change is probably wrong."""

from test_checker import edit

from nstrip.checker.checker import check_plan
from nstrip.models.plan import Status
from nstrip.solve import solve


def test_all_three_wanted_is_unsat_with_the_proposal_core(proposal_problem):
    status, plan, diag = solve(proposal_problem)
    assert status == Status.UNSAT and plan is None
    assert set(diag.core) == {"budget", "must_visit:museum", "must_visit:cafe"}  # Park is free, so it drops out
    assert diag.is_minimal and diag.world_facts == []
    fixes = {(r.cid, r.action, r.new_value, r.restores_feasibility) for r in diag.relaxations}
    assert fixes == {
        ("budget", "raise_budget", 35, True),
        ("must_visit:cafe", "drop_must_visit", None, True),
        ("must_visit:museum", "drop_must_visit", None, True),
    }


def test_cafe_optional_gives_museum_and_park(proposal_problem):
    p = edit(proposal_problem, "cafe", must_visit=False)
    status, plan, diag = solve(p)
    assert status == Status.SAT and diag is None
    assert {v.location_id for v in plan.visits} == {"museum", "park"}  # Café would cost 35 > 30
    assert plan.total_cost == 20 and plan.optimal
    assert plan.visits[0].start == 540 and plan.visits[0].end == plan.visits[1].start  # compact day, no gaps
    assert check_plan(p, plan).ok
