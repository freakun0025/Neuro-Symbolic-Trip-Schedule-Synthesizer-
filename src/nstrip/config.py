"""Defaults and environment. LLM provider/model settings live in .env (see .env.example)."""

from dotenv import load_dotenv

load_dotenv()

SOLVER_TIMEOUT_MS = 10_000  # feasibility, core minimisation, relaxations
OPTIMISE_TIMEOUT_MS = 3_000  # choosing the best optional subset; on timeout a greedy plan is flagged optimal=False
# Stage 2 (order and times) is cut off by Z3's deterministic work counter, not the clock, so a busy machine
# cannot change the plan. The largest need on the benchmark and demos is ~3.4M (inst_011).
STAGE2_RLIMIT = 4_000_000
DEFAULT_DAY_START = 9 * 60  # 09:00, used when the request gives no start (logged in assumed_defaults)
DEFAULT_DAY_END = 21 * 60  # 21:00, used when the request gives no end
MAX_RETRIES = 3  # extraction: first attempt + up to 3 retries with the validation error fed back
