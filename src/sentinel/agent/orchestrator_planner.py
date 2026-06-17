"""SENTINEL-012 Phase 3, Step 15 — the orchestrator planner (design §3c, AC-3 / AC-21).

Turns a ``Task`` (objective × domain × persona) into an inspectable ``Plan`` DAG, then **staffs**
every step against the :class:`AgentRegistry`: reuse an existing specialist by ``(capability,
domain)`` where one exists (AC-21), and mint a *validated* created ``AgentSpec`` only on a miss
(AC-3). The planner never runs anything — it proposes; the autonomy gate (Step 16) decides whether
the proposal executes.

Two passes, mirroring the Step-12/13 split of *inference* from *deterministic post-hook*:

1. **Plan pass (LLM):** a tool-free strategist (26B) emits the step-DAG via ``output_schema=Plan``.
   It only chooses *what* to produce and *in what order* — capabilities + dependencies. No staffing,
   no tools, no boundaries.
2. **Staffing pass (pure):** :func:`staff_plan` resolves each step's capability against the registry
   and stamps ``step.agent_spec_id``. A miss mints a **conservative** created spec (see
   :func:`_mint_created_spec`) — registered through ``registry.register`` so it is validated before
   it can ever run, and persisted to the ``agent_specs`` table (this is the first *writer* of
   ADR-0004's table).

The two passes are separated so the staffing logic is testable with a mocked planner: inject a
``Plan`` and assert the resolve/mint/validate behaviour without any inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.agent import orchestrator as orch
from sentinel.agent.modes._build import make_agent
from sentinel.agent.registry import AgentRegistry
from sentinel.artifacts.schemas import AgentSpec, Boundary, Plan, Step, Task
from sentinel.config import SentinelConfig, get_config

PLAN_KEY = "plan"

# A planner-created agent cannot invent a new output contract at runtime — ``output_schema_ref`` MUST
# name a schema already in ``KNOWN_OUTPUT_SCHEMAS`` (validate_agent_spec enforces this, §9.2). So a
# created spec is constrained to the existing artifact vocabulary; this is the default it gets when
# the planner invents a capability with no obvious schema. ``ProgramStrategy`` is the most general
# "synthesis/recommendations" artifact. Overridable per call via ``created_schema_ref``.
_DEFAULT_CREATED_SCHEMA = "ProgramStrategy"


@dataclass
class PlanProposal:
    """The planner's output: a staffed ``Plan`` + the specs it had to create (empty when every
    capability was reused). The autonomy gate (Step 16) shows ``created_specs`` for approval before
    anything in the plan runs."""

    plan: Plan
    created_specs: list[AgentSpec] = field(default_factory=list)


# What each shipped capability does — given to the planner so it picks the RIGHT one (the #1 planner
# error was confusing self_profile, which profiles OUR org, with competitor, which profiles a RIVAL).
_CAPABILITY_DESCRIPTIONS: dict[str, str] = {
    "self_profile": "profile OUR OWN organisation/products (the 'us' side). Use exactly ONCE for us.",
    "competitor": "profile ONE RIVAL company/product (the 'them' side). Use once PER named rival.",
    "compare": "compare US vs ONE rival across axes → a comparison matrix. Depends on self_profile + that competitor.",
    "client": "research one account/customer (public + private CRM signal) → an account brief.",
    "program_strategy": "synthesise a cross-product market-capture strategy from the comparison(s). Depends on the compare step(s).",
    # SENTINEL-014: universal domain specialists
    "software": "research a software product, library, or API → SoftwareBrief (tech stack, community health, DX, pricing).",
    "finance": "research a company, instrument, or market → FinancialProfile (key metrics, risk signals, market position).",
    "academic": "survey academic literature on a topic → AcademicBrief (key findings, research gaps, methodology).",
    "nutrition": "research a food, nutrient, or dietary pattern → NutritionBrief (evidence quality, claims, general guidance). Non-clinical only.",
    "travel": "research a destination or travel question → TravelBrief (highlights, practical info, safety, budget).",
    # SENTINEL-017: new domains
    "govt_proposal": "research a government client's challenges + a vendor's capabilities → GovernmentProposal (department mappings, pilot plan). Use when the objective is a government technology proposal.",
    "product_research": "discover ALL products meeting buyer criteria → ProductResearch (qualifying products with specs/prices, winner, value ranking). Use when the objective is product discovery/comparison for a buyer.",
    # Per-dept sub-agents (used internally by the govt_proposal multi-step DAG)
    "govt_dept_research": "research ONE government department's challenges, digital gaps, and AI opportunities. Used per-department inside a govt_proposal plan.",
    "govt_synthesis": "synthesize all per-dept research into a final GovernmentProposal. Must depend on all govt_dept_research steps.",
}


def _capability_catalogue(registry: AgentRegistry) -> str:
    """A human-readable list of reusable capabilities for the planner prompt — one line per distinct
    ``capability`` the registry can already staff, WITH a description so the planner picks the right one
    (not just by name). The planner is told to prefer these."""
    seen: dict[tuple[str, str], None] = {}
    for spec in registry.store.list_specs():
        if spec.active:
            seen.setdefault((spec.capability, spec.domain), None)
    if not seen:
        return "(none yet — every capability will be newly created)"
    lines = []
    for cap, dom in sorted(seen):
        desc = _CAPABILITY_DESCRIPTIONS.get(cap, "a domain specialist.")
        lines.append(f"- capability={cap!r}  domain={dom!r}  → {desc}")
    return "\n".join(lines)


def _mint_created_spec(capability: str, domain: str, schema_ref: str) -> AgentSpec:
    """Mint a CONSERVATIVE created spec for a capability the registry can't staff (AC-3).

    The safety envelope (§9.2 "no runtime escalation") is encoded here as the *narrowest* viable
    agent, so a planner-invented capability can never quietly gain power:
      - ``role="synthesizer"`` — a reasoner, which ``validate_agent_spec`` forces to be tool-free;
      - ``tools=[]`` — no capability surface;
      - ``boundaries=[PUBLIC]`` — the narrowest boundary; PRIVATE is never auto-granted (widening it
        is a deliberate human act, never a planner default);
      - ``output_schema_ref`` constrained to a KNOWN schema (created agents can't invent a contract).
    ``id`` is deterministic ⇒ re-planning the same miss is idempotent (no duplicate rows).
    """
    return AgentSpec(
        id=f"created-{domain}-{capability}",
        name=f"{capability}_specialist",
        capability=capability,
        domain=domain,
        role="synthesizer",
        skill_prompt=(
            f"You are a specialist producing the '{capability}' result for a {domain} research task. "
            "Synthesize only from the inputs provided in state; record gaps rather than inventing "
            "facts, and cite every claim to a provided source."
        ),
        tools=[],
        output_schema_ref=schema_ref,
        boundaries=[Boundary.PUBLIC],
        origin="created",
    )


def validate_plan(plan: Plan) -> list[str]:
    """Return a list of structural errors in *plan* — empty means valid.

    Currently checks the invariant that every ``compare`` step depends on exactly one
    ``self_profile`` step and at most one ``competitor`` step. A compare step that depends
    on two competitor steps crashes at runtime with a KeyError in ADK template injection.
    """
    by_id = {s.id: s for s in plan.steps}
    errors: list[str] = []
    for step in plan.steps:
        if step.capability != "compare":
            continue
        dep_caps = [by_id[d].capability for d in step.depends_on if d in by_id]
        n_self = dep_caps.count("self_profile")
        n_comp = dep_caps.count("competitor")
        if n_self == 0:
            errors.append(
                f"compare step '{step.id}' has no self_profile dependency "
                f"(depends_on={step.depends_on!r}). compare requires self_profile + competitor."
            )
        if n_comp == 0:
            errors.append(
                f"compare step '{step.id}' has no competitor dependency "
                f"(depends_on={step.depends_on!r})."
            )
        if n_comp > 1:
            errors.append(
                f"compare step '{step.id}' depends on {n_comp} competitor steps "
                f"— only one is allowed per compare. Split into one compare per rival."
            )
    return errors


def staff_plan(
    plan: Plan,
    task: Task,
    registry: AgentRegistry,
    *,
    created_schema_ref: str = _DEFAULT_CREATED_SCHEMA,
) -> list[AgentSpec]:
    """Resolve every step against the registry, stamping ``agent_spec_id`` (AC-21). Reuse where a
    spec exists; mint + register a validated created spec on a miss (AC-3). Returns the created
    specs (so the autonomy gate can surface them). Mutates ``plan.steps`` in place.

    A miss is registered immediately so a *second* step needing the same new capability reuses the
    just-created spec rather than minting a duplicate."""
    created: list[AgentSpec] = []
    domain = task.domain.name
    for step in plan.steps:
        # Normalise: strip any " (domain: ...)" suffix the LLM may have copied verbatim
        # from the catalogue line instead of using just the bare capability name.
        cap = _re.sub(r"\s*\(domain:[^)]*\)\s*$", "", step.capability, flags=_re.I).strip()
        if cap != step.capability:
            step.capability = cap
        spec = registry.resolve(step.capability, domain)
        if spec is None:
            spec = _mint_created_spec(step.capability, domain, created_schema_ref)
            registry.register(spec)        # validates (raises on a bad spec) + persists
            created.append(spec)
        step.agent_spec_id = spec.id
    return created


import re as _re

_COMPARE_RE = _re.compile(r"\b(?:vs\.?|versus|against|compared?\s+(?:to|with)|benchmark|head[- ]to[- ]head)\b", _re.I)
_STRATEGY_RE = _re.compile(r"\b(?:strateg|market[- ]capture|go[- ]to[- ]market|capture the market)\b", _re.I)
_PROFILE_RE = _re.compile(r"\b(?:profile|research|analy[sz]e|assess|overview of|about)\b", _re.I)
# External URL in objective → study of an external company/product, never uses self_profile
_EXTERNAL_URL_RE = _re.compile(r"https?://\S+", _re.I)
# Parenthetical dept list: "(flood, agriculture, land records)"
_GOVT_PAREN_RE = _re.compile(r"\(([^)]+)\)")
# Keyword-based dept extraction (common Indian govt domains)
_GOVT_DEPT_KEYWORDS = [
    "flood management", "agriculture", "land records", "e-governance",
    "healthcare", "education", "border security", "disaster management",
    "digital infrastructure", "rural development", "water management",
    "urban planning", "taxation", "public distribution",
]
_GOVT_DEFAULT_DEPTS = [
    "flood management and disaster response",
    "agriculture and rural development",
    "land records and e-governance",
    "healthcare and public services",
]


def _extract_govt_departments(text: str) -> list[str]:
    """Extract department names from the task objective for per-dept research steps.

    Priority: (1) parenthetical list, (2) keyword scan, (3) 4 generic defaults.
    Returns 2-6 dept name strings, lowercased, stripped.
    """
    # Try parenthetical list first: "(health, education, land records)"
    m = _GOVT_PAREN_RE.search(text)
    if m:
        parts = [p.strip().lower() for p in m.group(1).split(",") if p.strip()]
        if 2 <= len(parts) <= 6:
            return parts

    # Keyword scan
    text_lower = text.lower()
    found = [kw for kw in _GOVT_DEPT_KEYWORDS if kw in text_lower]
    if len(found) >= 2:
        return found[:6]

    return _GOVT_DEFAULT_DEPTS


def _dept_slug(dept: str) -> str:
    """Convert a dept name to a valid step-ID slug: 'flood management' → 'flood_management'."""
    return _re.sub(r"[^a-z0-9]+", "_", dept.lower()).strip("_")[:40]


_SINGLE_STEP_DOMAINS: frozenset[str] = frozenset(
    {"software", "finance", "academic", "nutrition", "travel",
     "product_research"}
    # NOTE: govt_proposal removed — uses multi-step per-dept DAG (see _template_plan below)
)

# Domain aliases: UI-facing domain names → canonical SKILL_SPECS capability.
# e-commerce tasks use the product_research skill (discovery + comparison + recommendation).
_DOMAIN_TO_CAPABILITY: dict[str, str] = {
    "e-commerce": "product_research",
    "ecommerce": "product_research",
    "shopping": "product_research",
}


def _template_plan(task: Task) -> Plan | None:
    """Deterministic plan for shipped value-chains, bypassing the LLM planner for reliability.

    Single-step domains (SENTINEL-014): each maps 1-to-1 to its SKILL_SPECS capability, so a
    1-step plan is always correct — no LLM variance, no risk of a wrong capability slug.

    Market domain (multi-step): regex-driven to handle the compare/strategy chain correctly (the
    12B planner tended to emit 2× competitor or a lone self_profile before this was added).

    Returns ``None`` for anything unrecognised → falls through to the LLM planner.
    """
    pid = f"plan-{task.id}"
    dom = task.domain.name
    cap = _DOMAIN_TO_CAPABILITY.get(dom, dom)

    # SENTINEL-014: each of these domains has exactly one registered skill; a deterministic
    # 1-step plan is both faster and 100% reliable vs. the LLM picking the capability slug.
    # Domain aliases (e.g. e-commerce → product_research) are resolved via _DOMAIN_TO_CAPABILITY.
    if cap in _SINGLE_STEP_DOMAINS:
        return Plan(id=pid, task_id=task.id,
                    steps=[Step(id=cap, capability=cap, output_key=cap)])

    # govt_proposal: one research step per extracted department + one synthesis step.
    # Dept name encoded in step ID so _plan_seeds() can decode it for per-dept targeting.
    if dom == "govt_proposal":
        depts = _extract_govt_departments(task.objective)
        research_steps = [
            Step(
                id=f"research_dept_{_dept_slug(dept)}",
                capability="govt_dept_research",
                output_key=f"research_dept_{_dept_slug(dept)}",
            )
            for dept in depts
        ]
        dept_ids = [s.id for s in research_steps]
        synthesis = Step(
            id="govt_synthesis",
            capability="govt_synthesis",
            output_key="govt_proposal",
            depends_on=dept_ids,
        )
        return Plan(id=pid, task_id=task.id, steps=research_steps + [synthesis])

    if dom != "market":
        return None
    from sentinel.agent.dag import PROGRAM_STRATEGY_CAP   # lazy: the aggregator capability key

    obj = task.objective
    if _COMPARE_RE.search(obj):                              # profile-us + compare-against-rival
        steps = [
            Step(id="self_profile", capability="self_profile", output_key="self_profile"),
            Step(id="competitor", capability="competitor", output_key="competitor"),
            Step(id="compare", capability="compare", depends_on=["self_profile", "competitor"],
                 output_key="compare"),
        ]
        if _STRATEGY_RE.search(obj):                         # …and synthesise a strategy from it
            steps.append(Step(id="strategy", capability=PROGRAM_STRATEGY_CAP, depends_on=["compare"],
                              output_key="program_strategy", inputs={"compare": "compare"}))
        return Plan(id=pid, task_id=task.id, steps=steps)

    # External URL in objective → studying an EXTERNAL company/product.
    # self_profile profiles OUR organisation and must NEVER appear here.
    # program_strategy requires ComparisonMatrix inputs (from a compare step) — not available
    # without self_profile.  Two parallel steps suffice: product_research covers the product/market
    # context; competitor runs the full planner→web-search→battlecard pipeline on the target company.
    if _EXTERNAL_URL_RE.search(obj):
        steps = [
            Step(id="product_research", capability="product_research", output_key="product_research"),
            Step(id="competitor", capability="competitor", output_key="competitor"),
        ]
        return Plan(id=pid, task_id=task.id, steps=steps)

    # Non-compare market tasks (e.g. "Analyze venture capital trends") fall through to the LLM
    # planner so it can pick the right capability using project context.  The old _PROFILE_RE
    # catch-all that mapped any objective containing "analyze/research" to self_profile was
    # wrong: self_profile is for OUR organisation, not external market research.
    return None


async def plan_task(
    task: Task,
    registry: AgentRegistry,
    *,
    cfg: SentinelConfig | None = None,
    backend: str | None = None,
    cloud_allowed: bool = True,
    created_schema_ref: str = _DEFAULT_CREATED_SCHEMA,
    trace: list[str] | None = None,
    project_context: str | None = None,
) -> PlanProposal:
    """Full planner: run the Plan-pass LLM, then the staffing pass. Returns a :class:`PlanProposal`
    (a staffed Plan + any created specs) — nothing executes here (propose-by-default, §AC-13)."""
    cfg = cfg or get_config()
    trace = trace if trace is not None else []

    # Deterministic template for a recognised value-chain (reliable, no LLM variance); else fall through
    # to the dynamic LLM planner for novel objectives/domains.
    plan = _template_plan(task)
    if plan is not None:
        trace.append(f"planner: deterministic template for {task.domain.name} "
                     f"({len(plan.steps)} steps)")
    else:
        from google.adk.agents.run_config import StreamingMode  # lazy: avoids an ADK import at module load

        planner = make_agent(
            cfg, "orchestrator.planner", name="orchestrator_planner",
            output_key=PLAN_KEY, output_schema=Plan, mode_backend=backend, cloud_allowed=cloud_allowed,
        )
        seed = {
            "objective": task.objective,
            "domain": task.domain.name,
            "persona": task.persona.model_dump_json(),
            "capability_catalogue": _capability_catalogue(registry),
            "project_context": project_context or "",
        }
        # Reasoner (26B) ⇒ SSE-streamed to clear the Cloudflare 524 wall (SENTINEL streaming policy).
        state = await orch.run_step(
            planner, message_text=task.objective, seed_state=seed,
            streaming=StreamingMode.SSE, trace=trace,
        )
        raw = state.get(PLAN_KEY)
        plan = raw if isinstance(raw, Plan) else Plan.model_validate(raw)
    plan.task_id = task.id                  # bind the plan to its task (integrity, not LLM's call)
    # The LLM often reuses a step slug (e.g. 's1') or a constant as the plan id — which collides under
    # the store's INSERT-OR-REPLACE-by-id and silently overwrites other tasks' plans. Force a unique
    # deterministic id per task so every task keeps its own plan (and re-planning is idempotent).
    plan.id = f"plan-{task.id}"
    # Structural validation — catches LLM hallucinations (e.g. compare depending on two competitors)
    # before they reach the DAG executor and crash with an ADK KeyError.
    plan_errors = validate_plan(plan)
    for err in plan_errors:
        trace.append(f"planner-validation WARNING: {err}")
    created = staff_plan(plan, task, registry, created_schema_ref=created_schema_ref)
    return PlanProposal(plan=plan, created_specs=created)
