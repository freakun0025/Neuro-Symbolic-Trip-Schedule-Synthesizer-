"""Deterministic explanation text (ARCHITECTURE §4.9). This is the ground truth; an LLM may only rephrase it."""

from nstrip.models import to_hhmm
from nstrip.models.constraints import ConstraintKind as K
from nstrip.models.constraints import parse_cid
from nstrip.models.plan import Diagnosis, Plan, Relaxation
from nstrip.models.problem import ProblemInstance


def money(amount: int, currency: str) -> str:
    return f"{ {'SGD': 'S$', 'USD': '$'}.get(currency, currency + ' ')}{amount}"


def render_plan(p: ProblemInstance, plan: Plan, currency: str = "SGD") -> str:
    acts = {a.id: a for a in p.activities}
    lines = [(f"Here is a plan that meets every requirement ({len(plan.visits)} stops, "
              f"total {money(plan.total_cost, currency)}):")]
    prev = None
    for v in plan.visits:
        if prev is not None and p.travel(prev, v.location_id):
            lines.append(f"    travel {p.travel(prev, v.location_id)} min")
        lines.append(f"  {to_hhmm(v.start)}-{to_hhmm(v.end)}  {acts[v.location_id].name}"
                     f" ({money(acts[v.location_id].cost, currency)})")
        prev = v.location_id
    visited = {v.location_id for v in plan.visits}
    skipped = [a.name for a in p.activities if a.id not in visited]
    if skipped:
        lines.append("Left out (optional, did not fit together with the rest): " + ", ".join(skipped) + ".")
    if p.assumed_defaults:
        lines.append("Assumed: " + "; ".join(p.assumed_defaults) + ".")
    if not plan.optimal:
        lines.append("Note: the optimiser timed out, so this plan is valid but may not be the best one.")
    return "\n".join(lines)


def describe(c: str, p: ProblemInstance, currency: str = "SGD") -> str:
    """One sentence per core member."""
    kind, ids = parse_cid(c)
    acts = {a.id: a for a in p.activities}
    name = acts[ids[0]].name if ids else ""
    if kind == K.BUDGET:
        return f"your budget is {money(p.budget, currency)}"
    if kind == K.HORIZON:
        via = f", including travel from {p.start_location}" if p.start_location else ""
        return f"everything must fit between {to_hhmm(p.horizon_start)} and {to_hhmm(p.horizon_end)}{via}"
    if kind == K.MUST_VISIT:
        a = acts[ids[0]]
        return f"you must visit {name} ({a.duration} min, {money(a.cost, currency)})"
    if kind == K.OPENING:
        a = acts[ids[0]]
        return f"{name} is open {to_hhmm(a.open)}-{to_hhmm(a.close)}"
    if kind == K.SHOWTIME:
        return f"{name} starts only at {' or '.join(map(to_hhmm, acts[ids[0]].showtimes))}"
    if kind == K.WINDOW:
        a = acts[ids[0]]
        parts = ([f"not before {to_hhmm(a.user_earliest)}"] if a.user_earliest is not None else []) + \
                ([f"finished by {to_hhmm(a.user_latest)}"] if a.user_latest is not None else [])
        return f"you asked for {name} {' and '.join(parts)}"
    return f"{name} must come before {acts[ids[1]].name}"


def describe_fix(r: Relaxation, p: ProblemInstance, currency: str = "SGD") -> str:
    _, ids = parse_cid(r.cid)
    acts = {a.id: a for a in p.activities}
    if r.action == "raise_budget":
        text = f"raise the budget from {money(r.old_value, currency)} to {money(r.new_value, currency)}" \
            if r.new_value is not None else "raise the budget"
    elif r.action == "extend_horizon_end":
        text = f"end the day at {to_hhmm(r.new_value)} instead of {to_hhmm(r.old_value)}" \
            if r.new_value is not None else "end the day later"
    elif r.action == "widen_window":
        side = "finish" if acts[ids[0]].user_latest == r.old_value else "start"
        text = (f"let {acts[ids[0]].name} {side} at {to_hhmm(r.new_value)} instead of {to_hhmm(r.old_value)}"
                if r.new_value is not None else f"relax the time you asked for at {acts[ids[0]].name}")
    elif r.action == "drop_must_visit":
        text = f"make {acts[ids[0]].name} optional"
    else:
        text = f"drop the rule that {acts[ids[0]].name} comes before {acts[ids[1]].name}"
    return text + ("" if r.restores_feasibility else " (not enough on its own: another conflict remains)")


def render_diagnosis(p: ProblemInstance, d: Diagnosis, currency: str = "SGD") -> str:
    lines = [("No plan can satisfy all of your requirements. These requirements conflict "
              "(drop or change any one of them and this conflict goes away):")]
    lines += [f"  - {describe(c, p, currency)}" for c in d.core]
    if d.relaxations:
        lines.append("Smallest changes that would help:")
        lines += [f"  - {describe_fix(r, p, currency)}" for r in d.relaxations]
    if d.world_facts:
        lines.append("Opening hours and showtimes are facts about the places and cannot be changed.")
    if p.assumed_defaults:
        lines.append("Assumed: " + "; ".join(p.assumed_defaults) + ".")
    return "\n".join(lines)
