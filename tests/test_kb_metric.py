import shutil

import pytest

from nstrip.kb.loader import KB_DIR, load_kb
from nstrip.kb.travel import build_matrix, haversine_km, is_metric


@pytest.fixture(scope="module")
def kb():
    return load_kb()


def test_singapore_kb_loads(kb):
    assert kb.city == "Singapore" and kb.currency == "SGD"
    assert len(kb.places) >= 35
    assert {p.category for p in kb.places.values()} >= {"theme_park", "show", "museum", "nature", "food"}
    assert len(kb.version) == 7


def test_shows_have_showtimes(kb):
    shows = [p for p in kb.places.values() if p.category == "show"]
    assert len(shows) >= 3 and all(p.showtimes for p in shows)
    assert kb.places["garden_rhapsody"].showtimes == [19 * 60 + 45, 20 * 60 + 45]


def test_travel_matrix_is_metric_symmetric_and_sane(kb):
    t = kb.transit
    assert is_metric(t)
    for a in kb.ids:
        assert t[a][a] == 0
        for b in kb.ids:
            assert t[a][b] == t[b][a]
    assert t["garden_rhapsody"]["supertree_grove"] == 0  # same spot
    assert 10 < t["gardens_domes"]["singapore_flyer"] <= 20  # neighbours in Marina Bay
    assert 45 < t["universal_studios"]["night_safari"] <= 75  # Sentosa to Mandai is the long haul


def test_haversine_one_degree_of_longitude_at_equator():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.01)


def test_non_metric_matrix_detected():
    m = {"a": {"a": 0, "b": 10, "c": 50}, "b": {"a": 10, "b": 0, "c": 10}, "c": {"a": 50, "b": 10, "c": 0}}
    assert not is_metric(m)  # a -> b -> c (20) beats a -> c (50)
    assert is_metric(build_matrix({"a": (1.0, 103.0), "b": (1.1, 103.1), "c": (1.3, 103.0)}, 10, 25))


@pytest.mark.parametrize("field, value, message", [
    ("showtimes", "18:00", "showtime 18:00"),  # Garden Rhapsody opens 19:30
    ("typical_duration_min", "500", "longer than the opening window"),
    ("open", "9am", "bad time"),
    ("id", "garden:rhapsody", "garden:rhapsody"),
])
def test_bad_rows_rejected(tmp_path, field, value, message):
    shutil.copytree(KB_DIR, tmp_path / "kb")
    csv_path = tmp_path / "kb" / "locations.csv"
    lines = csv_path.read_text().splitlines()
    header = lines[0].split(",")
    i = next(n for n, line in enumerate(lines) if line.startswith("garden_rhapsody,"))
    row = lines[i].split(",")
    row[header.index(field)] = value
    lines[i] = ",".join(row)
    csv_path.write_text("\n".join(lines))
    with pytest.raises(ValueError, match=message):
        load_kb(tmp_path / "kb")


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
def test_kb_version_ignores_line_endings(tmp_path, eol):
    # a Windows checkout (core.autocrlf) must give the same version as the committed LF files
    shutil.copytree(KB_DIR, tmp_path / "kb")
    for name in ("locations.csv", "travel_params.json"):
        p = tmp_path / "kb" / name
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", eol))
    assert load_kb(tmp_path / "kb").version == load_kb().version == "e5a5ae6"
