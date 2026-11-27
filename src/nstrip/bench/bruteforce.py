"""Exhaustive reference solver for tiny problems (n <= 7). No z3, no encoder: it exists only to cross-check them.

For a fixed order of visits, starting each visit as early as possible is optimal: every later constraint is
either a lower bound (previous end + travel, opening, user earliest, next showtime) or an upper bound that an
earlier start can only help. So trying every subset and every order, each scheduled greedily, is complete.
With a metric travel matrix, gaps between consecutive visits imply the gaps between all pairs.
"""

from itertools import combinations, permutations

from nstrip.models.plan import Plan, Visit
from nstrip.models.problem import ProblemInstance


def schedule(p: ProblemInstance, order: tuple[str, ...]) -> list[Visit] | None:
    acts = {a.id: a for a in p.activities}
    o = p.start_location
    out: list[Visit] = []
    for i in order:
        a = acts[i]
        start = max(p.horizon_start + (p.travel(o, i) if o else 0), a.open, a.user_earliest or 0)
        if out:
            start = max(start, out[-1].end + p.travel(out[-1].location_id, i))
        if a.showtimes:
            later = [t for t in sorted(a.showtimes) if t >= start]
            if not later:
                return None
            start = later[0]
        end = start + a.duration
        back = p.travel(i, o) if o and p.return_to_start else 0
        if end > a.close or (a.user_latest is not None and end > a.user_latest) or end + back > p.horizon_end:
            return None
        out.append(Visit(location_id=i, start=start, end=end))
    return out


def best_plan(p: ProblemInstance) -> Plan | None:
    """None if infeasible; otherwise a plan with the most optional places, then the lowest cost (the same
    lexicographic objective as the Z3 optimiser)."""
    must = [a.id for a in p.activities if a.must_visit]
    optional = [a.id for a in p.activities if not a.must_visit]
    cost = {a.id: a.cost for a in p.activities}
    best: tuple[int, int, list[Visit]] | None = None
    for k in range(len(optional), -1, -1):
        for extra in combinations(optional, k):
            chosen = must + list(extra)
            total = sum(cost[i] for i in chosen)
            if (p.budget is not None and total > p.budget) or (best and (k, -total) <= (best[0], -best[1])):
                continue
            for order in permutations(chosen):
                pos = {i: n for n, i in enumerate(order)}
                if any(a in pos and b in pos and pos[a] > pos[b] for a, b in p.precedences):
                    continue
                visits = schedule(p, order)
                if visits is not None:
                    best = (k, total, visits)
                    break
        if best and best[0] == k:
            break  # no smaller subset can have more optional places
    return None if best is None else Plan(visits=best[2], total_cost=best[1])
