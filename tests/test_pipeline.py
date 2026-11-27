import json

from nstrip.extract.llm_client import FakeClient
from nstrip.kb.loader import load_kb
from nstrip.models.ir import TripRequestIR
from nstrip.models.plan import Plan, Status, Visit
from nstrip.pipeline import run_pipeline

PROPOSAL = {"budget": 30, "duration_limit_min": 240,
            "activities": [{"location_id": i, "must_visit": True} for i in ("museum", "park", "cafe")],
            "precedences": [{"before": "museum", "after": "cafe"}]}


def test_proposal_request_end_to_end(tiny_kb):
    r = run_pipeline("I have 4 hours and $30 ...", tiny_kb, FakeClient([json.dumps(PROPOSAL)]))
    assert r.status == Status.UNSAT and r.llm_attempts == 1
    assert set(r.diagnosis.core) == {"budget", "must_visit:museum", "must_visit:cafe"}
    assert "raise the budget from $30 to $35" in r.explanation and "make Café optional" in r.explanation
    assert "budget: 20·X_museum + 0·X_park + 15·X_cafe ≤ 30" in r.constraints_readable
    assert "(declare-fun X_museum () Bool)" in r.smtlib
    assert r.problem.assumed_defaults == ["day start assumed 09:00"]


def test_edited_ir_skips_the_llm(tiny_kb):
    ir = TripRequestIR.model_validate(PROPOSAL | {"budget": 35})
    r = run_pipeline(None, tiny_kb, ir=ir)
    assert r.status == Status.SAT and r.plan.total_cost == 35 and r.llm_attempts == 0
    # least sum of starts: Park first, then Museum, then Café (Museum before Café holds)
    assert "09:00-10:00  Park ($0)\n  10:00-12:00  Museum ($20)\n  12:00-13:00  Café ($15)" in r.explanation


def test_unknown_place_needs_clarification():
    kb = load_kb()
    ir = {"activities": [{"location_id": "national_museum", "must_visit": True}],
          "unresolved_mentions": ["Gardens by the bey"]}
    r = run_pipeline("...", kb, FakeClient([json.dumps(ir)]))
    assert r.status == Status.NEEDS_CLARIFICATION and r.plan is None
    assert "Gardens by the bey" in r.explanation and "did you mean" in r.explanation


def test_extraction_failure_and_unreachable_llm(tiny_kb):
    assert run_pipeline("x", tiny_kb, FakeClient(["nope"] * 4)).status == Status.EXTRACTION_FAILED

    def down(_):
        raise ConnectionError("no network")
    r = run_pipeline("x", tiny_kb, FakeClient([down]))
    assert r.status == Status.EXTRACTION_FAILED and "ConnectionError" in r.error


def test_checker_disagreement_is_internal_error(tiny_kb, monkeypatch):
    bad = Plan(visits=[Visit(location_id="museum", start=540, end=600)], total_cost=20)  # 60 min, needs 120
    monkeypatch.setattr("nstrip.pipeline.solve", lambda p, t: (Status.SAT, bad, None))
    r = run_pipeline(None, tiny_kb, ir=TripRequestIR.model_validate(PROPOSAL | {"budget": 100}))
    assert r.status == Status.INTERNAL_ERROR and r.plan is None and "lasts 60 min" in r.error


def test_guarded_rephrase(tiny_kb):
    ir = TripRequestIR.model_validate(PROPOSAL)
    r = run_pipeline(None, tiny_kb, ir=ir, rephrase_client=FakeClient(["Sorry, can't help."]))
    assert r.explanation_source == "template"


def test_verification_fixes_a_misread_must_visit(tiny_kb):
    # the request says the café is optional; extraction marked it required, which caused the conflict
    cafe_optional = json.loads(json.dumps(PROPOSAL))
    cafe_optional["activities"][2]["must_visit"] = False
    seen = []
    verifier = FakeClient([lambda m: seen.append(m[-1]["content"]) or json.dumps(cafe_optional)])
    r = run_pipeline("4 hours, $30: museum, park, and the café if there is time", tiny_kb,
                     FakeClient([json.dumps(PROPOSAL)]), verify_client=verifier)
    assert r.status == Status.SAT and r.llm_attempts == 2
    assert r.verify_changes == ["activities[2].must_visit: True -> False"]
    assert "corrected" in r.explanation
    assert "you must visit Café\n" in seen[0] and "$15" not in seen[0]  # user requirements only, no KB facts


def test_verification_keeps_a_real_conflict(tiny_kb):
    r = run_pipeline("4 hours, $30: museum, park and café, all required", tiny_kb,
                     FakeClient([json.dumps(PROPOSAL)]), verify_client=FakeClient([json.dumps(PROPOSAL)]))
    assert r.status == Status.UNSAT and r.verify_changes == [] and r.llm_attempts == 2
