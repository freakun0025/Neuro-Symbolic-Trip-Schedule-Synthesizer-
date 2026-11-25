"""The codegen subprocess runner on canned programs (no LLM)."""

from nstrip.ablation.codegen import run_codegen, run_program
from nstrip.extract.llm_client import FakeClient
from nstrip.kb.loader import load_kb


def test_plan_unsat_crash_timeout_garbage():
    visits, outcome, err = run_program('import json; print(json.dumps([{"location_id": "a", "start": 600, '
                                       '"end": 660}]))')
    assert outcome == "SAT" and err is None and visits[0].start == 600
    assert run_program('print("thinking..."); print("UNSAT")')[1] == "UNSAT"
    _, outcome, err = run_program("raise ValueError('bad encoding')")
    assert outcome == "CRASH" and "bad encoding" in err
    assert run_program("while True: pass", timeout_s=1)[1:] == ("CRASH", "timeout after 1s")
    assert run_program('print("here is your plan")')[1] == "CRASH"


def test_z3_is_available_in_the_sandbox():
    code = "import z3\nx = z3.Int('x')\ns = z3.Solver()\ns.add(x > 2, x < 2)\nprint(s.check() == z3.unsat and 'UNSAT')"
    assert run_program(code)[1] == "UNSAT"


def test_runs_in_a_temp_dir_not_the_repo():
    visits, outcome, _ = run_program("import os, json; print(json.dumps([{'location_id': os.getcwd(), "
                                     "'start': 1, 'end': 2}]))")
    assert outcome == "SAT" and "Neuro-Symbolic" not in visits[0].location_id


def test_code_block_extracted_and_costed():
    kb = load_kb()
    reply = ("Here you go:\n```python\nimport json\n"
             "print(json.dumps([{'location_id': 'maxwell', 'start': 720, 'end': 765}]))\n```\nEnjoy!")
    plan, outcome, _ = run_codegen("lunch at Maxwell", kb, ["maxwell"], FakeClient([reply]))
    assert outcome == "SAT" and plan.total_cost == kb.places["maxwell"].cost
