"""SENTINEL-012 Phase 3, Step 14 — the AgentRegistry (design §2.1 / §10.3, AC-12 / AC-21).

The registry turns "make me an agent for capability X in domain Y" from *rebuild-every-time* into
*reuse-the-best-known-specialist*. It has three jobs:

1. **Seed** — index the shipped skills (``SKILL_SPECS``) as ``AgentSpec`` rows, so every existing
   capability is resolvable by ``(capability, domain)`` from day one (design §2.1: "the mode library
   becomes the seed of the skill registry").
2. **Resolve (AC-21)** — return the highest-scoring *active* spec for a key, reusing it rather than
   minting a duplicate. Ranking: ``(eval_score ?? -1.0, version)`` — a graded spec beats an ungraded
   one; a newer version breaks ties; an ungraded lone seed still resolves.
3. **Validate + build (AC-12)** — a *created* spec (the Phase-3 planner will mint these on a miss,
   Step 15) is checked against four invariants before it can run, then built through the SAME
   ``make_agent`` / ``resolve_model`` seam as every other agent — so a spec built under
   ``cloud_allowed=False`` constructs **no Gemini object** (sovereignty by introspection, not prompt).

Durability is ADR-0004's ``agent_specs`` table via :class:`SpecStore`; the registry is the policy
layer on top (seeding, ranking, validation, supersession), the store is the mechanism.

Scope note (Step 14): ``build_from_spec`` builds the *single agent* a spec describes. Seed skills are
multi-step pipelines — ``dag.py`` still staffs them via ``SKILL_SPECS`` / ``build_step_agents`` this
step; the registry *indexes* them for reuse, it does not yet replace the pipeline builder. Unifying
the two staffing paths is Step 15.
"""

from __future__ import annotations

from typing import get_args

from google.adk.agents import Agent

from sentinel.agent.modes._build import make_agent
from sentinel.agent.modes.spec import SKILL_SPECS, ResearchModeSpec
from sentinel.artifacts.schemas import KNOWN_OUTPUT_SCHEMAS, AgentSpec, Boundary
from sentinel.config import SentinelConfig, get_config
from sentinel.config.schema import (
    REASONER_ROLES,
    AgentConfig,
    PromptTemplate,
    Role,
)
from sentinel.memory.store import SpecStore
from sentinel.tools.private.workspace_mcp import build_private_toolset
from sentinel.tools.public.web_search import get_search_tool

# The tool *kinds* the engine knows how to wire (build_step_agents' vocabulary). A created spec may
# only name these — anything else is an off-allow-list capability escalation (§9.2), rejected by
# validate_agent_spec before the spec can be stored or run. Keep in lock-step with _resolve_tools.
ALLOWED_TOOLS: frozenset[str] = frozenset({"search", "private"})

_VALID_ROLES: frozenset[str] = frozenset(get_args(Role))


class SpecValidationError(ValueError):
    """A created/registered ``AgentSpec`` violated one or more registry invariants (AC-12). The
    message lists every violation, not just the first — the planner (Step 15) gets the full set."""


def spec_violations(spec: AgentSpec) -> list[str]:
    """Pure check (no I/O) → the list of invariant violations; empty list ⇒ valid. The non-raising
    twin of :func:`validate_agent_spec`, for the planner to test a candidate without exception flow.

    Four invariants (design §9.2 / §10.3):
      1. ``role`` is a known :data:`Role`.
      2. ``output_schema_ref`` names a schema in :data:`KNOWN_OUTPUT_SCHEMAS`.
      3. a reasoner (synthesizer/strategist) is **tool-free** — the SENTINEL-011 latency/sovereignty
         guard, here as a build-time invariant on the spec, not just on ``make_agent``.
      4. every tool is in :data:`ALLOWED_TOOLS` — no escalation to an unknown capability.
    """
    problems: list[str] = []
    if spec.role not in _VALID_ROLES:
        problems.append(f"unknown role {spec.role!r} (valid: {sorted(_VALID_ROLES)})")
    if spec.output_schema_ref not in KNOWN_OUTPUT_SCHEMAS:
        problems.append(
            f"unknown output_schema_ref {spec.output_schema_ref!r} "
            f"(known: {sorted(KNOWN_OUTPUT_SCHEMAS)})"
        )
    if spec.role in REASONER_ROLES and spec.tools:
        problems.append(
            f"reasoner role {spec.role!r} must be tool-free, but declares tools {spec.tools!r} "
            "(reasoners run on gemma-4-26B — give tool work to a tool-caller role)"
        )
    off_list = [t for t in spec.tools if t not in ALLOWED_TOOLS]
    if off_list:
        problems.append(
            f"off-allow-list tools {off_list!r} (allowed: {sorted(ALLOWED_TOOLS)})"
        )
    return problems


def validate_agent_spec(spec: AgentSpec) -> None:
    """Raise :class:`SpecValidationError` if ``spec`` violates any invariant; return silently if it
    is clean. The choke-point ``build_from_spec`` calls before building, and ``register`` before
    persisting — nothing unvalidated reaches the ``agent_specs`` table or a runnable agent."""
    problems = spec_violations(spec)
    if problems:
        raise SpecValidationError(
            f"AgentSpec {spec.id!r} ({spec.capability}/{spec.domain}) is invalid: "
            + "; ".join(problems)
        )


def _seed_spec(spec: ResearchModeSpec) -> AgentSpec:
    """Index a shipped skill as an ``AgentSpec``. The seed describes the skill's terminal
    artifact-producer (every mode ends in a tool-free ``synthesize`` reasoner), which is enough to
    make the capability resolvable. ``id`` is deterministic ⇒ re-seeding is idempotent."""
    return AgentSpec(
        id=f"seed-{spec.capability}-{spec.domain}",
        name=spec.name,
        capability=spec.capability,
        domain=spec.domain,
        role="synthesizer",
        skill_prompt=f"Seed skill {spec.capability!r} (domain {spec.domain!r}); "
                     f"built via the SKILL_SPECS pipeline {spec.name!r}.",
        tools=[],
        output_schema_ref=spec.output_schema.__name__,
        boundaries=[Boundary.PRIVATE, Boundary.PUBLIC] if spec.has_private else [Boundary.PUBLIC],
        origin="registry",
    )


def seed_specs() -> list[AgentSpec]:
    """Every shipped skill as an ``AgentSpec`` (the registry's initial population)."""
    return [_seed_spec(s) for s in SKILL_SPECS.values()]


def _resolve_tools(tool_names: list[str], cfg: SentinelConfig, search_provider: str) -> list | None:
    """Map a spec's abstract tool kinds → live tool objects, reusing the exact wiring
    ``build_step_agents`` uses (AP #1: one tool-construction path). Returns ``None`` for a tool-free
    spec so ``make_agent`` builds a bare reasoner."""
    tools: list = []
    for name in tool_names:
        if name == "search":
            tools.append(get_search_tool(
                search_provider, results=cfg.search.results,
                max_calls=getattr(cfg.search, "max_calls", 0),
            ))
        elif name == "private":
            tools.append(build_private_toolset())
        # off-allow-list names are impossible here — validate_agent_spec rejects them upstream.
    return tools or None


class AgentRegistry:
    """Reuse-by-score over a :class:`SpecStore` (ADR-0004). Seeds the shipped skills on first use so
    every capability resolves immediately; the Phase-3 planner adds ``origin="created"`` specs."""

    def __init__(self, store: SpecStore | None = None, *, seed: bool = True) -> None:
        self.store = store or SpecStore()
        if seed:
            self._seed()

    def _seed(self) -> None:
        """Idempotent — deterministic ids + ``INSERT OR REPLACE`` mean re-seeding never duplicates."""
        for spec in seed_specs():
            self.store.save_spec(spec)

    def register(self, spec: AgentSpec) -> str:
        """Validate then persist a spec (AC-12 gate on the write path). Raises before any row is
        written if the spec is invalid."""
        validate_agent_spec(spec)
        return self.store.save_spec(spec)

    def resolve(self, capability: str, domain: str) -> AgentSpec | None:
        """The best *active* spec for the key, or ``None`` if the capability is unknown (a planner
        miss → Step 15 mints one). Reuse, not rebuild: ranking by ``(eval_score ?? -1.0, version)``
        returns an existing spec; it never creates a row (AC-21)."""
        candidates = self.store.active_specs(capability, domain)
        if not candidates:
            return None
        return max(candidates, key=lambda s: (s.eval_score if s.eval_score is not None else -1.0,
                                              s.version))

    def build_from_spec(
        self,
        spec: AgentSpec,
        cfg: SentinelConfig | None = None,
        *,
        backend: str | None = None,
        cloud_allowed: bool = True,
        search_provider: str = "gemini",
        name: str | None = None,
        output_key: str | None = None,
    ) -> Agent:
        """Build the single agent a spec describes, through the standard ``make_agent`` /
        ``resolve_model`` seam (AC-12). The spec is validated first; its ``role``/``skill_prompt`` are
        injected as a transient config entry on a deep copy of ``cfg`` (the live config is never
        mutated), so the spec rides the same tiering + sovereignty path as a config-defined agent —
        under ``cloud_allowed=False`` a reasoner builds a ``LiteLlm`` on gemma-4-26B with no Gemini
        object constructed."""
        validate_agent_spec(spec)
        cfg = cfg or get_config()
        work = cfg.model_copy(deep=True)
        key = spec.id
        # Inject the spec's runtime knobs under a synthetic key so make_agent can look them up. A
        # fresh dict (not in-place mutation) keeps the copy's provenance clean.
        work.agents = {**work.agents, key: AgentConfig(role=spec.role)}
        work.prompts = {**work.prompts, key: PromptTemplate(
            template=spec.skill_prompt, variables=[], default_template=spec.skill_prompt,
        )}
        tools = _resolve_tools(spec.tools, work, search_provider)
        schema = KNOWN_OUTPUT_SCHEMAS[spec.output_schema_ref]
        return make_agent(
            work, key, name=name or spec.name, output_key=output_key or spec.capability,
            mode_backend=backend, tools=tools, output_schema=schema, cloud_allowed=cloud_allowed,
        )
