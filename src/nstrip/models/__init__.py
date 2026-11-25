"""Shared base model and unit types. Time = int minutes since midnight, money = int currency units."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Minute = Annotated[int, Field(ge=0, le=1440)]
NonNeg = Annotated[int, Field(ge=0)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
