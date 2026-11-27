import random

import pytest

from nstrip.kb.loader import KB, Place
from nstrip.kb.travel import build_matrix
from nstrip.models.problem import Activity, ProblemInstance


@pytest.fixture
def tiny_kb() -> KB:
    """The proposal's three places as a KB: transit 0, open all day, dollars."""
    def place(id, name, cost, d):
        return Place(id=id, name=name, aliases=[name.lower()], category="attraction", cost=cost,
                     typical_duration_min=d, open=0, close=1440, showtimes=[], lat=0, lon=0,
                     source_url="proposal §2", checked=True)
    places = {p.id: p for p in [place("museum", "Museum", 20, 120), place("park", "Park", 0, 60),
                                 place("cafe", "Café", 15, 60)]}
    return KB(city="Testville", currency="USD", curated_on="2026-11-25", version="tiny", places=places,
              transit=zero_transit(list(places)))


def zero_transit(ids: list[str]) -> dict[str, dict[str, int]]:
    return {i: {j: 0 for j in ids} for i in ids}


def random_problem(rng: random.Random, n: int) -> ProblemInstance:
    """Small random problem with every constraint kind, a metric travel matrix, and roughly as many
    UNSAT as SAT cases. Used to cross-check the solver (minimality, checker agreement, brute force)."""
    acts = []
    for i in range(n):
        d = rng.choice([30, 60, 90, 120])
        o = rng.choice([480, 540, 600, 720])
        c = min(1440, o + rng.choice([d, 240, 360, 600]))
        show = rng.random() < 0.2 and c - o >= d + 120
        early = rng.choice([None, None, None, 600])
        late = rng.choice([None, None, None, 840])
        acts.append(Activity(
            id=f"p{i}", name=f"Place {i}", must_visit=rng.random() < 0.6, duration=d, cost=rng.randint(0, 40),
            open=o, close=c, showtimes=[o + 30, o + 120] if show else [],
            user_earliest=early, user_latest=late if late and (early is None or late - early >= d) else None,
        ))
    ids = [a.id for a in acts]
    coords = {i: (1.25 + rng.random() * 0.15, 103.75 + rng.random() * 0.2) for i in ids}
    prec = [tuple(rng.sample(ids, 2))] if n >= 2 and rng.random() < 0.4 else []
    return ProblemInstance(
        horizon_start=540, horizon_end=540 + rng.choice([180, 300, 480, 720]),
        budget=rng.choice([None, 30, 60, 100]), activities=acts, precedences=prec,
        transit=build_matrix(coords, 10, 25), source="gold",
    )


@pytest.fixture
def proposal_problem() -> ProblemInstance:
    """Proposal §2 worked example: 4 h from 09:00, $30, all three wanted, Museum before Café,
    transit 0, everything open all day. UNSAT, because 20 + 0 + 15 = 35 > 30."""
    acts = [
        Activity(id="museum", name="Museum", must_visit=True, duration=120, cost=20, open=0, close=1440),
        Activity(id="park", name="Park", must_visit=True, duration=60, cost=0, open=0, close=1440),
        Activity(id="cafe", name="Café", must_visit=True, duration=60, cost=15, open=0, close=1440),
    ]
    return ProblemInstance(horizon_start=540, horizon_end=780, budget=30, activities=acts,
                           precedences=[("museum", "cafe")], transit=zero_transit([a.id for a in acts]),
                           source="gold")
