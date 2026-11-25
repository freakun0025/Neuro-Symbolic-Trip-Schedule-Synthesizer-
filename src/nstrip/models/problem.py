"""Grounded problem (spec §2.2): every fact filled in, all integers. This is what the compiler and checker see."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from nstrip.models import Minute, Model, NonNeg


class Activity(Model):
    id: str
    name: str
    must_visit: bool
    duration: Annotated[int, Field(gt=0)]  # D_i
    cost: NonNeg  # C_i
    open: Minute  # O_i
    close: Minute  # K_i
    showtimes: list[Minute] = []  # KB only; [] = no fixed start times
    user_earliest: Minute | None = None
    user_latest: Minute | None = None


class ProblemInstance(Model):
    horizon_start: Minute  # H0
    horizon_end: Minute  # H1
    budget: NonNeg | None = None  # B; None = no budget constraint
    start_location: str | None = None
    return_to_start: bool = False
    activities: list[Activity]
    precedences: list[tuple[str, str]] = []
    transit: dict[str, dict[str, NonNeg]]  # minutes, restricted to activities + start_location
    assumed_defaults: list[str] = []
    source: Literal["extracted", "gold"]

    @model_validator(mode="after")
    def _closed(self):
        ids = [a.id for a in self.activities]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate activity id")
        for a, b in self.precedences:
            if a not in ids or b not in ids:
                raise ValueError(f"precedence ({a}, {b}) refers to a non-activity")
        places = ids + ([self.start_location] if self.start_location else [])
        for i in places:
            for j in places:
                if i != j and j not in self.transit.get(i, {}):
                    raise ValueError(f"transit time {i} -> {j} missing")
        if self.return_to_start and not self.start_location:
            raise ValueError("return_to_start needs a start_location")
        return self

    def travel(self, a: str, b: str) -> int:
        return 0 if a == b else self.transit[a][b]
