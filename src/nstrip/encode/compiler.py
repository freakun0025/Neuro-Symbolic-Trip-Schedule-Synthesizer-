"""Deterministic compiler: ProblemInstance -> QF-LIA + Boolean constraints (ARCHITECTURE §4.3).

Every user requirement and world fact becomes one tracked constraint, guarded by an assumption literal named
after its cid (the mechanism behind assert_and_track), so it can show up in an unsat core. Non-overlap and
variable domains are hard. A constraint is emitted only when it applies.

The *_phi builders take a bound that is either a constant or a Z3 term, so relax.py can reuse exactly these
formulas with a relaxed bound instead of re-encoding them.
"""

from dataclasses import dataclass, field

import z3

from nstrip.models import to_hhmm
from nstrip.models.constraints import ConstraintKind as K
from nstrip.models.constraints import cid
from nstrip.models.problem import ProblemInstance

Bound = int | z3.ArithRef


@dataclass
class Tracked:
    cid: str
    kind: K
    lit: z3.BoolRef  # assumption literal, z3.Bool(cid)
    phi: z3.BoolRef  # the constraint itself
    readable: str


@dataclass
class Encoding:
    problem: ProblemInstance
    X: dict[str, z3.BoolRef]  # scheduled?
    S: dict[str, z3.ArithRef]  # start time, minutes since midnight
    hard: list[z3.BoolRef]
    tracked: dict[str, Tracked]
    P: dict[tuple[str, str], z3.BoolRef] = field(default_factory=dict)  # P[i, j]: i, then travel, then j

    @property
    def lits(self) -> list[z3.BoolRef]:
        return [t.lit for t in self.tracked.values()]

    def cost(self) -> z3.ArithRef:
        return sum((z3.If(self.X[a.id], a.cost, 0) for a in self.problem.activities), z3.IntVal(0))


def budget_phi(enc: Encoding, bound: Bound) -> z3.BoolRef:
    return enc.cost() <= bound


def horizon_phi(enc: Encoding, end: Bound) -> z3.BoolRef:
    """Every visit inside [H0, end], including travel from the start location and back to it if asked."""
    p, o = enc.problem, enc.problem.start_location
    parts = []
    for a in p.activities:
        earliest = p.horizon_start + (p.travel(o, a.id) if o else 0)
        back = p.travel(a.id, o) if o and p.return_to_start else 0
        s = enc.S[a.id]
        parts.append(z3.Implies(enc.X[a.id], z3.And(s >= earliest, s + a.duration + back <= end)))
    return z3.And(parts)


def window_phi(enc: Encoding, act_id: str, earliest: Bound | None, latest: Bound | None) -> z3.BoolRef:
    a = next(a for a in enc.problem.activities if a.id == act_id)
    s = enc.S[act_id]
    conds = ([s >= earliest] if earliest is not None else []) + \
            ([s + a.duration <= latest] if latest is not None else [])
    return z3.Implies(enc.X[act_id], z3.And(conds))


def compile_problem(p: ProblemInstance) -> Encoding:
    X = {a.id: z3.Bool(f"X_{a.id}") for a in p.activities}
    S = {a.id: z3.Int(f"S_{a.id}") for a in p.activities}
    enc = Encoding(problem=p, X=X, S=S, hard=[], tracked={})

    def track(kind: K, ids: tuple[str, ...], phi: z3.BoolRef, text: str) -> None:
        c = cid(kind, *ids)
        enc.tracked[c] = Tracked(cid=c, kind=kind, lit=z3.Bool(c), phi=phi, readable=text)

    if p.budget is not None:
        terms = " + ".join(f"{a.cost}·X_{a.id}" for a in p.activities)
        track(K.BUDGET, (), budget_phi(enc, p.budget), f"{terms} ≤ {p.budget}")

    via = f", travelling from {p.start_location}" + (" and back" if p.return_to_start else "") \
        if p.start_location else ""
    track(K.HORIZON, (), horizon_phi(enc, p.horizon_end),
          f"every visit within {to_hhmm(p.horizon_start)}–{to_hhmm(p.horizon_end)}{via}")

    for a in p.activities:
        x, s, d = X[a.id], S[a.id], a.duration
        enc.hard += [s >= 0, s <= 1440]
        if a.open > 0 or a.close < 1440:
            track(K.OPENING, (a.id,), z3.Implies(x, z3.And(s >= a.open, s + d <= a.close)),
                  f"X_{a.id} ⇒ {to_hhmm(a.open)} ≤ S_{a.id} ∧ S_{a.id} + {d} ≤ {to_hhmm(a.close)}")
        if a.showtimes:
            track(K.SHOWTIME, (a.id,), z3.Implies(x, z3.Or([s == t for t in a.showtimes])),
                  f"X_{a.id} ⇒ S_{a.id} ∈ {{{', '.join(map(to_hhmm, a.showtimes))}}}")
        if a.user_earliest is not None or a.user_latest is not None:
            lo = to_hhmm(a.user_earliest) if a.user_earliest is not None else "…"
            hi = to_hhmm(a.user_latest) if a.user_latest is not None else "…"
            track(K.WINDOW, (a.id,), window_phi(enc, a.id, a.user_earliest, a.user_latest),
                  f"X_{a.id} ⇒ visit inside {lo}–{hi}")
        if a.must_visit:
            track(K.MUST_VISIT, (a.id,), x, f"X_{a.id}")

    dur = {a.id: a.duration for a in p.activities}
    for a, b in p.precedences:
        t = p.travel(a, b)
        track(K.PRECEDENCE, (a, b), z3.Implies(z3.And(X[a], X[b]), S[a] + dur[a] + t <= S[b]),
              f"X_{a} ∧ X_{b} ⇒ S_{a} + {dur[a]} + {t} ≤ S_{b}")

    # Non-overlap with travel: P_ij names "i, then travel, then j" (Tseitin-style naming, for readability).
    ids = [a.id for a in p.activities]
    for n, i in enumerate(ids):
        for j in ids[n + 1:]:
            pij, pji = z3.Bool(f"P_{i}_{j}"), z3.Bool(f"P_{j}_{i}")
            enc.P[i, j], enc.P[j, i] = pij, pji
            enc.hard += [
                pij == (S[i] + dur[i] + p.travel(i, j) <= S[j]),
                pji == (S[j] + dur[j] + p.travel(j, i) <= S[i]),
                z3.Implies(z3.And(X[i], X[j]), z3.Or(pij, pji)),
            ]
    return enc
