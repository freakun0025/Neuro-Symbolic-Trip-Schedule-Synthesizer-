from test_checker import edit

from nstrip.models.plan import Status
from nstrip.solve import solve


def fixes(p):
    status, _, diag = solve(p)
    assert status == Status.UNSAT
    return diag, {r.cid: r for r in diag.relaxations}


def test_horizon_extended_by_exactly_the_missing_time(proposal_problem):
    p = edit(proposal_problem, budget=100, horizon_end=720)  # 3 h, but the three visits need 4 h
    diag, r = fixes(p)
    assert set(diag.core) == {"horizon", "must_visit:museum", "must_visit:park", "must_visit:cafe"}
    assert (r["horizon"].old_value, r["horizon"].new_value) == (720, 780)
    assert r["horizon"].restores_feasibility


def test_window_widened_to_the_smallest_fit(proposal_problem):
    p = edit(edit(proposal_problem, budget=100), "park", user_latest=560)  # park must end by 09:20
    diag, r = fixes(p)
    assert "window:park" in diag.core
    assert (r["window:park"].old_value, r["window:park"].new_value) == (560, 600)  # 09:00 + 60 min


def test_precedence_cycle(proposal_problem):
    p = edit(proposal_problem, budget=100, precedences=[("museum", "cafe"), ("cafe", "museum")])
    diag, r = fixes(p)
    assert {"precedence:museum:cafe", "precedence:cafe:museum"} <= set(diag.core)
    assert r["precedence:cafe:museum"].action == "drop_precedence"
    assert r["precedence:cafe:museum"].restores_feasibility


def test_two_independent_conflicts_no_single_fix_restores(proposal_problem):
    # conflict 1: budget (35 > 30). conflict 2: the Park only opens after the trip ends.
    p = edit(proposal_problem, "park", open=800, close=900)
    diag, r = fixes(p)
    assert diag.relaxations and not any(x.restores_feasibility for x in diag.relaxations)
    if "opening:park" in diag.core:
        assert diag.world_facts == ["opening:park"] and "opening:park" not in r  # world facts never relaxed
