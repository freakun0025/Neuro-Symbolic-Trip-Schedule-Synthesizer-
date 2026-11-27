"""Every committed benchmark label is backed by construction: a witness the checker accepts (SAT), or a seeded
conflict that is the instance's only conflict (UNSAT)."""

from collections import Counter

import pytest

from nstrip.bench.generate import TWO_CONFLICTS, generate, load_instances, only_conflict, only_two_conflicts
from nstrip.checker.checker import check_plan
from nstrip.ground import ground
from nstrip.kb.loader import load_kb

KB = load_kb()
ALL = load_instances()
INSTANCES = [i for i in ALL if i.conflict_type != "two_conflicts"]  # the proposal's 50
TWO = [i for i in ALL if i.conflict_type == "two_conflicts"]


def test_shape():
    assert len(INSTANCES) == 50 and len(TWO) == len(TWO_CONFLICTS)
    assert Counter(i.expected_status for i in INSTANCES) == {"SAT": 30, "UNSAT": 20}
    assert Counter(i.n_locations for i in INSTANCES) == {n: 5 for n in range(3, 13)}
    assert sorted(Counter(i.conflict_type for i in INSTANCES if i.conflict_type).values()) == [3, 3, 3, 3, 4, 4]
    assert sum(any(KB.places[a.location_id].showtimes for a in i.gold_ir.activities) for i in INSTANCES) >= 50 // 3
    assert {i.kb_version for i in INSTANCES} == {KB.version}  # regenerate if the KB changes


@pytest.mark.parametrize("inst", ALL, ids=lambda i: i.id)
def test_label(inst):
    p = ground(inst.gold_ir, KB, "gold")
    if inst.conflict_type == "two_conflicts":
        assert inst.expected_status == "UNSAT" and only_two_conflicts(p, *inst.seeded_conflicts)
    elif inst.expected_status == "SAT":
        assert inst.witness_plan is not None and check_plan(p, inst.witness_plan).ok
    else:
        assert inst.witness_plan is None and only_conflict(p, inst.seeded_conflict)


@pytest.mark.parametrize("inst", load_instances("heldout"), ids=lambda i: i.id)
def test_heldout_label(inst):
    from nstrip.models.plan import Status
    from nstrip.solve import solve
    p = ground(inst.gold_ir, KB, "gold")
    assert inst.set == "heldout" and inst.reviewed_by
    if inst.expected_status == "SAT":
        assert inst.witness_plan is not None and check_plan(p, inst.witness_plan).ok
    else:
        assert inst.conflict_note, "UNSAT needs a one-line arithmetic argument"
        assert solve(p)[0] == Status.UNSAT


def test_heldout_template_is_valid():
    import json
    from pathlib import Path

    from nstrip.models.bench import BenchmarkInstance
    raw = json.loads((Path(__file__).parents[1] / "data/benchmark/heldout/TEMPLATE.json.example").read_text())
    inst = BenchmarkInstance.model_validate(raw)
    assert check_plan(ground(inst.gold_ir, KB, "gold"), inst.witness_plan).ok


def test_generator_is_deterministic():
    a, b = generate(7, limit=4), generate(7, limit=4)
    assert [x.model_dump() for x in a] == [x.model_dump() for x in b]
