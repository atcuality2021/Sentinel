"""LLM gateway tests (SRS FR-11 / NFR-06): inference backend is config-only swappable.

One source of truth: ``build_model`` takes the model id + endpoint from config (the caller passes
``cfg.backend.vllm.*``); the ONLY environment read is the secret ``VLLM_API_KEY``. These tests pin
that — model/endpoint come from the arguments, never from ``VLLM_MODEL`` / ``VLLM_API_BASE`` env.
"""

from __future__ import annotations

import pytest

from sentinel.llm import gateway


def test_gemini_build_returns_model_id_string():
    # gemini → the model-id string, passed straight through (no env lookup)
    assert gateway.build_model("gemini", "gemini-2.5-flash") == "gemini-2.5-flash"
    assert gateway.build_model("gemini", "gemini-2.5-pro") == "gemini-2.5-pro"


def test_vllm_build_returns_litellm_object(monkeypatch):
    monkeypatch.setenv("VLLM_API_KEY", "k")
    m = gateway.build_model("vllm", "google/gemma-3-4b-it", "http://localhost:8000/v1")
    # Swap is config-only: a different model object, no orchestration change.
    assert type(m).__name__ == "LiteLlm"
    assert not isinstance(m, str)
    assert m.model == "hosted_vllm/google/gemma-3-4b-it"


def test_vllm_model_and_endpoint_come_from_args_not_env(monkeypatch):
    # env vars that LOOK like config must be ignored — the args (config) are authoritative
    monkeypatch.setenv("VLLM_MODEL", "SHOULD-BE-IGNORED")
    monkeypatch.setenv("VLLM_API_BASE", "http://should-be-ignored")
    m = gateway.build_model("vllm", "gemma-4-12B", "https://gemma.atcuality.com/v1")
    assert m.model == "hosted_vllm/gemma-4-12B"
    assert "ignored" not in (getattr(m, "api_base", "") or "")


def test_build_passes_env_key_and_arg_model_to_litellm(monkeypatch):
    """Capture exactly what build_model hands LiteLlm: model/endpoint from the ARGS (config),
    api_key from the ENV secret — the single source split, proven without LiteLlm internals."""
    import google.adk.models.lite_llm as lite

    captured: dict = {}

    class FakeLiteLlm:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(lite, "LiteLlm", FakeLiteLlm)
    monkeypatch.setenv("VLLM_API_KEY", "dummy-secret-value")
    monkeypatch.setenv("VLLM_MODEL", "SHOULD-BE-IGNORED")      # env config must be ignored
    monkeypatch.setenv("VLLM_API_BASE", "http://should-be-ignored")

    # A generic (non-atcuality) vLLM endpoint keeps the historical VLLM_API_KEY path. The
    # host-based ATCUALITY_API_KEY routing (SENTINEL-011) is covered in test_tiering.py (AC-1).
    gateway.build_model("vllm", "gemma-4-12B", "http://localhost:8000/v1")
    assert captured["model"] == "hosted_vllm/gemma-4-12B"        # from arg (config)
    assert captured["api_base"] == "http://localhost:8000/v1"    # from arg (config)
    assert captured["api_key"] == "dummy-secret-value"          # from env (secret) — only env read


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        gateway.build_model("azure", "whatever")


def test_resolve_backend_explicit_wins(monkeypatch):
    # env says one thing; an explicit value (e.g. cfg.backend.default, or the UI toggle) wins
    monkeypatch.setenv("SENTINEL_LLM_BACKEND", "gemini")
    assert gateway.resolve_backend("vllm") == "vllm"
    monkeypatch.setenv("SENTINEL_LLM_BACKEND", "vllm")
    assert gateway.resolve_backend("gemini") == "gemini"


def test_resolve_backend_env_is_only_a_bare_fallback(monkeypatch):
    monkeypatch.delenv("SENTINEL_LLM_BACKEND", raising=False)
    assert gateway.resolve_backend() == "gemini"  # bootstrap default
    monkeypatch.setenv("SENTINEL_LLM_BACKEND", "vllm")
    assert gateway.resolve_backend() == "vllm"


def test_resolve_backend_rejects_unknown():
    with pytest.raises(ValueError):
        gateway.resolve_backend("azure")


def test_active_backend_is_resolve_alias(monkeypatch):
    monkeypatch.setenv("SENTINEL_LLM_BACKEND", "gemini")
    assert gateway.active_backend() == "gemini"
    assert gateway.active_backend("vllm") == "vllm"
