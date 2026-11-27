"""Only applicable constraints are emitted, and cids are stable."""

from test_checker import edit

from nstrip.encode.compiler import compile_problem


def test_proposal_example_cids(proposal_problem):
    enc = compile_problem(proposal_problem)
    # everything is open all day, so no opening:* constraints; no windows, no showtimes
    assert set(enc.tracked) == {"budget", "horizon", "must_visit:museum", "must_visit:park", "must_visit:cafe",
                                "precedence:museum:cafe"}
    assert enc.tracked["budget"].readable == "20·X_museum + 0·X_park + 15·X_cafe ≤ 30"
    assert all(t.lit.decl().name() == c for c, t in enc.tracked.items())


def test_no_budget_means_no_budget_constraint(proposal_problem):
    assert "budget" not in compile_problem(edit(proposal_problem, budget=None)).tracked


def test_world_facts_and_windows_emitted_when_they_apply(proposal_problem):
    p = edit(edit(edit(proposal_problem, "museum", open=600, close=1020), "park", showtimes=[600, 720]),
             "cafe", user_latest=900)
    tracked = compile_problem(p).tracked
    assert {"opening:museum", "showtime:park", "window:cafe"} <= set(tracked)
    assert "opening:cafe" not in tracked
    assert tracked["showtime:park"].readable == "X_park ⇒ S_park ∈ {10:00, 12:00}"
