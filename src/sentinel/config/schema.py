"""SentinelConfig — typed, persisted source of truth for runtime behaviour (SENTINEL-001).

Externalizes what used to be hardcoded in the agent builders: per-agent model, prompt, and
generation parameters (temperature / max tokens / top_p / top_k). The orchestrator builds every
agent from this object, so an admin can tune the agent without editing code (the Settings UI in
SENTINEL-003 just edits this). Holds **no secrets** — API keys stay in the environment.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Capability tiers (SENTINEL-011 / ADR-0001). Verified live 2026-06-07: gemma-4-12B does native
# OpenAI tool-calling; gemma-4-26B reasons + emits structured JSON but its tool-calling is broken.
# So roles are split by CAPABILITY, not size — tool-callers → 12B, reasoners → 26B (never tools).
Role = Literal[
    "coordinator",        # tool-caller: Goal→Plan→Delegate→Merge over specialists
    "planner",            # tool-caller
    "public_research",    # tool-caller: web search
    "private_research",   # tool-caller: scoped MCP
    "extractor",          # tool-caller (SENTINEL-008 two-tier)
    "synthesizer",        # reasoner: no tools
    "strategist",         # reasoner: no tools (SENTINEL-009)
]
TOOL_CALLER_ROLES: frozenset[Role] = frozenset(
    {"coordinator", "planner", "public_research", "private_research", "extractor"}
)
REASONER_ROLES: frozenset[Role] = frozenset({"synthesizer", "strategist"})


# --------------------------------------------------------------------------- #
# Universal research agent (SENTINEL-012) — project/task vocabulary.
# Enums live here (config) so the Settings UI and validation share one source of truth;
# the row models (Project/Task/Domain/Persona) live in artifacts/schemas.py.
# --------------------------------------------------------------------------- #

# Orchestrator agent-creation autonomy (SENTINEL-012 AC-13). ``propose`` is the SAFE DEFAULT:
# the planner returns a Plan + any created AgentSpecs for human approval before anything runs.
# ``autonomous`` is explicit opt-in per project: register + execute immediately.
Autonomy = Literal["propose", "autonomous"]

# Domain risk tier (SENTINEL-012 §9.3 / AC-14). ``high_stakes`` domains (medicine/clinical, legal)
# are REJECTED at task creation this program — they need an enforced source allow-list +
# factuality/eval + citation resolution first. Re-introduction is a separate future spec.
RiskTier = Literal["standard", "high_stakes"]

# Named audience registry (SENTINEL-012 §1). A persona shapes RENDERING ONLY (reading level / tone /
# format), never the researched facts (AC-17). ``custom`` lets a project define its own profile.
PersonaName = Literal[
    "student", "doctor", "nurse", "developer", "enterprise", "consumer", "custom"
]

# Canonical high-stakes domain markers (SENTINEL-012 AC-14). A domain whose name matches any of
# these is treated as ``high_stakes`` and blocked at task creation. Matching logic lives in
# ``is_high_stakes`` (artifacts/schemas.py) so it can be unit-tested against the gate.
HIGH_STAKES_DOMAIN_MARKERS: frozenset[str] = frozenset(
    {
        # medical / clinical
        "med", "meds", "medicine", "medical", "clinical", "health", "diagnosis", "diagnostic",
        "drug", "pharma", "pharmaceutical", "patient", "therapy", "therapeutic", "disease", "treatment",
        # legal
        "legal", "law", "litigation", "attorney", "court",
    }
)


class ProjectSettings(BaseModel):
    """Per-project orchestration policy (SENTINEL-012).

    ``autonomy`` defaults to ``propose`` (the safe default, AC-13). ``backend_pref`` /
    ``compliance`` let a project pin its sovereignty posture independent of the global
    ``backend``/``governance`` defaults; ``None`` ⇒ inherit the global config. A project is an
    organising construct, not a security boundary (single-operator scope, §9.7).
    """

    autonomy: Autonomy = "propose"
    backend_pref: Literal["gemini", "vllm"] | None = None
    compliance: Literal["cloud_ok", "on_prem_preferred", "on_prem_required"] | None = None


class GenerationConfig(BaseModel):
    """LLM generation parameters. Fields left None inherit from the global default."""

    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None

    def merge(self, override: "GenerationConfig") -> "GenerationConfig":
        """Return self with any non-None field from ``override`` taking precedence."""
        return GenerationConfig(
            temperature=override.temperature if override.temperature is not None else self.temperature,
            max_output_tokens=(
                override.max_output_tokens if override.max_output_tokens is not None
                else self.max_output_tokens
            ),
            top_p=override.top_p if override.top_p is not None else self.top_p,
            top_k=override.top_k if override.top_k is not None else self.top_k,
        )


class BackendOption(BaseModel):
    model: str
    api_base: str | None = None


class BackendConfig(BaseModel):
    default: Literal["gemini", "vllm"] = "gemini"
    gemini: BackendOption = Field(default_factory=lambda: BackendOption(model="gemini-2.5-flash"))
    vllm: BackendOption = Field(
        default_factory=lambda: BackendOption(
            model="google/gemma-3-4b-it", api_base="http://localhost:8000/v1"
        )
    )
    # Per-role on-prem model map (SENTINEL-011), keyed by Role. ``None`` ⇒ every agent uses the flat
    # ``vllm`` option above — byte-identical to pre-tiering behaviour. An admin opting into Gemma-4
    # tiering populates this with {tool-caller roles → 12B, reasoner roles → 26B}. Lives at backend
    # level (not on the shared BackendOption) so ``gemini`` never carries a meaningless role map.
    roles: dict[str, BackendOption] | None = None
    # Global ceiling on concurrent leaf LLM runs (SENTINEL-013 Step 7). The DAG level-scheduler fans a
    # wave out with asyncio.gather; without a cap a wide fan-out (N competitors) could open N ADK
    # runners at once and starve interactive chat sharing the same vLLM endpoint. A module-level
    # semaphore in ``orchestrator.run_step`` (the single leaf every step funnels through) admits at most
    # this many at a time — mirroring LeadFlow's ``Semaphore(3)``. Guards the leaf only (no nested
    # acquire), so the deepest linear plan can never deadlock. ``ge=1`` keeps it a real gate.
    max_concurrency: int = Field(default=3, ge=1)
    # Turn controller (SENTINEL-015 FR-06): max LLM calls per step run. Passed to ADK
    # RunConfig.max_llm_calls — stops a runaway tool-call loop at this count.
    max_turns: int = Field(default=30, ge=1)
    # Retry policy (SENTINEL-015 FR-07): on transient failure, retry up to max_retries times
    # with exponential backoff: delay = base_retry_delay_s * (2 ** attempt).
    # Total max wait = 1+2+4 = 7s for default max_retries=3. Set to 1 to disable retry.
    max_retries: int = Field(default=3, ge=1)
    base_retry_delay_s: float = Field(default=1.0, gt=0)
    # LLM router fallback (SENTINEL-router): when vLLM is unreachable (timeout / 524), automatically
    # re-run planning + execution on this backend. "gemini" uses the existing gemini config.
    # "claude" uses ANTHROPIC_API_KEY. None disables fallback (fail fast).
    fallback: Literal["gemini", "claude"] | None = "gemini"
    fallback_model: str = "claude-haiku-4-5-20251001"


class PromptTemplate(BaseModel):
    """An editable instruction template. ``variables`` are required `{vars}` it must contain.

    ``default_template`` retains the shipped text so the UI can offer "reset to default".
    """

    template: str
    variables: list[str] = Field(default_factory=list)
    default_template: str | None = None


class AgentConfig(BaseModel):
    """Per-agent runtime knobs. ``model=None`` ⇒ use the active backend's default model."""

    enabled: bool = True
    model: str | None = None
    pin_gemini: bool = False  # grounding agents stay on Gemini regardless of backend
    # Capability tier for on-prem model selection (SENTINEL-011). Unused when ``backend.vllm.roles``
    # is None; ``defaults.py`` sets the correct role per agent key. Defaults to the safe reasoner tier.
    role: Role = "synthesizer"
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


class MemoryConfig(BaseModel):  # stub — filled by SENTINEL-002
    entity_memory: bool = True
    retention_days: int = 365
    inject_org_prefs: bool = True
    # Episodic memory injection (SENTINEL-015): recall past research sessions at task start
    # and inject a compact summary into the planner's context. When off, the run is
    # byte-identical to pre-015 (AC-10 parity).
    episodic_recall: bool = True
    episodic_recall_top_k: int = Field(default=3, ge=1, le=10)
    # KB/ChromaDB context injection (SENTINEL-016 G-03): pull top-N indexed document chunks into
    # base_seed["memory_context"] via hybrid_search before every DAG run.
    kb_context: bool = True
    # Context budget for memory injection (G-11 ContextBudget). Total tokens split proportionally
    # across entity-hot (30%), entity-cold (15%), episodic (25%), KB (30%). Default 2400.
    context_window_tokens: int = Field(default=2400, ge=800, le=16000,
                                       description="Total memory-context token budget per DAG run.")


class GovernanceConfig(BaseModel):
    """Sovereignty policy the orchestrator obeys (SENTINEL-005).

    ``compliance_mode`` is the master switch: ``on_prem_required`` forbids any cloud (Gemini)
    egress — reasoning is forced to vLLM and public grounding to a non-Gemini provider, both
    structurally (no Gemini object is ever built). ``block_cloud_on_private`` additionally forces
    any single run that touches the private boundary on-prem, regardless of the mode.
    """

    compliance_mode: Literal["cloud_ok", "on_prem_preferred", "on_prem_required"] = "cloud_ok"
    audit_log: bool = True
    block_cloud_on_private: bool = False


class StrategyConfig(BaseModel):
    """Strategy & action-plan overlay (SENTINEL-009).

    When ``enabled``, a tool-free ``strategist`` sub-agent reads the finished artifact and emits a
    ``StrategyOverlay`` (assessment + prioritized action_plan + objection_handling) shaped by an
    admin-editable Markdown playbook; the orchestrator merges it deterministically. Ships dark
    (default off) ⇒ byte-identical to SENTINEL-004. Playbooks are selected by filename stem under
    ``playbook_dir``; the strategist follows the reasoning backend/governance (never forces cloud).
    """

    enabled: bool = False  # ships dark
    playbook_dir: str = "playbooks"
    competitor_playbook: str = "competitor-counterplay"  # filename stem in playbook_dir
    client_playbook: str = "account-strategy"


class CoordinatorConfig(BaseModel):
    """A2A coordinator topology (SENTINEL-011 / ADR-0001).

    When ``enabled``, the orchestrator builds an ``LlmAgent`` coordinator (Goal→Plan→Delegate→Merge,
    on the 12B tool-caller) that delegates to the existing pipelines wrapped as specialists via
    ``AgentTool``; when off (default) the legacy per-mode ``SequentialAgent`` runs unchanged —
    byte-identical to today. ``remote_private`` + ``private_a2a_url`` are Phase 2 (AC-14): they run
    the PRIVATE specialist as an on-prem A2A service and require the ``a2a-sdk`` dependency + an ADR
    before any build. The URL is a non-secret endpoint, so it lives in config (never a key).
    """

    enabled: bool = False  # ship dark
    remote_private: bool = False  # Phase 2 — needs a2a-sdk + ADR (AC-14)
    private_a2a_url: str | None = None  # Phase 2 — on-prem A2A endpoint (non-secret)


class PriorityConfig(BaseModel):
    """Account-prioritization scoring policy (SENTINEL-010).

    The focus list ranks accounts by a deterministic 0-100 score (no LLM in the arithmetic). All
    knobs are admin-editable without a redeploy (NFR-5): ``weights`` overlays the registry's default
    per-signal weights (empty ⇒ registry defaults); ``hot``/``warm`` thresholds set the tier cuts;
    ``recency_half_life_days`` tunes how fast a stale account decays. Ships **on** — the focus list
    is an additive read surface, so enabling it changes no existing page; ``enabled=False`` only
    hides the dashboard card and the ``/focus`` route.
    """

    enabled: bool = True
    weights: dict[str, float] = Field(default_factory=dict)   # signal name → override weight
    hot_threshold: float = 66.0
    warm_threshold: float = 33.0
    recency_half_life_days: float = 14.0


class ResearchConfig(BaseModel):
    """Two-tier research depth (SENTINEL-008).

    When ``two_tier`` is on, a cheap ``extractor`` agent distils the gathered public research into
    typed per-source ``Extraction`` notes before synthesis, so one weak source can't poison the
    brief; the synthesizer then reads those structured extractions instead of raw page notes. Adds
    exactly one LLM call per run (NFR-1). Ships **dark** (default off) ⇒ the pipeline + every
    artifact is byte-identical to SENTINEL-004 (AC-6/11). The extractor follows the reasoning
    backend/governance via ``resolve_model`` — no Gemini in ``on_prem_required`` (AC-10).
    """

    two_tier: bool = False  # ships dark
    extract_max_notes_per_source: int = 8  # bounds synthesis input size (advisory, in the prompt)


class SearchConfig(BaseModel):
    """Pluggable public-search provider (SENTINEL-005).

    ``gemini`` uses ADK's native ``google_search`` (cloud, Gemini-pinned). The others are function
    tools the reasoning model calls via function-calling, so a no-cloud run still has eyes on the
    web. ``onprem_fallback`` is the non-cloud provider used when policy forbids Gemini but the
    configured provider is still ``gemini``.
    """

    provider: Literal["gemini", "duckduckgo", "brave", "serpapi", "google_cse", "searxng"] = "gemini"
    results: int = 5
    onprem_fallback: Literal["duckduckgo", "brave", "serpapi", "google_cse", "searxng"] = "duckduckgo"
    # Per-run budget on the public-research agent's `search()` calls (function-tool providers only;
    # the Gemini builtin manages its own grounding). When the model exhausts the budget the tool
    # returns a soft "synthesize now" message instead of more results, so the loop stops gracefully
    # rather than over-searching (a gemma-4-12B run was observed making ~34 tool turns, bloating the
    # 26B synthesizer input and wall-clock). 0 disables the cap (unbounded, legacy behaviour).
    max_calls: int = 8
    # SENTINEL-013: minimum seconds between consecutive function-tool `search()` calls within a run.
    # The keyless DuckDuckGo lite SERP rate-limits aggressive scraping, so a stagger keeps a multi-query
    # research loop from getting throttled to empty results. 0 ⇒ no stagger (keyed APIs don't need it;
    # the byte-identical default). Applied in the tool wrapper with an injectable clock (testable, no
    # real sleeping in the suite). See `web_search._make_function_tool`.
    stagger_s: float = 0.0


class MCPServerConfig(BaseModel):
    """One external MCP server agents may call (Firecrawl, SearchAPI, …).

    Secrets never live here — ``api_key_env`` / ``url_env`` name the .env variables that
    hold them. A server with its key/url unset is silently skipped (fail-soft, same as the
    private boundary). ``domains`` scopes the toolset to matching research domains
    (empty ⇒ offered to every domain); the tool-calling model then selects per step.
    ``tool_filter`` is an allow-list of tool names (empty ⇒ expose all — keep it tight
    for the 12B tool-caller, which degrades with very large tool menus).
    """

    enabled: bool = True
    transport: Literal["stdio", "http"] = "stdio"
    command: str = ""              # stdio: executable, e.g. "npx"
    args: str = ""                 # stdio: argument string, e.g. "-y firecrawl-mcp"
    api_key_env: str = ""          # stdio: env var passed through to the subprocess
    url_env: str = ""              # http: env var holding the (secret-bearing) server URL
    domains: list[str] = Field(default_factory=list)
    tool_filter: list[str] = Field(default_factory=list)
    description: str = ""


class AuthConfig(BaseModel):
    """Login authentication (session-based, scrypt hash, httponly cookie).

    ``password_hash`` is None on first boot — the app redirects to /setup so the
    admin can set a password before any other route is reachable. Holds no raw
    secret: the hash is safe to persist in sentinel.config.yaml (gitignored).
    """

    password_hash: str | None = None  # scrypt$<salt>$<key> or None = setup required


class SentinelConfig(BaseModel):
    """The whole runtime configuration. Build via :meth:`default` or load from YAML."""

    version: int = 1
    backend: BackendConfig = Field(default_factory=BackendConfig)
    generation: GenerationConfig = Field(
        default_factory=lambda: GenerationConfig(
            temperature=0.3, max_output_tokens=2048, top_p=0.95, top_k=40
        )
    )
    agents: dict[str, AgentConfig]
    prompts: dict[str, PromptTemplate]
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    coordinator: CoordinatorConfig = Field(default_factory=CoordinatorConfig)
    priority: PriorityConfig = Field(default_factory=PriorityConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    @classmethod
    def default(cls) -> "SentinelConfig":
        from sentinel.config.defaults import build_default  # lazy → avoids import cycle

        return build_default()
