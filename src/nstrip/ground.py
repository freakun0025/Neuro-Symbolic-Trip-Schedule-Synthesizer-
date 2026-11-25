"""Grounding (ARCHITECTURE §4.2): validated IR + KB -> ProblemInstance. Deterministic; the LLM never fills facts.

Horizon rules (every default is logged in assumed_defaults and shown to the user):
- start = day_start; else day_end - duration_limit if both of those are given; else 09:00.
- end = the earlier of day_end and start + duration_limit; else 21:00 (or midnight if the day starts later).
"""

from nstrip.config import DEFAULT_DAY_END, DEFAULT_DAY_START
from nstrip.kb.loader import KB
from nstrip.models import to_hhmm, to_minutes
from nstrip.models.ir import TripRequestIR
from nstrip.models.problem import Activity, ProblemInstance


def ground(ir: TripRequestIR, kb: KB, source: str = "extracted") -> ProblemInstance:
    defaults: list[str] = []
    start = to_minutes(ir.day_start) if ir.day_start else None
    end = to_minutes(ir.day_end) if ir.day_end else None
    limit = ir.duration_limit_min

    if start is None:
        if end is not None and limit is not None:
            start = max(0, end - limit)
            defaults.append(f"day start assumed {to_hhmm(start)} ({limit} min before the end time)")
        else:
            start = DEFAULT_DAY_START
            defaults.append(f"day start assumed {to_hhmm(start)}")
    if limit is not None:
        end = start + limit if end is None else min(end, start + limit)
    if end is None:
        end = DEFAULT_DAY_END if start < DEFAULT_DAY_END else 1440
        defaults.append(f"day end assumed {to_hhmm(end)}")
    end = min(end, 1440)

    acts = []
    for spec in ir.activities:
        place = kb.places.get(spec.location_id)
        if place is None:
            raise ValueError(f"{spec.location_id!r} is not in the knowledge base")
        acts.append(Activity(
            id=place.id, name=place.name, must_visit=spec.must_visit,
            duration=spec.duration_min or place.typical_duration_min,
            cost=place.cost if spec.cost is None else spec.cost,
            open=place.open, close=place.close, showtimes=place.showtimes,
            user_earliest=to_minutes(spec.earliest_start) if spec.earliest_start else None,
            user_latest=to_minutes(spec.latest_end) if spec.latest_end else None,
        ))

    ids = [a.id for a in acts]
    if ir.start_location:
        if ir.start_location not in kb.places:
            raise ValueError(f"start location {ir.start_location!r} is not in the knowledge base")
        if ir.start_location not in ids:
            ids.append(ir.start_location)
    return ProblemInstance(
        horizon_start=start, horizon_end=end, budget=ir.budget,
        start_location=ir.start_location, return_to_start=ir.return_to_start,
        activities=acts, precedences=[(p.before, p.after) for p in ir.precedences],
        transit={a: {b: kb.transit[a][b] for b in ids} for a in ids},
        assumed_defaults=defaults, source=source,
    )
