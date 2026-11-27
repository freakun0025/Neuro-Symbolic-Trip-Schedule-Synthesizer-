"""Knowledge base: data/kb/locations.csv + travel_params.json + kb_meta.json -> validated KB (spec §3, §6)."""

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from nstrip.kb.travel import Matrix, build_matrix, is_metric
from nstrip.models import Minute, Model, NonNeg, to_hhmm, to_minutes

KB_DIR = Path(__file__).resolve().parents[3] / "data" / "kb"
TIME_RE = re.compile(r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")  # 24:00 = midnight, end of the trip day


class Place(Model):
    id: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]  # no ':' so cids stay parseable
    name: str
    aliases: list[str]
    category: Literal["theme_park", "attraction", "show", "museum", "nature", "food", "shopping"]
    cost: NonNeg
    typical_duration_min: Annotated[int, Field(gt=0)]
    open: Minute
    close: Minute
    showtimes: list[Minute]
    lat: float
    lon: float
    source_url: str
    checked: bool  # values cross-checked on curated_on; False = still to verify against source_url

    @model_validator(mode="after")
    def _fits(self):
        if self.open >= self.close:
            raise ValueError("open must be before close")
        if self.typical_duration_min > self.close - self.open:
            raise ValueError("typical_duration_min is longer than the opening window")
        for t in self.showtimes:
            if t < self.open or t + self.typical_duration_min > self.close:
                raise ValueError(f"showtime {to_hhmm(t)} does not fit in {to_hhmm(self.open)}-{to_hhmm(self.close)}")
        return self


class KB(Model):
    city: str
    currency: str
    curated_on: str
    version: str  # hash of the CSV + travel params, stored with every benchmark instance
    places: dict[str, Place]
    transit: Matrix

    @property
    def ids(self) -> list[str]:
        return list(self.places)


def _minutes(s: str) -> int:
    if not TIME_RE.match(s):
        raise ValueError(f"bad time {s!r}, expected HH:MM")
    return 1440 if s == "24:00" else to_minutes(s)


def _place(row: dict[str, str]) -> Place:
    return Place(
        id=row["id"], name=row["name"], aliases=[a for a in row["aliases"].split("|") if a],
        category=row["category"], cost=row["cost"], typical_duration_min=row["typical_duration_min"],
        open=_minutes(row["open"]), close=_minutes(row["close"]),
        showtimes=[_minutes(t) for t in row["showtimes"].split("|") if t],
        lat=row["lat"], lon=row["lon"], source_url=row["source_url"], checked=row["checked"] == "yes",
    )


def load_kb(path: Path = KB_DIR) -> KB:
    # normalise line endings so the version hash is the same on a CRLF (Windows) checkout
    csv_bytes = (path / "locations.csv").read_bytes().replace(b"\r\n", b"\n")
    params_bytes = (path / "travel_params.json").read_bytes().replace(b"\r\n", b"\n")
    places: dict[str, Place] = {}
    for row in csv.DictReader(csv_bytes.decode().splitlines()):
        try:
            p = _place(row)
        except (ValidationError, ValueError) as e:
            raise ValueError(f"locations.csv row {row.get('id')!r}: {e}") from e
        if p.id in places:
            raise ValueError(f"locations.csv: duplicate id {p.id!r}")
        places[p.id] = p

    params = json.loads(params_bytes)
    transit = build_matrix({p.id: (p.lat, p.lon) for p in places.values()},
                           params["overhead_min"], params["speed_kmph"])
    if not is_metric(transit):
        raise ValueError("travel matrix violates the triangle inequality; pairwise non-overlap would be wrong")

    meta = json.loads((path / "kb_meta.json").read_text())
    return KB(city=meta["city"], currency=meta["currency"], curated_on=meta["curated_on"],
              version=hashlib.sha256(csv_bytes + params_bytes).hexdigest()[:7], places=places, transit=transit)
