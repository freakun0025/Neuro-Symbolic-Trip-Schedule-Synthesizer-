"""Solver-only scaling sweep (PRD §10 runtime, RISKS R25): random Singapore problems with n = 3..30 places,
with and without shows (whose showtimes add disjunctions). No LLM.

    python -m nstrip.bench.stress
"""

import argparse
import random
import statistics
import time

from nstrip.bench.run import RESULTS
from nstrip.ground import ground
from nstrip.kb.loader import load_kb
from nstrip.models.ir import TripRequestIR
from nstrip.models.plan import Status
from nstrip.solve import solve


def problem(rng: random.Random, kb, n: int, shows: bool):
    show_ids = [i for i, p in kb.places.items() if p.showtimes]
    rest = [i for i in kb.ids if i not in show_ids]
    ids = (rng.sample(show_ids, min(2, n)) if shows else []) + rng.sample(rest, n - (min(2, n) if shows else 0))
    must = set(rng.sample(ids, max(1, n // 4)))
    ir = TripRequestIR.model_validate({
        "day_start": "09:00", "day_end": "23:30", "budget": rng.choice([None, 150, 300]),
        "activities": [{"location_id": i, "must_visit": i in must} for i in ids]})
    return ground(ir, kb, "gold")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="3,6,9,12,15,20,25,30")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--seed", type=int, default=851)
    args = ap.parse_args()
    kb, rng = load_kb(), random.Random(args.seed)
    rows = ["| n | shows | median solve ms | max ms | SAT / UNSAT / timeout | proven optimal |", "|---|---|---|---|---|---|"]
    for n in map(int, args.sizes.split(",")):
        for shows in (False, True):
            times, statuses, optimal = [], [], 0
            for _ in range(args.reps):
                p = problem(rng, kb, n, shows)
                t0 = time.perf_counter()
                status, plan, _ = solve(p)
                times.append((time.perf_counter() - t0) * 1000)
                statuses.append(status)
                optimal += bool(plan and plan.optimal)
            counts = "/".join(str(statuses.count(s)) for s in (Status.SAT, Status.UNSAT, Status.SOLVER_TIMEOUT))
            rows.append(f"| {n} | {'yes' if shows else 'no'} | {statistics.median(times):.0f} | {max(times):.0f} | "
                        f"{counts} | {optimal}/{statuses.count(Status.SAT)} |")
            print(rows[-1], flush=True)
    out = RESULTS / "stress.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("# Solver scaling (no LLM)\n\n" + "\n".join(rows) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
