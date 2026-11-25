"""Travel times (spec §6 / RISKS R5).

T(i,j) = OVERHEAD + ceil(haversine_km / SPEED * 60), and 0 between places at the same coordinates.
This is metric by construction: haversine obeys the triangle inequality, ceil is subadditive, and the
overhead only adds slack. The loader still checks it, because pairwise non-overlap with transit is only
correct on a metric matrix.
"""

import math

Matrix = dict[str, dict[str, int]]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def build_matrix(coords: dict[str, tuple[float, float]], overhead_min: int, speed_kmph: float) -> Matrix:
    def minutes(pa: tuple[float, float], pb: tuple[float, float]) -> int:
        km = haversine_km(*pa, *pb)
        return 0 if km == 0 else overhead_min + math.ceil(km / speed_kmph * 60)

    return {a: {b: minutes(pa, pb) for b, pb in coords.items()} for a, pa in coords.items()}


def shortest_paths(m: Matrix) -> Matrix:
    """Floyd-Warshall closure."""
    d = {a: dict(row) for a, row in m.items()}
    for k, dk in d.items():
        for di in d.values():
            for j, dkj in dk.items():
                di[j] = min(di[j], di[k] + dkj)
    return d


def is_metric(m: Matrix) -> bool:
    """True if no detour is ever shorter than the direct trip (the matrix is its own shortest-path closure)."""
    return shortest_paths(m) == m
