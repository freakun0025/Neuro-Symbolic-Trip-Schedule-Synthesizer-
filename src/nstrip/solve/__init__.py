"""SOLVE (ARCHITECTURE §4.4): grounded problem -> SAT + plan | UNSAT + diagnosis | SOLVER_TIMEOUT."""

import z3

from nstrip.config import OPTIMISE_TIMEOUT_MS, SOLVER_TIMEOUT_MS
from nstrip.encode.compiler import compile_problem
from nstrip.models.constraints import ConstraintKind as K
from nstrip.models.constraints import parse_cid
from nstrip.models.plan import Diagnosis, Plan, Status
from nstrip.models.problem import ProblemInstance
from nstrip.solve.core import minimise_core
from nstrip.solve.relax import relax_all
from nstrip.solve.solver import make_solver, optimise_plan


def solve(p: ProblemInstance, timeout_ms: int = SOLVER_TIMEOUT_MS) -> tuple[Status, Plan | None, Diagnosis | None]:
    """Never guesses: a timeout is SOLVER_TIMEOUT, not SAT or UNSAT."""
    enc = compile_problem(p)
    r = make_solver(enc, timeout_ms).check(*enc.lits)
    if r == z3.sat:
        return Status.SAT, optimise_plan(enc, min(timeout_ms, OPTIMISE_TIMEOUT_MS)), None
    if r == z3.unknown:
        return Status.SOLVER_TIMEOUT, None, None
    core, raw_size, minimal, calls = minimise_core(enc, timeout_ms)
    return Status.UNSAT, None, Diagnosis(
        core=core, raw_core_size=raw_size, is_minimal=minimal,
        world_facts=[c for c in core if parse_cid(c)[0] in (K.OPENING, K.SHOWTIME)],
        relaxations=relax_all(enc, core, timeout_ms), solver_calls=calls,
    )
