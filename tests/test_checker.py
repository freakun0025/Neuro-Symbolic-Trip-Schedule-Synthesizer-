"""Every violation kind is detected on a hand-made bad plan, and a good plan passes."""

import pytest

from nstrip.checker.checker import check_plan
from nstrip.models.plan import Plan, Visit
from nstrip.models.problem import ProblemInstance


def edit(p: ProblemInstance, act_id: str | None = None, **changes) -> ProblemInstance:
    """Copy of p with one activity changed (if act_id) or top-level fields changed. Re-validates."""
    data = p.model_dump()
    if act_id:
        next(a for a in data["activities"] if a["id"] == act_id).update(changes)
    else:
        data.update(changes)
    return ProblemInstance.model_validate(data)


def kinds(p: ProblemInstance, *visits: tuple[str, int, int]) -> set[str]:
    plan = Plan(visits=[Visit(location_id=i, start=s, end=e) for i, s, e in visits], total_cost=0)
    report = check_plan(p, plan)
    assert report.ok == (not report.violations)
    return {v.kind for v in report.violations}


@pytest.fixture
def p(proposal_problem):
    """Proposal example with Café optional: Museum + Park is the valid plan."""
    return edit(proposal_problem, "cafe", must_visit=False)


GOOD = [("museum", 540, 660), ("park", 660, 720)]


def test_good_plan_passes(p):
    assert kinds(p, *GOOD) == set()


def test_proposal_example_cannot_fit_budget(proposal_problem):
    all_three = GOOD + [("cafe", 720, 780)]
    assert kinds(proposal_problem, *all_three) == {"budget"}
    assert kinds(proposal_problem, *GOOD) == {"missing_must_visit"}


def test_unknown_location(p):
    assert kinds(p, *GOOD, ("zoo", 720, 780)) == {"unknown_location"}


def test_duplicate(p):
    assert kinds(p, *GOOD, ("park", 720, 780)) == {"duplicate"}


def test_duration_mismatch(p):
    assert kinds(p, ("museum", 540, 650), ("park", 660, 720)) == {"duration_mismatch"}


def test_overlap(p):
    assert kinds(p, ("museum", 540, 660), ("park", 650, 710)) == {"overlap_or_transit"}


def test_transit_gap(p):
    t = p.transit | {"museum": p.transit["museum"] | {"park": 15}, "park": p.transit["park"] | {"museum": 15}}
    assert kinds(edit(p, transit=t), *GOOD) == {"overlap_or_transit"}
    assert kinds(edit(p, transit=t), ("museum", 540, 660), ("park", 675, 735)) == set()


def test_horizon(p):
    assert kinds(p, ("museum", 480, 600), ("park", 600, 660)) == {"horizon"}


def test_travel_from_start_location(p):
    ids = ["hotel", "museum", "park", "cafe"]
    t = {i: {j: (30 if "hotel" in (i, j) else 0) for j in ids} for i in ids}
    q = edit(p, start_location="hotel", transit=t)
    assert kinds(q, *GOOD) == {"horizon"}
    assert kinds(q, ("museum", 570, 690), ("park", 690, 750)) == set()
    back = edit(q, return_to_start=True)
    assert kinds(back, ("museum", 570, 690), ("park", 690, 750)) == set()  # 750 + 30 = 780, just fits
    assert kinds(back, ("museum", 570, 690), ("park", 700, 760)) == {"horizon"}  # 760 + 30 > 780


def test_opening(p):
    assert kinds(edit(p, "museum", open=600), *GOOD) == {"opening"}


def test_showtime(p):
    q = edit(p, "park", showtimes=[600, 720])
    assert kinds(q, *GOOD) == {"showtime"}
    assert kinds(q, ("museum", 540, 660), ("park", 720, 780)) == set()


def test_user_window(p):
    assert kinds(edit(p, "park", user_latest=700), *GOOD) == {"window"}
    assert kinds(edit(p, "museum", user_earliest=600), *GOOD) == {"window"}


def test_budget(p):
    assert kinds(edit(p, budget=10), *GOOD) == {"budget"}


def test_missing_must_visit(p):
    assert kinds(p, ("park", 540, 600)) == {"missing_must_visit"}


def test_precedence(p):
    q = edit(p, budget=None)
    assert kinds(q, ("cafe", 540, 600), ("museum", 600, 720), ("park", 720, 780)) == {"precedence"}
    assert kinds(q, ("museum", 540, 660), ("cafe", 660, 720), ("park", 720, 780)) == set()
    assert kinds(q, ("park", 540, 600), ("cafe", 600, 660)) == {"missing_must_visit"}  # vacuous without museum
