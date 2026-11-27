"""Benchmark instances and run records (spec §2.6)."""

from typing import Literal

from nstrip.models import Model
from nstrip.models.check import CheckReport
from nstrip.models.ir import TripRequestIR
from nstrip.models.plan import Diagnosis, Plan, Status, Visit

ConflictType = Literal["budget", "horizon", "window", "precedence_window", "precedence_cycle",
                       "showtime_clash", "two_conflicts", "other"]  # "other" = held-out only


class BenchmarkInstance(Model):
    id: str  # "inst_017" | "held_004"
    set: Literal["generated", "heldout"]
    n_locations: int
    budget_tightness: Literal["tight", "loose", "none"]
    expected_status: Literal["SAT", "UNSAT"]
    conflict_type: ConflictType | None = None
    seeded_conflict: list[str] | None = None  # cids
    seeded_conflicts: list[list[str]] | None = None  # two_conflicts only: the instance's only two minimal cores
    conflict_note: str | None = None  # held-out UNSAT: one-line arithmetic argument
    gold_ir: TripRequestIR
    witness_plan: Plan | None = None  # SAT only; must pass the checker
    request_template: str
    request_text: str
    paraphrase_model: str | None = None
    paraphrase_guard_passed: bool
    reviewed_by: str | None = None
    kb_version: str
    generator_seed: int | None = None  # None for held-out


class BaselineAnswer(Model):
    feasible: bool
    visits: list[Visit]  # empty if infeasible
    reason: str


class RunRecord(Model):
    run_id: str
    instance_id: str
    method: Literal["pipeline", "pipeline_verify", "oracle", "baseline", "codegen"]
    base_url: str
    model: str
    status: Status | Literal["BASELINE_SAT", "BASELINE_UNSAT", "BASELINE_FAILED",
                             "CODEGEN_SAT", "CODEGEN_UNSAT", "CODEGEN_CRASH"]
    extracted_ir: TripRequestIR | None = None
    plan: Plan | None = None
    diagnosis: Diagnosis | None = None
    check_vs_gold: CheckReport | None = None
    check_vs_extracted: CheckReport | None = None  # pipeline only; must be ok
    extraction_scores: dict | None = None  # per-kind tp/fp/fn
    error_classes: list[str] | None = None
    codegen_stderr: str | None = None
    core_sizes: dict[str, int] | None = None  # oracle UNSAT: raw, minimal, z3_minimize, calls
    error: str | None = None
    verify_changes: list[str] | None = None  # pipeline_verify: fields the LLM corrected
    timings_ms: dict[str, float] = {}
