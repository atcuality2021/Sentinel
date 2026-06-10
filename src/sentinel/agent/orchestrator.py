"""Orchestrator — runs a mode pipeline and returns a durable artifact.

Public entry point: ``run(target, mode, ...)``. It seeds session state, drives the ADK
SequentialAgent to completion, validates the structured output against its schema, and
writes it via the configured ArtifactWriter (FR-09). A run trace is captured for
observability (FR-12) and the demo narrative.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from google.adk.agents import SequentialAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from sentinel.agent.governance import (
    cloud_allowed,
    effective_backend,
    effective_search_provider,
)
from sentinel.artifacts.schemas import (
    SCHEMA_FOR_MODE,
    AccountBrief,
    ExtractionSet,
    Mode,
    StrategyOverlay,
)
from sentinel.artifacts.writer import ArtifactWriter, WriteResult, get_writer
from sentinel.config import get_config
from sentinel.memory import DataBoundary, MemoryDelta, MemoryEntry
from sentinel.tools.private.workspace_mcp import private_boundary_configured

APP_NAME = "sentinel"
_USER_ID = "operator"

_OUTPUT_KEY = {"competitor": "battlecard", "client": "account_brief"}

# The state keys written by the tool-free *reasoner* agents (synthesizer + strategist). These run on
# the slow gemma-4-26B and must be SSE-streamed (the 26B endpoint 524s on non-streamed long gens);
# every other agent is a tool-caller on the fast 12B and must run NON-streamed (streamed function-call
# argument deltas intermittently fail to reassemble into valid JSON in ADK's lite_llm). This set is the
# partition seam between the two passes (SENTINEL-011 / streaming-524). Reasoners are always the
# contiguous tail of the pipeline, so the partition preserves order.
REASONER_OUTPUT_KEYS = frozenset({"battlecard", "account_brief", "strategy"})

# Global concurrency gate on the leaf ADK runner (SENTINEL-013 Step 7). The DAG level-scheduler fans a
# wave out with asyncio.gather; this semaphore caps how many leaf runs are in-flight at once so a wide
# fan-out can't open N vLLM connections and starve interactive chat on the same endpoint. It is bound to
# the *running* loop (asyncio.Semaphore binds to the loop live at first await) and rebuilt whenever the
# loop or the configured limit changes — tests spin a fresh loop per ``asyncio.run`` and would otherwise
# hit "bound to a different event loop". One tuple is held at a time: (loop, limit, semaphore).
_LEAF_SEM: tuple[object, int, asyncio.Semaphore] | None = None


def _leaf_semaphore(limit: int) -> asyncio.Semaphore:
    """Return the process-wide leaf-run gate for the current loop, (re)creating it on a loop- or
    limit-change. ``limit`` comes from ``backend.max_concurrency``; ``ge=1`` in the schema keeps it a
    real gate (a 0 would deadlock every run)."""
    global _LEAF_SEM
    loop = asyncio.get_running_loop()
    if _LEAF_SEM is None or _LEAF_SEM[0] is not loop or _LEAF_SEM[1] != limit:
        _LEAF_SEM = (loop, limit, asyncio.Semaphore(limit))
    return _LEAF_SEM[2]


def _configured_max_concurrency() -> int:
    """The leaf-run ceiling from the *global* config, for callers that don't thread a per-run ``cfg``
    (the legacy direct ``run_step`` callers). Fail-soft: any config error falls back to 3, never 0 (a
    0 would gate every run to a deadlock)."""
    try:
        return max(1, int(get_config().backend.max_concurrency))
    except Exception:
        return 3


def _configured_max_turns() -> int:
    """Turn-controller ceiling from the *global* config (SENTINEL-015 FR-06). Mirrors
    ``_configured_max_concurrency`` — fail-soft, never 0."""
    try:
        return max(1, int(get_config().backend.max_turns))
    except Exception:
        return 30


@dataclass
class RunResult:
    mode: str
    target: str
    artifact: BaseModel
    write: WriteResult
    backend: str
    trace: list[str] = field(default_factory=list)
    delta: MemoryDelta | None = None


def allowed_boundaries(mode: Mode) -> set[DataBoundary]:
    """The boundaries a mode may read from memory. THIS is the enforcement seam (AC-3): a
    competitor run gets ``{PUBLIC}`` only, so it literally cannot pass PRIVATE to ``recall``."""
    if mode == "competitor":
        return {DataBoundary.PUBLIC}
    return {DataBoundary.PUBLIC, DataBoundary.PRIVATE}


def _render_memory_context(entries: list[MemoryEntry], *, relations: list | None = None) -> str:
    """Compact, boundary-tagged prior-memory block appended to the synthesizer instruction.

    Returns "" for no entries AND no relations so the instruction stays byte-identical to
    SENTINEL-001 (AC-10). Optionally includes a knowledge-graph section listing related entities
    (SENTINEL-016 G-06).
    """
    if not entries and not relations:
        return ""
    lines: list[str] = []
    if entries:
        lines.append(
            "\n\n## Prior memory for this entity (boundary-filtered, accumulated across prior runs)"
        )
        for e in entries:
            tag = e.boundary.value.upper()
            src = f" — {e.source_label}" if e.source_label else ""
            lines.append(f"- ({tag}) {e.content}{src}")
        lines.append(
            "Use this prior context where it is still relevant; prefer fresh findings on conflict, "
            "and never let PRIVATE memory leak into a public-only field."
        )
    if relations:
        lines.append("\n## Known entity relationships (knowledge graph, PUBLIC boundary)")
        for r in relations:
            ctx = f" — {r.context}" if r.context else ""
            lines.append(f"- {r.from_entity} → {r.rel_type} → {r.to_entity}{ctx}")
    return "\n".join(lines)


def _render_episodic_context(episodes: list) -> str:
    """Compact episodic recall block prepended to the synthesizer instruction (SENTINEL-015 FR-01).

    Returns "" for empty episodes so the instruction is byte-identical to pre-015 (AC-10 parity).
    Top 5 findings per episode, capped at 150 chars each.
    The injected text warns the LLM not to re-present these as fresh findings.
    """
    if not episodes:
        return ""
    lines = [
        "\n\n## Episodic Memory: Prior Research Sessions",
        "(These are recalled from previous runs. Do not present them as freshly discovered "
        "findings — use them only as background context to avoid redundancy.)",
    ]
    for ep in episodes:
        label = f"{ep.target} ({ep.mode})" if getattr(ep, "target", None) else ep.entity
        lines.append(f"\n### {label}")
        texts = getattr(ep, "finding_texts", []) or []
        for txt in texts[:5]:
            lines.append(f"- {str(txt)[:150]}")
    return "\n".join(lines)


def _build_sequential_agent(
    mode: Mode, backend, config, memory_context, *, cloud_allowed, search_provider
):
    """The legacy per-mode SequentialAgent (SENTINEL-001..005) — the default topology."""
    if mode == "competitor":
        from sentinel.agent.modes.competitor import build_competitor_agent

        return build_competitor_agent(
            backend, config, memory_context=memory_context,
            cloud_allowed=cloud_allowed, search_provider=search_provider,
        )
    if mode == "client":
        from sentinel.agent.modes.client import build_client_agent

        return build_client_agent(
            backend, config, memory_context=memory_context,
            cloud_allowed=cloud_allowed, search_provider=search_provider,
        )
    raise ValueError(f"Unknown mode {mode!r} (expected 'competitor' or 'client')")


def _build_agent(
    mode: Mode,
    backend: str | None = None,
    config=None,
    memory_context: str = "",
    *,
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
    trace: list[str] | None = None,
):
    """Build the run agent. Coordinator (A2A) when ``coordinator.enabled`` (SENTINEL-011), else the
    legacy SequentialAgent. Ships dark: with the flag off this is byte-identical to SENTINEL-001..005.

    Fail-soft (NFR-4): if the coordinator fails to build, degrade to the SequentialAgent so a
    misconfiguration never takes the run down.
    """
    cfg = config or get_config()
    if getattr(cfg.coordinator, "enabled", False):
        try:
            from sentinel.agent.coordinator import build_coordinator

            agent = build_coordinator(
                mode, cfg, backend=backend, cloud_allowed=cloud_allowed,
                search_provider=search_provider, memory_context=memory_context,
            )
            if trace is not None:
                specialists = ", ".join(t.agent.name for t in getattr(agent, "tools", []) or [])
                trace.append(f"coordinator=on · delegates to: {specialists}")
            return agent
        except Exception as exc:  # never let a coordinator misconfig break the run
            if trace is not None:
                trace.append(f"coordinator=on but build failed ({type(exc).__name__}); "
                             "degraded to sequential")
    return _build_sequential_agent(
        mode, backend, cfg, memory_context,
        cloud_allowed=cloud_allowed, search_provider=search_provider,
    )


def _model_label(agent) -> str:
    """Human-readable model id for the trace (string for Gemini, .model for LiteLlm)."""
    m = getattr(agent, "model", None)
    if isinstance(m, str):
        return m
    inner = getattr(m, "model", None)
    return str(inner) if inner else type(m).__name__


def _coerce_artifact(raw, schema: type[BaseModel]) -> BaseModel:
    """State may hold the artifact as a pydantic model, dict, or JSON string."""
    if isinstance(raw, schema):
        return raw
    if isinstance(raw, BaseModel):
        return schema.model_validate(raw.model_dump())
    if isinstance(raw, dict):
        return schema.model_validate(raw)
    if isinstance(raw, str):
        return schema.model_validate(json.loads(raw))
    raise TypeError(f"Cannot coerce {type(raw)} into {schema.__name__}")


def _merge_strategy(artifact, state) -> str:
    """Deterministically merge the strategy overlay onto the artifact (SENTINEL-009 AC-10).

    Pure code, not the LLM — the researched findings stay immutable; only the additive
    assessment/action_plan/objection_handling fields are populated. Fail-soft (NFR-3): a missing or
    malformed overlay leaves the artifact untouched and yields a trace note instead of raising.
    """
    raw = state.get("strategy")
    if raw is None:
        return "strategy: none"
    try:
        overlay = _coerce_artifact(raw, StrategyOverlay)
    except Exception as exc:
        return f"strategy: skipped ({type(exc).__name__})"
    artifact.assessment = overlay.assessment
    artifact.action_plan = overlay.action_plan
    if isinstance(artifact, AccountBrief):
        artifact.objection_handling = overlay.objection_handling
    return f"strategy: {len(overlay.action_plan)} actions"


def _merge_extraction_gaps(artifact, state) -> str:
    """Deterministically fold the two-tier extractor's gaps onto the artifact (SENTINEL-008 AC-4).

    The synthesizer consumed ``{extractions}`` in-graph, but a per-source Gap must never be silently
    lost if the LLM omits it — so pure code unions the extractor's gaps onto ``artifact.gaps``
    (deduped by boundary + what-was-missing). Fail-soft (NFR-3): a missing or malformed extractions
    state yields a trace note, never an exception.
    """
    raw = state.get("extractions")
    if raw is None:
        return "extractions: none"
    try:
        es = _coerce_artifact(raw, ExtractionSet)
    except Exception as exc:
        return f"extractions: skipped ({type(exc).__name__})"
    seen = {(g.boundary, g.what_was_missing) for g in artifact.gaps}
    added = 0
    for gap in es.gaps:
        if (gap.boundary, gap.what_was_missing) not in seen:
            artifact.gaps.append(gap)
            seen.add((gap.boundary, gap.what_was_missing))
            added += 1
    return f"extractions: {len(es.extractions)} sources, {len(es.gaps)} gaps (+{added} merged)"


def _recall_memory(
    target: str, mode: Mode, cfg, *, project_id: str | None = None
) -> tuple[str, object | None, int, int]:
    """Fetch the prior run + boundary-filtered entity memory + episodic episodes (SENTINEL-015).

    Returns ``(memory_context, prior_run, entity_count, episode_count)``.
    Fail-soft (NFR-5): any storage error degrades to ("", None, 0, 0) — never breaks a run.

    - Entity memory is gated by ``cfg.memory.entity_memory`` (pre-015).
    - Episodic injection is gated by ``cfg.memory.episodic_recall`` (SENTINEL-015 FR-01).
    - ``project_id`` is threaded to ``recall_episodes`` so KB semantic search supplements
      the keyword LIKE search when the project has indexed KB content (gap 5).
    - When both are off, ``memory_context`` is "" → byte-identical to SENTINEL-001 (AC-10).
    """
    prior = None
    entity_count = 0
    episode_count = 0
    try:
        from sentinel.memory import MemoryStore, RunStore

        store = RunStore()
        prior = store.latest_for(target)
        ctx_parts: list[str] = []

        if getattr(cfg.memory, "entity_memory", True):
            _mem = MemoryStore()
            recalled = _mem.recall(target, allowed_boundaries(mode))
            entity_count = len(recalled)
            relations = _mem.get_related(target)
            entity_ctx = _render_memory_context(recalled, relations=relations)
            if entity_ctx:
                ctx_parts.append(entity_ctx)

        if getattr(cfg.memory, "episodic_recall", True):
            top_k = int(getattr(cfg.memory, "episodic_recall_top_k", 3))
            episodes = store.recall_episodes(
                target, top_k=top_k, mode=mode, project_id=project_id
            )
            episode_count = len(episodes)
            ep_ctx = _render_episodic_context(episodes)
            if ep_ctx:
                ctx_parts.append(ep_ctx)

        return "".join(ctx_parts), prior, entity_count, episode_count
    except Exception:  # storage must never break a run
        return "", prior, entity_count, episode_count


def _persist_run(
    *, target, mode, backend, artifact, reference, prior_run, cfg, trace
) -> MemoryDelta | None:
    """Persist the run record (always), write memory entries (if enabled), compute the delta.

    Fail-soft: a storage error is recorded in the trace and yields ``delta=None``.
    """
    try:
        from sentinel.memory import (
            MemoryStore,
            RunStore,
            boundary_counts,
            compute_delta,
            finding_texts,
        )
        from sentinel.memory.schema import RunRecord

        texts = finding_texts(artifact)
        pub, priv = boundary_counts(artifact)
        delta = compute_delta(prior_run, texts)
        # Code-grade every produced artifact (SENTINEL-012 Step 5). Deterministic, no LLM/network.
        # Recorded in the trace here; DB persistence lands with the Phase-2 Result (which has a
        # `grade` field). The runtime sovereign guarantee is structural (resolve_model), so the
        # grader's `sovereign` check (which needs the built models) is exercised in the eval path.
        from sentinel.eval.graders import code_grade

        grade = code_grade(artifact, allowed_boundaries=allowed_boundaries(mode))
        trace.append(
            "grade: pass" if grade.passed
            else f"grade: FAIL ({', '.join(grade.hard_failures)})"
        )
        RunStore().save(
            RunRecord(
                entity=target, target=target, mode=mode, backend=backend,
                kind=type(artifact).__name__, public=pub, private=priv,
                gaps=len(getattr(artifact, "gaps", []) or []),
                reference=reference, finding_texts=texts,
                # provenance (SENTINEL-008): persist the run's cited sources; run_seq is assigned
                # by RunStore.save from the prior per-entity count.
                sources=list(getattr(artifact, "sources", []) or []),
            )
        )
        if getattr(cfg.memory, "entity_memory", True):
            MemoryStore().process_run(target, artifact)
        trace.append(
            f"memory: stored {pub} public + {priv} private findings · {delta.summary}"
        )
        return delta
    except Exception as exc:  # never let memory persistence break a completed run
        trace.append(f"memory: skipped ({type(exc).__name__})")
        return None


def _recompute_priority(*, target, mode, cfg, trace) -> None:
    """Recompute + persist the entity's deterministic PriorityScore after a run (SENTINEL-011b).

    Runs AFTER ``_persist_run`` so the just-completed run + freshly-extracted memory are reflected.
    Topology-agnostic: shared by the coordinator and SequentialAgent paths. Guarded by
    ``priority.enabled`` and fail-soft (NFR-4) — a scoring/storage error never breaks a completed run.

    Boundary invariant is inherited (SENTINEL-002): ``allowed_boundaries(mode)`` is passed straight
    through, so a competitor (PUBLIC-only) run can never score private engagement. No LLM, no network
    in the path (SENTINEL-010 NFR-1) — the arithmetic stays deterministic and auditable.
    """
    if not getattr(cfg.priority, "enabled", True):
        return
    try:
        from sentinel.priority import PriorityStore, compute_account_priority

        score = compute_account_priority(
            target, allowed_boundaries=allowed_boundaries(mode), config=cfg
        )
        PriorityStore().save(score)
        trace.append(f"priority: {score.tier} ({score.score:.0f})")
    except Exception as exc:  # never let priority recompute break a completed run
        trace.append(f"priority: skipped ({type(exc).__name__})")


def _reasoner_output_keys(mode: Mode, cfg) -> set[str]:
    """The Pass-2 (reasoner) output-key set for a mode — **derived from config roles**, not a hardcoded
    literal (SENTINEL-012 Phase 0).

    A sub-agent belongs to Pass 2 iff its config ``role`` is a reasoner role (``REASONER_ROLES`` =
    synthesizer/strategist → gemma-4-26B, SSE-streamed). Deriving the set from roles (rather than the
    frozen ``REASONER_OUTPUT_KEYS``) means any *new* reasoner skill partitions correctly without editing
    a global. Falls back to :data:`REASONER_OUTPUT_KEYS` if a spec can't be resolved.
    """
    from sentinel.agent.modes.spec import CLIENT_SPEC, COMPETITOR_SPEC
    from sentinel.config.schema import REASONER_ROLES

    try:
        spec = COMPETITOR_SPEC if mode == "competitor" else CLIENT_SPEC
        keys = {
            step.output_key for step in spec.steps
            if cfg.agents[step.agent_key].role in REASONER_ROLES
        }
        strat_key = f"{mode}.strategist"  # appended by maybe_strategist; a reasoner role
        if strat_key in cfg.agents and cfg.agents[strat_key].role in REASONER_ROLES:
            keys.add("strategy")
        return keys or set(REASONER_OUTPUT_KEYS)
    except Exception:  # never let partition-derivation break a run — fall back to the legacy literal
        return set(REASONER_OUTPUT_KEYS)


def _build_subagents(
    mode: Mode, backend, cfg, memory_context, *, cloud_allowed, search_provider
):
    """The flat, **un-parented** sub-agent list + the reasoner output-key set for a mode.

    Mirrors ``build_competitor_agent`` / ``build_client_agent`` but returns the list instead of the
    wrapped ``SequentialAgent`` — because the two-pass split (below) re-wraps two *subsets* in their
    own SequentialAgents, and ADK lets a sub-agent belong to exactly one parent. Building the full
    pipeline first and re-partitioning would raise "already has a parent"; building the flat list and
    wrapping each half once does not. Returns ``(subs, reasoner_keys)`` where ``reasoner_keys`` is the
    role-derived Pass-2 set (:func:`_reasoner_output_keys`).
    """
    from sentinel.agent.modes._build import maybe_strategist
    from sentinel.agent.modes.spec import CLIENT_SPEC, COMPETITOR_SPEC, build_step_agents

    spec = COMPETITOR_SPEC if mode == "competitor" else CLIENT_SPEC
    subs = build_step_agents(
        spec, cfg, backend, cloud_allowed=cloud_allowed, search_provider=search_provider,
        memory_context=memory_context, two_tier=getattr(cfg.research, "two_tier", False),
    )
    # Strategist (SENTINEL-009) is appended after the research steps, exactly as the mode builders
    # do — its output_key "strategy" lands it in Pass 2 (reasoner), after the synthesizer it reads.
    strategist = maybe_strategist(cfg, mode, backend=backend, cloud_allowed=cloud_allowed)
    if strategist is not None:
        subs.append(strategist)
    return subs, _reasoner_output_keys(mode, cfg)


async def run_step(
    agent,
    *,
    message_text,
    seed_state,
    streaming,
    trace,
    max_concurrency: int | None = None,
    max_turns: int | None = None,
    max_retries: int = 3,
    base_retry_delay_s: float = 1.0,
) -> dict:
    """Run one built agent to completion and return its final session state.

    **Generic, mode-free executor (SENTINEL-012 Phase 0):** the caller supplies the seed
    ``message_text``, so this same function drives the legacy two-pass pipeline today and
    arbitrary orchestrated steps in Phase 3.

    **Turn controller (SENTINEL-015 FR-06):** ``max_turns`` caps the number of LLM calls ADK
    will make per step. Passed as ``RunConfig.max_llm_calls``; guarded with ``try/except TypeError``
    for ADK versions that don't yet have this field. ``None`` falls back to
    :func:`_configured_max_turns` (default 30 from config).

    **Retry policy (SENTINEL-015 FR-07):** transient 5xx errors from the 26B vLLM endpoint
    are retried up to ``max_retries`` times with exponential backoff
    ``delay = base_retry_delay_s * 2^attempt`` (1s, 2s, 4s by default). Pass
    ``base_retry_delay_s=0.0`` in tests for instant retries. All callers keep working —
    new params have defaults.

    The concurrency semaphore wraps the entire retry loop — a retry is still the same leaf
    run occupying one concurrency slot. Sub-agent model labels are logged once before the
    first attempt to avoid trace flooding on retries.
    """
    limit = max_concurrency if max_concurrency is not None else _configured_max_concurrency()
    turns = max_turns if max_turns is not None else _configured_max_turns()

    async with _leaf_semaphore(limit):
        # Log sub-agent labels once before any attempt (trace flooding guard on retry).
        for sub in getattr(agent, "sub_agents", []) or []:
            trace.append(f"agent {sub.name} model={_model_label(sub)}")

        last_exc: Exception | None = None
        for attempt in range(max(1, max_retries)):
            try:
                runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
                session = await runner.session_service.create_session(
                    app_name=APP_NAME, user_id=_USER_ID, state=dict(seed_state),
                )
                message = types.Content(role="user", parts=[types.Part(text=message_text)])
                # Guard: max_llm_calls may not exist on all installed ADK versions.
                try:
                    run_config = RunConfig(streaming_mode=streaming, max_llm_calls=turns)
                except TypeError:
                    run_config = RunConfig(streaming_mode=streaming)
                async for event in runner.run_async(
                    user_id=_USER_ID, session_id=session.id,
                    new_message=message, run_config=run_config,
                ):
                    if getattr(event, "partial", False):
                        continue  # streaming delta — wait for the aggregated event
                    author = getattr(event, "author", "?")
                    if getattr(event, "content", None) and event.content.parts:
                        for p in event.content.parts:
                            if getattr(p, "function_call", None):
                                trace.append(f"{author} → tool:{p.function_call.name}")
                            elif getattr(p, "text", None) and p.text.strip():
                                trace.append(f"{author} · {p.text.strip()[:80]}")
                final = await runner.session_service.get_session(
                    app_name=APP_NAME, user_id=_USER_ID, session_id=session.id
                )
                return dict(final.state)
            except Exception as exc:
                last_exc = exc
                if attempt < max(1, max_retries) - 1:
                    delay = base_retry_delay_s * (2 ** attempt)
                    trace.append(
                        f"run_step: attempt {attempt + 1}/{max_retries} failed "
                        f"({type(exc).__name__}); retry in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    trace.append(
                        f"run_step: all {max_retries} attempts failed ({type(exc).__name__})"
                    )
        raise last_exc  # type: ignore[misc]


def _artifact_from_state(state: dict, mode: Mode):
    """Coerce the mode's output_key out of final state, raising if the pipeline produced nothing."""
    raw = state.get(_OUTPUT_KEY[mode])
    if raw is None:
        raise RuntimeError(
            f"Pipeline produced no '{_OUTPUT_KEY[mode]}' in state. State keys: {list(state)}"
        )
    return _coerce_artifact(raw, SCHEMA_FOR_MODE[mode])


async def _execute_pipeline(
    target: str,
    mode: Mode,
    *,
    cfg,
    backend: str | None,
    cloud_ok: bool,
    provider: str,
    memory_context: str,
    vertical_context: str | None,
    trace: list[str],
    max_turns: int | None = None,
    max_retries: int = 3,
    base_retry_delay_s: float = 1.0,
):
    """Build the agent(s), run the ADK runner, and return ``(artifact, final_state)``.

    **Two-pass split (SENTINEL-011 / streaming-524), the user's "12B tools → 26B reasoner" pipeline:**
    the SequentialAgent path is partitioned by output_key into Pass 1 (tool-callers on the fast 12B,
    run NON-streamed so function-call argument JSON reassembles cleanly) and Pass 2 (the tool-free
    reasoners on the slow 26B, run SSE-streamed so the long generation flows tokens past the ~100s
    Cloudflare origin timeout that 524s a non-streamed 26B gen). Pass 2 runs in a new session seeded
    with Pass-1's final state, so the synthesizer reasons over the 12B's research output.

    The coordinator path (A2A, ships dark) is a single LlmAgent that tool-calls specialists via
    AgentTool — streaming would break those tool-calls, so it runs single-pass, NON-streamed.

    Factored out of :func:`run_async` so it can be re-invoked: when a two-tier run raises, the
    caller retries this once with two-tier forced off (SENTINEL-008.1 fail-soft). Raises on a
    runner error or a missing artifact — the caller decides whether to fall back or propagate.
    """
    base_state = {"target": target, "vertical_context": vertical_context or ""}
    seed_msg = f"Produce a {mode} intelligence artifact for: {target}"
    mc = getattr(cfg.backend, "max_concurrency", None)  # leaf-run ceiling (Step 7), per-run cfg

    # --- Coordinator path (ships dark): single run, NON-streamed (it tool-calls specialists) ---- #
    if getattr(cfg.coordinator, "enabled", False):
        try:
            from sentinel.agent.coordinator import build_coordinator

            agent = build_coordinator(
                mode, cfg, backend=backend, cloud_allowed=cloud_ok,
                search_provider=provider, memory_context=memory_context,
            )
            specialists = ", ".join(t.agent.name for t in getattr(agent, "tools", []) or [])
            trace.append(f"coordinator=on · delegates to: {specialists}")
            final_state = await run_step(
                agent, message_text=seed_msg, seed_state=base_state,
                streaming=StreamingMode.NONE, trace=trace, max_concurrency=mc,
                max_turns=max_turns, max_retries=max_retries,
                base_retry_delay_s=base_retry_delay_s,
            )
            return _artifact_from_state(final_state, mode), final_state
        except Exception as exc:  # never let a coordinator misconfig break the run
            trace.append(f"coordinator=on but build failed ({type(exc).__name__}); "
                         "degraded to sequential two-pass")

    # --- SequentialAgent path: the two-pass 12B-tools → 26B-reasoner split ---------------------- #
    # Pass-2 membership is derived from config *roles* (reasoner → SSE), not a hardcoded key set.
    subs, reasoner_keys = _build_subagents(
        mode, backend, cfg, memory_context,
        cloud_allowed=cloud_ok, search_provider=provider,
    )
    pass1 = [s for s in subs if s.output_key not in reasoner_keys]
    pass2 = [s for s in subs if s.output_key in reasoner_keys]

    # Pass 1 — tool-calling + extraction on the fast 12B, NON-streamed. Produces the research state.
    state = dict(base_state)
    if pass1:
        trace.append(f"pass1 (12B tools, non-streamed): {', '.join(s.name for s in pass1)}")
        state = await run_step(
            SequentialAgent(name=f"{mode}_research", sub_agents=pass1),
            message_text=seed_msg, seed_state=base_state,
            streaming=StreamingMode.NONE, trace=trace, max_concurrency=mc,
            max_turns=max_turns, max_retries=max_retries,
            base_retry_delay_s=base_retry_delay_s,
        )

    # Pass 2 — reasoning on the slow 26B, SSE-streamed, seeded with Pass-1 state so the synthesizer
    # reasons over the 12B's findings. (If a mode somehow has no reasoner, Pass 1 already produced
    # the artifact.)
    if pass2:
        trace.append(f"pass2 (26B reason, SSE): {', '.join(s.name for s in pass2)}")
        state = await run_step(
            SequentialAgent(name=f"{mode}_reason", sub_agents=pass2),
            message_text=seed_msg, seed_state=state,
            streaming=StreamingMode.SSE, trace=trace, max_concurrency=mc,
            max_turns=max_turns, max_retries=max_retries,
            base_retry_delay_s=base_retry_delay_s,
        )

    return _artifact_from_state(state, mode), state


async def run_async(
    target: str,
    mode: Mode = "competitor",
    *,
    vertical_context: str | None = None,
    writer: ArtifactWriter | None = None,
    backend: str | None = None,
    config=None,
    project_id: str | None = None,
) -> RunResult:
    cfg = config or get_config()

    # --- Governance routing (SENTINEL-005): the "brain" decides cloud vs on-prem ---------- #
    # A client run with a connected private boundary counts as "private" for block_cloud_on_private.
    private = mode == "client" and private_boundary_configured()
    cloud_ok = cloud_allowed(cfg) and not (private and cfg.governance.block_cloud_on_private)
    eff_backend = effective_backend(cfg, backend, private=private)
    provider = effective_search_provider(cfg, allow_cloud=cloud_ok, backend=eff_backend)

    # --- Memory recall (boundary-filtered + episodic) BEFORE the run -------------------- #
    # The allowed set is fixed by mode: a competitor run can only ever recall PUBLIC memory.
    memory_context, prior_run, entity_count, episode_count = _recall_memory(
        target, mode, cfg, project_id=project_id
    )

    # Label the run with what the agents ACTUALLY used: governance may have forced on-prem,
    # so the trace shows the effective backend + the resolved public-search provider (AC-10).
    resolved_backend = eff_backend
    trace: list[str] = [
        f"backend={resolved_backend}", f"mode={mode}", f"target={target}",
        f"compliance={cfg.governance.compliance_mode}", f"cloud_allowed={cloud_ok}",
        f"search={provider}",
        f"memory: {entity_count} entity facts + {episode_count} episodes recalled",
    ]

    writer = writer or get_writer("markdown")
    two_tier = getattr(cfg.research, "two_tier", False)
    # Harness params resolved once here, forwarded to every _execute_pipeline call below.
    _max_turns = getattr(cfg.backend, "max_turns", None)
    _max_retries = int(getattr(cfg.backend, "max_retries", 3))
    _retry_delay = float(getattr(cfg.backend, "base_retry_delay_s", 1.0))
    try:
        artifact, state = await _execute_pipeline(
            target, mode, cfg=cfg, backend=backend, cloud_ok=cloud_ok, provider=provider,
            memory_context=memory_context, vertical_context=vertical_context, trace=trace,
            max_turns=_max_turns, max_retries=_max_retries, base_retry_delay_s=_retry_delay,
        )
    except Exception as exc:
        # Two-tier is a pure enhancement (SENTINEL-008.1): any extractor failure — JSON truncation,
        # context-window overflow, a transient 5xx — must degrade to single-tier, never abort the
        # run. A single-tier run (or any other topology) has no fallback: re-raise.
        if not two_tier:
            raise
        trace.append(
            f"two-tier failed ({type(exc).__name__}: {str(exc)[:80]}); fell back to single-tier"
        )
        single = cfg.model_copy(deep=True)
        single.research.two_tier = False
        two_tier = False  # so the gap-merge below is skipped (single-tier has no extractions)
        artifact, state = await _execute_pipeline(
            target, mode, cfg=single, backend=backend, cloud_ok=cloud_ok, provider=provider,
            memory_context=memory_context, vertical_context=vertical_context, trace=trace,
            max_turns=_max_turns, max_retries=_max_retries, base_retry_delay_s=_retry_delay,
        )

    # Strategy overlay (SENTINEL-009): deterministically merge before writing. Guarded — when
    # strategy is off no strategist ran, so state has no "strategy" key and this is a no-op anyway.
    if getattr(cfg.strategy, "enabled", False):
        trace.append(_merge_strategy(artifact, state))
    # Two-tier (SENTINEL-008): union the extractor's per-source gaps onto the artifact so none is
    # lost. No-op when off (no extractor ran ⇒ no "extractions" state key); also skipped after a
    # fallback (two_tier flipped False above).
    if two_tier:
        trace.append(_merge_extraction_gaps(artifact, state))
    write_result = writer.write(artifact)
    trace.append(f"artifact written → {write_result.backend}:{write_result.reference}")

    # --- Persist run + extract memory + compute delta AFTER the run ---------------------- #
    delta = _persist_run(
        target=target, mode=mode, backend=resolved_backend, artifact=artifact,
        reference=write_result.reference, prior_run=prior_run, cfg=cfg, trace=trace,
    )

    # --- Recompute the deterministic focus score (SENTINEL-011b) ------------------------- #
    # After persistence, so this run's findings + memory feed the score. Fail-soft, no LLM.
    _recompute_priority(target=target, mode=mode, cfg=cfg, trace=trace)

    return RunResult(
        mode=mode, target=target, artifact=artifact,
        write=write_result, backend=resolved_backend, trace=trace, delta=delta,
    )


def run(
    target: str,
    mode: Mode = "competitor",
    *,
    vertical_context: str | None = None,
    writer: ArtifactWriter | None = None,
    backend: str | None = None,
    config=None,
) -> RunResult:
    """Synchronous wrapper around :func:`run_async`."""
    return asyncio.run(
        run_async(
            target, mode, vertical_context=vertical_context, writer=writer,
            backend=backend, config=config,
        )
    )
