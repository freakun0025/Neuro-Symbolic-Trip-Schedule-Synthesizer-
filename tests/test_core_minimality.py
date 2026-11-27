"""On random problems: every UNSAT core is UNSAT and irreducible, and every SAT plan passes the checker."""

import random

import pytest
import z3
from conftest import random_problem

from nstrip.checker.checker import check_plan
from nstrip.encode.compiler import compile_problem
from nstrip.models.plan import Status
from nstrip.solve import solve
from nstrip.solve.solver import make_solver


def is_unsat(p, cids) -> bool:
    enc = compile_problem(p)
    return make_solver(enc).check(*[enc.tracked[c].lit for c in cids]) == z3.unsat


@pytest.mark.parametrize("seed", range(60))
def test_random_problem(seed):
    rng = random.Random(seed)
    p = random_problem(rng, rng.randint(2, 6))
    status, plan, diag = solve(p)
    if status == Status.SAT:
        assert check_plan(p, plan).ok, check_plan(p, plan).violations
        return
    assert status == Status.UNSAT and diag.is_minimal
    assert diag.raw_core_size >= len(diag.core) >= 1
    assert is_unsat(p, diag.core)
    for c in diag.core:  # minimality, re-verified independently of minimise_core
        assert not is_unsat(p, [x for x in diag.core if x != c]), f"{c} is not needed in {diag.core}"


def test_random_problems_cover_both_outcomes():
    outcomes = {solve(random_problem(random.Random(s), random.Random(s).randint(2, 6)))[0] for s in range(60)}
    assert outcomes == {Status.SAT, Status.UNSAT}
