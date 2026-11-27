"""run_one for every method with scripted clients, plus metrics helpers."""

import json

import pytest

from nstrip.bench.generate import load_instances
from nstrip.bench.metrics import classify, score_extraction, summarize, wilson
from nstrip.bench.run import run_one
from nstrip.extract.llm_client import FakeClient
from nstrip.ground import ground
from nstrip.kb.loader import load_kb
from nstrip.models import to_hhmm

KB = load_kb()
INST = {i.id: i for i in load_instances()}
SAT = next(i for i in INST.values() if i.expected_status == "SAT")
UNSAT = next(i for i in INST.values() if i.conflict_type == "budget")


def gold_json(inst):
    return inst.gold_ir.model_dump_json()


def test_oracle_records_core_sizes():
    rec = run_one("oracle", UNSAT, KB, None, "t")
    assert rec.status == "UNSAT" and set(rec.diagnosis.core) == set(UNSAT.seeded_conflict)
    assert rec.core_sizes["minimal"] == len(UNSAT.seeded_conflict) and rec.core_sizes["z3_minimize"] >= 1


def test_pipeline_with_perfect_extraction_scores_exactly():
    rec = run_one("pipeline", SAT, KB, FakeClient([gold_json(SAT)]), "t")
    assert rec.status == "SAT" and rec.check_vs_gold.ok and rec.check_vs_extracted.ok
    assert all(fp == fn == 0 for _, fp, fn in rec.extraction_scores.values()) and rec.error_classes == []


def test_pipeline_with_a_dropped_precedence_is_classified():
    inst = next(i for i in INST.values() if i.gold_ir.precedences and i.expected_status == "SAT")
    wrong = inst.gold_ir.model_copy(update={"precedences": []})
    rec = run_one("pipeline", inst, KB, FakeClient([wrong.model_dump_json()]), "t")
    assert "missing_precedence" in rec.error_classes and rec.extraction_scores["precedence"][2] == 1


def test_baseline_plan_is_checked_against_gold():
    w = SAT.witness_plan
    answer = {"feasible": True, "reason": "ok",
              "visits": [{"location_id": v.location_id, "start": to_hhmm(v.start), "end": to_hhmm(v.end)}
                         for v in w.visits]}
    rec = run_one("baseline", SAT, KB, FakeClient([json.dumps(answer)]), "t")
    assert rec.status == "BASELINE_SAT" and rec.check_vs_gold.ok
    rec = run_one("baseline", UNSAT, KB, FakeClient([json.dumps(answer | {"visits": [], "feasible": False})]), "t")
    assert rec.status == "BASELINE_UNSAT"
    assert run_one("baseline", SAT, KB, FakeClient(["no"] * 3), "t").status == "BASELINE_FAILED"


def test_codegen_crash_is_recorded():
    rec = run_one("codegen", SAT, KB, FakeClient(["```python\nimport z3\nundefined_name\n```"]), "t")
    assert rec.status == "CODEGEN_CRASH" and "NameError" in rec.codegen_stderr


def test_summary_rows():
    records = [run_one("oracle", i, KB, None, "t") for i in (SAT, UNSAT)]
    rows = {(s, m): v for s, m, v in summarize(records, INST)}
    assert rows[("overview", "end-to-end success")].startswith("2/2")
    assert rows[("cores", "core equals the seeded conflict")].startswith("1/1")


def test_wilson():
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(18, 20)
    assert lo == pytest.approx(0.699, abs=0.005) and hi == pytest.approx(0.972, abs=0.005)


def test_classify_reversed_precedence_and_numbers():
    g = {("activity", "a", True), ("activity", "b", True), ("precedence", "a", "b"), ("budget", 30)}
    e = {("activity", "a", True), ("activity", "b", False), ("precedence", "b", "a"), ("budget", 3)}
    assert classify(g, e, None) == ["no_ir", "reversed_precedence", "wrong_must_visit", "wrong_number"]


def test_score_with_no_ir_counts_everything_missed():
    gold = ground(SAT.gold_ir, KB, "gold")
    scores, classes = score_extraction(gold, None, KB)
    assert all(tp == 0 and fn > 0 for tp, _, fn in scores.values()) and "no_ir" in classes


def test_compare_puts_one_row_per_run(tmp_path):
    import json

    from nstrip.bench.metrics import compare
    for name, method, value in [("d_pipeline_generated_m", "pipeline", "9/10 = 90%"),
                                ("d_oracle_generated_z3", "oracle", "10/10 = 100%")]:
        (tmp_path / name).mkdir()
        (tmp_path / name / "config.json").write_text(json.dumps({"method": method, "model": None}))
        (tmp_path / name / "summary.csv").write_text(
            f"section,metric,value\noverview,end-to-end success,{value} [95% CI 1%-2%]\n")
    lines = compare("generated", tmp_path).splitlines()
    rows = [x for x in lines if x.startswith("| [")]
    assert len(rows) == 2 and "oracle" in rows[0] and "9/10 = 90%<br>[1%-2%]" in rows[1]
