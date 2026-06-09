"""Governance routing — the sovereignty "brain" the orchestrator obeys (SENTINEL-005).

Pure functions over :class:`SentinelConfig`. They translate the operator's policy
(``governance.compliance_mode`` + ``block_cloud_on_private``, set in Settings) into two concrete
decisions the run path enforces structurally:

  - which *reasoning* backend a run may use (cloud Gemini vs on-prem vLLM), and
  - which *public-search* provider grounds it (Gemini's ``google_search`` vs a non-cloud tool).

The no-cloud guarantee in ``on_prem_required`` is not a prompt instruction — it is realized by
``effective_backend`` returning ``"vllm"`` (so ``resolve_model`` never builds a Gemini object) and
``effective_search_provider`` never returning ``"gemini"`` (so ``google_search`` is never attached).
Holds no secrets and performs no I/O.
"""

from __future__ import annotations

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


def effective_search_provider(cfg: SentinelConfig, *, allow_cloud: bool) -> str:
    """Resolve the public-search provider, after applying policy (AC-4, AC-5).

    When cloud is not allowed but the configured provider is ``gemini``, fall back to the
    configured non-cloud provider (default ``duckduckgo``) so a sovereign run still has web eyes.
    """
    provider = cfg.search.provider
    if not allow_cloud and provider == "gemini":
        return cfg.search.onprem_fallback
    return provider
