"""The whole pipeline (ARCHITECTURE §2): extract -> ground -> compile -> solve -> check -> explain.

The only path from LLM output into Z3 is TripRequestIR validation -> ground() -> compile_problem().
Errors become statuses in the result, never exceptions that reach the UI.
"""

import difflib
import re
import time

from nstrip.checker.checker import check_plan
from nstrip.config import SOLVER_TIMEOUT_MS
from nstrip.encode.compiler import compile_problem
from nstrip.explain.rephrase import rephrase
from nstrip.explain.templates import describe, render_diagnosis, render_plan
from nstrip.extract.extractor import extract, verify
from nstrip.extract.llm_client import LLMClient
from nstrip.ground import ground
from nstrip.kb.loader import KB
from nstrip.models.ir import TripRequestIR
from nstrip.models.plan import PipelineResult, Status
from nstrip.solve import solve
from nstrip.solve.solver import make_solver


def suggest(mention: str, kb: KB) -> str:
    names = {p.name.lower(): p.name for p in kb.places.values()}
    names |= {a: p.name for p in kb.places.values() for a in p.aliases}
    close = difflib.get_close_matches(mention.lower(), list(names), n=2, cutoff=0.6)
    return f" (did you mean {' or '.join(dict.fromkeys(names[c] for c in close))}?)" if close else ""


def run_pipeline(text: str | None, kb: KB, client: LLMClient | None = None, ir: TripRequestIR | None = None,
                 rephrase_client: LLMClient | None = None, verify_client: LLMClient | None = None,
                 timeout_ms: int = SOLVER_TIMEOUT_MS) -> PipelineResult:
    """Give `text` + `client` to extract, or `ir` to skip the LLM (edited IR in the UI, oracle runs)."""
    timings: dict[str, float] = {}
    attempts = 0

    def tick(stage: str, t0: float) -> None:
        timings[stage] = round((time.perf_counter() - t0) * 1000, 2)

    if ir is None:
        if client is None or not text:
            raise ValueError("run_pipeline needs text and a client, or an ir")
        t0 = time.perf_counter()
        try:
            ir, attempts, err = extract(text, kb, client)
        except Exception as e:  # noqa: BLE001  network, auth, cache miss: a status, never a crash
            return PipelineResult(status=Status.EXTRACTION_FAILED, error=f"{type(e).__name__}: {e}",
                                  explanation="The language model could not be reached, so nothing was planned.")
        tick("extract", t0)
        if ir is None:
            return PipelineResult(status=Status.EXTRACTION_FAILED, llm_attempts=attempts, error=err,
                                  timings_ms=timings,
                                  explanation="The request could not be turned into valid constraints.")

    def stop(status: Status, explanation: str, **extra) -> PipelineResult:
        return PipelineResult(status=status, ir=ir, explanation=explanation, timings_ms=timings,
                              llm_attempts=attempts, **extra)

    if ir.unresolved_mentions:
        unknown = "; ".join(f"{m}{suggest(m, kb)}" for m in ir.unresolved_mentions)
        return stop(Status.NEEDS_CLARIFICATION,
                    f"These places are not in the {kb.city} knowledge base: {unknown}. "
                    "Nothing was dropped silently; please rephrase or choose places from the list.")
    if not ir.activities:
        return stop(Status.NEEDS_CLARIFICATION, "No places from the knowledge base were mentioned.")

    t0 = time.perf_counter()
    try:
        p = ground(ir, kb, "extracted")
    except ValueError as e:
        return stop(Status.NEEDS_CLARIFICATION, str(e))
    enc = compile_problem(p)
    readable = [f"{c}: {t.readable}" for c, t in enc.tracked.items()]
    smtlib = make_solver(enc).sexpr()
    tick("ground_compile", t0)

    t0 = time.perf_counter()
    status, plan, diag = solve(p, timeout_ms)
    tick("solve", t0)
    result = {"problem": p, "constraints_readable": readable, "smtlib": smtlib}

    if status == Status.SOLVER_TIMEOUT:
        return stop(status, "The solver ran out of time; no answer is given rather than a guess.", **result)
    if status == Status.SAT:
        report = check_plan(p, plan)
        if not report.ok:  # the encoder and the independent checker disagree: a compiler bug
            return stop(Status.INTERNAL_ERROR, "Internal error: the plan failed independent verification.",
                        error="; ".join(v.detail for v in report.violations), **result)
        text_out = render_plan(p, plan, kb.currency)
    else:
        if verify_client is not None and text:  # optional solver -> LLM feedback, one round (FR-27)
            return _verified(text, kb, ir, p, diag, verify_client, rephrase_client, timeout_ms,
                             stop(status, render_diagnosis(p, diag, kb.currency), plan=plan, diagnosis=diag,
                                  **result))
        text_out = render_diagnosis(p, diag, kb.currency)

    source = "template"
    if rephrase_client is not None:
        text_out, source = rephrase(text_out, rephrase_client, [a.name for a in p.activities])
    return stop(status, text_out, plan=plan, diagnosis=diag, explanation_source=source, **result)


def _verified(text, kb, ir, p, diag, client, rephrase_client, timeout_ms, first: PipelineResult) -> PipelineResult:
    """Show the LLM the user requirements in the minimal conflict (never the place facts) and let it correct its
    own extraction. A changed form goes through validation, grounding and the solver again like any other."""
    # plain sentences, minus the KB facts in brackets (durations, prices): the LLM checks only what the user said
    user_core = [re.sub(r" \(.*\)$", "", describe(c, p, kb.currency)) for c in diag.core
                 if c not in diag.world_facts]
    t0 = time.perf_counter()
    try:
        new, changes = verify(text, ir, user_core, kb, client)
    except Exception as e:  # noqa: BLE001  verification is optional: keep the first answer
        return first.model_copy(update={"error": f"verification failed: {type(e).__name__}: {e}"})
    ms = round((time.perf_counter() - t0) * 1000, 2)
    if new is None or not changes:
        return first.model_copy(update={"verify_changes": [], "llm_attempts": first.llm_attempts + 1,
                                        "timings_ms": first.timings_ms | {"verify": ms}})
    again = run_pipeline(None, kb, ir=new, rephrase_client=rephrase_client, timeout_ms=timeout_ms)
    note = "\n\nThe language model re-read your request and corrected: " + "; ".join(changes)
    return again.model_copy(update={"verify_changes": changes, "llm_attempts": first.llm_attempts + 1,
                                    "explanation": again.explanation + note,
                                    "timings_ms": first.timings_ms | {"verify": ms}})
