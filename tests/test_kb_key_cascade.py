"""Tests for embedder and reranker key cascade.

Root cause: EMBED_API_KEY was not set in .env → 401 on all KB operations.
Fix: embedder and reranker cascade EMBED_API_KEY → VLLM_API_KEY → ATCUALITY_API_KEY
so any on-prem deployment with VLLM_API_KEY set gets KB for free.
"""
from __future__ import annotations

import importlib
import os


def _reload_embedder(env: dict) -> object:
    import sentinel.kb.embedder as mod
    importlib.reload(mod)
    return mod


# --------------------------------------------------------------------------- #
# Embedder _api_key cascade
# --------------------------------------------------------------------------- #

def test_embed_key_used_when_set(monkeypatch):
    monkeypatch.setenv("EMBED_API_KEY", "embed-key-123")
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    monkeypatch.delenv("ATCUALITY_API_KEY", raising=False)
    from sentinel.kb.embedder import _api_key
    assert _api_key() == "embed-key-123"


def test_vllm_key_used_when_embed_key_absent(monkeypatch):
    monkeypatch.delenv("EMBED_API_KEY", raising=False)
    monkeypatch.setenv("VLLM_API_KEY", "vllm-key-abc")
    monkeypatch.delenv("ATCUALITY_API_KEY", raising=False)
    from sentinel.kb.embedder import _api_key
    assert _api_key() == "vllm-key-abc"


def test_atcuality_key_used_when_only_atcuality_set(monkeypatch):
    monkeypatch.delenv("EMBED_API_KEY", raising=False)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc-key-xyz")
    from sentinel.kb.embedder import _api_key
    assert _api_key() == "atc-key-xyz"


def test_embed_key_takes_priority_over_vllm(monkeypatch):
    monkeypatch.setenv("EMBED_API_KEY", "embed-specific")
    monkeypatch.setenv("VLLM_API_KEY", "vllm-general")
    from sentinel.kb.embedder import _api_key
    assert _api_key() == "embed-specific"


def test_empty_string_returned_when_no_keys_set(monkeypatch):
    monkeypatch.delenv("EMBED_API_KEY", raising=False)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    monkeypatch.delenv("ATCUALITY_API_KEY", raising=False)
    from sentinel.kb.embedder import _api_key
    assert _api_key() == ""


# --------------------------------------------------------------------------- #
# Reranker key cascade
# --------------------------------------------------------------------------- #

def _reranker_key(env_patch: dict, monkeypatch) -> str:
    """Extract the key the reranker would use given the env patch."""
    for k in ("RERANK_API_KEY", "EMBED_API_KEY", "VLLM_API_KEY", "ATCUALITY_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env_patch.items():
        monkeypatch.setenv(k, v)
    return (
        os.environ.get("RERANK_API_KEY")
        or os.environ.get("EMBED_API_KEY")
        or os.environ.get("VLLM_API_KEY")
        or os.environ.get("ATCUALITY_API_KEY")
        or ""
    )


def test_reranker_uses_rerank_key_when_set(monkeypatch):
    key = _reranker_key({"RERANK_API_KEY": "rerank-specific", "VLLM_API_KEY": "vllm"}, monkeypatch)
    assert key == "rerank-specific"


def test_reranker_falls_back_to_embed_key(monkeypatch):
    key = _reranker_key({"EMBED_API_KEY": "embed-key"}, monkeypatch)
    assert key == "embed-key"


def test_reranker_falls_back_to_vllm_key(monkeypatch):
    key = _reranker_key({"VLLM_API_KEY": "vllm-key"}, monkeypatch)
    assert key == "vllm-key"


def test_reranker_falls_back_to_atcuality_key(monkeypatch):
    key = _reranker_key({"ATCUALITY_API_KEY": "atc-key"}, monkeypatch)
    assert key == "atc-key"


def test_reranker_empty_when_nothing_set(monkeypatch):
    key = _reranker_key({}, monkeypatch)
    assert key == ""
