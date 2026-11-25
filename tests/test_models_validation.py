import json

import pytest
from pydantic import ValidationError

from nstrip.models.constraints import ConstraintKind, canonical_tuples, cid, parse_cid
from nstrip.models.ir import make_ir_model
from nstrip.models.problem import ProblemInstance

IR = make_ir_model(["museum", "park", "cafe"])


def ir(**overrides):
    data = {"activities": [{"location_id": "museum", "must_visit": True},
                           {"location_id": "cafe", "must_visit": False}]} | overrides
    return IR.model_validate(data)


def test_valid_ir_parses_from_json():
    got = IR.model_validate_json('{"budget": 30, "activities": [{"location_id": "park", "must_visit": true}]}')
    assert got.budget == 30 and got.activities[0].location_id == "park"


def test_schema_lists_the_kb_ids():
    assert '"enum": ["museum", "park", "cafe"]' in json.dumps(IR.model_json_schema())


@pytest.mark.parametrize("bad", [
    {"activities": [{"location_id": "zoo", "must_visit": True}]},  # not in the KB
    {"precedences": [{"before": "museum", "after": "park"}]},  # park is not an activity
    {"precedences": [{"before": "museum", "after": "museum"}]},
    {"activities": [{"location_id": "park", "must_visit": True}, {"location_id": "park", "must_visit": False}]},
    {"day_start": "9:00"}, {"day_start": "24:00"},
    {"day_start": "18:00", "day_end": "09:00"},
    {"activities": [{"location_id": "park", "must_visit": True, "earliest_start": "15:00", "latest_end": "14:00"}]},
    {"return_to_start": True},
    {"budget": -5},
    {"surprise_field": 1},
])
def test_invalid_ir_rejected(bad):
    with pytest.raises(ValidationError):
        ir(**bad)


def test_budget_decimals_round_down():
    assert ir(budget=30.9).budget == 30


def test_problem_needs_every_transit_pair(proposal_problem):
    data = proposal_problem.model_dump()
    del data["transit"]["park"]["cafe"]
    with pytest.raises(ValidationError, match="park -> cafe"):
        ProblemInstance.model_validate(data)


def test_cid_round_trip():
    s = cid(ConstraintKind.PRECEDENCE, "museum", "cafe")
    assert s == "precedence:museum:cafe"
    assert parse_cid(s) == (ConstraintKind.PRECEDENCE, ("museum", "cafe"))


def test_canonical_tuples(proposal_problem):
    t = canonical_tuples(proposal_problem)
    assert {("budget", 30), ("horizon_end", 780), ("activity", "cafe", True),
            ("precedence", "museum", "cafe"), ("cost", "museum", 20)} <= t
    assert not any(x[0] == "window" for x in t)
