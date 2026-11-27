"""Optional LLM rephrase of the template text (FR-15, D13). Accepted only if it keeps exactly the same numbers
and times and every place name; otherwise the template is shown. "The LLM only rephrases" must not let it
change a number."""

import re

from nstrip.extract.llm_client import LLMClient

NUMBER = re.compile(r"\d+(?::\d\d)?")

INSTRUCTIONS = ("Rewrite the following trip-planning result in friendly, plain English for a traveller. "
                "Keep every number, time, price and place name exactly as written. Do not add advice, facts, "
                "alternatives or new numbers. Plain text only.")


def guard_ok(template: str, text: str, names: list[str]) -> bool:
    return sorted(NUMBER.findall(text)) == sorted(NUMBER.findall(template)) and \
        all(n in text for n in names if n in template)


def rephrase(template: str, client: LLMClient, names: list[str]) -> tuple[str, str]:
    """-> (text, "llm_rephrase" | "template")."""
    try:
        out = client.chat([{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": template}])
    except Exception:  # noqa: BLE001  a broken rephrase must never break the answer
        return template, "template"
    return (out.strip(), "llm_rephrase") if guard_ok(template, out, names) else (template, "template")
