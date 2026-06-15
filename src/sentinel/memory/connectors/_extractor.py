# src/sentinel/memory/connectors/_extractor.py
"""Lightweight LLM-backed fact extractor for the Self-Driving Memory Brain.

Uses a direct litellm call (same pattern as dag.py chunked synthesis) against the
12B tool-caller model tier so we never spin up a full ADK runner just to parse text.
Always fails soft — any error returns [].
"""
from __future__ import annotations

import json
import logging

from sentinel.memory.connectors.base import SourceFinding, SOURCE_TYPES
from sentinel.memory.schema import DataBoundary

log = logging.getLogger(__name__)

_MAX_RAW_CHARS = 4000
_MAX_FINDINGS = 20
_MIN_TEXT_LEN = 10

_EXTRACT_PROMPT = """\
You are a precise fact extractor. Given raw content about "{entity}", extract factual findings.

Return a JSON array (only the array, no preamble) of objects with these fields:
  "text": a single self-contained factual sentence (no pronouns, include the entity name)
  "evidence": the verbatim quote or URL snippet that supports it

Rules:
- Each "text" must be ≥ 10 characters and a complete sentence.
- Maximum 20 items.
- If no facts are extractable, return [].
- Respond with ONLY the JSON array, nothing else.

Raw content:
{raw_text}
"""


async def extract_findings(
    entity: str,
    source_type: SOURCE_TYPES,
    raw_text: str,
    source_url: str,
    *,
    trust_score: float,
    boundary: DataBoundary,
) -> list[SourceFinding]:
    """Extract structured SourceFindings from raw text via the 12B tool-caller model.

    Truncates raw_text to _MAX_RAW_CHARS, calls the model, parses JSON,
    and returns at most _MAX_FINDINGS findings. Fails soft on any error.
    """
    truncated = raw_text[:_MAX_RAW_CHARS]
    prompt = _EXTRACT_PROMPT.format(entity=entity, raw_text=truncated)

    try:
        import litellm as _litellm
        from sentinel.config import get_config
        from sentinel.llm.gateway import _vllm_api_key

        cfg = get_config()
        backend = cfg.backend.default

        if backend == "vllm":
            roles = cfg.backend.roles or {}
            # Use the extractor role model (12B tool-caller tier) if configured,
            # falling back to the flat vllm option.
            opt = roles.get("extractor") or cfg.backend.vllm
            model_id = opt.model
            api_base = opt.api_base or "http://localhost:8000/v1"
            api_key = _vllm_api_key(api_base)

            resp = await _litellm.acompletion(
                model=f"hosted_vllm/{model_id}",
                messages=[{"role": "user", "content": prompt}],
                api_base=api_base,
                api_key=api_key,
                max_tokens=1024,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        else:
            # Gemini path — use litellm with the gemini model id
            import os
            gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
            resp = await _litellm.acompletion(
                model=cfg.backend.gemini.model,
                messages=[{"role": "user", "content": prompt}],
                api_key=gemini_key,
                max_tokens=1024,
                temperature=0.1,
            )

        raw_json = resp.choices[0].message.content or ""
        return _parse_response(raw_json, entity, source_type, source_url, trust_score, boundary)

    except Exception as exc:
        log.warning("extract_findings failed for %r (%s): %s", entity, source_type, exc)
        return []


def _parse_response(
    raw_json: str,
    entity: str,
    source_type: SOURCE_TYPES,
    source_url: str,
    trust_score: float,
    boundary: DataBoundary,
) -> list[SourceFinding]:
    """Parse the LLM JSON response into SourceFindings. Fails soft on bad JSON."""
    try:
        # The model may wrap the array in {"findings": [...]} due to json_object mode.
        parsed = json.loads(raw_json.strip())
        if isinstance(parsed, dict):
            # Unwrap common wrapper keys
            for key in ("findings", "results", "items", "data"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break
            else:
                # Try any list value
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
                else:
                    return []
        if not isinstance(parsed, list):
            return []

        findings: list[SourceFinding] = []
        for item in parsed[:_MAX_FINDINGS]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if len(text) < _MIN_TEXT_LEN:
                continue
            label = f"{source_type.capitalize()} — {entity}"
            findings.append(
                SourceFinding(
                    text=text,
                    boundary=boundary,
                    source_type=source_type,
                    source_url=source_url,
                    source_label=label,
                    trust_score=trust_score,
                )
            )
        return findings

    except Exception as exc:
        log.warning("_parse_response failed: %s | raw=%r", exc, raw_json[:200])
        return []
