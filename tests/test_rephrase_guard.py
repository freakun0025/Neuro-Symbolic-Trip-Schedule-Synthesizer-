from nstrip.explain.rephrase import guard_ok, rephrase
from nstrip.extract.llm_client import FakeClient

TEMPLATE = "Raise the budget from $30 to $35, or make Café optional. Museum is open 10:00-17:00."
NAMES = ["Museum", "Café", "Park"]


def test_same_numbers_and_names_accepted():
    text = "You could bump your budget from $30 up to $35, or skip Café. Note Museum opens 10:00-17:00."
    assert rephrase(TEMPLATE, FakeClient([text]), NAMES) == (text, "llm_rephrase")


def test_changed_number_rejected():
    assert not guard_ok(TEMPLATE, "Raise the budget to about $40 or skip Café; Museum 10:00-17:00, $30.", NAMES)


def test_dropped_number_or_name_rejected():
    assert not guard_ok(TEMPLATE, "Raise the budget to $35 or skip Café. Museum is open 10:00-17:00.", NAMES)
    assert not guard_ok(TEMPLATE, "Budget $30 to $35, or skip the coffee place. Museum 10:00-17:00.", NAMES)


def test_failures_fall_back_to_template():
    assert rephrase(TEMPLATE, FakeClient(["Just go to the zoo!"]), NAMES) == (TEMPLATE, "template")

    def boom(_):
        raise ConnectionError("offline")
    assert rephrase(TEMPLATE, FakeClient([boom]), NAMES) == (TEMPLATE, "template")
