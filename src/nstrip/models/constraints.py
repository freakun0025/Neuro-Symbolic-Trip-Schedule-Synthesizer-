"""Constraint ids (the names that appear in unsat cores) and canonical tuples for extraction scoring (spec §2.3, §4)."""

from enum import StrEnum

from nstrip.models.problem import ProblemInstance


class ConstraintKind(StrEnum):
    BUDGET = "budget"
    HORIZON = "horizon"
    OPENING = "opening"
    SHOWTIME = "showtime"
    WINDOW = "window"
    MUST_VISIT = "must_visit"
    PRECEDENCE = "precedence"


RELAXABLE = frozenset({ConstraintKind.BUDGET, ConstraintKind.HORIZON, ConstraintKind.WINDOW,
                       ConstraintKind.MUST_VISIT, ConstraintKind.PRECEDENCE})  # OPENING, SHOWTIME are world facts


def cid(kind: ConstraintKind, *ids: str) -> str:
    """cid(PRECEDENCE, "museum", "cafe") -> "precedence:museum:cafe". KB ids never contain ':'."""
    return ":".join([kind.value, *ids])


def parse_cid(s: str) -> tuple[ConstraintKind, tuple[str, ...]]:
    kind, *ids = s.split(":")
    return ConstraintKind(kind), tuple(ids)


def canonical_tuples(p: ProblemInstance) -> set[tuple]:
    """Grounded problem -> comparable facts. Computed after grounding so restating a KB value is not an error.
    Opening hours and showtimes come only from the KB, so they are not scored."""
    t: set[tuple] = {("horizon_start", p.horizon_start), ("horizon_end", p.horizon_end)}
    if p.budget is not None:
        t.add(("budget", p.budget))
    if p.start_location:
        t.add(("origin", p.start_location, p.return_to_start))
    for a in p.activities:
        t |= {("activity", a.id, a.must_visit), ("duration", a.id, a.duration), ("cost", a.id, a.cost)}
        if a.user_earliest is not None or a.user_latest is not None:
            t.add(("window", a.id, a.user_earliest, a.user_latest))
    t |= {("precedence", a, b) for a, b in p.precedences}
    return t
