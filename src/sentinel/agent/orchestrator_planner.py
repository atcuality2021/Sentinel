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
        lines.append(f"- {cap} (domain: {dom}) — {desc}")
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


_SINGLE_STEP_DOMAINS: frozenset[str] = frozenset(
    {"software", "finance", "academic", "nutrition", "travel"}
)


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

    # SENTINEL-014: each of these domains has exactly one registered skill; a deterministic
    # 1-step plan is both faster and 100% reliable vs. the LLM picking the capability slug.
    if dom in _SINGLE_STEP_DOMAINS:
        return Plan(id=pid, task_id=task.id,
                    steps=[Step(id=dom, capability=dom, output_key=dom)])

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
    if _PROFILE_RE.search(obj):                              # profile-us only
        return Plan(id=pid, task_id=task.id,
                    steps=[Step(id="self_profile", capability="self_profile",
                                output_key="self_profile")])
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
    created = staff_plan(plan, task, registry, created_schema_ref=created_schema_ref)
    return PlanProposal(plan=plan, created_specs=created)
