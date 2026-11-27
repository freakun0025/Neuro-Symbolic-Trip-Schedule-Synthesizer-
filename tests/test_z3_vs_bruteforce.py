"""Z3 and an exhaustive solver that shares no code with it must agree on SAT/UNSAT and on the optimum
(most optional places, then lowest cost). This is what backs "encoding errors are testable compiler bugs"."""

import random

import pytest
from conftest import random_problem

from nstrip.bench.bruteforce import best_plan
from nstrip.checker.checker import check_plan
from nstrip.models.plan import Status
from nstrip.solve import solve


def objective(p, plan):
    optional = {a.id for a in p.activities if not a.must_visit}
    return sum(v.location_id in optional for v in plan.visits), plan.total_cost


@pytest.mark.parametrize("seed", range(120))
def test_agree(seed):
    rng = random.Random(1000 + seed)
    p = random_problem(rng, rng.randint(2, 6))
    status, plan, _ = solve(p)
    ref = best_plan(p)
    assert (status == Status.SAT) == (ref is not None)
    if ref is not None:
        assert check_plan(p, ref).ok  # the reference itself is right
        assert objective(p, plan) == objective(p, ref)


def test_proposal_example(proposal_problem):
    assert best_plan(proposal_problem) is None
