"""Pure-LLM baseline (FR-22, RISKS R13): the LLM plans the day itself, with the same KB rows and travel times
the solver gets, and is allowed to say the request is infeasible. Its plan is checked against gold like any
other method."""

import json

from pydantic import ValidationError

from nstrip.extract.extractor import FENCE, short_errors
from nstrip.extract.llm_client import LLMClient
from nstrip.kb.loader import KB
from nstrip.models import Model, to_hhmm, to_minutes
from nstrip.models.bench import BaselineAnswer
from nstrip.models.ir import TimeStr
from nstrip.models.plan import Visit


class _Stop(Model):
    location_id: str
    start: TimeStr
    end: TimeStr


class _Answer(Model):
    feasible: bool
    visits: list[_Stop]
    reason: str


SYSTEM = """You are a careful trip planner for ONE day in {city}. Plan a schedule that satisfies ALL of the
traveller's requirements, using only the facts below. Requirements include: total budget, the time window
of the day, places that must be visited, the order they ask for, times they give for specific places, and
how long they want to stay. Each visit lasts exactly its duration (the typical duration unless the traveller
gives one), must be inside the place's opening hours, shows can only start at a listed showtime, visits
cannot overlap, and you need the listed travel time between consecutive stops (and from/to the starting
place if one is given). Optional places should be included only if everything still fits.
If no schedule can satisfy every requirement, answer feasible=false with an empty visits list and say why.

Places (id | name | cost {currency} | typical minutes | open-close | showtimes):
{places}

Travel times in minutes (row -> column):
{travel}

Answer with JSON only: {{"feasible": bool, "visits": [{{"location_id": id, "start": "HH:MM", "end": "HH:MM"}}],
"reason": short string}}. Times are 24-hour HH:MM."""


def kb_rows(kb: KB, ids: list[str]) -> tuple[str, str]:
    places = "\n".join(
        f"{i} | {kb.places[i].name} | {kb.places[i].cost} | {kb.places[i].typical_duration_min} | "
        f"{to_hhmm(kb.places[i].open)}-{to_hhmm(kb.places[i].close)} | "
        f"{', '.join(map(to_hhmm, kb.places[i].showtimes)) or '-'}" for i in ids)
    travel = "\n".join(f"{a}: " + ", ".join(f"{b} {kb.transit[a][b]}" for b in ids if b != a) for a in ids)
    return places, travel


def plan_with_llm(text: str, kb: KB, ids: list[str], client: LLMClient, max_retries: int = 2) -> BaselineAnswer:
    places, travel = kb_rows(kb, ids)
    messages = [{"role": "system", "content": SYSTEM.format(city=kb.city, currency=kb.currency, places=places,
                                                            travel=travel)},
                {"role": "user", "content": text}]
    schema = _Answer.model_json_schema()
    for _ in range(max_retries + 1):
        raw = client.chat(messages, json_schema=schema)
        try:
            a = _Answer.model_validate_json(FENCE.sub("", raw))
        except ValidationError as e:
            messages = messages + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": f"Invalid JSON:\n{short_errors(e)}\nAnswer again."}]
            continue
        visits = [Visit(location_id=v.location_id, start=to_minutes(v.start), end=to_minutes(v.end))
                  for v in a.visits] if a.feasible else []
        return BaselineAnswer(feasible=a.feasible, visits=sorted(visits, key=lambda v: v.start), reason=a.reason)
    raise ValueError("baseline answer was invalid after retries: " + json.dumps(raw[:200]))
