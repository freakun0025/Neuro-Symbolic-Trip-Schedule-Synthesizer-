"""Solver results and the pipeline's output (spec §2.4)."""

from enum import StrEnum
from typing import Literal

from nstrip.models import Minute, Model
from nstrip.models.ir import TripRequestIR
from nstrip.models.problem import ProblemInstance


class Status(StrEnum):
    SAT = "SAT"
    UNSAT = "UNSAT"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Visit(Model):
    location_id: str
    start: Minute
    end: Minute


class Plan(Model):
    visits: list[Visit]  # sorted by start
    total_cost: int
    optimal: bool = True  # False if Optimize timed out and a merely feasible model was used


class Relaxation(Model):
    cid: str
    action: Literal["raise_budget", "extend_horizon_end", "widen_window", "drop_must_visit", "drop_precedence"]
    old_value: int | None = None
    new_value: int | None = None  # None for drops
    restores_feasibility: bool


class Diagnosis(Model):
    core: list[str]  # cids, minimal
    raw_core_size: int  # size of Z3's unsat_core() before minimisation
    is_minimal: bool  # False only if a minimisation check timed out
    world_facts: list[str]  # core members of kind OPENING or SHOWTIME
    relaxations: list[Relaxation]
    solver_calls: int


class PipelineResult(Model):
    status: Status
    ir: TripRequestIR | None = None
    problem: ProblemInstance | None = None
    constraints_readable: list[str] = []
    smtlib: str | None = None
    plan: Plan | None = None
    diagnosis: Diagnosis | None = None
    explanation: str = ""
    explanation_source: Literal["template", "llm_rephrase"] = "template"
    timings_ms: dict[str, float] = {}
    llm_attempts: int = 0
    error: str | None = None
    verify_changes: list[str] | None = None  # None = no verification ran; [] = the LLM confirmed its form
