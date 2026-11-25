"""Paraphrase part of the generated requests (FR-21), so extraction is not tested only on template phrasing.

A paraphrase is kept only if it has exactly the same numbers/times and every place name of the template;
otherwise it is retried (max 5) and the template stays. Every instance still needs a human review
(`reviewed_by` in the instance file and manifest.json).

    python -m nstrip.bench.paraphrase --fraction 0.5
"""

import argparse

from nstrip.bench.generate import BENCH_DIR, load_instances, write
from nstrip.explain.rephrase import guard_ok
from nstrip.extract.llm_client import LLMClient, make_client
from nstrip.kb.loader import load_kb

INSTRUCTIONS = ("Rewrite this one-day trip request the way a real traveller might type it: change the wording and "
                "the sentence order, informal is fine. Keep EVERY number, time (exactly as written, 24-hour HH:MM), "
                "money amount and place name exactly as written. Do not add, drop or change any requirement. "
                "Keep it clear which places are required and which are only 'if there is time'. Do not comment on "
                "the request (never say whether it is possible) and do not ask questions. "
                "Output only the rewritten request.")
# Review note (2026-11-25): 5 of the first 28 paraphrases passed the numbers/names guard but changed meaning
# (must-visit turned optional or vice versa, or added "that's impossible"); they were reverted to the template
# and the two last sentences above were added afterwards.


def paraphrase(template: str, names: list[str], client: LLMClient, tries: int = 5) -> str | None:
    for k in range(tries):
        out = client.chat([{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": template}],
                          temperature=0.7, seed=851 + k).strip()
        if guard_ok(template, out, names):
            return out
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fraction", type=float, default=0.5, help="share of instances to paraphrase (every k-th)")
    ap.add_argument("--model", help="override NSTRIP_PARAPHRASE_MODEL / NSTRIP_MODEL")
    args = ap.parse_args()
    kb, client = load_kb(), make_client("paraphrase", model=args.model)
    names = [p.name for p in kb.places.values()]
    step = max(1, round(1 / args.fraction)) if args.fraction > 0 else 0
    out, kept = [], 0
    for n, inst in enumerate(load_instances()):
        if step and n % step == 0:
            text = paraphrase(inst.request_template, [x for x in names if x in inst.request_template], client)
            if text:
                inst = inst.model_copy(update={"request_text": text, "paraphrase_model": client.model,
                                               "paraphrase_guard_passed": True, "reviewed_by": None})
                kept += 1
        out.append(inst)
    write(out, BENCH_DIR)
    print(f"paraphrased {kept} instances with {client.model}; review every instance before the final run")


if __name__ == "__main__":
    main()
