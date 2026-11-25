import json

from nstrip.extract.extractor import extract
from nstrip.extract.llm_client import FakeClient
from nstrip.kb.loader import load_kb

GOOD = json.dumps({"budget": 30, "duration_limit_min": 240,
                   "activities": [{"location_id": "museum", "must_visit": True}]})


def test_valid_first_time(tiny_kb):
    client = FakeClient([GOOD])
    got, attempts, err = extract("4 hours, $30, the museum", tiny_kb, client)
    assert (got.budget, attempts, err) == (30, 1, None)
    assert '"museum"' in json.dumps(client.calls[0]["json_schema"])  # the enum of KB ids is sent


def test_invalid_then_valid_feeds_the_error_back(tiny_kb):
    bad = json.dumps({"activities": [{"location_id": "zoo", "must_visit": True}]})
    client = FakeClient([bad, "```json\n" + GOOD + "\n```"])  # code fences are tolerated
    got, attempts, _ = extract("museum", tiny_kb, client)
    assert got is not None and attempts == 2
    retry = client.calls[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": bad}
    assert "activities.0.location_id" in retry[-1]["content"]


def test_gives_up_after_retries(tiny_kb):
    client = FakeClient(["not json"] * 4)
    got, attempts, err = extract("museum", tiny_kb, client)
    assert got is None and attempts == 4 and err


def test_singapore_prompt_has_places_and_few_shots():
    kb = load_kb()
    client = FakeClient([GOOD.replace("museum", "national_museum")])
    extract("National Museum please", kb, client)
    msgs = client.calls[0]["messages"]
    assert "garden_rhapsody: Garden Rhapsody" in msgs[0]["content"]
    assert len(msgs) == 1 + 2 * 2 + 1  # system, two few-shot pairs, the request
    assert msgs[-1]["content"] == "National Museum please"


def test_few_shots_skipped_when_kb_lacks_their_places(tiny_kb):
    client = FakeClient([GOOD])
    extract("museum", tiny_kb, client)
    assert len(client.calls[0]["messages"]) == 2
