"""Extraction prompt (ARCHITECTURE §4.1). The LLM translates; it never plans, checks or fills KB facts."""

import json

from nstrip.kb.loader import KB

SYSTEM_RULES = """You convert a traveller's request for ONE day in {city} into JSON matching the schema below.
You only record what the user said. You never plan the day, never judge feasibility, never invent facts.

Rules:
- location_id must be an id from the place list. Match the user's words to names and aliases.
  A place the user mentions that is NOT in the list goes into unresolved_mentions (in the user's words).
  Never substitute a different place for it.
- must_visit: true for places the user wants, needs or must see; false for "maybe", "if there's time",
  "optionally", "would be nice".
- Fill duration_min or cost for a place ONLY if the user states it for that place; otherwise null
  (the system already knows typical durations and prices).
- All times are 24-hour "HH:MM". "I have 4 hours" -> duration_limit_min 240. "from 10am" -> day_start "10:00".
  "until 6pm", "back by 18:00" -> day_end "18:00".
- budget: the total amount of money in whole {currency}, rounded down; null if not mentioned.
- earliest_start / latest_end: only for a time the user gives for that specific place
  ("lunch at Maxwell after 1pm" -> earliest_start "13:00"; "finish the zoo by 3pm" -> latest_end "15:00").
- precedences: only explicit orderings ("X before Y", "after X go to Y" -> before X, after Y).
- start_location: only if the user names a starting place from the list; return_to_start: true only if they
  say they must end back there.
- Vague wishes ("something relaxing", "good food", "not too touristy") go into ignored_preferences.
- Output JSON only. No prose, no code fences."""

FEW_SHOTS = [
    (("I've got 5 hours from 2pm and S$80. I want to see the Flower Dome and the Singapore Flyer, and Spectra "
      "if there's time. Flyer before the domes please. Also something relaxing, and maybe Kinokuniya."),
     {"day_start": "14:00", "duration_limit_min": 300, "budget": 80,
      "activities": [{"location_id": "gardens_domes", "must_visit": True},
                     {"location_id": "singapore_flyer", "must_visit": True},
                     {"location_id": "spectra", "must_visit": False}],
      "precedences": [{"before": "singapore_flyer", "after": "gardens_domes"}],
      "unresolved_mentions": ["Kinokuniya"], "ignored_preferences": ["something relaxing"]}),
    (("Starting from Orchard Road at 9:30, I must do the National Museum, then lunch at Maxwell after 12:30 "
      "for about 45 minutes. Need to be back at Orchard by 5pm."),
     {"day_start": "09:30", "day_end": "17:00", "start_location": "orchard_road", "return_to_start": True,
      "activities": [{"location_id": "national_museum", "must_visit": True},
                     {"location_id": "maxwell", "must_visit": True, "duration_min": 45,
                      "earliest_start": "12:30"}],
      "precedences": [{"before": "national_museum", "after": "maxwell"}]}),
]


def place_list(kb: KB) -> str:
    return "\n".join(f"- {p.id}: {p.name} (also: {', '.join(p.aliases)}) [{p.category}]"
                     for p in kb.places.values())


def render_prompt(text: str, kb: KB, schema: dict) -> list[dict]:
    system = (SYSTEM_RULES.format(city=kb.city, currency=kb.currency)
              + f"\n\nPlace list (id: name):\n{place_list(kb)}"
              + f"\n\nJSON schema:\n{json.dumps(schema)}")
    messages = [{"role": "system", "content": system}]
    usable = set(kb.ids)
    for request, answer in FEW_SHOTS:
        ids = {a["location_id"] for a in answer["activities"]} | {answer.get("start_location")} - {None}
        if ids <= usable:  # skip examples whose places this KB does not have (e.g. the test fixture)
            messages += [{"role": "user", "content": request},
                         {"role": "assistant", "content": json.dumps(answer)}]
    messages.append({"role": "user", "content": text})
    return messages
