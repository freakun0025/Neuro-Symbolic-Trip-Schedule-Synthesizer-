"""Checker output (spec §2.5)."""

from typing import Literal

from nstrip.models import Model

ViolationKind = Literal["unknown_location", "duplicate", "duration_mismatch", "overlap_or_transit", "horizon",
                        "opening", "showtime", "window", "budget", "missing_must_visit", "precedence"]


class Violation(Model):
    kind: ViolationKind
    detail: str
    location_ids: list[str] = []


class CheckReport(Model):
    ok: bool
    violations: list[Violation]
