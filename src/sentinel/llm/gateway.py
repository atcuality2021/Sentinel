"""LLM gateway — the swappable inference layer (SRS FR-11 / NFR-06).

The sovereignty thesis lives here: orchestration never names a backend. It asks the gateway to
*build a model* from the config (``SentinelConfig.backend``) — either a Gemini model-id string
(cloud) or a ``LiteLlm`` bound to a customer-controlled vLLM server (on-prem). Swapping is
config-only, with zero changes to agents, tools, or the private-data path.

ONE source of truth: model id + endpoint + default backend all come from ``SentinelConfig`` (edited
in the Settings UI, persisted to ``sentinel.config.yaml``). The ONLY value read from the environment
here is the **secret API key** — keys never live in config. ``build_model`` is the single factory;
nothing else constructs a model object.
"""

from __future__ import annotations

import os
from pathlib import Path

# ADK accepts either a model-id string (Gemini) or a BaseLlm instance (e.g. LiteLlm).
# We keep the return type loose on purpose so callers stay backend-agnostic.
Model = object

# Load .env once at import time so keys are always available regardless of how the process
# was launched (uvicorn, python -m sentinel, pytest, direct script).  dotenv skips keys
# already present in os.environ so this never overrides explicit environment settings.
try:
    from dotenv import load_dotenv as _ld

    _ld(dotenv_path=Path(__file__).parents[3] / ".env", override=False)
except Exception:  # pragma: no cover — dotenv absent or .env missing are both fine
    pass


def _vllm_api_key(api_base: str | None) -> str:  # noqa: ARG001 — api_base reserved for future per-host keys
    """Resolve the vLLM secret — env only, never config/args (SENTINEL-011).

    Priority: VLLM_API_KEY → ATCUALITY_API_KEY → BILTIQ_LLM_KEY → "not-needed".
    ATCUALITY_API_KEY is the unified gateway key for all atcuality.com-hosted endpoints.
    BILTIQ_LLM_KEY covers environments started from the BiltIQ platform launcher.
    VLLM_API_KEY is kept for backwards-compat with deployments that set it explicitly.
    """
    return (
        os.getenv("VLLM_API_KEY")
        or os.getenv("ATCUALITY_API_KEY")
        or os.getenv("BILTIQ_LLM_KEY")
        or "not-needed"
    )


def build_model(
    backend: str,
    model_id: str,
    api_base: str | None = None,
    *,
    response_format: dict | None = None,
) -> Model:
    """Pure factory: (backend, model_id, api_base) → a model object ADK accepts.

    ``gemini`` → the model-id string; ``vllm`` → a ``LiteLlm`` bound to the OpenAI-compatible
    endpoint. The model id and ``api_base`` are supplied by the caller from config
    (``cfg.backend.vllm.*``). The api **key** is the one secret — selected by endpoint host via
    :func:`_vllm_api_key` and read from the environment, never persisted. This is the single place a
    model object is constructed.

    ``response_format`` (vLLM only) is forwarded to litellm as an extra completion arg — ADK's
    ``LiteLlm`` stashes ``**kwargs`` in ``_additional_args`` and merges them into every completion
    call, overriding its own default. For a structured-output agent we pass
    ``{"type":"json_schema","json_schema":{...}}`` so vLLM *guided-decodes* valid, terminating JSON:
    without it the gemma-4-26B reasoner free-generates and degenerates into a whitespace loop that
    truncates at max_output_tokens (proven live 2026-06-08). Omitted ⇒ byte-identical to before.
    """
    if backend == "vllm":
        try:
            from google.adk.models.lite_llm import LiteLlm
        except ImportError as e:  # pragma: no cover - environment guard
            raise RuntimeError(
                "vLLM backend needs LiteLlm: pip install 'google-adk[extensions]'"
            ) from e
        extra: dict = {}
        if response_format is not None:
            extra["response_format"] = response_format
        # litellm routes the 'hosted_vllm/' prefix to an OpenAI-compatible vLLM endpoint.
        return LiteLlm(
            model=f"hosted_vllm/{model_id}",
            api_base=api_base or "http://localhost:8000/v1",
            api_key=_vllm_api_key(api_base),  # the only env read: the secret, by host
            **extra,
        )
    if backend == "gemini":
        return model_id
    raise ValueError(f"Unknown backend {backend!r} (expected 'gemini' or 'vllm')")


def resolve_backend(backend: str | None = None) -> str:
    """Resolve the backend NAME. Explicit arg wins; else the env bootstrap; else 'gemini'.

    The run path always passes an explicit value (``cfg.backend.default``), so the env fallback only
    applies to a bare call. ``SENTINEL_LLM_BACKEND`` is a first-boot bootstrap, never a live override
    of the saved config.
    """
    name = (backend or os.getenv("SENTINEL_LLM_BACKEND", "gemini")).lower()
    if name not in ("gemini", "vllm"):
        raise ValueError(f"Unknown backend {name!r} (expected 'gemini' or 'vllm')")
    return name


def active_backend(backend: str | None = None) -> str:
    """Name of the active backend, for traces and labels — an alias of :func:`resolve_backend`."""
    return resolve_backend(backend)
