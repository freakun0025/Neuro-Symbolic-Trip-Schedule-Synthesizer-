import openai
import pytest

from nstrip.extract.llm_client import CacheMiss, DiskCache, OpenAICompatClient, make_client


def client(tmp_path, live=True):
    return OpenAICompatClient("m", base_url="http://example/v1", cache=DiskCache(tmp_path), live=live)


def bad_request(msg="response_format not supported"):
    e = openai.BadRequestError.__new__(openai.BadRequestError)  # skip the HTTP-response plumbing
    Exception.__init__(e, msg)
    return e


def test_cache_replays_without_network(tmp_path, monkeypatch):
    c = client(tmp_path)
    calls = []
    monkeypatch.setattr(c, "_create", lambda **kw: calls.append(kw) or "hello")
    msgs = [{"role": "user", "content": "hi"}]
    assert c.chat(msgs) == "hello" and c.chat(msgs) == "hello"
    assert len(calls) == 1 and c.stats["cache_hits"] == 1
    offline = client(tmp_path, live=False)
    assert offline.chat(msgs) == "hello"
    with pytest.raises(CacheMiss):
        offline.chat([{"role": "user", "content": "never asked"}])


def test_cache_key_includes_provider_and_model(tmp_path):
    a = DiskCache.key(base_url="x", model="m", messages=[])
    assert a != DiskCache.key(base_url="y", model="m", messages=[]) != DiskCache.key(base_url="x", model="n",
                                                                                      messages=[])


def test_schema_mode_falls_back_once_per_client(tmp_path, monkeypatch):
    c = client(tmp_path)
    seen = []

    def create(**kw):
        mode = kw.get("response_format", {}).get("type", "text")
        seen.append(mode)
        if mode == "json_schema":
            raise bad_request()
        return "{}"

    monkeypatch.setattr(c, "_create", create)
    c.chat([{"role": "user", "content": "a"}], json_schema={"type": "object"})
    c.chat([{"role": "user", "content": "b"}], json_schema={"type": "object"})
    assert seen == ["json_schema", "json_object", "json_object"] and c.stats["format_fallbacks"] == 1


def test_rejected_seed_is_dropped_without_losing_the_format(tmp_path, monkeypatch):
    c = client(tmp_path)  # Gemini's OpenAI endpoint: 400 'Unknown name "seed"'
    seen = []

    def create(**kw):
        seen.append(("seed" in kw, kw.get("response_format", {}).get("type", "text")))
        if "seed" in kw:
            raise bad_request('Unknown name "seed": Cannot find field.')
        return "{}"

    monkeypatch.setattr(c, "_create", create)
    c.chat([{"role": "user", "content": "a"}], json_schema={"type": "object"}, seed=1)
    c.chat([{"role": "user", "content": "b"}], json_schema={"type": "object"}, seed=1)
    assert seen == [(True, "json_schema"), (False, "json_schema"), (False, "json_schema")]
    assert c.stats["format_fallbacks"] == 0


def test_make_client_reads_roles_from_env(monkeypatch):
    for k in ("NSTRIP_MODEL", "NSTRIP_BASELINE_MODEL", "OPENAI_BASE_URL", "NSTRIP_BASELINE_BASE_URL", "NSTRIP_MODE"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="NSTRIP_MODEL"):
        make_client("extract")
    monkeypatch.setenv("NSTRIP_MODEL", "small")
    monkeypatch.setenv("NSTRIP_BASELINE_MODEL", "big")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("NSTRIP_BASELINE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    monkeypatch.setenv("NSTRIP_MODE", "cache")
    ext, base = make_client("extract"), make_client("baseline")
    assert (ext.model, ext.base_url, ext.live) == ("small", "https://api.groq.com/openai/v1", False)
    assert (base.model, base.base_url) == ("big", "https://generativelanguage.googleapis.com/v1beta/openai")
