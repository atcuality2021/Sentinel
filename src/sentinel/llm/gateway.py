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
from urllib.parse import urlsplit

# ADK accepts either a model-id string (Gemini) or a BaseLlm instance (e.g. LiteLlm).
# We keep the return type loose on purpose so callers stay backend-agnostic.
Model = object


def _vllm_api_key(api_base: str | None) -> str:
    """Resolve the vLLM secret from the endpoint host — env only, never config/args (SENTINEL-011).

    The sovereign Gemma-4 gateway (``*.atcuality.com``: 12B tool-caller + 26B reasoner) authenticates
    with ``ATCUALITY_API_KEY``; any other vLLM endpoint keeps the historical ``VLLM_API_KEY``. The key
    is a pure function of *where* the request goes, so ``build_model`` keeps its signature and no
    caller has to pass a secret. Both fall back to ``"not-needed"`` for keyless local servers.
    """
    host = urlsplit(api_base or "").hostname or ""
    if host == "atcuality.com" or host.endswith(".atcuality.com"):
        return os.getenv("ATCUALITY_API_KEY", "not-needed")
    return os.getenv("VLLM_API_KEY", "not-needed")


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
