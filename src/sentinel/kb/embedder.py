from __future__ import annotations

import os

from openai import OpenAI

_DEFAULT_BASE = "https://embed.atcuality.com/v1"
_DEFAULT_MODEL = "Qwen3-VL-Embedding-2B"


def _api_key() -> str:
    # Cascade: explicit embed key → vLLM key (same gateway) → atcuality key → empty.
    # Any on-prem deployment that sets VLLM_API_KEY gets embedding without a second key.
    return (
        os.environ.get("EMBED_API_KEY")
        or os.environ.get("VLLM_API_KEY")
        or os.environ.get("ATCUALITY_API_KEY")
        or ""
    )


def _client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("EMBED_API_BASE", _DEFAULT_BASE),
        api_key=_api_key(),
    )


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via Qwen3-VL endpoint. Returns vectors in input order."""
    if not texts:
        return []
    model = os.environ.get("EMBED_MODEL", _DEFAULT_MODEL)
    resp = _client().embeddings.create(model=model, input=texts)
    return [d.embedding for d in sorted(resp.data, key=lambda x: x.index)]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
