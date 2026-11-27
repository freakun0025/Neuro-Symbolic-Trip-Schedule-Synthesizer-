"""Feasibility (CDCL(T), the modern form of DPLL(T)) and plan selection (ARCHITECTURE §4.4, §4.5)."""

import z3

from nstrip.config import SOLVER_TIMEOUT_MS
from nstrip.encode.compiler import Encoding
from nstrip.models.plan import Plan, Visit

FREE_ORDER_MAX = 8  # stage 2 searches visit orders only up to this many chosen places (ARCHITECTURE D24)


def make_solver(enc: Encoding, timeout_ms: int = SOLVER_TIMEOUT_MS) -> z3.Solver:
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    s.add(enc.hard)
    s.add([z3.Implies(t.lit, t.phi) for t in enc.tracked.values()])
    return s


def check_feasible(enc: Encoding, timeout_ms: int = SOLVER_TIMEOUT_MS) -> str:
    return str(make_solver(enc, timeout_ms).check(*enc.lits))  # "sat" | "unsat" | "unknown"


def _plan(enc: Encoding, m: z3.ModelRef, optimal: bool) -> Plan:
    visits = []
    for a in enc.problem.activities:
        if z3.is_true(m.eval(enc.X[a.id], model_completion=True)):
            start = m.eval(enc.S[a.id], model_completion=True).as_long()
            visits.append(Visit(location_id=a.id, start=start, end=start + a.duration))
    cost = {a.id: a.cost for a in enc.problem.activities}
    return Plan(visits=sorted(visits, key=lambda v: v.start),
                total_cost=sum(cost[v.location_id] for v in visits), optimal=optimal)


def _optimizer(enc: Encoding, timeout_ms: int) -> z3.Optimize:
    o = z3.Optimize()
    o.set("timeout", timeout_ms)
    o.add(enc.hard)
    o.add([t.phi for t in enc.tracked.values()])  # all tracked constraints are hard here
    return o


def optimise_plan(enc: Encoding, timeout_ms: int = SOLVER_TIMEOUT_MS) -> Plan:
    """Two stages. Call only on a feasible encoding.
    1. Lexicographic: most optional places, then lowest cost. This decides *what* to visit.
    2. With those places fixed, choose the order and the times: start everything as early as possible (least
       sum of starts), ties broken lexicographically by start time in place-id order, so the same request
       always gives the same plan. Stage 1 alone leaves the order to whichever tied model Z3 finds first,
       which differs from run to run. Up to FREE_ORDER_MAX chosen places the order is searched (a routing
       problem); above that, or on timeout, stage 1's order is compacted instead.
    """
    acts = enc.problem.activities
    o = _optimizer(enc, timeout_ms)
    o.maximize(sum((z3.If(enc.X[a.id], 1, 0) for a in acts if not a.must_visit), z3.IntVal(0)))
    o.minimize(enc.cost())
    optimal = o.check() == z3.sat
    m = o.model() if optimal else _greedy_model(enc, timeout_ms)

    chosen = sorted(a.id for a in acts if z3.is_true(m.eval(enc.X[a.id], model_completion=True)))
    fixed = [enc.X[a.id] == m.eval(enc.X[a.id], model_completion=True) for a in acts]
    order = [pij == m.eval(pij, model_completion=True) for (i, j), pij in enc.P.items()
             if i in chosen and j in chosen]
    # Free order only for small plans: it is a routing search (fast up to ~8 places, seconds beyond). The switch
    # depends on the count, not on time, so the result stays deterministic; larger plans compact stage 1's order.
    tries = ([], order) if len(chosen) <= FREE_ORDER_MAX else (order,)
    for extra in tries:  # free order first; stage 1's order if that times out
        o2 = _optimizer(enc, timeout_ms)
        o2.add(fixed + extra)
        o2.minimize(sum((enc.S[i] for i in chosen), z3.IntVal(0)))
        for i in chosen:
            o2.minimize(enc.S[i])
        if o2.check() == z3.sat:
            return _plan(enc, o2.model(), optimal=optimal)
    return _plan(enc, m, optimal=optimal)  # stage 2 only moves start times; stage 1's choice is kept


def _greedy_model(enc: Encoding, timeout_ms: int) -> z3.ModelRef:
    """Stage 1 timed out (choosing the best subset of optional places is an orienteering problem). Grow the
    plan greedily instead: add optional places cheapest first, keeping each one that stays feasible. Every
    step is a fast feasibility check; the plan is valid but flagged optimal=False."""
    s = make_solver(enc, timeout_ms)
    if s.check(*enc.lits) != z3.sat:
        raise RuntimeError("optimise_plan called on an encoding that is not feasible")
    keep: list[z3.BoolRef] = []
    for a in sorted((a for a in enc.problem.activities if not a.must_visit), key=lambda a: a.cost):
        if s.check(*enc.lits, *keep, enc.X[a.id]) == z3.sat:
            keep.append(enc.X[a.id])
    s.check(*enc.lits, *keep)
    return s.model()
