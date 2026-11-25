"""One OpenAI-compatible client for every provider (D16). The provider is the base URL, the model is a name.

Every call goes through a disk cache keyed by (base URL, model, messages, schema, temperature, seed), and the
cache is committed, so benchmark runs replay offline. Tests use FakeClient and never touch the network.
"""

import hashlib
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import openai

import nstrip.config  # noqa: F401  (loads .env)

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "llm"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
ROLES = ("extract", "baseline", "codegen", "paraphrase", "rephrase")


class CacheMiss(RuntimeError):
    pass


class LLMClient(Protocol):
    base_url: str
    model: str

    def chat(self, messages: list[dict], json_schema: dict | None = None,
             temperature: float = 0.0, seed: int | None = None) -> str: ...


class DiskCache:
    def __init__(self, root: Path = CACHE_DIR):
        self.root = root

    @staticmethod
    def key(**request) -> str:
        return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()

    def get(self, key: str) -> str | None:
        f = self.root / f"{key}.json"
        return json.loads(f.read_text())["response"] if f.exists() else None

    def put(self, key: str, request: dict, response: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{key}.json").write_text(json.dumps({"request": request, "response": response}, indent=1))


class OpenAICompatClient:
    """Asks for json_schema output, falls back to json_object, then to plain text, once per client.
    Pydantic validation downstream is the only authority, so a weaker mode only costs retries."""

    RETRYABLE = (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                 openai.InternalServerError)

    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None,
                 cache: DiskCache | None = None, live: bool = True, max_tries: int = 5):
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.cache = cache or DiskCache()
        self.live = live
        self.max_tries = max_tries
        self._api_key = api_key
        self._sdk: openai.OpenAI | None = None
        self._modes = ["json_schema", "json_object", "text"]
        self._seed_ok = True  # False once the provider rejects the seed field
        self.stats = {"calls": 0, "cache_hits": 0, "format_fallbacks": 0}

    def chat(self, messages, json_schema=None, temperature=0.0, seed=None) -> str:
        request = {"base_url": self.base_url, "model": self.model, "messages": messages,
                   "json_schema": json_schema, "temperature": temperature, "seed": seed}
        key = self.cache.key(**request)
        if (hit := self.cache.get(key)) is not None:
            self.stats["cache_hits"] += 1
            return hit
        if not self.live:
            raise CacheMiss(f"no cached response for {self.model} (NSTRIP_MODE=cache)")
        text = self._call(messages, json_schema, temperature, seed)
        self.cache.put(key, request, text)
        return text

    def _call(self, messages, json_schema, temperature, seed) -> str:
        while True:
            mode = self._modes[0] if json_schema else "text"
            kwargs = {"model": self.model, "messages": messages, "temperature": temperature}
            if seed is not None and self._seed_ok:
                kwargs["seed"] = seed
            if mode == "json_schema":
                kwargs["response_format"] = {"type": "json_schema",
                                             "json_schema": {"name": "response", "schema": json_schema}}
            elif mode == "json_object":
                kwargs["response_format"] = {"type": "json_object"}
            try:
                return self._with_backoff(kwargs)
            except openai.BadRequestError as e:
                if "seed" in kwargs and "seed" in f"{e} {getattr(e, 'body', '')}":  # e.g. Gemini: no seed field; the cache key keeps it
                    self._seed_ok = False
                    continue
                if mode == "text":
                    raise
                self._modes.pop(0)  # this provider rejects the mode: remember and step down
                self.stats["format_fallbacks"] += 1

    def _with_backoff(self, kwargs) -> str:
        for attempt in range(self.max_tries):
            try:
                self.stats["calls"] += 1
                return self._create(**kwargs)
            except self.RETRYABLE:
                if attempt == self.max_tries - 1:
                    raise
                time.sleep(min(60, 2 ** attempt * 2))  # free tiers have per-minute limits
        raise AssertionError("unreachable")

    def _create(self, **kwargs) -> str:  # the only network call; tests replace it
        if self._sdk is None:
            self._sdk = openai.OpenAI(api_key=self._api_key or "missing-key", base_url=self.base_url)
        resp = self._sdk.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


class FakeClient:
    """Scripted responses for tests: each item is a string or a function of the messages."""

    def __init__(self, responses: list[str | Callable[[list[dict]], str]], model: str = "fake"):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.model, self.base_url = model, "fake://"

    def chat(self, messages, json_schema=None, temperature=0.0, seed=None) -> str:
        self.calls.append({"messages": messages, "json_schema": json_schema})
        r = self.responses.pop(0)
        return r(messages) if callable(r) else r


def make_client(role: str, model: str | None = None, live: bool | None = None) -> OpenAICompatClient:
    """Resolve a role's client from the environment: NSTRIP_<ROLE>_MODEL, else NSTRIP_MODEL;
    NSTRIP_<ROLE>_BASE_URL / _API_KEY, else OPENAI_BASE_URL / OPENAI_API_KEY; NSTRIP_MODE=cache -> offline."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; one of {ROLES}")
    r = role.upper()
    model = model or os.getenv(f"NSTRIP_{r}_MODEL") or os.getenv("NSTRIP_MODEL")
    if not model:
        raise RuntimeError(f"no model for role {role!r}: set NSTRIP_MODEL (or NSTRIP_{r}_MODEL) in .env")
    if live is None:
        live = os.getenv("NSTRIP_MODE", "live") != "cache"
    return OpenAICompatClient(
        model=model,
        base_url=os.getenv(f"NSTRIP_{r}_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv(f"NSTRIP_{r}_API_KEY") or os.getenv("OPENAI_API_KEY"),
        live=live,
    )
