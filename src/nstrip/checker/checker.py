"""Independent plan checker (spec §5).

Deliberately shares nothing with the encoder: no z3, no nstrip.encode / nstrip.solve (a test enforces this).
It sorts the visits and checks only *consecutive* pairs, where the encoder constrains every pair. With a metric
travel matrix the two are equivalent; without one the checker is weaker, never stronger. So a checker failure
on a Z3 plan always means a compiler bug.
"""

from itertools import pairwise

from nstrip.models import to_hhmm
from nstrip.models.check import CheckReport, Violation, ViolationKind
from nstrip.models.plan import Plan
from nstrip.models.problem import ProblemInstance


def check_plan(p: ProblemInstance, plan: Plan) -> CheckReport:
    acts = {a.id: a for a in p.activities}
    out: list[Violation] = []

    def bad(kind: ViolationKind, detail: str, *ids: str) -> None:
        out.append(Violation(kind=kind, detail=detail, location_ids=list(ids)))

    # 1. each visit on its own
    visits = []  # (visit, activity) for known, non-duplicate visits
    for v in plan.visits:
        a = acts.get(v.location_id)
        if a is None:
            bad("unknown_location", f"{v.location_id} is not one of the requested places", v.location_id)
            continue
        if any(a.id == seen.id for _, seen in visits):
            bad("duplicate", f"{a.name} is visited more than once", a.id)
            continue
        visits.append((v, a))
        span = f"{to_hhmm(v.start)}-{to_hhmm(v.end)}"
        if v.end - v.start != a.duration:
            bad("duration_mismatch", f"{a.name} lasts {v.end - v.start} min, needs {a.duration}", a.id)
        if v.start < p.horizon_start or v.end > p.horizon_end:
            bad("horizon", f"{a.name} {span} is outside the trip "
                           f"{to_hhmm(p.horizon_start)}-{to_hhmm(p.horizon_end)}", a.id)
        if v.start < a.open or v.end > a.close:
            bad("opening", f"{a.name} {span} is outside opening hours {to_hhmm(a.open)}-{to_hhmm(a.close)}", a.id)
        if a.showtimes and v.start not in a.showtimes:
            bad("showtime", f"{a.name} starts at {to_hhmm(v.start)}, shows start only at "
                            f"{', '.join(map(to_hhmm, a.showtimes))}", a.id)
        if (a.user_earliest is not None and v.start < a.user_earliest) or \
                (a.user_latest is not None and v.end > a.user_latest):
            bad("window", f"{a.name} {span} is outside the requested window", a.id)

    # 2. consecutive pairs only, after sorting by start
    visits.sort(key=lambda va: va[0].start)
    for (v1, a1), (v2, a2) in pairwise(visits):
        gap = p.travel(a1.id, a2.id)
        if v2.start < v1.end + gap:
            bad("overlap_or_transit", f"{a2.name} starts {to_hhmm(v2.start)}, but {a1.name} ends "
                                      f"{to_hhmm(v1.end)} and travel takes {gap} min", a1.id, a2.id)

    # 3. getting there from the start location, and back
    if visits and p.start_location:
        v, a = visits[0]
        if v.start < p.horizon_start + p.travel(p.start_location, a.id):
            bad("horizon", f"no time to travel from {p.start_location} to {a.name} by {to_hhmm(v.start)}", a.id)
        if p.return_to_start:
            v, a = max(visits, key=lambda va: va[0].end)
            if v.end + p.travel(a.id, p.start_location) > p.horizon_end:
                bad("horizon", f"no time to return to {p.start_location} after {a.name}", a.id)

    # 4. whole-plan requirements
    cost = sum(a.cost for _, a in visits)
    if p.budget is not None and cost > p.budget:
        bad("budget", f"total cost {cost} exceeds the budget {p.budget}")
    visited = {a.id: v for v, a in visits}
    for a in p.activities:
        if a.must_visit and a.id not in visited:
            bad("missing_must_visit", f"{a.name} must be visited", a.id)
    for x, y in p.precedences:
        if x in visited and y in visited and visited[x].end + p.travel(x, y) > visited[y].start:
            bad("precedence", f"{acts[x].name} must end (plus travel) before {acts[y].name} starts", x, y)

    return CheckReport(ok=not out, violations=out)
