"""The same request must give the same plan every time (stage 1 ties used to leave the order to chance)."""

import json

from nstrip.app.gradio_app import EXAMPLES
from nstrip.extract.extractor import ir_model
from nstrip.kb.loader import load_kb
from nstrip.pipeline import run_pipeline

KB = load_kb()
IR = ir_model(tuple(KB.ids))


def test_marina_bay_plan_is_identical_across_runs():
    ex = next(e for e in json.loads(EXAMPLES.read_text()) if e["title"].startswith("Marina Bay"))
    plans = {tuple(run_pipeline(None, KB, ir=IR.model_validate(ex["ir"])).plan.visits) for _ in range(4)}
    assert len(plans) == 1
