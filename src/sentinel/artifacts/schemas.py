"""Artifact schemas for Sentinel.

Every fact an artifact carries is tagged with the *boundary* it came from
(``public`` via grounded search, ``private`` via scoped MCP connectors). This makes
the sovereignty guarantee (SRS NFR-04) visible in the output itself: a reader can see
exactly which data crossed which boundary. Schemas are deliberately industry-agnostic
(decision Q-4) — vertical context is an optional input, never a hardcoded field.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Boundary(str, Enum):
    """Which tool boundary a piece of data was sourced from."""

    PUBLIC = "public"   # Gemini grounded web search
    PRIVATE = "private"  # scoped, user-authorized MCP connectors


class Source(BaseModel):
    """Provenance for a single fact."""

    boundary: Boundary = Field(description="Which boundary this came from.")
    label: str = Field(description="Human-readable source name, e.g. 'TechCrunch' or 'CRM: Acme deal'.")
    url: str | None = Field(default=None, description="Public URL when boundary=public; null for private.")


class Finding(BaseModel):
    """A single researched claim with its provenance."""

    text: str = Field(description="The finding, stated as one concrete sentence.")
    source: Source


class Gap(BaseModel):
    """A source that was expected but unavailable — recorded, never silently dropped (FR-10)."""

    boundary: Boundary
    what_was_missing: str
    impact: str = Field(description="What the artifact lacks because of this gap.")


# --------------------------------------------------------------------------- #
# Two-tier research (SENTINEL-008) — a cheap extractor distils each gathered
# source into typed notes BEFORE synthesis, so one weak source can't poison the
# brief. Artifact schemas below are unchanged: 008 changes how findings are
# produced, not their shape.
# --------------------------------------------------------------------------- #
class Extraction(BaseModel):
    """Typed notes distilled from ONE source, with that source's provenance preserved (AC-9)."""

    source: Source
    notes: list[str] = Field(
        default_factory=list,
        description="Atomic, factual notes drawn only from THIS source — no cross-source inference.",
    )


class ExtractionSet(BaseModel):
    """The extractor agent's output schema (AC-1): per-source extractions + a Gap per source it
    could not parse (AC-4). Default-empty so a malformed/empty extractor result is still valid."""

    extractions: list[Extraction] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Strategy overlay (SENTINEL-009) — the strategist's ONLY output, merged onto the
# artifact by deterministic code so the researched findings stay immutable.
# --------------------------------------------------------------------------- #
class RecommendedAction(BaseModel):
    """A single prioritized next move tied to the brief's findings."""

    action: str = Field(description="The concrete next move, imperative voice.")
    priority: Literal["high", "med", "low"]
    timeline: str = Field(description="When, e.g. 'this week', 'next 30 days'.")
    rationale: str = Field(description="Why — tied to a finding/insight in the brief.")


class Objection(BaseModel):
    """A likely buyer objection and an evidence-based reframe (client mode, FR-098)."""

    objection: str = Field(description="A likely buyer objection.")
    reframe: str = Field(description="Evidence-based reframe drawn from the brief.")


class StrategyOverlay(BaseModel):
    """The strategist sub-agent's sole output (SENTINEL-009 AC-5). Merged onto the artifact."""

    assessment: str = Field(description="1-2 sentences: where the entity stands + best angle.")
    action_plan: list[RecommendedAction] = Field(default_factory=list)
    objection_handling: list[Objection] = Field(
        default_factory=list, description="Empty in competitor mode."
    )


# --------------------------------------------------------------------------- #
# Competitor mode → Battlecard (FR-07)
# --------------------------------------------------------------------------- #
class Battlecard(BaseModel):
    """Structured competitor battlecard. Output schema for competitor mode."""

    target: str = Field(description="The competitor this battlecard is about.")
    vertical_context: str | None = Field(default=None, description="Optional industry lens supplied by the user.")
    one_line_summary: str = Field(description="One-sentence positioning summary of the competitor.")
    positioning: str = Field(description="How the competitor positions itself in the market.")
    strengths: list[Finding] = Field(default_factory=list)
    weaknesses: list[Finding] = Field(default_factory=list)
    pricing_signals: list[Finding] = Field(default_factory=list)
    recent_developments: list[Finding] = Field(default_factory=list)
    how_to_win: list[str] = Field(
        default_factory=list,
        description="Counter-positioning angles a seller can use against this competitor. "
        "Legacy (SENTINEL-009 OQ-1): superseded by the structured action_plan; kept for back-compat.",
    )
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    # Strategy overlay (SENTINEL-009) — default-empty so a strategy-off Battlecard is byte-identical.
    assessment: str | None = Field(default=None, description="Strategic standing + best angle.")
    action_plan: list[RecommendedAction] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Client/account mode → Account Brief (FR-08)
# --------------------------------------------------------------------------- #
class AccountBrief(BaseModel):
    """Structured account brief merging public + private signal. Output schema for client mode."""

    account: str = Field(description="The account/client this brief is about.")
    vertical_context: str | None = Field(default=None)
    one_line_summary: str = Field(description="One-sentence state-of-the-relationship summary.")
    public_signal: list[Finding] = Field(
        default_factory=list, description="Firmographics, news, filings, public profiles (boundary=public).",
    )
    private_signal: list[Finding] = Field(
        default_factory=list, description="Deal stage, history, prior proposals, last contact (boundary=private).",
    )
    merged_insights: list[str] = Field(
        default_factory=list,
        description="Cross-boundary reasoning — what the public+private combination implies. The core value.",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="Legacy (SENTINEL-009 OQ-1): superseded by the structured action_plan; "
        "kept for back-compat.",
    )
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    # Strategy overlay (SENTINEL-009) — default-empty so a strategy-off AccountBrief is byte-identical.
    assessment: str | None = Field(default=None, description="Strategic standing + best angle.")
    action_plan: list[RecommendedAction] = Field(default_factory=list)
    objection_handling: list[Objection] = Field(default_factory=list)


Mode = Literal["competitor", "client"]

SCHEMA_FOR_MODE: dict[str, type[BaseModel]] = {
    "competitor": Battlecard,
    "client": AccountBrief,
}


# --------------------------------------------------------------------------- #
# Competitor discovery (breadth step that feeds the depth Battlecard).
# A discovery specialist turns one of OUR products into a list of rival names;
# each name is then run through the existing competitor Battlecard (depth).
# --------------------------------------------------------------------------- #
class CompetitorCandidate(BaseModel):
    """One discovered rival for a given product."""

    name: str = Field(description="The competing company or product, named precisely (e.g. 'Glean').")
    category: str = Field(description="The market category they compete in, e.g. 'Enterprise RAG search'.")
    reason: str = Field(description="One sentence: why they compete with the given product.")


class CompetitorList(BaseModel):
    """The discovery specialist's output: rivals for one of our products."""

    product: str = Field(description="Our product the rivals were found for.")
    competitors: list[CompetitorCandidate] = Field(default_factory=list)


# =========================================================================== #
# SENTINEL-012 — Universal research agent: Project / Task / Plan / eval model.
# These are the orchestration-layer row models that sit ABOVE the proven mode
# engine. Enums (Autonomy/RiskTier/PersonaName) live in config/schema.py.
# =========================================================================== #
from sentinel.config.schema import (  # noqa: E402 — models below reference these enums
    HIGH_STAKES_DOMAIN_MARKERS,
    PersonaName,
    ProjectSettings,
    RiskTier,
    Role,
)


class Domain(BaseModel):
    """What is being researched → which source/tool set + output schema applies (SENTINEL-012).

    ``risk_tier`` gates task creation: ``high_stakes`` (medicine/clinical, legal) is rejected this
    program (AC-14). The tier is derived from the name via :func:`is_high_stakes`, but stored
    explicitly so a persisted Task records the decision that was made at creation time.
    """

    name: str = Field(description="Domain key, e.g. 'market', 'food', 'software', 'academic'.")
    risk_tier: RiskTier = "standard"


class Persona(BaseModel):
    """Who the output is for → rendering profile (data, not facts). Render-only (AC-17).

    ``name`` widened from the PersonaName literal to free text (2026-06-12): the persona library
    lets operators save their own audiences ("CFO brief", "field nurse"), so the closed enum now
    only describes the BUILT-IN registry names — any saved-persona name is equally valid here.
    """

    name: str = "enterprise"
    reading_level: str = Field(default="professional", description="e.g. 'K-12', 'undergraduate', 'professional'.")
    tone: str = Field(default="neutral", description="e.g. 'plain', 'clinical', 'technical', 'persuasive'.")
    format: str = Field(default="brief", description="e.g. 'bullets', 'brief', 'report', 'one-pager'.")
    source_policy: str | None = Field(
        default=None, description="Credible-source policy for this audience, e.g. 'peer-reviewed only'."
    )
    auto_selected: bool = Field(
        default=False, description="True when the agent picked this persona from the domain (the "
        "form's 'auto' option) rather than the user choosing it — surfaced in the UI pill.")


class SavedPersona(BaseModel):
    """An operator-defined audience in the persona library (editable at /personas).

    Separate from :class:`Persona` on purpose: this is the *library record* (has identity,
    description, provenance), while Persona is the *value object* a task carries. ``to_persona()``
    bridges them at task-creation time.
    """

    id: str
    name: str = Field(description="Display name, e.g. 'CFO brief' — also how the task form refers to it.")
    description: str = Field(default="", description="Who this audience is; feeds the generator prompt.")
    reading_level: str = "professional"
    tone: str = "neutral"
    format: str = "brief"
    source_policy: str | None = None
    created_at: str = Field(description="ISO-8601 UTC timestamp (caller-supplied; no wall-clock in models).")

    def to_persona(self) -> Persona:
        return Persona(name=self.name, reading_level=self.reading_level, tone=self.tone,
                       format=self.format, source_policy=self.source_policy)


# Full audience profiles per named persona (SENTINEL-012 §1 made real). Until 2026-06-12 every
# name shipped with the identical professional/neutral/brief defaults, so picking "student" only
# changed one word in the renderer prompt — the docs' K-12-study-guide / nurse-checklist promise
# existed in the schema but was wired to defaults. INVARIANT: "enterprise" must stay EQUAL to the
# Persona() defaults — dag._finalize_result skips the persona render pass when persona == Persona(),
# so a richer enterprise profile would silently add an LLM call to every default task.
PERSONA_PROFILES: dict[str, dict[str, str]] = {
    "enterprise": {},  # = Persona() defaults: professional · neutral · brief (skip-pass invariant)
    "developer": {
        "reading_level": "professional (engineering)",
        "tone": "technical",
        "format": "comparison table with code-level notes",
        "source_policy": "official docs, changelogs and maintainer sources preferred",
    },
    "consumer": {
        "reading_level": "general public",
        "tone": "plain",
        "format": "short bullets ending in a clear recommendation",
        "source_policy": "reputable consumer sources; flag sponsored or affiliate content",
    },
    "student": {
        "reading_level": "K-12 to undergraduate",
        "tone": "plain",
        "format": "study guide with definitions and worked examples",
        "source_policy": "textbooks, .edu and encyclopedic references preferred",
    },
    "doctor": {
        "reading_level": "professional (clinical)",
        "tone": "clinical",
        "format": "structured brief with evidence levels per claim",
        "source_policy": "peer-reviewed and regulatory sources only",
    },
    "nurse": {
        "reading_level": "professional (clinical)",
        "tone": "clinical",
        "format": "checklist with a one-line rationale per item",
        "source_policy": "peer-reviewed and clinical-guideline sources only",
    },
    # "custom" deliberately absent: it starts from Persona() defaults and is defined entirely by
    # the caller's overrides (the form's customise-persona fields).
}


# How the agent picks a persona when the form says "auto" (the §G.3 doc examples made policy):
# study domains read like study guides, builder domains like engineering notes, consumer domains
# like buying advice; the B2B domains keep the professional default. Deterministic on purpose —
# explainable in the UI pill ("student · auto-selected for academic") and unit-testable, where an
# LLM choice would be neither.
DOMAIN_DEFAULT_PERSONA: dict[str, str] = {
    "academic": "student",
    "software": "developer",
    "nutrition": "consumer",
    "travel": "consumer",
    "product_research": "consumer",
    "market": "enterprise",
    "account": "enterprise",
    "finance": "enterprise",
    "govt_proposal": "enterprise",
}


def auto_persona_name(domain_name: str) -> str:
    """The agent's persona pick for a domain (the form's 'auto' option). Unknown domains get the
    professional default rather than raising — domains are free text at the schema level."""
    return DOMAIN_DEFAULT_PERSONA.get((domain_name or "").strip().lower(), "enterprise")


def persona_for(name: str | None, *, reading_level: str = "", tone: str = "",
                format: str = "", source_policy: str = "",
                extra_profiles: dict[str, dict[str, str]] | None = None) -> Persona:
    """Build the FULL audience profile for a persona name (render-only fields, AC-17).

    Resolution order: ``extra_profiles`` (the persona library's saved audiences — including
    *overrides* of a built-in name, keyed by lowercase name; passed in by the web layer so this
    module stays storage-free) → built-in registry profile for ``name`` → ``custom`` starts from
    defaults; then non-blank keyword overrides win field-by-field (how any persona is customised
    per task). A saved entry therefore EDITS the matching built-in (the /personas editor) — except
    ``enterprise``, which is never overridable so it stays EQUAL to ``Persona()`` and keeps the
    dag skip-pass invariant. Unknown/blank names degrade to the default enterprise reader rather
    than raising: the form constrains the options, but a hand-typed query string must degrade safely.
    """
    n = (name or "").strip().lower()
    extra = {k.strip().lower(): v for k, v in (extra_profiles or {}).items()}
    if n != "enterprise" and n in extra:           # saved persona OR an override of a built-in
        profile: dict[str, str] = {k: v for k, v in extra[n].items() if k in
                                   ("reading_level", "tone", "format", "source_policy") and v}
    elif n in PERSONA_PROFILES:
        profile = dict(PERSONA_PROFILES[n])
    elif n == "custom":
        profile = {}
    else:
        n, profile = "enterprise", {}
    overrides = {"reading_level": reading_level, "tone": tone,
                 "format": format, "source_policy": source_policy}
    for key, value in overrides.items():
        if value.strip():
            profile[key] = value.strip()
    return Persona(name=n, **profile)


def is_high_stakes(domain_name: str) -> bool:
    """Return True if ``domain_name`` names a high-stakes domain that must be blocked at task
    creation (SENTINEL-012 AC-14).

    SAFETY-CRITICAL. A false negative here lets a clinical/legal research task through the gate —
    exactly what §9.3 scopes out until we have an enforced source allow-list + factuality eval.
    Prefer over-blocking (false positive) to under-blocking. Matching is against
    :data:`HIGH_STAKES_DOMAIN_MARKERS` (config/schema.py).

    Strategy: normalise (lowercase + split on non-alphanumerics) into tokens, then block if ANY
    token is a high-stakes marker. Token-level (not substring) avoids false positives like
    "legalese-checker" while still catching "Clinical Research" and "med-device". Over-blocking is
    preferred to under-blocking for this safety gate.
    """
    import re

    tokens = {t for t in re.split(r"[^a-z0-9]+", domain_name.lower()) if t}
    return bool(tokens & HIGH_STAKES_DOMAIN_MARKERS)


class Project(BaseModel):
    """A research project — the top-level organising construct (SENTINEL-012)."""

    id: str
    name: str
    website: str | None = None
    description: str = Field(default="", description="Short description of the research objective.")
    context: str = Field(default="", description="Agent context — appended to vertical_context for every task in this project.")
    source_docs: list[str] = Field(default_factory=list, description="Paths/URLs of supplied context docs.")
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    created_at: str = Field(description="ISO-8601 UTC timestamp (caller-supplied; no wall-clock in models).")


TaskStatus = Literal["created", "planned", "running", "done", "failed", "rejected"]


class Task(BaseModel):
    """A unit of research within a project: objective × domain × persona (SENTINEL-012)."""

    id: str
    project_id: str
    objective: str = Field(description="What to research — free text or a resolved template.")
    domain: Domain
    persona: Persona = Field(default_factory=Persona)
    status: TaskStatus = "created"
    plan_id: str | None = None
    created_at: str = Field(description="ISO-8601 UTC timestamp (caller-supplied).")
    # G-14: user_id seeds UserProfileStore lookup so synthesizer output adapts to saved preferences.
    # G-17: handoff_id marks the originating SessionHandoff done after a successful run.
    # Both ride in the existing tasks.data JSON column — no DDL change needed.
    user_id: str | None = Field(default=None, description="Operator user ID for profile injection (G-14).")
    handoff_id: str | None = Field(default=None, description="A2A SessionHandoff to complete post-run (G-17).")
    # Extra background injected into every agent prompt as vertical_context (e.g. org description,
    # data sovereignty requirements, budget constraints). Rides in tasks.data JSON — no DDL change.
    context: str | None = Field(default=None, description="Research context / additional background for this task.")
    # Conversational chat history — list of {role, content} dicts for post-run refinement.
    # Rides in tasks.data JSON — no DDL change.
    chat: list[dict] = Field(default_factory=list, description="Chat history for post-run refinement (role/content dicts).")
    # The latest run output, persisted on the task so it lives at the task's own URL (PRG): Approve &
    # Run redirects to /tasks/{id}, which re-renders this instead of the result being trapped in a POST
    # response body. Forward-ref to ``Result`` (defined below) — resolved by ``Task.model_rebuild()`` at
    # module end. Rides in the existing ``tasks.data`` JSON column ⇒ no store-schema change (no ADR).
    result: "Result | None" = Field(default=None, description="Latest persisted run Result (render-only).")


StepStatus = Literal["pending", "running", "done", "failed", "skipped"]


class Step(BaseModel):
    """One node in a Plan DAG (SENTINEL-012 §1). Distinct from ``modes.spec.StepSpec`` (a mode
    definition) — this is a *runtime* step with dependencies and status."""

    id: str
    capability: str = Field(description="The capability this step needs, e.g. 'self_profile', 'compare'.")
    depends_on: list[str] = Field(default_factory=list, description="Step ids that must finish first.")
    agent_spec_id: str | None = Field(default=None, description="Resolved/created AgentSpec; None until staffed.")
    inputs: dict[str, str] = Field(default_factory=dict, description="output_key → state-key wiring.")
    output_key: str = Field(description="State key this step writes its result under.")
    status: StepStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None


PlanStatus = Literal["proposed", "approved", "running", "done", "failed"]


class Plan(BaseModel):
    """The orchestrator's output: an inspectable step-DAG (SENTINEL-012)."""

    id: str
    task_id: str
    steps: list[Step] = Field(default_factory=list)
    status: PlanStatus = "proposed"


class AgentSpec(BaseModel):
    """A reusable, versioned specialist definition (SENTINEL-012 §10.3). Keyed by
    ``(capability, domain)`` + ``version``; the registry reuses the highest-scoring active spec
    rather than rebuilding per task (AC-21). ``origin`` distinguishes seed skills from
    planner-created ones; created specs are validated before they can run (AC-12)."""

    id: str
    name: str
    capability: str = Field(description="What this agent does — the registry lookup key.")
    domain: str = Field(description="The domain it was tuned for; pairs with capability as the key.")
    role: Role = Field(description="tool-caller vs reasoner (drives the two-pass partition + tool guard).")
    skill_prompt: str = Field(description="The agent's instruction/prompt.")
    tools: list[str] = Field(default_factory=list, description="Tool names; MUST be empty for a reasoner.")
    output_schema_ref: str = Field(description="Name of a known artifact schema (validated against a registry).")
    boundaries: list[Boundary] = Field(
        default_factory=lambda: [Boundary.PUBLIC],
        description="Boundaries this agent may touch; FIXED on the spec (no runtime escalation, §9.2).",
    )
    origin: Literal["registry", "created"] = "registry"
    version: int = 1
    eval_score: float | None = Field(default=None, description="Latest aggregate eval score; None until graded.")
    active: bool = Field(default=True, description="Whether this version is the active one for its key.")


class GradeReport(BaseModel):
    """Output of a grader (SENTINEL-012 §10.1). ``hard_failures`` block; other failing ``checks`` flag."""

    passed: bool
    grader: Literal["code", "model"] = "code"
    hard_failures: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict, description="check name → passed.")
    score: float | None = Field(default=None, description="Aggregate 0-1 (model grader); None for pure code grade.")
    notes: str | None = None


class RubricScore(BaseModel):
    """LLM-as-judge rubric (SENTINEL-012 §10.1). Each axis 1-5; independent judge model."""

    relevance: int = Field(ge=1, le=5)
    faithfulness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    persona_fit: int = Field(ge=1, le=5)
    justification: str = Field(description="One paragraph: why these scores, tied to the artifact.")


# --------------------------------------------------------------------------- #
# New domain-skill output schemas (the BiltIQ value chain, SENTINEL-012 §2.4).
# --------------------------------------------------------------------------- #
class ProductProfile(BaseModel):
    """One of OUR products, as profiled by the self_profile skill."""

    name: str
    category: str
    positioning: str = Field(description="How we position this product.")
    strengths: list[str] = Field(default_factory=list)


class SelfProfile(BaseModel):
    """Output of the ``self_profile`` skill: our own org/products (the 'us' side of the compare)."""

    org: str = Field(description="Our organisation/brand.")
    products: list[ProductProfile] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)


class ComparisonAxis(BaseModel):
    """A single us-vs-them comparison dimension."""

    axis: str = Field(description="The dimension compared, e.g. 'pricing', 'integrations', 'SLA'.")
    ours: str = Field(description="Our position on this axis.")
    theirs: str = Field(description="The rival's position on this axis.")
    verdict: Literal["win", "lose", "parity"]
    note: str | None = None


class ComparisonMatrix(BaseModel):
    """Output of the ``compare`` skill: our product vs one rival across axes (SENTINEL-012 §2.4)."""

    subject: str = Field(description="Our product.")
    rival: str = Field(description="The competitor product/company.")
    axes: list[ComparisonAxis] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class ProgramStrategy(BaseModel):
    """Project-level, cross-product market-capture strategy (SENTINEL-012 §9.6). Consumes the SET of
    ComparisonMatrix results — distinct from the per-artifact ``StrategyOverlay``."""

    assessment: str = Field(description="Where we stand across the product line + the overall angle.")
    action_plan: list[RecommendedAction] = Field(default_factory=list)
    ran_on_partial_data: bool = Field(
        default=False, description="True if some comparisons were missing when this was synthesised (§9.4)."
    )


class Result(BaseModel):
    """The deliverable of an orchestrated Task (SENTINEL-012 §1). ``degraded``/``missing_inputs``
    surface fail-soft state so a partial run is reported, never silently presented as complete (§9.4)."""

    task_id: str
    summary: str = Field(default="", description="Human-readable headline of what was produced.")
    artifacts: list[str] = Field(default_factory=list, description="Refs (ids) to produced artifacts.")
    citations: list[Source] = Field(default_factory=list)
    dashboard_payload: dict = Field(default_factory=dict, description="UI render data (map/matrix/strategy).")
    grade: GradeReport | None = None
    persona_rendered: str | None = Field(
        default=None,
        description="Audience-adapted prose for the task's persona (render-only; facts unchanged, AC-8/17).",
    )
    degraded: bool = False
    missing_inputs: list[str] = Field(default_factory=list)
    preferred_format: str | None = Field(
        default=None,
        description="Hard render hint stamped from UserProfile.preferred_format: "
                    "'bullets' | 'prose' | 'table'. None = default bullets.",
    )


# --------------------------------------------------------------------------- #
# Universal domain-specialist output schemas (SENTINEL-014).
# Each domain has its own artifact type tailored to that research context.
# All follow the same Findings+Sources+Gaps pattern for provenance consistency.
# --------------------------------------------------------------------------- #

class SoftwareBrief(BaseModel):
    """Output of the ``software`` skill: deep profile of a software product, library, or API."""

    target: str = Field(description="The software product, library, or API being researched.")
    one_line_summary: str = Field(description="One-sentence positioning of the software.")
    category: str = Field(description="Category, e.g. 'vector database', 'LLM inference framework'.")
    tech_stack: list[Finding] = Field(default_factory=list, description="Languages, frameworks, dependencies.")
    api_quality: list[Finding] = Field(default_factory=list, description="API design, SDK quality, DX signals.")
    community_health: list[Finding] = Field(
        default_factory=list, description="Stars, contributors, activity, ecosystem size.")
    maintenance_activity: list[Finding] = Field(
        default_factory=list, description="Release cadence, issue resolution, roadmap signals.")
    integration_support: list[Finding] = Field(
        default_factory=list, description="Known integrations, connectors, marketplace presence.")
    pricing_model: list[Finding] = Field(default_factory=list, description="Licensing, pricing tiers, OSS status.")
    alternatives: list[str] = Field(default_factory=list, description="Named alternative products.")
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    assessment: str | None = Field(default=None, description="Strategic standing + build/buy/adopt signal.")
    action_plan: list[RecommendedAction] = Field(default_factory=list)


class FinancialProfile(BaseModel):
    """Output of the ``finance`` skill: intelligence brief on a company, instrument, or market."""

    target: str = Field(description="The company, instrument, or market being profiled.")
    one_line_summary: str = Field(description="One-sentence financial standing summary.")
    financial_summary: str = Field(description="Narrative overview of financial health and trajectory.")
    key_metrics: list[Finding] = Field(
        default_factory=list, description="Revenue, growth, margins, debt, valuation — cited figures only.")
    market_position: list[Finding] = Field(
        default_factory=list, description="Competitive standing, market share, sector trends.")
    risk_signals: list[Finding] = Field(
        default_factory=list, description="Red flags, regulatory risks, concentration risks.")
    recent_developments: list[Finding] = Field(
        default_factory=list, description="Earnings, M&A, leadership changes, filings.")
    investment_thesis: str | None = Field(
        default=None, description="Neutral synthesis of bull/bear case — no advice, facts only.")
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    assessment: str | None = Field(default=None)
    action_plan: list[RecommendedAction] = Field(default_factory=list)


class AcademicBrief(BaseModel):
    """Output of the ``academic`` skill: literature survey on a research topic or question."""

    topic: str = Field(description="The academic topic or research question.")
    one_line_summary: str = Field(description="One-sentence overview of the state of knowledge.")
    topic_overview: str = Field(description="Narrative: what is known, key debates, open questions.")
    key_findings: list[Finding] = Field(
        default_factory=list, description="Concrete, cited research findings — each with its source.")
    research_gaps: list[Gap] = Field(
        default_factory=list, description="What is not yet known or contested.")
    notable_researchers: list[str] = Field(
        default_factory=list, description="Named researchers or institutions prominent in this area.")
    methodology_notes: list[str] = Field(
        default_factory=list, description="Dominant methods, dataset types, or evaluation approaches.")
    sources: list[Source] = Field(default_factory=list)
    assessment: str | None = Field(default=None, description="Synthesis of where the field stands.")
    action_plan: list[RecommendedAction] = Field(default_factory=list)


class NutritionBrief(BaseModel):
    """Output of the ``nutrition`` skill: evidence-based brief on a food, nutrient, or dietary pattern.

    Non-clinical: this schema surfaces public research and general guidance only.
    It is NOT a clinical recommendation and must not be used as such.
    """

    topic: str = Field(description="The food, nutrient, ingredient, or dietary approach researched.")
    one_line_summary: str = Field(description="One-sentence evidence-based summary.")
    evidence_quality: str = Field(
        description="Strength of evidence: 'strong RCT evidence', 'observational only', 'conflicting', etc.")
    key_claims: list[Finding] = Field(
        default_factory=list, description="Cited evidence-backed claims (positive, neutral, or negative).")
    practical_guidance: list[str] = Field(
        default_factory=list, description="General public-health guidance derived from the evidence.")
    contraindications: list[str] = Field(
        default_factory=list,
        description="Known populations or interactions to be aware of (general, non-clinical).")
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    disclaimer: str = Field(
        default="General information only. Not medical or clinical advice. Consult a qualified practitioner.",
        description="Always present. Not removable via prompt.",
    )
    assessment: str | None = Field(default=None)
    action_plan: list[RecommendedAction] = Field(default_factory=list)


class TravelBrief(BaseModel):
    """Output of the ``travel`` skill: research brief on a destination, itinerary, or travel question."""

    destination: str = Field(description="The destination, route, or travel topic researched.")
    one_line_summary: str = Field(description="One-sentence travel summary.")
    destination_overview: str = Field(description="What makes this destination notable; character/vibe.")
    practical_info: list[Finding] = Field(
        default_factory=list, description="Visa, currency, transport, connectivity — cited facts.")
    highlights: list[Finding] = Field(
        default_factory=list, description="Key experiences, sites, or activities with sources.")
    safety_notes: list[Finding] = Field(
        default_factory=list, description="Safety, health advisories, and precautions (current, cited).")
    best_time: str | None = Field(default=None, description="Best season/months to visit with reasoning.")
    budget_range: str | None = Field(default=None, description="Indicative daily budget range.")
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    assessment: str | None = Field(default=None)
    action_plan: list[RecommendedAction] = Field(default_factory=list)


class DepartmentMapping(BaseModel):
    """One government department's challenge mapped to a vendor capability."""
    department: str = Field(description="Government department or policy area.")
    challenge: str = Field(description="Specific problem or operational challenge faced.")
    solution: str = Field(description="How the vendor's product/service addresses this challenge.")
    impact: str = Field(default="", description="Expected outcome or benefit.")


class DeptResearchOutput(BaseModel):
    """Intermediate output of one govt_dept_research step — findings for a single department."""

    department: str = Field(default="", description="The department this research covers.")
    findings: str = Field(default="", description="Aggregated findings text about this department.")
    sources: list[str] = Field(default_factory=list, description="Source URLs cited.")
    gaps: list[str] = Field(default_factory=list, description="Missing evidence.")


class GovernmentProposal(BaseModel):
    """Output of the ``govt_proposal`` skill: vendor capability mapped to government client needs."""

    client: str = Field(description="Government entity being proposed to (e.g. 'Assam State Government').")
    vendor: str = Field(description="Company or product making the proposal.")
    one_line_summary: str = Field(description="One-sentence value proposition.")
    executive_summary: str = Field(description="2-3 paragraph executive summary of the proposal.")
    client_challenges: list[Finding] = Field(
        default_factory=list, description="Researched problems, pain points, and priorities of the client.")
    vendor_capabilities: list[Finding] = Field(
        default_factory=list, description="Researched capabilities and strengths of the vendor.")
    department_mappings: list[DepartmentMapping] = Field(
        default_factory=list, description="Per-department capability-to-need mapping.")
    competitive_advantage: str = Field(
        default="", description="Why this vendor vs cloud/foreign alternatives (sovereignty, cost, compliance).")
    pilot_plan: str = Field(default="", description="90-day or phased engagement / pilot plan.")
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    assessment: str | None = Field(default=None)
    action_plan: list[RecommendedAction] = Field(default_factory=list)


class ProductOption(BaseModel):
    """A single product found during product research."""
    name: str = Field(description="Full product model name.")
    brand: str = Field(description="Brand / manufacturer.")
    price: str = Field(default="", description="Current price with currency (e.g. '₹84,990').")
    processor: str = Field(default="", description="CPU model and generation.")
    ram: str = Field(default="", description="RAM size and type.")
    storage: str = Field(default="", description="Storage size and type.")
    display: str = Field(default="", description="Screen size, resolution, panel type.")
    battery: str = Field(default="", description="Battery capacity and estimated life.")
    score: str = Field(default="", description="Value score or review rating (e.g. '8.5/10').")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    source_url: str = Field(default="", description="Product page or review URL.")


class ProductResearch(BaseModel):
    """Output of the ``product_research`` skill: multi-product discovery, comparison, and recommendation."""

    criteria: str = Field(description="The buyer's stated requirements (budget, specs, use case).")
    one_line_summary: str = Field(description="One-sentence headline recommendation.")
    products_found: list[ProductOption] = Field(
        default_factory=list, description="All products discovered that meet the criteria.")
    winner: str = Field(default="", description="Recommended product name.")
    winner_rationale: str = Field(default="", description="Why this product wins on value-for-money.")
    value_ranking: list[str] = Field(
        default_factory=list, description="All products ranked best-to-worst by value-for-money.")
    sources: list[Source] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    assessment: str | None = Field(default=None)
    action_plan: list[RecommendedAction] = Field(default_factory=list)


# A registry of artifact schemas that an AgentSpec.output_schema_ref may name (SENTINEL-012 §9.2).
# Used by validate_agent_spec to reject specs that point at an unknown schema.
KNOWN_OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "Battlecard": Battlecard,
    "AccountBrief": AccountBrief,
    "CompetitorList": CompetitorList,
    "SelfProfile": SelfProfile,
    "ComparisonMatrix": ComparisonMatrix,
    "ProgramStrategy": ProgramStrategy,
    # SENTINEL-014: universal domain specialists
    "SoftwareBrief": SoftwareBrief,
    "FinancialProfile": FinancialProfile,
    "AcademicBrief": AcademicBrief,
    "NutritionBrief": NutritionBrief,
    "TravelBrief": TravelBrief,
    "GovernmentProposal": GovernmentProposal,
    "ProductResearch": ProductResearch,
    "DeptResearchOutput": DeptResearchOutput,
}


# ``Task.result`` is a forward reference to ``Result`` (defined above, after ``Task``). Rebuild the
# model now that ``Result`` is in module scope so the annotation resolves.
Task.model_rebuild()
