"""Benchmark generator (ARCHITECTURE §7).

Labels come from construction, never from Z3:
- SAT: a witness schedule is built first and the request is written around it; the checker must accept it.
- UNSAT: a SAT instance gets exactly one seeded conflict that is infeasible by arithmetic.
Z3 only cross-checks. It must agree, the seeded set alone must be UNSAT, and dropping any seeded member from
the full instance must make it SAT, so the seeded conflict is the only one (its unique minimal core).

    python -m nstrip.bench.generate --seed 851
"""

import argparse
import json
import random
from pathlib import Path

import z3

from nstrip.checker.checker import check_plan
from nstrip.encode.compiler import compile_problem
from nstrip.ground import ground
from nstrip.kb.loader import KB, load_kb
from nstrip.models import to_hhmm
from nstrip.models.bench import BenchmarkInstance
from nstrip.models.ir import TripRequestIR
from nstrip.models.plan import Plan, Status, Visit
from nstrip.solve import solve
from nstrip.solve.solver import make_solver

BENCH_DIR = Path(__file__).resolve().parents[3] / "data" / "benchmark"
CONFLICTS = ["budget", "horizon", "window", "precedence_window", "precedence_cycle", "showtime_clash"]
LAST = 23 * 60 + 55  # latest time an IR can name ("HH:MM" stops at 23:59)
# Five extra UNSAT instances with two independent conflicts (inst_051..055). Without them "core == seeded
# conflict" would hold by construction, since every other instance has exactly one conflict.
TWO_CONFLICTS = [("budget", "window"), ("window", "precedence_cycle"), ("budget", "precedence_cycle"),
                 ("horizon", "window"), ("horizon", "precedence_cycle")]
ORIGINS = ["orchard_road", "merlion_park", "maxwell", "national_museum", "clarke_quay"]


def r5(m: int, up: bool = False) -> int:
    return (m + 4) // 5 * 5 if up else m // 5 * 5


# ---------------------------------------------------------------- SAT: witness first

def witness(rng: random.Random, kb: KB, ids: list[str], start: int, origin: str | None, back: bool,
            durations: dict[str, int]) -> list[Visit] | None:
    """Greedy day through a random order of the places, skipping what does not fit."""
    target = rng.randint(2, min(5, len(ids)))
    visits: list[Visit] = []
    t, prev = start, origin
    for i in rng.sample(ids, len(ids)):
        if len(visits) == target:
            break
        p = kb.places[i]
        s = max(t + (kb.transit[prev][i] if prev else 0), p.open)
        if p.showtimes:
            later = [x for x in p.showtimes if x >= s]
            if not later:
                continue
            s = later[0]
        e = s + durations[i]
        if e > p.close or e + (kb.transit[i][origin] if back else 0) > LAST:
            continue
        visits.append(Visit(location_id=i, start=s, end=e))
        t, prev = e, i
    return visits if len(visits) >= 2 else None


def sat_draft(rng: random.Random, kb: KB, n: int, tightness: str, exclude: set[str] = frozenset(),
              late: bool = False) -> tuple[dict, Plan] | None:
    ids = rng.sample([i for i in kb.ids if i not in exclude], n)
    start = rng.choice([840, 900, 960] if late else [540, 600, 660])
    origin = rng.choice(ORIGINS) if rng.random() < 0.25 else None
    back = origin is not None and rng.random() < 0.5
    durations = {i: kb.places[i].typical_duration_min for i in ids}
    overrides = {}
    for i in ids:
        p = kb.places[i]
        new = max(30, durations[i] + rng.choice([-30, 30]))
        if rng.random() < 0.15 and not p.showtimes and new <= p.close - p.open:
            overrides[i] = durations[i] = new
    visits = witness(rng, kb, ids, start, origin, back, durations)
    if visits is None:
        return None
    wid = [v.location_id for v in visits]
    end_raw = visits[-1].end + (kb.transit[wid[-1]][origin] if back else 0)
    slack = rng.choice([0, 15, 30]) if tightness == "tight" else rng.choice([60, 120, 180])
    end = min(LAST, r5(end_raw + slack, up=True))
    must = set(rng.sample(wid, rng.randint(1, len(wid))))
    cost_w = sum(kb.places[i].cost for i in wid)
    budget = {"none": None, "tight": cost_w + rng.randint(0, max(1, cost_w // 10)),
              "loose": cost_w * 3 // 2 + rng.choice([10, 20, 50])}[tightness]

    acts = []
    window_on = rng.choice(visits) if rng.random() < 0.3 else None
    for i in ids:
        a = {"location_id": i, "must_visit": i in must}
        if i in overrides:
            a["duration_min"] = overrides[i]
        if window_on and window_on.location_id == i:
            a["earliest_start"] = to_hhmm(r5(window_on.start - rng.choice([0, 30, 60])))
            a["latest_end"] = to_hhmm(min(LAST, r5(window_on.end + rng.choice([0, 30, 60]), up=True)))
        acts.append(a)
    ir = {"day_start": to_hhmm(start), "budget": budget, "activities": acts, "precedences": []}
    if rng.random() < 0.3:
        ir["duration_limit_min"] = end - start
    else:
        ir["day_end"] = to_hhmm(end)
    if origin:
        ir |= {"start_location": origin, "return_to_start": back}
    if rng.random() < 0.5:
        a, b = sorted(rng.sample(range(len(wid)), 2))
        ir["precedences"].append({"before": wid[a], "after": wid[b]})
    cost = {i: kb.places[i].cost for i in ids}
    return ir, Plan(visits=visits, total_cost=sum(cost[i] for i in wid))


# ---------------------------------------------------------------- UNSAT: one seeded conflict

def musts(ir: dict) -> list[str]:
    return [a["location_id"] for a in ir["activities"] if a["must_visit"]]


def duration_of(ir: dict, kb: KB, i: str) -> int:
    a = next(a for a in ir["activities"] if a["location_id"] == i)
    return a.get("duration_min") or kb.places[i].typical_duration_min


def set_end(ir: dict, end: int) -> None:
    ir.pop("duration_limit_min", None)
    ir["day_end"] = to_hhmm(end)


def seed_budget(rng, kb, ir, w):
    paid = [i for i in musts(ir) if kb.places[i].cost > 0]
    if not paid:
        return None
    total = sum(kb.places[i].cost for i in paid)
    ir["budget"] = max(0, total - rng.randint(1, min(10, total)))  # sum of paid must-visits > budget
    return ["budget"] + [f"must_visit:{i}" for i in paid]


def seed_horizon(rng, kb, ir, w):
    start = int(ir["day_start"][:2]) * 60 + int(ir["day_start"][3:])
    need = sum(duration_of(ir, kb, i) for i in musts(ir))
    end = r5(start + need - rng.choice([5, 15, 30]))
    if end <= start + 30:
        return None
    set_end(ir, end)  # sum of must-visit durations > the whole day
    return ["horizon"] + [f"must_visit:{i}" for i in musts(ir)]


def seed_window(rng, kb, ir, w):
    v = next(v for v in w.visits if v.location_id in musts(ir))
    a = next(a for a in ir["activities"] if a["location_id"] == v.location_id)
    e = r5(v.start)
    d = duration_of(ir, kb, v.location_id)
    cut = min(rng.choice([5, 10, 15]), d - 5)  # the window stays at least 5 min long, but shorter than the visit
    a["earliest_start"] = to_hhmm(e)
    a["latest_end"] = to_hhmm(e + d - cut)
    return [f"window:{v.location_id}", f"must_visit:{v.location_id}"]


def seed_precedence_cycle(rng, kb, ir, w):
    order = [v.location_id for v in w.visits if v.location_id in musts(ir)]
    if len(order) < 2:
        return None
    a, b = rng.sample(order, 2)
    have = {(p["before"], p["after"]) for p in ir["precedences"]}
    ir["precedences"] += [{"before": x, "after": y} for x, y in [(a, b), (b, a)] if (x, y) not in have]
    return [f"precedence:{a}:{b}", f"precedence:{b}:{a}", f"must_visit:{a}", f"must_visit:{b}"]


def add_must(ir: dict, i: str, **extra) -> None:
    ir["activities"].append({"location_id": i, "must_visit": True} | extra)


def seed_precedence_window(rng, kb, ir, w, pair):
    a, b = pair  # a opens at or after b closes, yet a must come before b
    add_must(ir, a)
    add_must(ir, b)
    ir["precedences"].append({"before": a, "after": b})
    set_end(ir, LAST)
    return [f"precedence:{a}:{b}", f"opening:{a}", f"opening:{b}", f"must_visit:{a}", f"must_visit:{b}"]


def seed_showtime_clash(rng, kb, ir, w, pair):
    s, f = pair  # every showtime of s falls inside the fixed slot the user gives for f
    t = kb.places[s].showtimes
    e, latest = t[0] - 5, t[-1] + 5
    add_must(ir, s)
    add_must(ir, f, duration_min=latest - e, earliest_start=to_hhmm(e), latest_end=to_hhmm(latest))
    set_end(ir, LAST)
    return [f"showtime:{s}", f"window:{f}", f"must_visit:{s}", f"must_visit:{f}"]


def special_pairs(kb: KB) -> dict[str, list[tuple[str, str]]]:
    P = kb.places
    return {
        "precedence_window": [(a, b) for a in P for b in P if P[a].open >= P[b].close
                              and not P[a].showtimes and not P[b].showtimes],
        "showtime_clash": [(s, f) for s in P for f in P if len(P[s].showtimes) >= 2 and P[f].category == "food"
                           and P[f].open <= P[s].showtimes[0] - 5 and P[f].close >= P[s].showtimes[-1] + 5],
    }


def only_conflict(p, seeded: list[str]) -> bool:
    """Oracle cross-check: the seeded set alone is UNSAT, and dropping any member of it makes the whole
    instance SAT. Then it is the instance's unique minimal core."""
    enc = compile_problem(p)
    lits = {c: t.lit for c, t in enc.tracked.items()}
    if not set(seeded) <= set(lits):
        return False
    s = make_solver(enc)
    if s.check(*[lits[c] for c in seeded]) != z3.unsat:
        return False
    return all(s.check(*[x for k, x in lits.items() if k != c]) == z3.sat for c in seeded)


def only_two_conflicts(p, a: list[str], b: list[str]) -> bool:
    """Oracle cross-check: a and b are each UNSAT alone, and dropping any one member of a together with any one
    member of b makes the instance SAT. Then every minimal core contains all of a or all of b, so a and b are
    the instance's only minimal cores."""
    enc = compile_problem(p)
    lits = {c: t.lit for c, t in enc.tracked.items()}
    if set(a) == set(b) or not (set(a) | set(b)) <= set(lits):
        return False
    s = make_solver(enc)
    if any(s.check(*[lits[c] for c in x]) != z3.unsat for x in (a, b)):
        return False
    return all(s.check(*[v for k, v in lits.items() if k not in (x, y)]) == z3.sat for x in a for y in b)


# ---------------------------------------------------------------- request text

def join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def render(ir: dict, kb: KB, rng: random.Random) -> str:
    name = {i: p.name for i, p in kb.places.items()}
    acts = ir["activities"]
    s = []
    if "duration_limit_min" in ir:
        h, m = divmod(ir["duration_limit_min"], 60)
        span = f"{h} hours" + (f" and {m} minutes" if m else "") if h else f"{m} minutes"
        s.append(rng.choice([f"I have {span} starting at {ir['day_start']}.",
                             f"Starting at {ir['day_start']}, I've got {span} to spend."]))
    else:
        s.append(rng.choice([f"I'm free from {ir['day_start']} to {ir['day_end']}.",
                             f"My day out runs from {ir['day_start']} until {ir['day_end']}."]))
    if ir.get("start_location"):
        o = name[ir["start_location"]]
        s.append(f"I'm starting from {o}" + (" and need to be back there by the end." if ir["return_to_start"]
                                              else "."))
    if ir["budget"] is None:
        s.append("Money is not a concern.")
    else:
        s.append(rng.choice([f"My budget is S${ir['budget']}.", f"I can spend at most S${ir['budget']}."]))
    must = [name[a["location_id"]] for a in acts if a["must_visit"]]
    opt = [name[a["location_id"]] for a in acts if not a["must_visit"]]
    if must:
        s.append(rng.choice([f"I want to visit {join(must)}.", f"I definitely need to see {join(must)}."]))
    if opt:
        s.append(rng.choice([f"If there's time, I'd also like {join(opt)}.", f"Optionally, {join(opt)}."]))
    for p in ir["precedences"]:
        s.append(f"I want to do {name[p['before']]} before {name[p['after']]}.")
    for a in acts:
        n = name[a["location_id"]]
        if "duration_min" in a:
            s.append(f"I'd like to spend {a['duration_min']} minutes at {n}.")
        if "earliest_start" in a:
            s.append(f"I want to be at {n} no earlier than {a['earliest_start']} and done there by {a['latest_end']}.")
    return " ".join(s)


# ---------------------------------------------------------------- driver

def generate(seed: int = 851, kb: KB | None = None, limit: int | None = None) -> list[BenchmarkInstance]:
    kb = kb or load_kb()
    rng = random.Random(seed)
    pairs = special_pairs(kb)
    seeders = {"budget": seed_budget, "horizon": seed_horizon, "window": seed_window,
               "precedence_cycle": seed_precedence_cycle}
    out: list[BenchmarkInstance] = []
    unsat_types = iter(CONFLICTS * 4)  # 20 UNSAT instances: 4, 4, 3, 3, 3, 3
    for n in range(3, 13):
        for k in range(5):
            if limit is not None and len(out) == limit:
                return out
            idx = len(out) + 1
            tightness = ["tight", "loose", "none"][idx % 3]
            conflict = next(unsat_types) if k >= 3 else None
            for _ in range(500):
                special = conflict in pairs
                pair = rng.choice(pairs[conflict]) if special else None
                draft = sat_draft(rng, kb, n - 2 if special else n, tightness, exclude=set(pair or ()),
                                  late=special)
                if draft is None:
                    continue
                ir, wit = draft
                seeded = None
                if conflict:
                    seeded = (seed_precedence_window if conflict == "precedence_window" else seed_showtime_clash)(
                        rng, kb, ir, wit, pair) if special else seeders[conflict](rng, kb, ir, wit)
                    if seeded is None:
                        continue
                gold = TripRequestIR.model_validate(ir)
                p = ground(gold, kb, "gold")
                if conflict is None:
                    if not check_plan(p, wit).ok or solve(p)[0] != Status.SAT:
                        raise AssertionError(f"generator bug: witness for instance {idx} is not valid")
                elif not only_conflict(p, seeded):
                    continue  # the seeded conflict is not the only one: draw again
                text = render(ir, kb, rng)
                out.append(BenchmarkInstance(
                    id=f"inst_{idx:03d}", set="generated", n_locations=n, budget_tightness=tightness,
                    expected_status="UNSAT" if conflict else "SAT", conflict_type=conflict,
                    seeded_conflict=sorted(seeded) if seeded else None, gold_ir=gold,
                    witness_plan=None if conflict else wit, request_template=text, request_text=text,
                    paraphrase_guard_passed=False, kb_version=kb.version, generator_seed=seed,
                ))
                break
            else:
                raise RuntimeError(f"could not generate instance {idx} (n={n}, conflict={conflict})")
    if limit is None:
        out += two_conflict_instances(seed, kb, start=len(out) + 1)
    return out


def two_conflict_instances(seed: int, kb: KB, start: int) -> list[BenchmarkInstance]:
    rng = random.Random(seed + 1)  # own stream, so the first 50 instances do not change
    seeders = {"budget": seed_budget, "horizon": seed_horizon, "window": seed_window,
               "precedence_cycle": seed_precedence_cycle}
    out = []
    for k, (first, second) in enumerate(TWO_CONFLICTS):
        idx, n = start + k, 5 + k
        for _ in range(2000):
            draft = sat_draft(rng, kb, n, "tight")
            if draft is None:
                continue
            ir, wit = draft
            a = seeders[first](rng, kb, ir, wit)
            b = seeders[second](rng, kb, ir, wit) if a else None
            if not b:
                continue
            gold = TripRequestIR.model_validate(ir)
            if not only_two_conflicts(ground(gold, kb, "gold"), a, b):
                continue
            text = render(ir, kb, rng)
            out.append(BenchmarkInstance(
                id=f"inst_{idx:03d}", set="generated", n_locations=n, budget_tightness="tight",
                expected_status="UNSAT", conflict_type="two_conflicts", seeded_conflicts=[sorted(a), sorted(b)],
                gold_ir=gold, request_template=text, request_text=text, paraphrase_guard_passed=False,
                kb_version=kb.version, generator_seed=seed))
            break
        else:
            raise RuntimeError(f"could not generate two-conflict instance {idx} ({first} + {second})")
    return out


def load_instances(which: str = "generated", root: Path = BENCH_DIR) -> list[BenchmarkInstance]:
    folder = root / ("instances" if which == "generated" else "heldout")
    return [BenchmarkInstance.model_validate_json(f.read_text()) for f in sorted(folder.glob("*.json"))]


def write(instances: list[BenchmarkInstance], root: Path = BENCH_DIR) -> None:
    folder = root / "instances"
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob("inst_*.json"):
        f.unlink()
    for inst in instances:
        (folder / f"{inst.id}.json").write_text(inst.model_dump_json(indent=1, exclude_none=False))
    manifest = {"generator_seed": instances[0].generator_seed, "kb_version": instances[0].kb_version,
                "count": len(instances), "ids": [i.id for i in instances],
                "paraphrased": sum(i.paraphrase_model is not None for i in instances),
                "reviewed": {i.id: i.reviewed_by for i in instances}}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=851)
    ap.add_argument("--out", type=Path, default=BENCH_DIR)
    args = ap.parse_args()
    instances = generate(args.seed)
    write(instances, args.out)
    sat = sum(i.expected_status == "SAT" for i in instances)
    print(f"wrote {len(instances)} instances ({sat} SAT, {len(instances) - sat} UNSAT) to {args.out}")


if __name__ == "__main__":
    main()
