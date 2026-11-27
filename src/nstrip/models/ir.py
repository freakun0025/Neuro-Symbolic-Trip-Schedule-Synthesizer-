"""LLM-facing IR (spec §2.1). The only place "HH:MM" strings exist; grounding turns them into minutes.

Validation errors are sent back to the LLM on retry, so messages are written for it to read.
"""

import math
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, create_model, field_validator, model_validator

from nstrip.models import Model, NonNeg, to_minutes

TimeStr = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class ActivitySpec(Model):
    location_id: str
    must_visit: bool  # "want/must/need" -> True ; "maybe/if time" -> False
    duration_min: Annotated[int, Field(gt=0)] | None = None  # user override; None -> KB value
    cost: NonNeg | None = None  # user override; None -> KB value
    earliest_start: TimeStr | None = None  # user window, "not before 3pm"
    latest_end: TimeStr | None = None  # user window, "done by 5pm"

    @model_validator(mode="after")
    def _window_order(self):
        if self.earliest_start and self.latest_end and \
                to_minutes(self.earliest_start) >= to_minutes(self.latest_end):
            raise ValueError(f"{self.location_id}: earliest_start must be before latest_end")
        return self


class PrecedenceSpec(Model):
    before: str
    after: str


class TripRequestIR(Model):
    schema_version: Literal["1.0"] = "1.0"
    day_start: TimeStr | None = None
    day_end: TimeStr | None = None
    duration_limit_min: Annotated[int, Field(gt=0, le=1440)] | None = None  # "I have 4 hours" -> 240
    budget: NonNeg | None = None
    start_location: str | None = None
    return_to_start: bool = False
    activities: list[ActivitySpec]
    precedences: list[PrecedenceSpec] = []
    unresolved_mentions: list[str] = []  # places not in the KB -> NEEDS_CLARIFICATION
    ignored_preferences: list[str] = []  # vague wishes, shown to the user, never encoded

    @field_validator("budget", mode="before")
    @classmethod
    def _floor_budget(cls, v):
        return math.floor(v) if isinstance(v, float) else v  # "$30.50" -> 30, never round up

    @model_validator(mode="after")
    def _consistent(self):
        ids = [a.location_id for a in self.activities]
        if len(ids) != len(set(ids)):
            raise ValueError("each place may appear only once in activities")
        for p in self.precedences:
            if p.before == p.after:
                raise ValueError(f"precedence from {p.before} to itself")
            missing = {p.before, p.after} - set(ids)
            if missing:
                raise ValueError(f"precedence uses places that are not in activities: {sorted(missing)}")
        if self.day_start and self.day_end and to_minutes(self.day_start) >= to_minutes(self.day_end):
            raise ValueError("day_start must be before day_end")
        if self.return_to_start and self.start_location is None:
            raise ValueError("return_to_start needs a start_location")
        return self


def make_ir_model(kb_ids: list[str]) -> type[TripRequestIR]:
    """The IR with every location field restricted to the KB ids, so the LLM cannot invent a place."""
    loc = Literal[tuple(kb_ids)]
    act = create_model("ActivitySpec", __base__=ActivitySpec, location_id=(loc, ...))
    prec = create_model("PrecedenceSpec", __base__=PrecedenceSpec, before=(loc, ...), after=(loc, ...))
    return create_model(
        "TripRequestIR",
        __base__=TripRequestIR,
        start_location=(loc | None, None),
        activities=(list[act], ...),
        precedences=(list[prec], []),
    )
