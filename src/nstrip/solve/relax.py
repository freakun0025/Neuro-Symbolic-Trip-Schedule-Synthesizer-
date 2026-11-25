"""Per-member relaxations with Z3 Optimize (ARCHITECTURE §4.7).

Each relaxation is solved on the FULL problem with only that member relaxed, so `restores_feasibility` is
False when another, independent conflict remains. Opening hours and showtimes are world facts: never relaxed.
Relaxations are not ranked against each other (dollars vs. minutes); they are listed in core order.
"""

import z3

from nstrip.config import SOLVER_TIMEOUT_MS
from nstrip.encode.compiler import Encoding, budget_phi, horizon_phi, window_phi
from nstrip.models.constraints import RELAXABLE, parse_cid
from nstrip.models.constraints import ConstraintKind as K
from nstrip.models.plan import Relaxation


def relax_member(enc: Encoding, c: str, timeout_ms: int = SOLVER_TIMEOUT_MS) -> Relaxation | None:
    kind, ids = parse_cid(c)
    if kind not in RELAXABLE:
        return None
    p = enc.problem
    o = z3.Optimize()
    o.set("timeout", timeout_ms)
    o.add(enc.hard)
    o.add([t.phi for t in enc.tracked.values() if t.cid != c])
    d, d2 = z3.Int("relax_delta"), z3.Int("relax_delta_2")
    old = new = None

    if kind == K.BUDGET:
        action, old, new = "raise_budget", p.budget, p.budget + d
        o.add(d >= 0, budget_phi(enc, new))
        o.minimize(d)
    elif kind == K.HORIZON:
        action, old, new = "extend_horizon_end", p.horizon_end, p.horizon_end + d
        o.add(d >= 0, horizon_phi(enc, new))
        o.minimize(d)
    elif kind == K.WINDOW:
        a = next(a for a in p.activities if a.id == ids[0])
        lo = a.user_earliest - d2 if a.user_earliest is not None else None
        hi = a.user_latest + d if a.user_latest is not None else None
        o.add(d >= 0, d2 >= 0, window_phi(enc, a.id, lo, hi))
        o.minimize(d + d2)
        action = "widen_window"
    elif kind == K.MUST_VISIT:
        action = "drop_must_visit"  # the activity simply becomes optional
    else:
        action = "drop_precedence"

    restores = o.check() == z3.sat
    if restores and kind == K.WINDOW:
        # report the side that moved: the latest end, unless only the earliest start had to move
        val = {v: o.model().eval(v, model_completion=True).as_long() for v in (d, d2)}
        if hi is not None and (val[d] > 0 or lo is None or val[d2] == 0):
            old, new = a.user_latest, a.user_latest + val[d]
        else:
            old, new = a.user_earliest, a.user_earliest - val[d2]
    elif restores and new is not None:
        new = o.model().eval(new, model_completion=True).as_long()
    else:
        new = None
    return Relaxation(cid=c, action=action, old_value=old, new_value=new, restores_feasibility=restores)


def relax_all(enc: Encoding, core: list[str], timeout_ms: int = SOLVER_TIMEOUT_MS) -> list[Relaxation]:
    return [r for c in core if (r := relax_member(enc, c, timeout_ms)) is not None]
