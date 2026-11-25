"""Metrics (PRD §10): run records -> summary.csv + tables.md. Counts come with Wilson 95% intervals;
with n = 50 we make no significance claims.

    python -m nstrip.bench.metrics results/<run_id> [results/<run_id> ...]
"""

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from nstrip.bench.generate import load_instances
from nstrip.ground import ground
from nstrip.kb.loader import KB
from nstrip.models.bench import BenchmarkInstance, RunRecord
from nstrip.models.constraints import canonical_tuples
from nstrip.models.ir import TripRequestIR
from nstrip.models.problem import ProblemInstance

SAT_CLAIMS = {"SAT", "BASELINE_SAT", "CODEGEN_SAT"}
UNSAT_CLAIMS = {"UNSAT", "BASELINE_UNSAT", "CODEGEN_UNSAT"}
NUMBER_KINDS = {"budget", "horizon_start", "horizon_end", "duration", "cost"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(k: int, n: int) -> str:
    if n == 0:
        return "n/a (0 cases)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} [95% CI {lo:.0%}-{hi:.0%}]"


# ---------------------------------------------------------------- extraction scoring

def score_extraction(gold: ProblemInstance, ir: TripRequestIR | None, kb: KB) -> tuple[dict, list[str]]:
    """Canonical tuples (after grounding) -> per-kind [tp, fp, fn] and the error classes of this instance."""
    g = canonical_tuples(gold)
    try:
        e = canonical_tuples(ground(ir, kb, "extracted")) if ir is not None and ir.activities else set()
    except ValueError:
        e = set()
    scores: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for t in g & e:
        scores[t[0]][0] += 1
    for t in e - g:
        scores[t[0]][1] += 1
    for t in g - e:
        scores[t[0]][2] += 1
    return dict(scores), classify(g, e, ir)


def classify(g: set[tuple], e: set[tuple], ir: TripRequestIR | None) -> list[str]:
    out: set[str] = set()
    ga = {t[1]: t[2] for t in g if t[0] == "activity"}
    ea = {t[1]: t[2] for t in e if t[0] == "activity"}
    if ga.keys() - ea.keys():
        out.add("missed_activity")
    if ea.keys() - ga.keys():
        out.add("extra_activity")
    if any(ga[i] != ea[i] for i in ga.keys() & ea.keys()):
        out.add("wrong_must_visit")
    common = ga.keys() & ea.keys()
    for t in g ^ e:
        kind = t[0]
        if kind in {"budget", "horizon_start", "horizon_end"} or (kind in {"duration", "cost"} and t[1] in common):
            out.add("wrong_number")
        elif kind == "window":
            out.add("wrong_window")
        elif kind == "origin":
            out.add("wrong_origin")
    gp = {t[1:] for t in g if t[0] == "precedence"}
    ep = {t[1:] for t in e if t[0] == "precedence"}
    for a, b in gp - ep:
        out.add("reversed_precedence" if (b, a) in ep else "missing_precedence")
    if any((b, a) not in gp for a, b in ep - gp):
        out.add("extra_precedence")
    if ir is not None and ir.unresolved_mentions:
        out.add("unresolved_place")
    if ir is None:
        out.add("no_ir")
    return sorted(out)


# ---------------------------------------------------------------- summary

def correct(rec: RunRecord, inst: BenchmarkInstance) -> bool:
    """End-to-end success: right SAT/UNSAT status and, if SAT, zero violations against gold."""
    if inst.expected_status == "UNSAT":
        return rec.status in UNSAT_CLAIMS
    return rec.status in SAT_CLAIMS and rec.check_vs_gold is not None and rec.check_vs_gold.ok


def summarize(records: list[RunRecord], instances: dict[str, BenchmarkInstance]) -> list[tuple[str, str, str]]:
    """-> rows (section, metric, value)."""
    rows: list[tuple[str, str, str]] = []

    def add(section: str, metric: str, value: object) -> None:
        rows.append((section, metric, str(value)))

    pairs = [(r, instances[r.instance_id]) for r in records if r.instance_id in instances]
    n = len(pairs)
    add("overview", "instances", n)
    add("overview", "statuses", dict(Counter(str(r.status) for r, _ in pairs)))
    add("overview", "end-to-end success", rate(sum(correct(r, i) for r, i in pairs), n))

    claimed = [(r, i) for r, i in pairs if r.status in SAT_CLAIMS]
    add("plans", "SAT-claimed plans violating gold",
        rate(sum(r.check_vs_gold is not None and not r.check_vs_gold.ok for r, _ in claimed), len(claimed)))
    solver_plans = [r for r, _ in claimed if r.status == "SAT"]
    if solver_plans:
        add("plans", "solver plans proven optimal (else greedy after timeout)",
            rate(sum(r.plan.optimal for r in solver_plans), len(solver_plans)))
    with_ext = [r for r, _ in claimed if r.check_vs_extracted is not None]
    if with_ext:
        add("plans", "plans violating their own extracted constraints (must be 0)",
            rate(sum(not r.check_vs_extracted.ok for r in with_ext), len(with_ext)))
    violation_kinds = Counter(v.kind for r, _ in claimed if r.check_vs_gold for v in r.check_vs_gold.violations)
    if violation_kinds:
        add("plans", "gold violation kinds", dict(violation_kinds))

    tp = sum(r.status in UNSAT_CLAIMS and i.expected_status == "UNSAT" for r, i in pairs)
    fp = sum(r.status in UNSAT_CLAIMS and i.expected_status == "SAT" for r, i in pairs)
    fn = sum(r.status not in UNSAT_CLAIMS and i.expected_status == "UNSAT" for r, i in pairs)
    add("infeasibility", "precision (UNSAT = positive)", rate(tp, tp + fp))
    add("infeasibility", "recall (UNSAT = positive)", rate(tp, tp + fn))

    diag = [(r, i) for r, i in pairs if r.diagnosis is not None and i.seeded_conflict]
    if diag:
        add("cores", "core equals the seeded conflict",
            rate(sum(set(r.diagnosis.core) == set(i.seeded_conflict) for r, i in diag), len(diag)))
        add("cores", "cores reported minimal", rate(sum(r.diagnosis.is_minimal for r, _ in diag), len(diag)))
    two = [(r, i) for r, i in pairs if r.diagnosis is not None and i.seeded_conflicts]
    if two:  # two seeded conflicts: the core must be one of them (both are minimal, neither is preferred)
        add("cores", "two-conflict instances: core is one of the seeded conflicts",
            rate(sum(set(r.diagnosis.core) in [set(c) for c in i.seeded_conflicts] for r, i in two), len(two)))
    sizes = [r.core_sizes for r, _ in pairs if r.core_sizes]
    if sizes:
        for key in ("raw", "minimal", "z3_minimize", "calls"):
            add("cores", f"mean {key} core size" if key != "calls" else "mean solver calls to minimise",
                f"{statistics.mean(s[key] for s in sizes):.2f}")

    scored = [r for r, _ in pairs if r.extraction_scores is not None]
    if scored:
        total: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for r in scored:
            for kind, (a, b, c) in r.extraction_scores.items():
                total[kind][0] += a
                total[kind][1] += b
                total[kind][2] += c
        for kind, (a, b, c) in sorted(total.items()) + [("ALL", [sum(x[k] for x in total.values())
                                                                 for k in range(3)])]:
            p = a / (a + b) if a + b else 1.0
            rc = a / (a + c) if a + c else 1.0
            f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
            add("extraction", f"{kind} P/R/F1", f"{p:.2f} / {rc:.2f} / {f1:.2f} (tp {a}, fp {b}, fn {c})")
        exact = sum(not any(v[1] or v[2] for v in r.extraction_scores.values()) for r in scored)
        add("extraction", "instances extracted exactly", rate(exact, len(scored)))
        classes = Counter(c for r in scored for c in (r.error_classes or []))
        harmful = Counter(c for r, i in pairs if r.extraction_scores is not None and not correct(r, i)
                          for c in (r.error_classes or []))
        for c, k in classes.most_common():
            add("error taxonomy", c, f"{k} instances, {harmful[c]} with a wrong final answer")

    verified = [(r, i) for r, i in pairs if r.verify_changes is not None]
    if verified:
        changed = [(r, i) for r, i in verified if r.verify_changes]
        add("verification", "UNSAT answers re-checked by the LLM", str(len(verified)))
        add("verification", "forms the LLM changed", rate(len(changed), len(verified)))
        add("verification", "false UNSAT corrected (expected SAT, now SAT)",
            rate(sum(i.expected_status == "SAT" and correct(r, i) for r, i in changed),
                 sum(i.expected_status == "SAT" for _, i in verified)))
        add("verification", "real conflicts erased (expected UNSAT, now not UNSAT; must be 0)",
            rate(sum(i.expected_status == "UNSAT" and r.status not in UNSAT_CLAIMS for r, i in changed),
                 sum(i.expected_status == "UNSAT" for _, i in verified)))

    if any(str(r.status).startswith("CODEGEN") for r, _ in pairs):
        add("codegen", "programs that crashed / timed out / printed garbage",
            rate(sum(r.status == "CODEGEN_CRASH" for r, _ in pairs), n))

    by_n: dict[int, list[float]] = defaultdict(list)
    for r, i in pairs:
        if "solve" in r.timings_ms:
            by_n[i.n_locations].append(r.timings_ms["solve"])
    for k in sorted(by_n):
        v = by_n[k]
        add("runtime (solve ms)", f"n={k}", f"mean {statistics.mean(v):.0f}, median {statistics.median(v):.0f}")
    ext = [r.timings_ms["extract"] for r, _ in pairs if "extract" in r.timings_ms]
    if ext:
        add("runtime (extract ms)", "all", f"mean {statistics.mean(ext):.0f}, median {statistics.median(ext):.0f}")
    return rows


def load_run(run_dir: Path) -> tuple[dict, list[RunRecord]]:
    config = json.loads((run_dir / "config.json").read_text())
    records = [RunRecord.model_validate_json(line) for line in (run_dir / "records.jsonl").read_text().splitlines()
               if line.strip()]
    return config, records


def write_tables(run_dir: Path) -> str:
    config, records = load_run(run_dir)
    instances = {i.id: i for i in load_instances(config["set"])}
    rows = summarize(records, instances)
    with (run_dir / "summary.csv").open("w", newline="") as f:
        csv.writer(f).writerows([("section", "metric", "value"), *rows])
    md = [f"# {config['method']} on the {config['set']} set", "",
          (f"model `{config.get('model')}` at `{config.get('base_url')}`, KB {config.get('kb_version')}, "
           f"run {config.get('run_id')}"), ""]
    section = None
    for s, metric, value in rows:
        if s != section:
            md += ["", f"## {s}", "", "| metric | value |", "|---|---|"]
            section = s
        md.append(f"| {metric} | {value} |")
    text = "\n".join(md) + "\n"
    (run_dir / "tables.md").write_text(text)
    return text


COMPARE = [("overview", "end-to-end success", "end-to-end success"),
           ("plans", "SAT-claimed plans violating gold", "claimed plans violating gold"),
           ("infeasibility", "precision (UNSAT = positive)", "UNSAT precision"),
           ("infeasibility", "recall (UNSAT = positive)", "UNSAT recall"),
           ("cores", "core equals the seeded conflict", "core = seeded conflict"),
           ("cores", "two-conflict instances: core is one of the seeded conflicts", "core one of two seeded"),
           ("extraction", "instances extracted exactly", "extracted exactly"),
           ("codegen", "programs that crashed / timed out / printed garbage", "programs crashed")]
ORDER = {"oracle": 0, "pipeline": 1, "pipeline_verify": 2, "codegen": 3, "baseline": 4}


def compare(which: str = "generated", root: Path | None = None) -> str:
    """One row per run of `which` (oracle / pipeline / codegen / baseline, every model): results/comparison_<set>.md."""
    root = root or Path(__file__).resolve().parents[3] / "results"
    runs = []
    for d in sorted(root.glob(f"*_{which}_*")):
        if not (d / "summary.csv").exists():
            continue
        config = json.loads((d / "config.json").read_text())
        with (d / "summary.csv").open() as f:
            vals = {(r["section"], r["metric"]): r["value"] for r in csv.DictReader(f)}
        runs.append((ORDER.get(config["method"], 9), config, vals, d.name))
    head = ["method", "model", *(c[2] for c in COMPARE)]
    note = ("Rates are counts with Wilson 95% intervals; '-' = not applicable. Each run's full tables are in "
            "results/<run>/tables.md.")
    md = [f"# Comparison on the {which} set", "", note, "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, config, vals, name in sorted(runs, key=lambda r: (r[0], r[3])):
        cells = [f"[{config['method']}]({name}/tables.md)", f"`{config.get('model') or 'none (gold IR)'}`"]
        cells += [vals.get((s, m), "-").replace(" [95% CI ", "<br>[") for s, m, _ in COMPARE]
        md.append("| " + " | ".join(cells) + " |")
    text = "\n".join(md) + "\n"
    (root / f"comparison_{which}.md").write_text(text)
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path, help="run folders to re-tabulate")
    ap.add_argument("--compare", choices=["generated", "heldout"], help="write results/comparison_<set>.md")
    args = ap.parse_args()
    for run_dir in args.runs:
        print(write_tables(run_dir))
    if args.compare:
        print(compare(args.compare))


if __name__ == "__main__":
    main()
