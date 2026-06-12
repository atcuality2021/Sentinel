"""Settings helpers — parse + validate config edits before committing (SENTINEL-003).

Pure functions, no I/O. Each ``apply_*`` takes the live :class:`SentinelConfig`, edits a
**deep copy**, validates, and returns the new config; the caller commits via
``set_config(cfg, persist=True)`` only if no ``ValueError`` was raised. Keeping validation out of
the route bodies makes it unit-testable and guarantees a bad edit never half-writes the stored
config (spec NFR-2). Holds no secrets — keys stay in the environment (NFR-1).
"""

from __future__ import annotations

from collections.abc import Mapping

from sentinel.config.render import render_prompt
from sentinel.config.schema import (
    REASONER_ROLES,
    TOOL_CALLER_ROLES,
    AgentConfig,
    BackendOption,
    CoordinatorConfig,
    GenerationConfig,
    GovernanceConfig,
    PromptTemplate,
    SearchConfig,
    SentinelConfig,
    StrategyConfig,
)
from sentinel.strategy import discover_playbooks

_VALID_ROLES = TOOL_CALLER_ROLES | REASONER_ROLES

# Safe bounds for generation parameters (spec AC-3). Out-of-range → ValueError with a human msg.
_TEMP_MIN, _TEMP_MAX = 0.0, 2.0
_TOKENS_MIN, _TOKENS_MAX = 1, 32768
_TOP_P_MIN, _TOP_P_MAX = 0.0, 1.0
_TOP_K_MIN = 1

_VALID_BACKENDS = ("gemini", "vllm")
_VALID_COMPLIANCE = ("cloud_ok", "on_prem_preferred", "on_prem_required")
_VALID_PROVIDERS = ("gemini", "duckduckgo", "brave", "serpapi", "searxng")
_VALID_FALLBACKS = ("duckduckgo", "brave", "serpapi", "searxng")
_RESULTS_MIN, _RESULTS_MAX = 1, 20


def _as_float(raw: str, field: str, lo: float, hi: float) -> float:
    try:
        val = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number (got {raw!r}).") from None
    if not (lo <= val <= hi):
        raise ValueError(f"{field} must be between {lo} and {hi} (got {val}).")
    return val


def _as_int(raw: str, field: str, lo: int, hi: int | None = None) -> int:
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number (got {raw!r}).") from None
    if val < lo or (hi is not None and val > hi):
        bound = f"between {lo} and {hi}" if hi is not None else f"at least {lo}"
        raise ValueError(f"{field} must be {bound} (got {val}).")
    return val


def _blank(raw: object) -> bool:
    return raw is None or (isinstance(raw, str) and raw.strip() == "")


def parse_generation(form: Mapping[str, str], *, allow_blank: bool) -> GenerationConfig:
    """Build a bounds-checked :class:`GenerationConfig` from form fields.

    ``allow_blank=True`` (per-agent overrides): a blank field ⇒ ``None`` (inherit the global
    default). ``allow_blank=False`` (global defaults): every field is required and concrete.
    Out-of-range or non-numeric input raises ``ValueError`` (spec FR-4, AC-3).
    """
    def field(name: str, parser, *bounds):
        raw = form.get(name, "")
        if _blank(raw):
            if allow_blank:
                return None
            raise ValueError(f"{name} is required.")
        return parser(raw if not isinstance(raw, str) else raw.strip(), name, *bounds)

    return GenerationConfig(
        temperature=field("temperature", _as_float, _TEMP_MIN, _TEMP_MAX),
        max_output_tokens=field("max_output_tokens", _as_int, _TOKENS_MIN, _TOKENS_MAX),
        top_p=field("top_p", _as_float, _TOP_P_MIN, _TOP_P_MAX),
        top_k=field("top_k", _as_int, _TOP_K_MIN),
    )


def apply_backends(
    cfg: SentinelConfig,
    *,
    default: str,
    gemini_model: str,
    vllm_model: str,
    vllm_api_base: str,
) -> SentinelConfig:
    """Return a copy with backend default + model ids updated (spec AC-2)."""
    default = (default or "").strip().lower()
    if default not in _VALID_BACKENDS:
        raise ValueError(f"Backend must be one of {_VALID_BACKENDS} (got {default!r}).")
    if _blank(gemini_model):
        raise ValueError("Gemini model id is required.")
    if _blank(vllm_model):
        raise ValueError("vLLM model id is required.")
    if _blank(vllm_api_base):
        raise ValueError("vLLM API base URL is required.")

    new = cfg.model_copy(deep=True)
    new.backend.default = default  # type: ignore[assignment]  # validated against the literal above
    new.backend.gemini = BackendOption(model=gemini_model.strip())
    new.backend.vllm = BackendOption(model=vllm_model.strip(), api_base=vllm_api_base.strip())
    return new


def apply_generation(cfg: SentinelConfig, gen: GenerationConfig) -> SentinelConfig:
    """Return a copy with the global generation defaults replaced (spec AC-3)."""
    new = cfg.model_copy(deep=True)
    new.generation = gen
    return new


def apply_agent(
    cfg: SentinelConfig,
    key: str,
    *,
    enabled: bool,
    model: str | None,
    pin_gemini: bool,
    gen: GenerationConfig,
) -> SentinelConfig:
    """Return a copy with one agent's knobs updated. Unknown key ⇒ ``ValueError`` (spec AC-4)."""
    new = cfg.model_copy(deep=True)
    if key not in new.agents:
        raise ValueError(f"Unknown agent {key!r}.")
    new.agents[key] = AgentConfig(
        enabled=enabled,
        model=(model.strip() or None) if isinstance(model, str) else model,
        pin_gemini=pin_gemini,
        role=new.agents[key].role,  # preserve the capability tier (SENTINEL-011) — editing an
        generation=gen,             # agent's knobs must not silently reset its role
    )
    return new


def apply_prompt(cfg: SentinelConfig, key: str, template: str) -> SentinelConfig:
    """Return a copy with one prompt's template replaced, validated via ``render_prompt``.

    A template that drops a required ``{var}`` or adds an unknown one is rejected before commit
    (spec AC-5). The original ``variables`` and ``default_template`` are preserved so reset still
    works (AC-6, AC-7).
    """
    new = cfg.model_copy(deep=True)
    if key not in new.prompts:
        raise ValueError(f"Unknown prompt {key!r}.")
    if _blank(template):
        raise ValueError("Prompt template cannot be empty.")
    existing = new.prompts[key]
    candidate = PromptTemplate(
        template=template,
        variables=existing.variables,
        default_template=existing.default_template,
    )
    render_prompt(candidate)  # raises ValueError on a broken edit — caller never commits
    new.prompts[key] = candidate
    return new


def reset_prompt(cfg: SentinelConfig, key: str) -> SentinelConfig:
    """Return a copy with one prompt restored to its shipped ``default_template`` (spec AC-7)."""
    new = cfg.model_copy(deep=True)
    if key not in new.prompts:
        raise ValueError(f"Unknown prompt {key!r}.")
    existing = new.prompts[key]
    if existing.default_template is None:
        raise ValueError(f"Prompt {key!r} has no shipped default to reset to.")
    new.prompts[key] = PromptTemplate(
        template=existing.default_template,
        variables=existing.variables,
        default_template=existing.default_template,
    )
    return new


def create_prompt(cfg: SentinelConfig, key: str, template: str, variables: list[str]) -> SentinelConfig:
    """Return a copy with a brand-new custom prompt key added.

    Custom prompts have no shipped default (``default_template=None``) — they can be deleted
    but not reset. Raises if the key already exists (use ``apply_prompt`` to update) or if
    the template is empty.
    """
    new = cfg.model_copy(deep=True)
    key = key.strip()
    if not key:
        raise ValueError("Prompt key cannot be empty.")
    if key in new.prompts:
        raise ValueError(f"Prompt {key!r} already exists — use Save to update it.")
    if _blank(template):
        raise ValueError("Prompt template cannot be empty.")
    new.prompts[key] = PromptTemplate(
        template=template,
        variables=[v.strip() for v in variables if v.strip()],
        default_template=None,
    )
    return new


def delete_prompt(cfg: SentinelConfig, key: str) -> SentinelConfig:
    """Return a copy with a custom prompt removed.

    Only prompts without a shipped ``default_template`` may be deleted; shipped prompts must
    be reset instead (preserving the default as a fallback).
    """
    new = cfg.model_copy(deep=True)
    if key not in new.prompts:
        raise ValueError(f"Unknown prompt {key!r}.")
    if new.prompts[key].default_template is not None:
        raise ValueError(f"Cannot delete a shipped prompt — use Reset to restore the default.")
    del new.prompts[key]
    return new


def apply_memory(
    cfg: SentinelConfig,
    *,
    entity_memory: bool,
    retention_days: str | int,
    inject_org_prefs: bool,
    episodic_recall: bool = True,
    episodic_recall_top_k: str | int = 3,
    context_window_tokens: str | int = 2400,
) -> SentinelConfig:
    """Return a copy with memory settings updated (spec AC-8 + SENTINEL-015 + MEDIUM-07)."""
    days = _as_int(str(retention_days), "retention_days", 1)
    top_k = _as_int(str(episodic_recall_top_k), "episodic_recall_top_k", 1, 10)
    ctx_tokens = _as_int(str(context_window_tokens), "context_window_tokens", 800, 16000)
    new = cfg.model_copy(deep=True)
    new.memory.entity_memory = entity_memory
    new.memory.retention_days = days
    new.memory.inject_org_prefs = inject_org_prefs
    new.memory.episodic_recall = episodic_recall
    new.memory.episodic_recall_top_k = top_k
    new.memory.context_window_tokens = ctx_tokens
    return new


def apply_harness(
    cfg: SentinelConfig,
    *,
    max_turns: str | int,
    max_retries: str | int,
    base_retry_delay_s: str | float,
) -> SentinelConfig:
    """Return a copy with agent harness settings updated (SENTINEL-015 FR-06/FR-07).

    ``max_turns`` caps LLM calls per step (turn controller).
    ``max_retries`` + ``base_retry_delay_s`` configure the exponential-backoff retry policy.
    """
    turns = _as_int(str(max_turns), "max_turns", 1)
    retries = _as_int(str(max_retries), "max_retries", 1)
    delay = _as_float(str(base_retry_delay_s), "base_retry_delay_s", 0.0, 60.0)
    new = cfg.model_copy(deep=True)
    new.backend.max_turns = turns
    new.backend.max_retries = retries
    new.backend.base_retry_delay_s = delay
    return new


def apply_governance(
    cfg: SentinelConfig,
    *,
    compliance_mode: str,
    audit_log: bool,
    block_cloud_on_private: bool,
) -> SentinelConfig:
    """Return a copy with the sovereignty policy updated (SENTINEL-005 AC-9).

    A bad ``compliance_mode`` is rejected before commit so a typo can't silently weaken (or break)
    the policy. No secret is touched — provider keys stay in the environment (NFR-1).
    """
    mode = (compliance_mode or "").strip().lower()
    if mode not in _VALID_COMPLIANCE:
        raise ValueError(f"compliance_mode must be one of {_VALID_COMPLIANCE} (got {mode!r}).")
    new = cfg.model_copy(deep=True)
    new.governance = GovernanceConfig(
        compliance_mode=mode,  # type: ignore[arg-type]  # validated against the literal above
        audit_log=audit_log,
        block_cloud_on_private=block_cloud_on_private,
    )
    return new


def apply_search(
    cfg: SentinelConfig,
    *,
    provider: str,
    results: str | int,
    onprem_fallback: str,
) -> SentinelConfig:
    """Return a copy with the public-search provider updated (SENTINEL-005 AC-9).

    Validates the provider/fallback enums and the result count; provider API keys never pass
    through here (they live in the environment, shown only as pills).
    """
    p = (provider or "").strip().lower()
    if p not in _VALID_PROVIDERS:
        raise ValueError(f"Search provider must be one of {_VALID_PROVIDERS} (got {p!r}).")
    fb = (onprem_fallback or "").strip().lower()
    if fb not in _VALID_FALLBACKS:
        raise ValueError(f"On-prem fallback must be one of {_VALID_FALLBACKS} (got {fb!r}).")
    count = _as_int(str(results), "results", _RESULTS_MIN, _RESULTS_MAX)
    new = cfg.model_copy(deep=True)
    new.search = SearchConfig(
        provider=p,  # type: ignore[arg-type]  # validated above
        results=count,
        onprem_fallback=fb,  # type: ignore[arg-type]  # validated above
    )
    return new


def apply_models(
    cfg: SentinelConfig, roles: Mapping[str, Mapping[str, str]]
) -> SentinelConfig:
    """Return a copy with the per-role Gemma-4 model map updated (SENTINEL-011 AC-13).

    ``roles`` maps a role name → ``{'model': ..., 'api_base': ...}``. A blank model means that role
    is left unmapped (it falls back to the flat vLLM option). If no role is mapped, ``backend.roles``
    is set to ``None`` — tiering off, byte-identical to today. Unknown role names are rejected before
    commit. No secret passes through here — the endpoint key stays in the environment (NFR-1).
    """
    built: dict[str, BackendOption] = {}
    for role, opt in (roles or {}).items():
        r = (role or "").strip()
        if r not in _VALID_ROLES:
            raise ValueError(f"Unknown role {r!r} (expected one of {sorted(_VALID_ROLES)}).")
        model = (opt.get("model") or "").strip()
        api_base = (opt.get("api_base") or "").strip() or None
        if not model:
            continue  # blank model ⇒ role not mapped (flat vLLM fallback)
        built[r] = BackendOption(model=model, api_base=api_base)
    new = cfg.model_copy(deep=True)
    new.backend.roles = built or None
    return new


def apply_strategy(
    cfg: SentinelConfig,
    *,
    enabled: bool,
    playbook_dir: str,
    competitor_playbook: str,
    client_playbook: str,
) -> SentinelConfig:
    """Return a copy with the strategy overlay settings updated (SENTINEL-009 AC-14).

    When enabling, the selected playbook stems must exist as valid playbooks under ``playbook_dir``
    (checked via ``discover_playbooks``) so a typo can't enable a strategist with no framework. When
    disabled, the stems are stored but not validated (nothing runs). No secret is touched.
    """
    pdir = (playbook_dir or "").strip() or "playbooks"
    comp = (competitor_playbook or "").strip()
    clnt = (client_playbook or "").strip()
    if enabled:
        if not comp or not clnt:
            raise ValueError("Both competitor and client playbook stems are required when enabled.")
        available = {pb.name for pb in discover_playbooks(pdir)}
        for stem, label in ((comp, "competitor"), (clnt, "client")):
            if stem not in available:
                raise ValueError(
                    f"{label} playbook {stem!r} not found in {pdir!r} "
                    f"(available: {sorted(available)})."
                )
    new = cfg.model_copy(deep=True)
    new.strategy = StrategyConfig(
        enabled=enabled, playbook_dir=pdir,
        competitor_playbook=comp or "competitor-counterplay",
        client_playbook=clnt or "account-strategy",
    )
    return new


def create_agent(cfg: SentinelConfig, key: str, role: str, model: str | None) -> SentinelConfig:
    """Return a copy with a new custom agent key added.

    Custom agents can be deleted; built-in keys (those already present) must be edited via
    ``apply_agent``. Raises if key already exists or key is blank.
    """
    from sentinel.config.schema import Role
    import typing
    new = cfg.model_copy(deep=True)
    key = key.strip().replace(" ", "_")
    if not key:
        raise ValueError("Agent key cannot be empty.")
    if key in new.agents:
        raise ValueError(f"Agent {key!r} already exists — use Save to update it.")
    valid_roles: tuple[str, ...] = typing.get_args(Role)
    if role not in valid_roles:
        raise ValueError(f"Invalid role {role!r}. Valid: {', '.join(valid_roles)}")
    new.agents[key] = AgentConfig(
        enabled=True,
        model=(model.strip() or None) if isinstance(model, str) else None,
        role=role,  # type: ignore[arg-type]
    )
    return new


def delete_agent(cfg: SentinelConfig, key: str) -> SentinelConfig:
    """Return a copy with a custom agent removed.

    Built-in agents (those present in the default config) cannot be deleted — disable them instead.
    """
    from sentinel.config.defaults import build_default
    defaults = build_default()
    new = cfg.model_copy(deep=True)
    if key not in new.agents:
        raise ValueError(f"Unknown agent {key!r}.")
    if key in defaults.agents:
        raise ValueError(f"Cannot delete built-in agent {key!r} — disable it instead.")
    del new.agents[key]
    return new


def apply_coordinator(cfg: SentinelConfig, *, enabled: bool) -> SentinelConfig:
    """Return a copy with the A2A coordinator toggled (SENTINEL-011 AC-13).

    ``remote_private`` (Phase 2) is NOT operator-togglable here — it needs the ``a2a-sdk`` dependency
    + an ADR (AC-14), so the UI control is rendered disabled and this never enables it. The existing
    ``private_a2a_url`` (a non-secret endpoint) is preserved.
    """
    new = cfg.model_copy(deep=True)
    new.coordinator = CoordinatorConfig(
        enabled=enabled,
        remote_private=False,  # Phase 2 — gated, never enabled from the UI
        private_a2a_url=new.coordinator.private_a2a_url,
    )
    return new
