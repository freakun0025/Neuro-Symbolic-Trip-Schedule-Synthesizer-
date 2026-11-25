"""Deletion-based unsat-core minimisation (ARCHITECTURE §4.6).

Drop each member in turn and re-check. If the rest is still UNSAT the member was not needed, and the core
shrinks to the new (smaller) core Z3 returns. If the rest is SAT the member is necessary, and it stays
necessary as the core shrinks further (a subset of a satisfiable set is satisfiable). The result is
*minimal* (irreducible), not necessarily *minimum*. Cost: at most |core| + 1 solver calls.
"""

import z3

from nstrip.config import SOLVER_TIMEOUT_MS
from nstrip.encode.compiler import Encoding
from nstrip.solve.solver import make_solver


def minimise_core(enc: Encoding, timeout_ms: int = SOLVER_TIMEOUT_MS) -> tuple[list[str], int, bool, int]:
    """-> (minimal core as cids, raw core size, is_minimal, solver calls). is_minimal is False only if a
    re-check timed out, in which case that member is kept to be safe."""
    lit = {t.cid: t.lit for t in enc.tracked.values()}
    s = make_solver(enc, timeout_ms)
    if s.check(*lit.values()) != z3.unsat:
        raise ValueError("minimise_core needs an UNSAT encoding")
    core = [c.decl().name() for c in s.unsat_core()]
    raw_size, minimal, calls = len(core), True, 1
    for c in list(core):
        if c not in core:  # already removed by an earlier shrink
            continue
        rest = [x for x in core if x != c]
        r = s.check(*[lit[x] for x in rest])
        calls += 1
        if r == z3.unsat:
            shrunk = {x.decl().name() for x in s.unsat_core()}
            core = [x for x in rest if x in shrunk]
        elif r == z3.unknown:
            minimal = False
    return core, raw_size, minimal, calls
