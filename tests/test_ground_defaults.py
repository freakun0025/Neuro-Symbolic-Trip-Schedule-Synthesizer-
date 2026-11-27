import pytest

from nstrip.ground import ground
from nstrip.kb.loader import load_kb
from nstrip.models.ir import TripRequestIR


def ir(**kw):
    return TripRequestIR.model_validate({"activities": [{"location_id": "museum", "must_visit": True}]} | kw)


def test_no_times_gives_logged_default_day(tiny_kb):
    p = ground(ir(), tiny_kb)
    assert (p.horizon_start, p.horizon_end) == (540, 1260)
    assert p.assumed_defaults == ["day start assumed 09:00", "day end assumed 21:00"]


def test_four_hours_anchors_at_nine(tiny_kb):
    p = ground(ir(duration_limit_min=240), tiny_kb)
    assert (p.horizon_start, p.horizon_end) == (540, 780)
    assert p.assumed_defaults == ["day start assumed 09:00"]


def test_hours_with_an_end_time_count_back_from_it(tiny_kb):
    p = ground(ir(duration_limit_min=240, day_end="18:00"), tiny_kb)
    assert (p.horizon_start, p.horizon_end) == (840, 1080)


def test_explicit_times_win_and_limit_cuts_the_end(tiny_kb):
    p = ground(ir(day_start="10:00", day_end="20:00", duration_limit_min=120), tiny_kb)
    assert (p.horizon_start, p.horizon_end, p.assumed_defaults) == (600, 720, [])


def test_late_start_defaults_to_midnight(tiny_kb):
    assert ground(ir(day_start="21:30"), tiny_kb).horizon_end == 1440


def test_kb_facts_unless_user_overrides(tiny_kb):
    p = ground(ir(activities=[{"location_id": "museum", "must_visit": True, "duration_min": 90},
                              {"location_id": "cafe", "must_visit": False, "cost": 9,
                               "earliest_start": "13:00", "latest_end": "15:00"}]), tiny_kb)
    museum, cafe = p.activities
    assert (museum.duration, museum.cost, museum.name) == (90, 20, "Museum")
    assert (cafe.duration, cafe.cost, cafe.user_earliest, cafe.user_latest) == (60, 9, 780, 900)


def test_unknown_place_is_an_error_not_a_guess(tiny_kb):
    with pytest.raises(ValueError, match="zoo"):
        ground(ir(activities=[{"location_id": "zoo", "must_visit": True}]), tiny_kb)


def test_singapore_transit_includes_start_location():
    kb = load_kb()
    p = ground(ir(activities=[{"location_id": "maxwell", "must_visit": True}], start_location="orchard_road",
                  return_to_start=True), kb)
    assert set(p.transit) == {"maxwell", "orchard_road"}
    assert p.transit["orchard_road"]["maxwell"] == kb.transit["orchard_road"]["maxwell"]
