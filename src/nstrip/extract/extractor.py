"""EXTRACT (ARCHITECTURE §4.1): text -> validated TripRequestIR, retrying with the validation error fed back."""

import re
from functools import lru_cache

from pydantic import ValidationError

from nstrip.config import MAX_RETRIES
from nstrip.extract.llm_client import LLMClient
from nstrip.extract.prompts import render_prompt
from nstrip.kb.loader import KB
from nstrip.models.ir import TripRequestIR, make_ir_model

FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


@lru_cache(maxsize=8)
def ir_model(kb_ids: tuple[str, ...]) -> type[TripRequestIR]:
    return make_ir_model(list(kb_ids))


def short_errors(e: ValidationError, limit: int = 8) -> str:
    return "\n".join(f"- {'.'.join(map(str, err['loc'])) or '(root)'}: {err['msg']}" for err in e.errors()[:limit])


def extract(text: str, kb: KB, client: LLMClient,
            max_retries: int = MAX_RETRIES) -> tuple[TripRequestIR | None, int, str | None]:
    """-> (ir or None, attempts used, last validation error). None means EXTRACTION_FAILED."""
    schema = ir_model(tuple(kb.ids)).model_json_schema()
    return _ask(render_prompt(text, kb, schema), kb, client, max_retries)


def _ask(messages: list[dict], kb: KB, client: LLMClient,
         max_retries: int) -> tuple[TripRequestIR | None, int, str | None]:
    model = ir_model(tuple(kb.ids))
    schema = model.model_json_schema()
    error = None
    for attempt in range(1, max_retries + 2):
        raw = client.chat(messages, json_schema=schema)
        try:
            return model.model_validate_json(FENCE.sub("", raw)), attempt, None
        except ValidationError as e:
            error = short_errors(e)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Your JSON was invalid:\n{error}\nReturn the corrected JSON only."},
            ]
    return None, max_retries + 1, error


VERIFY = ("The constraint solver found that these requirements from your form cannot all hold together:\n"
          "{core}\n\nRe-read my original request. For each listed requirement, check whether it says what I "
          "actually wrote (required vs. 'if there is time', times, amounts, which place comes first). If one "
          "does not match my words, return the form with only that corrected. If every listed requirement "
          "matches my words, return the form unchanged. Never drop or weaken something I actually asked for "
          "just to make the day possible: a real conflict must stay. Return the JSON form only.")


def verify(text: str, ir: TripRequestIR, user_core: list[str], kb: KB, client: LLMClient,
           max_retries: int = MAX_RETRIES) -> tuple[TripRequestIR | None, list[str]]:
    """Solver -> LLM feedback (optional, one round). The LLM re-reads the request against the requirements in
    the minimal conflict and may correct its own *extraction*. It never sees KB facts (opening hours, prices)
    and is told not to relax real requirements; every field it changes is returned so it can be audited.
    -> (corrected ir or None if invalid, changed field paths; [] = confirmed unchanged)."""
    schema = ir_model(tuple(kb.ids)).model_json_schema()
    messages = render_prompt(text, kb, schema) + [
        {"role": "assistant", "content": ir.model_dump_json(exclude_defaults=True)},
        {"role": "user", "content": VERIFY.format(core="\n".join(f"- {c}" for c in user_core))}]
    new, _, _ = _ask(messages, kb, client, max_retries)
    return new, (_diff(ir.model_dump(), new.model_dump()) if new else [])


def _diff(a, b, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(set(a) | set(b)) for d in _diff(a.get(k), b.get(k), f"{path}.{k}".lstrip("."))]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for n, (x, y) in enumerate(zip(a, b, strict=True)) for d in _diff(x, y, f"{path}[{n}]")]
    return [] if a == b else [f"{path}: {a!r} -> {b!r}"]
