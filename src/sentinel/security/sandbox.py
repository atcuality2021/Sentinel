"""Tool output sandbox — defense-in-depth validation layer (SENTINEL-016 G-12).

Checks tool/search results for prompt injection, malicious URL schemes, and
PII bleed before they flow to the synthesizer. This is additive: a flagged
result is sanitized (not dropped) so the run degrades gracefully rather than
crashing. Security boundaries are enforced by the governance layer; this module
adds a best-effort detection pass on uncontrolled third-party text.

Usage::

    result = validate_tool_output(raw_text, entity="acme", context="search")
    if not result.safe:
        logger.warning("sandbox flagged: %s", result.reason)
    text_to_use = result.sanitized
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns that suggest prompt-injection attempts in tool output.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I),
    re.compile(r"system\s*:\s*you\s+are\s+now", re.I),
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"\[\s*INST\s*\]", re.I),
    re.compile(r"###\s*(system|instruction|prompt)\b", re.I),
    re.compile(r"<\|im_start\|>", re.I),
]

# URL schemes that should never appear in research output.
_DANGEROUS_SCHEMES: re.Pattern = re.compile(
    r"\b(javascript|data|vbscript|file|blob):", re.I
)

# Patterns that look like leaked credentials or PII.
_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key", re.compile(r"\b(AKIA|sk-|ghp_|xox[baprs]-)[A-Za-z0-9/+]{16,}", re.I)),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13})\b")),
]

_REDACTED = "[REDACTED]"


@dataclass
class SandboxResult:
    safe: bool
    reason: str
    sanitized: str


def validate_tool_output(
    text: str,
    *,
    entity: str = "",
    context: str = "tool",
) -> SandboxResult:
    """Validate and sanitize ``text`` returned by a tool or search provider.

    Returns a :class:`SandboxResult`. ``sanitized`` is always safe to pass to
    the synthesizer — injection patterns are stripped, PII is redacted.
    Never raises (fail-soft).
    """
    if not text:
        return SandboxResult(safe=True, reason="", sanitized=text)

    try:
        issues: list[str] = []
        sanitized = text

        # Prompt injection check
        for pat in _INJECTION_PATTERNS:
            if pat.search(sanitized):
                issues.append(f"prompt_injection({pat.pattern[:30]})")
                sanitized = pat.sub("[FILTERED]", sanitized)

        # Dangerous URL scheme check
        if _DANGEROUS_SCHEMES.search(sanitized):
            issues.append("dangerous_url_scheme")
            sanitized = _DANGEROUS_SCHEMES.sub("[FILTERED_SCHEME]:", sanitized)

        # PII / credential check
        for label, pat in _PII_PATTERNS:
            if pat.search(sanitized):
                issues.append(f"pii_{label}")
                sanitized = pat.sub(_REDACTED, sanitized)

        safe = len(issues) == 0
        reason = "; ".join(issues) if issues else ""
        return SandboxResult(safe=safe, reason=reason, sanitized=sanitized)

    except Exception:
        # Fail-soft: if the validator itself errors, pass the text through unchanged.
        return SandboxResult(safe=True, reason="validator_error", sanitized=text)
