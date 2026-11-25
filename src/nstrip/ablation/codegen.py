"""Hao-style ablation (ARCHITECTURE §8.1, D19): the LLM writes the Z3 program itself.

Same request text, same KB rows and travel times, same model as the pipeline; the only difference is
"LLM writes solver code" instead of "LLM fills a typed IR that a tested compiler encodes". Single-shot: this is
a simplification of Hao et al., not a reproduction (RISKS R24).

The generated code runs in a fresh `python -I` subprocess, in a temporary directory, with a timeout, only on
team-made benchmark instances (RISKS R23). It is never reachable from the UI.
"""

import json
import re
import subprocess
import sys
import tempfile

from nstrip.baseline.pure_llm import kb_rows
from nstrip.extract.llm_client import LLMClient
from nstrip.kb.loader import KB
from nstrip.models.plan import Plan, Visit

SYSTEM = """You translate a traveller's one-day trip request in {city} into a Python program that uses the z3
solver (`import z3`) to find a schedule satisfying EVERY requirement, or prove that none exists.

Facts (times in minutes since midnight, e.g. 09:00 = 540; money in whole {currency}):
Places (id | name | cost | typical duration | open-close | showtimes):
{places}
Travel times in minutes between places (row -> column):
{travel}

Rules of the domain: a visit lasts exactly its duration (the typical one unless the traveller gives one); it must
lie within opening hours; a show may only start at one of its showtimes; visits cannot overlap and consecutive
visits need the travel time between them; must-visit places are required, optional ones may be skipped;
budget is the sum of costs of visited places.

Contract: output ONE python code block. When run, the program must print exactly one final line:
either the word UNSAT, or a JSON list of objects {{"location_id": id, "start": minutes, "end": minutes}}
for the visited places. Do not read input, do not use the network, do not print anything after that line.

Example of the output format only: [{{"location_id": "museum", "start": 540, "end": 660}}]"""

CODE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def write_program(text: str, kb: KB, ids: list[str], client: LLMClient) -> str:
    places, travel = kb_rows(kb, ids)
    raw = client.chat([{"role": "system", "content": SYSTEM.format(city=kb.city, currency=kb.currency,
                                                                   places=places, travel=travel)},
                       {"role": "user", "content": text}])
    m = CODE.search(raw)
    return m.group(1) if m else raw


def run_program(code: str, timeout_s: int = 20) -> tuple[list[Visit] | None, str, str | None]:
    """-> (visits | None, "SAT" | "UNSAT" | "CRASH", stderr tail on crash)."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp, capture_output=True, text=True,
                               timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            return None, "CRASH", f"timeout after {timeout_s}s"
    lines = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    if r.returncode != 0 or not lines:
        return None, "CRASH", (r.stderr or "no output")[-800:]
    if lines[-1] == "UNSAT":
        return None, "UNSAT", None
    try:
        visits = [Visit(location_id=str(v["location_id"]), start=int(v["start"]), end=int(v["end"]))
                  for v in json.loads(lines[-1])]
    except (ValueError, TypeError, KeyError) as e:
        return None, "CRASH", f"unparseable output {lines[-1][:200]!r}: {e}"
    return sorted(visits, key=lambda v: v.start), "SAT", None


def run_codegen(text: str, kb: KB, ids: list[str], client: LLMClient,
                timeout_s: int = 20) -> tuple[Plan | None, str, str | None]:
    visits, outcome, err = run_program(write_program(text, kb, ids, client), timeout_s)
    if visits is None:
        return None, outcome, err
    cost = sum(kb.places[v.location_id].cost for v in visits if v.location_id in kb.places)
    return Plan(visits=visits, total_cost=cost), outcome, None
