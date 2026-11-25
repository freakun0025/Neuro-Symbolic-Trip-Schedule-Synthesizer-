"""Evaluation runner (ARCHITECTURE §8): one RunRecord per instance -> results/<run_id>/records.jsonl.

    python -m nstrip.bench.run --method oracle   --set generated
    python -m nstrip.bench.run --method pipeline --set generated [--model ...] [--limit 5]
    python -m nstrip.bench.run --method baseline --set generated --model <strongest>
    python -m nstrip.bench.run --method codegen  --set generated
Then: python -m nstrip.bench.metrics results/<run_id>
"""

import argparse
import datetime
import json
import re
import subprocess
import time
from pathlib import Path

from nstrip.bench.generate import load_instances
from nstrip.bench.metrics import score_extraction, write_tables
from nstrip.checker.checker import check_plan
from nstrip.encode.compiler import compile_problem
from nstrip.extract.llm_client import make_client
from nstrip.ground import ground
from nstrip.kb.loader import KB, load_kb
from nstrip.models.bench import BenchmarkInstance, RunRecord
from nstrip.models.plan import Plan
from nstrip.pipeline import run_pipeline
from nstrip.solve import solve
from nstrip.solve.solver import make_solver

RESULTS = Path(__file__).resolve().parents[3] / "results"


def z3_minimized_core_size(p) -> int:
    enc = compile_problem(p)
    s = make_solver(enc)
    s.set("core.minimize", True)
    s.check(*enc.lits)
    return len(s.unsat_core())


def run_one(method: str, inst: BenchmarkInstance, kb: KB, client, run_id: str) -> RunRecord:
    gold = ground(inst.gold_ir, kb, "gold")
    base = {"run_id": run_id, "instance_id": inst.id, "method": method,
            "base_url": getattr(client, "base_url", "none"), "model": getattr(client, "model", "none")}
    ids = [a.location_id for a in inst.gold_ir.activities] + \
        ([inst.gold_ir.start_location] if inst.gold_ir.start_location else [])
    ids = list(dict.fromkeys(ids))
    t0 = time.perf_counter()

    if method == "oracle":
        status, plan, diag = solve(gold)
        timings = {"solve": round((time.perf_counter() - t0) * 1000, 2)}
        sizes = None
        if diag is not None:
            sizes = {"raw": diag.raw_core_size, "minimal": len(diag.core), "calls": diag.solver_calls,
                     "z3_minimize": z3_minimized_core_size(gold)}
        return RunRecord(**base, status=status, plan=plan, diagnosis=diag, core_sizes=sizes, timings_ms=timings,
                         check_vs_gold=check_plan(gold, plan) if plan else None)

    if method in ("pipeline", "pipeline_verify"):  # _verify: optional solver -> LLM feedback round on UNSAT
        r = run_pipeline(inst.request_text, kb, client, verify_client=client if method == "pipeline_verify" else None)
        scores, classes = score_extraction(gold, r.ir, kb)
        return RunRecord(**base, status=r.status, extracted_ir=r.ir, plan=r.plan, diagnosis=r.diagnosis,
                         check_vs_gold=check_plan(gold, r.plan) if r.plan else None,
                         check_vs_extracted=check_plan(r.problem, r.plan) if r.plan else None,
                         extraction_scores=scores, error_classes=classes, error=r.error, timings_ms=r.timings_ms,
                         verify_changes=r.verify_changes)

    if method == "baseline":
        from nstrip.baseline.pure_llm import plan_with_llm
        try:
            ans = plan_with_llm(inst.request_text, kb, ids, client)
        except Exception as e:  # noqa: BLE001  record the failure, keep going
            return RunRecord(**base, status="BASELINE_FAILED", error=str(e))
        plan = Plan(visits=ans.visits, total_cost=sum(kb.places[v.location_id].cost for v in ans.visits
                                                      if v.location_id in kb.places)) if ans.feasible else None
        return RunRecord(**base, status="BASELINE_SAT" if ans.feasible else "BASELINE_UNSAT", plan=plan,
                         check_vs_gold=check_plan(gold, plan) if plan else None, error=ans.reason,
                         timings_ms={"llm": round((time.perf_counter() - t0) * 1000, 2)})

    if method == "codegen":
        from nstrip.ablation.codegen import run_codegen
        plan, outcome, err = run_codegen(inst.request_text, kb, ids, client)
        return RunRecord(**base, status=f"CODEGEN_{outcome}", plan=plan, codegen_stderr=err,
                         check_vs_gold=check_plan(gold, plan) if plan else None,
                         timings_ms={"llm_and_run": round((time.perf_counter() - t0) * 1000, 2)})
    raise ValueError(f"unknown method {method!r}")


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run(method: str, which: str, model: str | None = None, limit: int | None = None, role: str | None = None,
        out: Path = RESULTS) -> Path:
    kb = load_kb()
    role = role or {"pipeline": "extract", "pipeline_verify": "extract", "baseline": "baseline",
                    "codegen": "codegen"}.get(method)
    client = make_client(role, model=model) if role else None
    slug = re.sub(r"[^A-Za-z0-9.-]+", "-", client.model if client else "z3")
    run_id = f"{datetime.date.today()}_{method}_{which}_{slug}"
    run_dir = out / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    instances = load_instances(which)[:limit]
    (run_dir / "config.json").write_text(json.dumps({
        "run_id": run_id, "method": method, "set": which, "model": client.model if client else None,
        "base_url": client.base_url if client else None, "kb_version": kb.version, "git_sha": git_sha(),
        "instances": len(instances)}, indent=1))
    # One write at the end: synced folders (OneDrive) time out on many small flushes, and a crashed run loses
    # nothing because every LLM call is in the disk cache, so re-running replays it.
    lines = []
    for n, inst in enumerate(instances, 1):
        rec = run_one(method, inst, kb, client, run_id)
        lines.append(rec.model_dump_json() + "\n")
        print(f"[{n}/{len(instances)}] {inst.id} expected {inst.expected_status:5} got {rec.status}", flush=True)
    (run_dir / "records.jsonl").write_text("".join(lines))
    write_tables(run_dir)
    return run_dir


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", required=True, choices=["oracle", "pipeline", "pipeline_verify", "baseline", "codegen"])
    ap.add_argument("--set", default="generated", choices=["generated", "heldout"])
    ap.add_argument("--model", help="override the role's model name (same provider)")
    ap.add_argument("--role", choices=["extract", "baseline", "codegen"],
                    help="use another role's provider and model, e.g. baseline with the extraction model")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    run_dir = run(args.method, args.set, args.model, args.limit, role=args.role if args.method != "oracle" else None)
    print(f"\nwrote {run_dir}/records.jsonl, summary.csv, tables.md")


if __name__ == "__main__":
    main()
