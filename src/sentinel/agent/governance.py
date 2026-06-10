"""Governance routing — the sovereignty "brain" the orchestrator obeys (SENTINEL-005).

Pure functions over :class:`SentinelConfig`. They translate the operator's policy
(``governance.compliance_mode`` + ``block_cloud_on_private``, set in Settings) into two concrete
decisions the run path enforces structurally:

  - which *reasoning* backend a run may use (cloud Gemini vs on-prem vLLM), and
  - which *public-search* provider grounds it (Gemini's ``google_search`` vs a non-cloud tool).

The no-cloud guarantee in ``on_prem_required`` is not a prompt instruction — it is realized by
``effective_backend`` returning ``"vllm"`` (so ``resolve_model`` never builds a Gemini object) and
``effective_search_provider`` never returning ``"gemini"`` (so ``google_search`` is never attached).
Holds no secrets and performs no I/O — except :func:`effective_search_provider` reads ``BRAVE_API_KEY``
from the environment to auto-upgrade DDG (anti-botted) to Brave when the key is present (SENTINEL-015).
"""

from __future__ import annotations

import os

from sentinel.config.schema import SentinelConfig
from sentinel.llm.gateway import resolve_backend


def cloud_allowed(cfg: SentinelConfig) -> bool:
    """Cloud (Gemini) egress is allowed unless the mode is ``on_prem_required`` (AC-1)."""
    return cfg.governance.compliance_mode != "on_prem_required"


def effective_backend(
    cfg: SentinelConfig, requested: str | None = None, *, private: bool = False
) -> str:
    """Resolve the reasoning backend a run may use, after applying policy (AC-2, AC-8).

    Forced to ``"vllm"`` when cloud is disallowed, or when this run touches the private boundary
    and ``block_cloud_on_private`` is set. Otherwise the requested backend (or the configured
    default) resolved through the gateway.
    """
    if not cloud_allowed(cfg):
        return "vllm"
    if private and cfg.governance.block_cloud_on_private:
        return "vllm"
    return resolve_backend(requested or cfg.backend.default)


def effective_search_provider(
    cfg: SentinelConfig, *, allow_cloud: bool, backend: str | None = None
) -> str:
    """Resolve the public-search provider, after applying policy (AC-4, AC-5) + runtime upgrade.

    Resolution order:
    1. Apply compliance + backend policy: ``google_search`` (Gemini builtin) only works with
       Google's API — it is NOT a callable function tool that LiteLlm can invoke. When cloud is
       disallowed OR the resolved backend is ``vllm``, fall back to ``onprem_fallback`` (usually
       ``duckduckgo``). Callers that have already resolved the backend should pass it explicitly;
       when omitted we derive it from ``cfg.backend.default``.
    2. Auto-upgrade DDG → Brave when ``BRAVE_API_KEY`` is set (SENTINEL-015 FR-09): DDG lite
       returns HTTP 202 anti-bot challenges with 0 results; Brave is already implemented in
       ``web_search.py``. Only ``duckduckgo`` is upgraded — any explicit non-DDG choice is honored.
    """
    provider = cfg.search.provider
    resolved_backend = backend if backend is not None else cfg.backend.default
    if (not allow_cloud or resolved_backend == "vllm") and provider == "gemini":
        provider = cfg.search.onprem_fallback
    if provider == "duckduckgo" and os.environ.get("BRAVE_API_KEY"):
        return "brave"
    return provider
