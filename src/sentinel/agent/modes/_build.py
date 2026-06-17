"""Shared agent-builder helper — turns a SentinelConfig entry into an ADK Agent.

Both mode builders (competitor, client) use ``make_agent`` so model/prompt/generation resolution
lives in one place (SENTINEL-001). This is the seam where config becomes a running agent.
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import Agent
from google.genai import types

from sentinel.config.render import render_prompt
from sentinel.config.schema import (
    REASONER_ROLES,
    AgentConfig,
    GenerationConfig,
    SentinelConfig,
)
from sentinel.llm.gateway import build_model, resolve_backend

# Gemini floor for max_output_tokens: gemini-2.5-flash is a *thinking* model — its hidden thinking
# tokens count against max_output_tokens, so a budget sized for the visible JSON (e.g. the
# synthesizer's 3072) truncates the payload mid-object → pydantic ValidationError in ADK's
# validate_schema → the node fails and the run degrades to empty findings (proven live 2026-06-11;
# discover.py:60 hit the same wall at 1024 and settled on 4096 for a short list). 8192 leaves room
# for thinking + a full multi-section research artifact. vLLM is unaffected (no thinking budget,
# and the 26B synthesizes in chunks), so the floor applies only when the agent resolves to Gemini.
GEMINI_MIN_OUTPUT_TOKENS = 32768


def _agent_backend(
    cfg: SentinelConfig, ac: AgentConfig, mode_backend: str | None, *, cloud_allowed: bool
) -> str:
    """The backend this agent will actually run on — same precedence as :func:`resolve_model`."""
    if not cloud_allowed:
        return "vllm"
    if mode_backend in ("gemini", "claude"):
        return mode_backend
    if ac.pin_gemini:
        return "gemini"
    return resolve_backend(mode_backend or cfg.backend.default)


def to_genai(gen: GenerationConfig) -> types.GenerateContentConfig | None:
    """Map our GenerationConfig to ADK's generate_content_config (omitting None fields)."""
    kw = {}
    if gen.temperature is not None:
        kw["temperature"] = gen.temperature
    if gen.max_output_tokens is not None:
        kw["max_output_tokens"] = gen.max_output_tokens
    if gen.top_p is not None:
        kw["top_p"] = gen.top_p
    if gen.top_k is not None:
        kw["top_k"] = gen.top_k
    return types.GenerateContentConfig(**kw) if kw else None


def _vllm_response_format(output_schema) -> dict | None:
    """vLLM structured-output spec for a schema-bound agent — or None for a free-text agent.

    Returns the ``{"type":"json_schema","json_schema":{name,schema}}`` shape vLLM guided-decodes
    against, so the model can only emit valid, terminating JSON. This is the lever that stops the
    gemma-4-26B reasoner degenerating into a whitespace-repetition loop (the top-level ``guided_json``
    param is silently ignored by the endpoint — ``response_format`` is what it honours; proven live
    2026-06-08). Gemini needs none of this (ADK sets its native ``response_schema`` from output_schema)
    so this is consulted only on the vLLM path.
    """
    if output_schema is None:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": output_schema.__name__,
            "schema": output_schema.model_json_schema(),
        },
    }


def resolve_model(
    cfg: SentinelConfig,
    ac: AgentConfig,
    mode_backend: str | None,
    *,
    cloud_allowed: bool = True,
    output_schema=None,
):
    """Resolve a model object: per-agent model if set, else the active backend's default.

    Grounding agents (`pin_gemini`) stay on Gemini regardless of the chosen backend — UNLESS
    governance forbids cloud (``cloud_allowed=False``, i.e. ``on_prem_required`` or a private run
    under ``block_cloud_on_private``). In that case ``pin_gemini`` is ignored and the backend is
    forced to ``vllm``, so **no Gemini object is ever constructed** (SENTINEL-005 NFR-2). This is
    the structural enforcement seam: the sovereignty guarantee is provable by introspection, not
    by a prompt instruction.

    ``output_schema`` (when set) constrains the vLLM decode to that schema via ``response_format``
    json_schema — see :func:`_vllm_response_format`. Ignored on the Gemini path (ADK handles it).
    """
    backend = _agent_backend(cfg, ac, mode_backend, cloud_allowed=cloud_allowed)
    if backend == "gemini":
        model_id = ac.model or cfg.backend.gemini.model
        return build_model("gemini", model_id)
    if backend == "claude":
        model_id = ac.model or cfg.backend.fallback_model or "claude-haiku-4-5-20251001"
        return build_model("claude", model_id)
    # Role tiering (SENTINEL-011): when an on-prem role map is set, pick this agent's role-specific
    # vLLM option (tool-callers → 12B, reasoners → 26B); otherwise the flat vllm option (today's
    # behaviour, byte-identical when roles is None). Per-agent ac.model still overrides the model id.
    opt = (cfg.backend.roles or {}).get(ac.role) or cfg.backend.vllm
    model_id = ac.model or opt.model
    return build_model(
        "vllm", model_id, opt.api_base,
        response_format=_vllm_response_format(output_schema),
    )


def make_agent(
    cfg: SentinelConfig,
    key: str,
    *,
    name: str,
    output_key: str,
    mode_backend: str | None = None,
    tools: list | None = None,
    output_schema=None,
    note_substitutions: dict[str, str] | None = None,
    instruction_suffix: str = "",
    cloud_allowed: bool = True,
    prompt_key: str | None = None,
) -> Agent:
    # ``prompt_key`` lets a step reuse one agent's config (model/role/generation) with a different
    # prompt template — e.g. the two-tier synthesizer keeps ``<mode>.synthesizer`` config but renders
    # ``<mode>.synthesizer_2t`` (SENTINEL-008). Defaults to ``key`` ⇒ byte-identical single-tier path.
    ac = cfg.agents[key]
    # Reasoner roles (synthesizer/strategist) run on gemma-4-26B and are kept structurally tool-free
    # (build-time invariant, not a prompt convention — SENTINEL-011 AC-7). NOTE (2026-06-08): the 26B's
    # tool-calling is no longer *broken* — omni's vLLM now runs --enable-auto-tool-choice
    # --tool-call-parser gemma4, so it tool-calls correctly (ADR-0001 Update). We keep the guard by
    # *policy (latency)*: the 26B decodes ~7× slower than the 12B, must be SSE-streamed to clear the
    # Cloudflare 524 wall, and streaming + tool-calling is the fragile lite_llm arg combo — so tools
    # belong on the fast 12B tool-callers, the 26B on streamed reasoning. Gated on the role map being
    # active: the 26B is only ever selected under tiering, and an untiered/legacy config (roles=None)
    # must stay byte-identical — its inert role field never makes a tool-caller look like a reasoner.
    if tools and cfg.backend.roles is not None and ac.role in REASONER_ROLES:
        raise ValueError(
            f"agent {key!r} has reasoner role {ac.role!r}; reasoners (gemma-4-26B) must be "
            "tool-free — give the tool-using work to a tool-caller role (gemma-4-12B)"
        )
    gen = cfg.generation.merge(ac.generation)
    # Thinking-token floor (see GEMINI_MIN_OUTPUT_TOKENS): a cap tuned for vLLM's visible output
    # starves a Gemini thinking model and decapitates the JSON. Applied at build time so every
    # mode/config inherits it — the per-machine config file never needs touching.
    # Also applies when max_output_tokens is None (API default) — None means "let Gemini pick",
    # which for gemini-2.5-flash is often ≤8192. The thinking budget silently burns those tokens
    # first, leaving <2k for the actual JSON payload → EOF truncation (seen live 2026-06-17).
    if _agent_backend(cfg, ac, mode_backend, cloud_allowed=cloud_allowed) == "gemini" and (
        gen.max_output_tokens is None
        or gen.max_output_tokens < GEMINI_MIN_OUTPUT_TOKENS
    ):
        gen = gen.merge(GenerationConfig(max_output_tokens=GEMINI_MIN_OUTPUT_TOKENS))
    instruction = render_prompt(cfg.prompts[prompt_key or key])
    for var, value in (note_substitutions or {}).items():
        instruction = instruction.replace("{" + var + "}", value)
    # Appended context (e.g. recalled memory, SENTINEL-002). Empty by default so the rendered
    # instruction stays byte-identical to the template when there's nothing to inject.
    instruction += instruction_suffix

    kwargs: dict = {
        "name": name,
        "model": resolve_model(
            cfg, ac, mode_backend, cloud_allowed=cloud_allowed, output_schema=output_schema
        ),
        "instruction": instruction,
        "output_key": output_key,
        "generate_content_config": to_genai(gen),
    }
    if tools is not None:
        kwargs["tools"] = tools
    if output_schema is not None:
        kwargs["output_schema"] = output_schema
    return Agent(**kwargs)


def maybe_strategist(
    cfg: SentinelConfig, mode: str, *, backend: str | None, cloud_allowed: bool
) -> Agent | None:
    """Build the tool-free strategist sub-agent, or None when strategy is disabled (SENTINEL-009).

    Loads the mode's playbook and appends its body to the strategist instruction via the existing
    ``instruction_suffix`` seam (so editing the ``.md`` changes the next run). The strategist emits
    only a ``StrategyOverlay`` (``output_key="strategy"``) and carries no tools — its role is a
    reasoner (26B under tiering). Sovereignty is inherited: ``cloud_allowed`` flows to
    ``resolve_model`` unchanged, so ``on_prem_required`` builds no Gemini object (AC-11).
    """
    if not cfg.strategy.enabled:
        return None
    # local imports avoid a module-import cycle (schemas/strategy are leaf modules)
    from sentinel.artifacts.schemas import StrategyOverlay
    from sentinel.strategy import load_playbook

    stem = cfg.strategy.competitor_playbook if mode == "competitor" else cfg.strategy.client_playbook
    pb = load_playbook(Path(cfg.strategy.playbook_dir) / f"{stem}.md")
    suffix = f"\n\n{pb.body}" if pb else "\n\n(No playbook loaded — use sound default judgement.)"
    return make_agent(
        cfg, f"{mode}.strategist", name=f"{mode}_strategist",
        output_key="strategy", mode_backend=backend, output_schema=StrategyOverlay,
        instruction_suffix=suffix, cloud_allowed=cloud_allowed,  # tools omitted → tool-free
    )
