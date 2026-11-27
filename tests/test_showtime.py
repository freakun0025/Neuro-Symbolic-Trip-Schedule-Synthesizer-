"""Fixed showtimes: X_i => S_i in {t_k}. A world fact: it can be in a core but is never relaxed."""

from conftest import zero_transit

from nstrip.checker.checker import check_plan
from nstrip.models.plan import Status
from nstrip.models.problem import Activity, ProblemInstance
from nstrip.solve import solve


def dinner_and_show(dinner_minutes: int) -> ProblemInstance:
    """Dinner must fit 19:00-21:00 (user window); Garden Rhapsody starts only at 19:45 or 20:45."""
    acts = [
        Activity(id="rhapsody", name="Garden Rhapsody", must_visit=True, duration=15, cost=0,
                 open=1170, close=1440, showtimes=[1185, 1245]),
        Activity(id="dinner", name="Dinner", must_visit=True, duration=dinner_minutes, cost=20,
                 open=0, close=1440, user_earliest=1140, user_latest=1260),
    ]
    return ProblemInstance(horizon_start=540, horizon_end=1440, activities=acts,
                           transit=zero_transit(["rhapsody", "dinner"]), source="gold")


def test_show_starts_on_a_listed_time():
    p = dinner_and_show(105)  # 19:00-20:45, then the 20:45 show
    status, plan, _ = solve(p)
    assert status == Status.SAT and check_plan(p, plan).ok
    assert {v.location_id: v.start for v in plan.visits} == {"dinner": 1140, "rhapsody": 1245}


def test_showtime_clash_is_explained_not_relaxed():
    p = dinner_and_show(110)  # 19:00-20:50 overlaps both shows; dinner cannot start before 19:00
    status, _, diag = solve(p)
    assert status == Status.UNSAT
    assert set(diag.core) == {"showtime:rhapsody", "window:dinner", "must_visit:dinner", "must_visit:rhapsody"}
    assert diag.world_facts == ["showtime:rhapsody"]
    assert "showtime:rhapsody" not in {r.cid for r in diag.relaxations}
    widen = next(r for r in diag.relaxations if r.cid == "window:dinner")
    # cheapest fix: start dinner 5 min earlier (18:55-20:45, then the 20:45 show), not end it 50 min later
    assert widen.restores_feasibility and (widen.old_value, widen.new_value) == (1140, 1135)
