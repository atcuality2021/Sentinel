"""DAG driver over a hand-built or planner-emitted ``Plan`` (SENTINEL-012 Step 10 → generalised Step 13).

This is the first *orchestrated* path: instead of one mode's fixed `SequentialAgent`, it walks a
hand-built :class:`~sentinel.artifacts.schemas.Plan` (a step-DAG) and runs each node as a skill on the
generic :func:`sentinel.agent.orchestrator.run_step` executor.

**Step 13** split execution from projection: :func:`_execute_plan` is the engine (toposort → per-step
two-pass run → budgets/cache/fail-soft), and the *assembler* shapes the deliverable. :func:`run_plan`
keeps the BiltIQ map+compare+strategy projection (:func:`_assemble_result`); :func:`run_dag` is the
task-shape-agnostic entry (:func:`assemble_generic`) the Phase-3 planner targets. The BiltIQ shape it
still encodes via :func:`biltiq_program_plan`:

    S1  self_profile(us)
         │
         ├─ S2a competitor(rivalA) ─ S3a compare(us, rivalA) ─┐
         ├─ S2b competitor(rivalB) ─ S3b compare(us, rivalB) ─┤
         │                                                     ▼
         └────────────────────────────────────────── S4  program_strategy(over the matrix set)

It is deliberately *hand-built* (the rivals and edges are fixed when the plan is constructed by
:func:`biltiq_program_plan`); the generic, planner-emitted runner lands in Phase 3. What is real here:

- **Budgets** (:class:`TaskBudget`): max steps / max reasoner calls / wall-clock → a *partial*
  :class:`Result`, never an exception, on exhaustion (AC-16).
- **Fail-soft** (§9.4): a step failure degrades the Result (``degraded`` + ``missing_inputs``) and
  skips only its dependents — the run never crashes (AC-15). The aggregator runs on partial data and
  flags it; linear steps skip when a required input is missing.
- **Per-entity cache** (:class:`StepCache`): freshness gated by ``RunStore.latest_for`` (the plan's
  named mechanism), payload in a JSON sidecar — a cache hit skips re-research entirely.
- **Observability**: each :class:`Step` carries ``status`` + ``started_at``/``finished_at``; a trace
  list mirrors the two-pass executor. ``resume-from-last-good`` re-runs only steps not already ``done``.

Sovereignty is inherited unchanged: every agent is built through ``build_step_agents`` /
``build_program_strategist`` → ``resolve_model(cloud_allowed=)``, so ``on_prem_required`` constructs
no Gemini object anywhere in the DAG (AC-7/11).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sentinel.agent._compat import Agent, SequentialAgent
from google.adk.agents.run_config import StreamingMode

from sentinel.agent import orchestrator as orch
from sentinel.agent.modes.spec import SKILL_SPECS, ResearchModeSpec, build_step_agents
from sentinel.agent.program_strategy import (
    PROGRAM_STRATEGY_KEY,
    build_program_strategist,
    finalize_program_strategy,
    program_strategy_seed,
)
from sentinel.artifacts.schemas import (
    ComparisonMatrix,
    ExtractionSet,
    ProgramStrategy,
    Plan,
    Result,
    Source,
    Step,
)
from sentinel.config import SentinelConfig, get_config
from sentinel.config.schema import REASONER_ROLES
from sentinel.memory.store import RunStore, data_dir

# The capability the program-level strategist is staffed under. It is NOT a SKILL_SPECS entry — it is a
# standalone module (program_strategy.py) with a bespoke merge/finalize path — so the driver dispatches
# it specially below.
PROGRAM_STRATEGY_CAP = "program_strategy"

# Only an *aggregator* runs on partial inputs (§9.4): missing some comparisons is expected and flagged
# via ProgramStrategy.ran_on_partial_data. Every other capability is linear — a missing required input
# means the step cannot produce a faithful result, so it is skipped (and the Result degrades).
PARTIAL_TOLERANT_CAPS = frozenset({PROGRAM_STRATEGY_CAP})

# A step is satisfied (its output is usable by dependents) only when it actually produced an artifact.
_SATISFIED = frozenset({"done", "cached"})


@dataclass
class _StepOutcome:
    """The record :func:`_run_one_step` returns for one admitted step — computed against a *snapshot* of
    ``results`` and mutating no shared accumulator, so a whole level can be run concurrently
    (:func:`asyncio.gather`) and the records folded back deterministically by the scheduler (Step 5).

    ``ran`` is ``True`` only for a real execution (a cache hit completes the step but is not a "run" for
    budget accounting — mirroring the sequential loop's ``continue`` before ``steps_run += 1``).
    ``missing`` carries dep/step ids the fold appends to ``missing_inputs`` (the aggregator's partial
    deps on success; the step's own id on failure)."""

    step: Step
    status: str                               # done | cached | failed
    output_key: str
    artifact: dict | None = None
    reasoner_delta: int = 0
    ran: bool = False
    missing: list[str] = field(default_factory=list)
    degraded: bool = False
    trace: list[str] = field(default_factory=list)


@dataclass
class _Execution:
    """The raw outcome of driving a plan to completion — *before* it is projected into a task-shaped
    :class:`Result`. Splitting execution (mechanism) from assembly (policy) is what lets one driver
    serve both the BiltIQ map+compare+strategy deliverable and an arbitrary planner-emitted DAG
    (SENTINEL-012 Step 13): the loop is identical, only the final projection differs."""

    plan: Plan
    results: dict[str, dict]                  # step.output_key → produced artifact dict
    produced: list[tuple[str, str]]           # (capability, output_key), in completion order
    missing_inputs: list[str]
    degraded: bool


@dataclass
class TaskBudget:
    """A ceiling on a task's cost. The DAG checks it *before* each step and degrades to a partial
    Result the moment any limit is reached (AC-16) — the operator gets what completed, honestly
    labelled, instead of an over-budget run or a hang.

    ``wall_clock_s`` is measured with an injectable monotonic ``clock`` (see :func:`run_plan`) so the
    timeout is testable without sleeping."""

    max_steps: int = 20
    max_reasoner_calls: int = 15
    wall_clock_s: float = 600.0

    def exhausted(self, *, steps_run: int, reasoner_calls: int, elapsed_s: float) -> str | None:
        """Return the name of the first breached limit, or ``None`` if there's budget left."""
        if steps_run >= self.max_steps:
            return "max_steps"
        if reasoner_calls >= self.max_reasoner_calls:
            return "max_reasoner_calls"
        if elapsed_s >= self.wall_clock_s:
            return "wall_clock_s"
        return None


class StepCache:
    """Per-entity skill cache. **Freshness** is gated by ``RunStore.latest_for`` (the plan's named
    mechanism — a RunRecord proves the entity was researched); the **payload** lives in a JSON sidecar
    under the data dir, because a RunRecord is a findings *index*, not the full typed artifact a cache
    hit must hand downstream. A hit therefore needs both: a recent run AND a stored payload.

    Scoped by ``project_id`` so two projects researching the same entity don't cross-pollute (ADR-0003).
    Fail-soft: any read/write error degrades to a miss/no-op, never breaking a run."""

    def __init__(self, *, run_store: RunStore | None = None, project_id: str | None = None) -> None:
        self.run_store = run_store or RunStore()
        self.project_id = project_id
        self.dir = data_dir() / "dag_cache"

    def _sidecar(self, entity: str, capability: str) -> Path:
        scope = self.project_id or "_global"
        safe = "".join(c if c.isalnum() else "_" for c in f"{scope}__{capability}__{entity}").lower()
        return self.dir / f"{safe}.json"

    def get(self, entity: str, capability: str) -> dict | None:
        """Return the cached artifact dict for ``(entity, capability)``, or ``None`` on a miss."""
        try:
            if self.run_store.latest_for(entity, project_id=self.project_id) is None:
                return None  # no recent run ⇒ nothing fresh to reuse
            path = self._sidecar(entity, capability)
            if not path.exists():
                return None
            return json.loads(path.read_text())
        except Exception:  # a cache miss must never break a run
            return None

    def put(self, entity: str, capability: str, artifact: dict) -> None:
        """Persist a freshly-produced artifact dict so a later run can skip re-research."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._sidecar(entity, capability).write_text(json.dumps(artifact))
        except Exception:  # caching is best-effort
            pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terminal_key(capability: str, spec: ResearchModeSpec | None) -> str:
    """The state key a skill writes its final artifact under (the synthesize step is always last)."""
    if capability == PROGRAM_STRATEGY_CAP:
        return PROGRAM_STRATEGY_KEY
    assert spec is not None
    return spec.steps[-1].output_key


def _is_cacheable(spec: ResearchModeSpec | None) -> bool:
    """A skill is cacheable iff it does external research (a search/private step). Pure reasoners
    (compare, program_strategy) read other skills' outputs, so caching them by entity is meaningless."""
    return bool(spec) and any(s.tool in ("search", "private") for s in spec.steps)


def _reasoner_cost(capability: str, spec: ResearchModeSpec | None) -> int:
    """How many 26B-reasoner calls a step will consume — used to *reserve* against ``max_reasoner_calls``
    at frontier admission so a concurrent fan-out can't blow the ceiling between the gate and the run
    (the budget-race the sequential check couldn't have). Mirrors the deltas :func:`_run_one_step`
    actually returns: the aggregator and a created (tool-free) capability each cost 1; a declarative
    skill costs 1 iff it has a ``synthesize`` step, else 0."""
    if capability == PROGRAM_STRATEGY_CAP:
        return 1
    if spec is not None:
        return 1 if any(s.role == "synthesize" for s in spec.steps) else 0
    return 1  # created capability: a single-pass SSE reasoner


def _toposort(steps: list[Step]) -> list[Step]:
    """Kahn's algorithm over ``depends_on`` → a run order. Raises on a cycle or a dangling dependency
    so a malformed hand-built plan fails loudly at build time, not silently mid-run."""
    by_id = {s.id: s for s in steps}
    indeg = {s.id: 0 for s in steps}
    deps: dict[str, list[str]] = {s.id: [] for s in steps}
    for s in steps:
        for dep in s.depends_on:
            if dep not in by_id:
                raise ValueError(f"step {s.id!r} depends on unknown step {dep!r}")
            indeg[s.id] += 1
            deps[dep].append(s.id)
    # Stable queue: preserve the plan's declared order among ready steps (deterministic runs).
    ready = [s.id for s in steps if indeg[s.id] == 0]
    order: list[str] = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for nxt in deps[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(steps):
        raise ValueError("plan DAG has a cycle")
    return [by_id[i] for i in order]


async def _run_agents(
    agents: list[Agent], *, name: str, streaming, seed: dict, message: str, trace: list[str],
    max_concurrency: int | None = None,
    max_retries: int = 3,
) -> dict:
    """Run a one-pass slice of a skill. A single agent is driven directly; multiple are wrapped in a
    SequentialAgent (ADK lets a sub-agent have exactly one parent, so we wrap on demand). The per-run
    ``max_concurrency`` (from ``cfg.backend``) is forwarded to the leaf gate in :func:`orch.run_step`
    (Step 7). ``max_retries`` defaults to 3 for the normal pipeline; callers that apply their own
    fail-soft logic (e.g. per-source extraction) pass 1 to skip retry."""
    import time as _time
    runnable = agents[0] if len(agents) == 1 else SequentialAgent(name=name, sub_agents=agents)
    _t0 = _time.monotonic()
    result = await orch.run_step(
        runnable, message_text=message, seed_state=seed, streaming=streaming, trace=trace,
        max_concurrency=max_concurrency, max_retries=max_retries,
    )
    # G-13: record latency telemetry (fail-soft — never affects the result).
    try:
        _latency_ms = (_time.monotonic() - _t0) * 1000.0
        from sentinel.telemetry import TelemetryEvent
        from sentinel.memory.store import TelemetryStore
        _model = getattr(runnable, "model", "") or ""
        _run_id = str(seed.get("task_id") or seed.get("run_id") or name)
        TelemetryStore().record(TelemetryEvent(
            step=name, model=_model, run_id=_run_id,
            latency_ms=_latency_ms,
            project_id=seed.get("project_id"),
        ))
    except Exception:
        pass
    return result


def _max_concurrency(cfg) -> int | None:
    """The leaf-run ceiling from a per-run ``cfg`` (or ``None`` to defer to global config in run_step)."""
    return getattr(getattr(cfg, "backend", None), "max_concurrency", None)


def _split_findings(findings_raw) -> list[str]:
    """Split ``public_findings`` into per-source units for parallel extraction (SENTINEL-013 §3).

    If ``findings_raw`` is a JSON list of source dicts (search result rows), each dict becomes one
    unit. A search-tool response envelope ``{"results": [...]}`` is unwrapped first. Everything else
    is treated as a single opaque source so ``two_tier=False`` behaviour is preserved (AC-8)."""
    import json as _json

    data = findings_raw
    if isinstance(data, str):
        try:
            data = _json.loads(data)
        except (ValueError, TypeError):
            return [str(findings_raw)]

    if isinstance(data, list) and data:
        return [_json.dumps(item) if isinstance(item, dict) else str(item) for item in data]
    if isinstance(data, dict):
        inner = data.get("results") or data.get("items") or []
        if isinstance(inner, list) and inner:
            return [_json.dumps(item) for item in inner]
        return [_json.dumps(data)]

    return [str(findings_raw)]


async def _run_parallel_extract(
    extractor,
    state: dict,
    *,
    spec: ResearchModeSpec,
    cfg,
    trace: list[str],
    mc: int | None,
) -> dict:
    """Parallel per-source extraction (SENTINEL-013 Step 8).

    Reads ``{public_findings}`` from state, splits into per-source units, runs the cheap 12B
    extractor once per source concurrently (bounded by the global semaphore via :func:`_run_agents`
    → :func:`orch.run_step`), and reduces the per-source :class:`ExtractionSet`s into one that
    the synthesizer reads as ``{extractions}``.

    Each extractor call receives exactly ONE source as its ``{public_findings}`` — this is the
    bounded-input guarantee (AC-8). Fail-soft: a per-source failure contributes an empty extraction
    and a trace entry; the run never crashes (NFR-3)."""
    findings_raw = state.get("public_findings")
    if not findings_raw:
        state["extractions"] = ExtractionSet().model_dump()
        trace.append("parallel extract: no public_findings — empty ExtractionSet")
        return state

    sources = _split_findings(findings_raw)
    max_notes = getattr(getattr(cfg, "research", None), "extract_max_notes_per_source", 8)
    trace.append(f"parallel extract: {len(sources)} source(s) from public_findings")

    async def _extract_one(source_text: str, idx: int) -> ExtractionSet | None:
        try:
            per_source_seed = dict(state)
            per_source_seed["public_findings"] = source_text
            result_state = await _run_agents(
                [extractor], name=f"{spec.capability}_extract_{idx}",
                streaming=StreamingMode.NONE,
                seed=per_source_seed,
                message=f"Extract insights from source {idx}",
                trace=trace, max_concurrency=mc, max_retries=1,
            )
            raw = result_state.get("extractions")
            if raw is None:
                return None
            if isinstance(raw, ExtractionSet):
                return raw
            if isinstance(raw, dict):
                return ExtractionSet.model_validate(raw)
        except Exception as exc:
            trace.append(
                f"parallel extract source {idx}: FAILED ({type(exc).__name__}: {str(exc)[:60]})"
            )
        return None

    per_source = await asyncio.gather(*[_extract_one(src, i) for i, src in enumerate(sources)])

    all_extractions = []
    all_gaps: list = []
    for es in per_source:
        if es is not None:
            all_extractions.extend(es.extractions[:max_notes])
            all_gaps.extend(es.gaps or [])

    state["extractions"] = ExtractionSet(extractions=all_extractions, gaps=all_gaps).model_dump()
    return state


# ------------------------------------------------------------------------------- #
# Field-group definitions for chunked battlecard/accountbrief synthesis.
# Each entry generates one JSON sub-object; results are merged into the final artifact.
# ------------------------------------------------------------------------------- #
_BATTLECARD_CHUNKS = [
    {
        "name": "core",
        "prompt": (
            "Competitor: {target}\nResearch:\n{findings}\n\n"
            "Output ONLY valid JSON (no commentary) for these fields:\n"
            '{{"target":"string","one_line_summary":"one sentence","positioning":"2-3 sentences",'
            '"vertical_context":null}}'
        ),
    },
    {
        "name": "analysis",
        "prompt": (
            "Competitor: {target}\nResearch:\n{findings}\n\n"
            "Output ONLY valid JSON for strengths and weaknesses (max 5 each):\n"
            '{{"strengths":[{{"summary":"...","evidence":"...","boundary":"public"}}],'
            '"weaknesses":[{{"summary":"...","evidence":"...","boundary":"public"}}]}}'
        ),
    },
    {
        "name": "market",
        "prompt": (
            "Competitor: {target}\nResearch:\n{findings}\n\n"
            "Output ONLY valid JSON for pricing and recent news (max 5 each):\n"
            '{{"pricing_signals":[{{"summary":"...","evidence":"...","boundary":"public"}}],'
            '"recent_developments":[{{"summary":"...","evidence":"...","boundary":"public"}}]}}'
        ),
    },
    {
        "name": "strategy",
        "prompt": (
            "Competitor: {target}\nResearch:\n{findings}\n\n"
            "Output ONLY valid JSON for counter-strategy (max 5 items per list):\n"
            '{{"how_to_win":["angle 1","angle 2"],"assessment":"strategic standing",'
            '"action_plan":[],"gaps":[]}}'
        ),
    },
    {
        "name": "evidence",
        "prompt": (
            "Competitor: {target}\nResearch:\n{findings}\n\n"
            "Output ONLY valid JSON listing up to 5 sources:\n"
            '{{"sources":[{{"title":"...","url":"...","snippet":"..."}}]}}'
        ),
    },
]


async def _synthesize_chunked(
    state: dict,
    output_key: str,
    *,
    cfg,
    backend: str,
    cloud_allowed: bool,
    trace: list[str],
) -> dict:
    """Generate a large schema artifact in field-group chunks via direct litellm calls.

    Replaces a single max_output_tokens=8192 synthesizer call that hits the token
    ceiling and produces truncated JSON, with 5 focused calls (1024 tokens each).
    Each call targets a distinct JSON sub-object; results are merged under *output_key*.
    Uses json_object response_format so vLLM forces valid, closed JSON on every chunk.
    """
    import json as _json
    import litellm as _litellm
    from sentinel.llm.gateway import _vllm_api_key

    synth_ac = cfg.agents.get("competitor.synthesizer")
    if synth_ac is None:
        trace.append("chunked_synth: no competitor.synthesizer agent config — skipped")
        return state

    opt = (cfg.backend.roles or {}).get(synth_ac.role) or cfg.backend.vllm
    model_id = synth_ac.model or opt.model
    api_base = opt.api_base
    api_key = _vllm_api_key(api_base)

    target = str(state.get("target", "unknown"))
    # Only apply chunked synthesis for a named competitor (short string).
    # A long objective-style string means this is a generic research task — fall back to ADK pass2
    # so the normal synthesizer prompt runs (chunked prompts assume a single company name).
    if len(target) > 80 or "\n" in target:
        trace.append(f"chunked_synth: target looks like an objective ({len(target)} chars) — skipped")
        return state

    findings_key = "extractions" if state.get("extractions") else "public_findings"
    findings_str = str(state.get(findings_key, ""))[:3000]  # cap to avoid context overflow

    merged: dict = {}
    for chunk in _BATTLECARD_CHUNKS:
        prompt = chunk["prompt"].format(target=target, findings=findings_str)
        try:
            resp = await _litellm.acompletion(
                model=f"hosted_vllm/{model_id}",
                messages=[{"role": "user", "content": prompt}],
                api_base=api_base,
                api_key=api_key,
                max_tokens=1024,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            text = (resp.choices[0].message.content or "").strip()
            if text.startswith("{"):
                merged.update(_json.loads(text))
                trace.append(f"chunked_synth/{chunk['name']}: ok ({len(text)} chars)")
            else:
                trace.append(f"chunked_synth/{chunk['name']}: non-JSON response, skipped")
        except Exception as exc:
            trace.append(
                f"chunked_synth/{chunk['name']}: FAILED ({type(exc).__name__}: {str(exc)[:80]})"
            )

    if merged:
        state = {**state, output_key: merged}
        trace.append(f"chunked_synth: merged {len(merged)} top-level keys → {output_key!r}")
    return state


async def _run_skill(
    spec: ResearchModeSpec, seed: dict, *, cfg, backend, cloud_allowed, search_provider, two_tier,
    trace: list[str], project_id: str | None = None,
) -> dict:
    """Build + run one declarative skill via the two-pass split (12B tools → 26B reasoner), the same
    partition the legacy pipeline uses — derived here from config *roles*, not a hardcoded key set, so
    any new skill partitions correctly. Returns the final session state.

    When ``two_tier`` (SENTINEL-013 Step 8), the single extractor agent that :func:`build_step_agents`
    injects is stripped from pass1 and replaced with :func:`_run_parallel_extract` — one extractor call
    per source, bounded input, concurrent under the global semaphore. The synthesizer already carries the
    ``_2t`` prompt variant (set by :func:`build_step_agents` when ``two_tier=True``), so it still reads
    typed ``{extractions}``; only the production of that key changes."""
    # Lift memory + persona framing from seed into the synthesizer's instruction_suffix
    # (SENTINEL-016 G-04). build_step_agents appends this as text after the prompt, so it reaches
    # the 26B reasoner regardless of whether prompt templates have {memory_context} placeholders.
    _instruction_ctx = str(seed.get("memory_context") or "") + str(seed.get("persona_framing") or "")
    agents = build_step_agents(
        spec, cfg, backend, cloud_allowed=cloud_allowed, search_provider=search_provider,
        two_tier=two_tier, memory_context=_instruction_ctx, project_id=project_id,
    )
    reasoner_keys = {
        s.output_key for s in spec.steps if cfg.agents[s.agent_key].role in REASONER_ROLES
    }
    # Step 8: strip the single extractor from pass1 so we can run it per-source concurrently below.
    extractor_agent = None
    if two_tier and spec.extractor_key:
        non_ext = [a for a in agents if a.output_key != "extractions"]
        ext = [a for a in agents if a.output_key == "extractions"]
        if ext:
            extractor_agent = ext[0]
            agents = non_ext

    pass1 = [a for a in agents if a.output_key not in reasoner_keys]
    pass2 = [a for a in agents if a.output_key in reasoner_keys]
    msg = f"Run the {spec.capability} skill"
    mc = _max_concurrency(cfg)
    state = dict(seed)
    if pass1:
        state = await _run_agents(
            pass1, name=f"{spec.capability}_p1", streaming=StreamingMode.NONE,
            seed=state, message=msg, trace=trace, max_concurrency=mc,
        )
    if extractor_agent is not None:
        state = await _run_parallel_extract(
            extractor_agent, state, spec=spec, cfg=cfg, trace=trace, mc=mc,
        )
    # G-12: sandbox-validate tool outputs before they reach the synthesizer (pass2).
    # This is a best-effort injection/PII check; the run continues with sanitized text on any flag.
    if pass1 and state.get("public_findings"):
        try:
            from sentinel.security.sandbox import validate_tool_output
            _sb = validate_tool_output(str(state["public_findings"]), context=spec.capability)
            state = {**state, "public_findings": _sb.sanitized}
            if not _sb.safe:
                trace.append(f"sandbox({spec.capability}): {_sb.reason}")
        except Exception:
            pass
    if pass2:
        # Guard: compare_synthesizer uses {self_profile} and {battlecard} as ADK template vars.
        # If the planner omitted self_profile (e.g. generated two competitor steps instead of
        # self_profile+competitor), ADK throws KeyError and kills the step. Inject placeholders
        # so the run degrades to a best-effort comparison rather than crashing outright.
        if spec.capability == "compare":
            if "self_profile" not in state:
                # Find any battlecard already in state to use as the "us" side as a fallback.
                _sp_fallback = next(
                    (v for k, v in state.items()
                     if isinstance(v, dict) and k not in ("battlecard",)
                     and any(fk in v for fk in ("strengths", "weaknesses", "org", "target"))),
                    "No self-profile available — treat this as a general comparison.",
                )
                state["self_profile"] = _sp_fallback
                trace.append("compare: self_profile missing from seed — injected fallback")
            if "battlecard" not in state:
                _bc_fallback = next(
                    (v for k, v in state.items()
                     if isinstance(v, dict)
                     and any(fk in v for fk in ("strengths", "weaknesses", "target"))),
                    "No competitor battlecard available.",
                )
                state["battlecard"] = _bc_fallback
                trace.append("compare: battlecard missing from seed — injected fallback")

        if spec.capability == "competitor":
            # Chunked synthesis: 5 × 1024-token calls instead of one 8192-token call.
            # Prevents JSON truncation at the token ceiling (SENTINEL-017 fix).
            # Falls back to the ADK pass2 if all chunks fail (e.g. no API in tests).
            terminal = spec.steps[-1].output_key
            state = await _synthesize_chunked(
                state, terminal, cfg=cfg, backend=backend,
                cloud_allowed=cloud_allowed, trace=trace,
            )
            if terminal not in state:
                trace.append(
                    f"chunked_synth: produced no {terminal!r} — falling back to ADK pass2"
                )
                state = await _run_agents(
                    pass2, name=f"{spec.capability}_p2", streaming=StreamingMode.SSE,
                    seed=state, message=msg, trace=trace, max_concurrency=mc,
                )
        else:
            state = await _run_agents(
                pass2, name=f"{spec.capability}_p2", streaming=StreamingMode.SSE,
                seed=state, message=msg, trace=trace, max_concurrency=mc,
            )
    return state


def _dependency_state(step: Step, by_id: dict, results: dict) -> dict:
    """Expose each satisfied dependency's artifact under BOTH the producer's ``output_key`` and the
    producing skill's CANONICAL terminal key — e.g. a ``competitor`` step's Battlecard appears as
    ``{battlecard}`` and a ``self_profile`` step's profile as ``{self_profile}``, the exact state keys
    downstream skills read.

    This is the data-flow fix: the planner emits ``depends_on`` but rarely ``Step.inputs``, so without
    this a consumer (e.g. ``compare``, which reads ``{self_profile}`` + ``{battlecard}``) never receives
    its upstream outputs and fails with a 'Context variable not found' KeyError (fail-soft → partial).
    Keying by the skill's canonical name (not the planner's free ``output_key``) bridges the naming gap
    between what a producer is *named* and what a consumer *expects*."""
    pool: dict = {}
    for dep_id in step.depends_on:
        dep = by_id.get(dep_id)
        if dep is None or dep.output_key not in results:
            continue
        art = results[dep.output_key]
        pool[dep.output_key] = art                      # under the producer's own output_key
        dep_spec = SKILL_SPECS.get(dep.capability)
        if dep_spec is not None or dep.capability == PROGRAM_STRATEGY_CAP:
            pool[_terminal_key(dep.capability, dep_spec)] = art   # under the skill's canonical key
    return pool


async def _run_created_step(
    step: Step, seed: dict, *, registry, cfg, backend, cloud_allowed, search_provider,
    trace: list[str],
) -> dict:
    """Build + run a planner-*created* capability from its registry spec (TD-1).

    The step carries an ``agent_spec_id`` the planner stamped (Step 15); we fetch that spec and build
    its single agent via ``registry.build_from_spec`` — the same ``make_agent``/``resolve_model`` seam
    every other agent rides, so sovereignty + tiering are inherited (under ``cloud_allowed=False`` it
    builds a ``LiteLlm`` on gemma-4-26B, no Gemini object). The minted spec is a tool-free synthesizer,
    so the agent runs single-pass SSE and writes its artifact straight to ``step.output_key``. A
    missing registry/spec raises — caught by the caller's per-step guard, degrading just this step."""
    created = registry.store.get_spec(step.agent_spec_id) if (registry and step.agent_spec_id) else None
    if created is None:
        raise RuntimeError(
            f"no registry spec for created capability {step.capability!r} "
            f"(agent_spec_id={step.agent_spec_id!r})"
        )
    agent = registry.build_from_spec(
        created, cfg, backend=backend, cloud_allowed=cloud_allowed,
        search_provider=search_provider, output_key=step.output_key,
    )
    state = await _run_agents(
        [agent], name=f"{step.capability}_created", streaming=StreamingMode.SSE,
        seed=seed, message=f"Run the {step.capability} skill", trace=trace,
        max_concurrency=_max_concurrency(cfg),
    )
    raw = state.get(step.output_key)
    if raw is None:
        raise RuntimeError(f"created capability {step.capability!r} produced no {step.output_key!r}")
    return raw if isinstance(raw, dict) else dict(raw)


async def _run_program_strategy(
    matrices: Sequence[ComparisonMatrix], *, missing: int, cfg, backend, cloud_allowed,
    trace: list[str],
) -> dict:
    """Drive the aggregator: seed it with the comparison SET, run the reasoner, stamp the §9.4 flag
    from run state (not the LLM). Returns the strategy artifact dict."""
    agent = build_program_strategist(cfg, backend, cloud_allowed=cloud_allowed)
    state = await _run_agents(
        [agent], name="program_strategy", streaming=StreamingMode.SSE,
        seed=program_strategy_seed(matrices), message="Synthesise the program strategy", trace=trace,
        max_concurrency=_max_concurrency(cfg),
    )
    strat = ProgramStrategy.model_validate(state[PROGRAM_STRATEGY_KEY])
    return finalize_program_strategy(strat, missing=missing).model_dump()


def _fold_outcome(
    outcome: _StepOutcome,
    *,
    results: dict[str, dict],
    produced: list[tuple[str, str]],
    satisfied: set[str],
    missing_inputs: list[str],
    trace: list[str],
) -> None:
    """Fold one :class:`_StepOutcome` into the shared accumulators. Called once per outcome, in the
    plan's **declared order** (the scheduler sorts a concurrently-run level back into declared order
    before folding), so ``produced`` — and therefore the deliverable's headline 'last produced'
    artifact and the citation union — is deterministic regardless of completion order (AC-6)."""
    trace.extend(outcome.trace)
    missing_inputs.extend(outcome.missing)
    if outcome.status in _SATISFIED:
        results[outcome.output_key] = outcome.artifact
        produced.append((outcome.step.capability, outcome.output_key))
        satisfied.add(outcome.step.id)


async def _run_one_step(
    step: Step,
    *,
    by_id: dict,
    results_snapshot: dict[str, dict],
    base: dict,
    seeds: dict[str, dict],
    unsatisfied: list[str],
    spec: ResearchModeSpec | None,
    cache: StepCache | None,
    use_cache: bool,
    cfg,
    backend,
    cloud_allowed: bool,
    search_provider: str,
    two_tier: bool,
    registry,
    project_id: str | None = None,
) -> _StepOutcome:
    """Run a single **already-admitted** step (deps satisfied, budget checked by the scheduler) against a
    snapshot of ``results`` and return a :class:`_StepOutcome`. Pure w.r.t. shared accumulators — it
    reads ``results_snapshot`` and the step's own fields, never the live scheduler state — which is what
    lets the scheduler fan a level out with :func:`asyncio.gather` (Step 5) and fold the records in
    declared order afterwards. ``step.started_at``/``finished_at``/``status`` are stamped here because
    each step object is owned by exactly one task (no cross-step race).

    Mirrors the sequential body exactly: seed assembly → per-entity cache → two-pass skill / aggregator /
    created-capability run, with the same fail-soft contract (any exception degrades just this step)."""
    trace: list[str] = []

    # --- assemble this step's seed (precedence low→high: base ⊕ deps ⊕ literal seeds ⊕ explicit inputs)
    seed = dict(base)
    seed.update(_dependency_state(step, by_id, results_snapshot))
    seed.update(seeds.get(step.id, {}))
    for out_key, state_key in step.inputs.items():
        if out_key in results_snapshot:
            seed[state_key] = results_snapshot[out_key]

    step.started_at = _now_iso()
    step.status = "running"
    entity = seed.get("target")

    # --- govt_synthesis: aggregate all per-dept research into a single public_findings block ------ #
    if step.capability == "govt_synthesis":
        dept_parts: list[str] = []
        for k, v in seed.items():
            if k.startswith("research_dept_"):
                dept_name = k.removeprefix("research_dept_").replace("_", " ").title()
                if isinstance(v, dict):
                    text = v.get("findings") or v.get("summary") or str(v)[:1200]
                    srcs = v.get("sources") or []
                    src_txt = (", ".join(str(s) for s in srcs[:5])) if srcs else ""
                    part = f"=== {dept_name} ===\n{text}"
                    if src_txt:
                        part += f"\nSources: {src_txt}"
                else:
                    part = f"=== {dept_name} ===\n{v}"
                dept_parts.append(part)
        if dept_parts:
            seed["public_findings"] = "\n\n".join(dept_parts)
        else:
            seed.setdefault("public_findings", "No department research available.")

    # --- cache: per-entity, research skills only -------------------------------------------------- #
    if use_cache and cache is not None and _is_cacheable(spec) and entity:
        hit = cache.get(str(entity), step.capability)
        if hit is not None:
            step.status = "cached"
            step.finished_at = _now_iso()
            trace.append(f"{step.id} ({step.capability}): cache hit for {entity!r} — re-research skipped")
            return _StepOutcome(
                step=step, status="cached", output_key=step.output_key, artifact=hit, trace=trace,
            )

    # --- run the step ----------------------------------------------------------------------------- #
    try:
        reasoner_delta = 0
        if step.capability == PROGRAM_STRATEGY_CAP:
            # step.inputs maps output_key → compare_step_id (set by the template planner).
            # LLM-generated multi-compare plans often leave inputs={}, so fall back to
            # scanning depends_on for any key that yields a valid ComparisonMatrix.
            _input_keys = list(step.inputs.keys()) or step.depends_on
            _raw_matrices = []
            for k in _input_keys:
                raw = results_snapshot.get(k)
                if raw is None:
                    continue
                try:
                    _raw_matrices.append(ComparisonMatrix.model_validate(raw))
                except Exception:
                    pass
            matrices = _raw_matrices
            artifact = await _run_program_strategy(
                matrices, missing=len(unsatisfied), cfg=cfg, backend=backend,
                cloud_allowed=cloud_allowed, trace=trace,
            )
            reasoner_delta = 1
        elif spec is not None:
            state = await _run_skill(
                spec, seed, cfg=cfg, backend=backend, cloud_allowed=cloud_allowed,
                search_provider=search_provider, two_tier=two_tier, trace=trace,
                project_id=project_id,
            )
            terminal = _terminal_key(step.capability, spec)
            raw = state.get(terminal)
            if raw is None:
                raise RuntimeError(f"{step.capability} produced no {terminal!r}")
            artifact = raw if isinstance(raw, dict) else dict(raw)
            if any(s.role == "synthesize" for s in spec.steps):
                reasoner_delta = 1
            if use_cache and cache is not None and _is_cacheable(spec) and entity:
                cache.put(str(entity), step.capability, artifact)
        else:
            # Created capability (TD-1): staffed from the registry spec the planner stamped (single-pass SSE).
            artifact = await _run_created_step(
                step, seed, registry=registry, cfg=cfg, backend=backend,
                cloud_allowed=cloud_allowed, search_provider=search_provider, trace=trace,
            )
            reasoner_delta = 1
    except Exception as exc:  # one bad step degrades the Result; it never crashes the run (AC-15)
        step.status = "failed"
        step.finished_at = _now_iso()
        trace.append(f"{step.id} ({step.capability}): FAILED ({type(exc).__name__}: {str(exc)[:80]})")
        return _StepOutcome(
            step=step, status="failed", output_key=step.output_key,
            missing=[step.id], degraded=True, trace=trace,
        )

    step.status = "done"
    step.finished_at = _now_iso()
    trace.append(f"{step.id} ({step.capability}): done → {step.output_key}")

    # Write code-grade eval_score back to created-capability specs so the registry
    # ranking activates (gap 2: eval_score was never written back post-grading).
    # Skill-based steps seed their spec via the fixed SKILL_SPECS; only created
    # capabilities carry a mutable agent_spec_id that benefits from writeback.
    if step.agent_spec_id and registry is not None and artifact is not None:
        try:
            from sentinel.artifacts.schemas import KNOWN_OUTPUT_SCHEMAS
            from sentinel.eval.graders import code_grade

            spec_row = registry.store.get_spec(step.agent_spec_id)
            if spec_row is not None:
                schema = KNOWN_OUTPUT_SCHEMAS.get(spec_row.output_schema_ref)
                if schema is not None:
                    art_obj = schema.model_validate(artifact)
                    grade = code_grade(art_obj)
                    registry.store.update_eval_score(
                        step.agent_spec_id, 1.0 if grade.passed else 0.0
                    )
        except Exception:
            pass  # grading never breaks a completed step

    return _StepOutcome(
        step=step, status="done", output_key=step.output_key, artifact=artifact,
        reasoner_delta=reasoner_delta, ran=True, trace=trace,
    )


async def _execute_plan(
    plan: Plan,
    *,
    seeds: dict[str, dict] | None = None,
    base_seed: dict | None = None,
    budget: TaskBudget | None = None,
    cfg: SentinelConfig | None = None,
    backend: str | None = None,
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
    two_tier: bool = False,
    cache: StepCache | None = None,
    use_cache: bool = True,
    project_id: str | None = None,
    registry: "AgentRegistry | None" = None,
    clock: Callable[[], float] = time.monotonic,
    trace: list[str] | None = None,
) -> _Execution:
    """Drive a hand-built step-DAG to completion and return the raw :class:`_Execution` (no projection).

    Each step is staffed by capability: ``SKILL_SPECS[cap]`` for the declarative skills, the standalone
    program-strategist for the ``program_strategy`` aggregator, or — for a planner-*created* capability
    with no SKILL_SPECS entry — the registry spec the planner stamped on the step, built via
    ``registry.build_from_spec`` (TD-1). A step's seed state is
    ``base_seed`` ⊕ its literal ``seeds[step.id]`` (e.g. ``{"target": ...}``) ⊕ upstream outputs wired
    by ``Step.inputs`` (``producer_output_key → this step's state key``). The step's result is read from
    the skill's terminal state key and re-stored under ``step.output_key`` so sibling steps of the same
    capability don't collide.

    Fail-soft throughout: a step failure, a missing required input, or budget exhaustion degrades the
    run (``degraded`` + ``missing_inputs``) rather than raising. A *structural* fault (a cycle or a
    dangling ``depends_on``) DOES raise from :func:`_toposort` — a malformed plan is a build error, not
    a runtime degradation. ``resume-from-last-good`` skips steps already marked ``done`` on the plan."""
    cfg = cfg or get_config()
    budget = budget or TaskBudget()
    seeds = seeds or {}
    base = dict(base_seed or {})
    trace = trace if trace is not None else []
    if use_cache and cache is None:
        cache = StepCache(project_id=project_id)
    registry = _resolve_registry(plan, registry)

    results: dict[str, dict] = {}            # step.output_key → produced artifact dict
    produced: list[tuple[str, str]] = []     # (capability, output_key), in completion order
    satisfied: set[str] = set()              # step ids whose output is usable
    missing_inputs: list[str] = []
    degraded = False
    steps_run = 0
    reasoner_calls = 0
    start = clock()

    order = _toposort(plan.steps)
    by_id = {s.id: s for s in plan.steps}    # for dependency → state wiring
    plan.status = "running"

    # Level-scheduled frontier walk (Step 5). Each wave is the set of not-yet-processed steps whose
    # deps are ALL processed; its admitted steps run concurrently (asyncio.gather), and the records are
    # folded back in DECLARED order so produced/missing_inputs/degraded are independent of which step
    # finished first (AC-6). Because the DAG is acyclic, the topo-earliest remaining step always has all
    # deps processed → a wave is always non-empty until ``remaining`` drains (no stall, no re-cycle-check).
    processed: set[str] = set()
    remaining = list(order)
    while remaining:
        frontier = [s for s in remaining if set(s.depends_on) <= processed]
        if not frontier:  # defensive — _toposort already guarantees progress
            break

        # --- classify the frontier in declared order; reserve budget at admission --------------- #
        # ``proj_*`` project the post-wave counters so N concurrent steps reserve against the ceiling
        # before any of them runs (the budget-race a sequential pre-check couldn't see — Step 6).
        plans: list[dict] = []
        run_specs: list[tuple[Step, ResearchModeSpec | None, list[str]]] = []
        proj_steps = steps_run
        proj_reasoner = reasoner_calls
        elapsed = clock() - start
        for step in frontier:
            if step.status == "done":  # resume-from-last-good: completed on a prior attempt
                plans.append({"kind": "resume", "step": step})
                continue
            spec = SKILL_SPECS.get(step.capability)
            is_aggregator = step.capability in PARTIAL_TOLERANT_CAPS
            unsatisfied = [d for d in step.depends_on if d not in satisfied]
            if unsatisfied and not (is_aggregator and len(unsatisfied) < len(step.depends_on)):
                plans.append({"kind": "skip_dep", "step": step, "unsatisfied": unsatisfied})
                continue
            reason = budget.exhausted(
                steps_run=proj_steps, reasoner_calls=proj_reasoner, elapsed_s=elapsed
            )
            if reason:
                plans.append({"kind": "skip_budget", "step": step, "reason": reason,
                              "unsatisfied": unsatisfied})
                continue
            plans.append({"kind": "run", "step": step, "unsatisfied": unsatisfied})
            run_specs.append((step, spec, unsatisfied))
            proj_steps += 1
            proj_reasoner += _reasoner_cost(step.capability, spec)

        # --- run the admitted steps concurrently ------------------------------------------------ #
        # ``return_exceptions=True`` keeps one step's unexpected raise from poisoning the whole level;
        # _run_one_step already catches its own run errors, so this is belt-and-suspenders. gather
        # preserves order, so we zip back to run_specs and convert any stray exception to a failed record.
        #
        # Each step is HARD-CAPPED at the remaining wall-clock budget (asyncio.wait_for): the budget
        # check above runs *between* waves, so a step that hangs mid-execution (stuck tool call,
        # non-streamed gen that never returns) would otherwise pin the whole run as "running" forever —
        # the budget can never fire because the gather never returns (seen live 2026-06-11: a
        # govt_dept_research step ran 25+ min). TimeoutError lands in the BaseException branch below
        # → failed step, degraded result, honest trace; the run always terminates. ``elapsed`` is the
        # admission-time reading from above — no extra clock() call, so the injectable test clock
        # still sees exactly one tick per wave.
        # Floor: late waves still get a beat to finish (30s), but never more than the operator's own
        # wall-clock setting — a tiny budget must stay tiny (and keeps this testable without sleeping).
        step_cap = max(min(30.0, budget.wall_clock_s), budget.wall_clock_s - elapsed)
        raw_outcomes = await asyncio.gather(*[
            asyncio.wait_for(_run_one_step(
                step, by_id=by_id, results_snapshot=results, base=base, seeds=seeds,
                unsatisfied=uns, spec=spec, cache=cache, use_cache=use_cache, cfg=cfg,
                backend=backend, cloud_allowed=cloud_allowed, search_provider=search_provider,
                two_tier=two_tier, registry=registry, project_id=project_id,
            ), timeout=step_cap)
            for step, spec, uns in run_specs
        ], return_exceptions=True)
        by_step_id: dict[str, _StepOutcome] = {}
        for (step, _spec, _uns), oc in zip(run_specs, raw_outcomes):
            if isinstance(oc, BaseException):
                step.status = "failed"
                step.finished_at = _now_iso()
                oc = _StepOutcome(
                    step=step, status="failed", output_key=step.output_key,
                    missing=[step.id], degraded=True,
                    trace=[f"{step.id} ({step.capability}): FAILED "
                           f"({type(oc).__name__}: {str(oc)[:80]})"],
                )
            by_step_id[step.id] = oc

        # --- fold every frontier step in DECLARED order ----------------------------------------- #
        for p in plans:
            step = p["step"]
            kind = p["kind"]
            if kind == "resume":
                satisfied.add(step.id)
                if step.output_key in results:
                    produced.append((step.capability, step.output_key))
            elif kind == "skip_dep":
                step.status = "skipped"
                missing_inputs.append(step.id)
                degraded = True
                trace.append(f"{step.id} ({step.capability}): skipped — missing deps {p['unsatisfied']}")
            elif kind == "skip_budget":
                if p["unsatisfied"]:  # aggregator that would have run on partial inputs
                    missing_inputs.extend(p["unsatisfied"])
                step.status = "skipped"
                missing_inputs.append(step.id)
                degraded = True
                trace.append(
                    f"{step.id} ({step.capability}): skipped — budget exhausted ({p['reason']})"
                )
            else:  # run
                if p["unsatisfied"]:  # aggregator running on partial inputs
                    missing_inputs.extend(p["unsatisfied"])
                    degraded = True
                outcome = by_step_id[step.id]
                _fold_outcome(
                    outcome, results=results, produced=produced, satisfied=satisfied,
                    missing_inputs=missing_inputs, trace=trace,
                )
                reasoner_calls += outcome.reasoner_delta
                steps_run += 1 if outcome.ran else 0
                degraded = degraded or outcome.degraded

        processed.update(s.id for s in frontier)
        remaining = [s for s in remaining if s.id not in processed]

    plan.status = "failed" if degraded else "done"
    return _Execution(
        plan=plan, results=results, produced=produced,
        missing_inputs=missing_inputs, degraded=degraded,
    )


# A plan-projector turns the raw execution into the task's deliverable. Two ship today: the BiltIQ
# map+compare+strategy projector (:func:`_assemble_result`) and the task-shape-agnostic
# :func:`assemble_generic`. Phase 3's planner picks the projector for the task it emitted.
Assembler = Callable[..., Result]


def _resolve_registry(plan: Plan, registry):
    """Build the default registry only if the plan staffs a *created* capability (no SKILL_SPECS entry,
    not the aggregator). A pure-seeded plan never opens the spec DB — preserving the prior behaviour and
    perf of the common BiltIQ map+compare+strategy path."""
    if registry is not None:
        return registry
    if any(s.capability not in SKILL_SPECS and s.capability != PROGRAM_STRATEGY_CAP
           for s in plan.steps):
        from sentinel.agent.registry import AgentRegistry

        return AgentRegistry()
    return registry


def _schema_for_capability(cap: str, output_key: str, plan: Plan, registry):
    """Resolve the Pydantic output schema a produced artifact validates against, so the finalize pass
    can reconstruct a *typed* artifact from the stored dict. SKILL_SPECS skills declare it; the
    aggregator is ``ProgramStrategy``; a created capability names it via its registry spec."""
    spec = SKILL_SPECS.get(cap)
    if spec is not None and spec.output_schema is not None:
        return spec.output_schema
    if cap == PROGRAM_STRATEGY_CAP:
        return ProgramStrategy
    step = next((s for s in plan.steps if s.output_key == output_key), None)
    if step is not None and step.agent_spec_id and registry is not None:
        cspec = registry.store.get_spec(step.agent_spec_id)
        if cspec is not None:
            from sentinel.artifacts.schemas import KNOWN_OUTPUT_SCHEMAS

            return KNOWN_OUTPUT_SCHEMAS.get(cspec.output_schema_ref)
    return None


def _primary_typed(execu: "_Execution", registry, *, cfg):
    """The last produced artifact, reconstructed as its typed model (or ``None`` if it can't be typed).
    'Last produced' is the deliverable's headline: the final synthesis/strategy a persona reads and a
    judge grades."""
    if not execu.produced:
        return None
    cap, key = execu.produced[-1]
    raw = execu.results.get(key)
    schema = _schema_for_capability(cap, key, execu.plan, registry)
    if raw is None or schema is None:
        return None
    try:
        return schema.model_validate(raw)
    except Exception:
        return None


async def _finalize_result(
    result: Result, execu: "_Execution", *, persona, grade, grade_objective, registry,
    cfg, backend, cloud_allowed, trace,
) -> Result:
    """Post-projection pass (TD-2/TD-3): attach the persona-adapted prose and/or a sampled model grade.

    Both operate on the *typed* primary artifact and are **opt-in + additive** — a default persona and
    ``grade=False`` leave the Result byte-identical to before, so every existing caller is unchanged.
    Persona is render-only (facts copied by code in :mod:`persona`), so AC-17 invariance holds; the
    model grade is soft (informs, never blocks). Both degrade silently on failure — finalize never
    crashes a Result that already executed."""
    from sentinel.artifacts.schemas import Persona

    wants_persona = persona is not None and persona != Persona()
    if not wants_persona and not grade:
        return result
    artifact = _primary_typed(execu, registry, cfg=cfg)
    if artifact is None:
        return result

    if wants_persona:
        try:
            from sentinel.agent.persona import render_for_persona

            rendered = await render_for_persona(
                artifact, persona, cfg=cfg, backend=backend, cloud_allowed=cloud_allowed, trace=trace,
            )
            result.persona_rendered = rendered.rendered_text
        except Exception as exc:  # presentation is non-critical — never fail an executed Result
            trace.append(f"persona render skipped ({type(exc).__name__}: {str(exc)[:60]})")
    if grade:
        try:
            from sentinel.eval.graders import model_grade

            result.grade = await model_grade(
                artifact, objective=grade_objective or result.summary, sources=result.citations,
                cfg=cfg, backend=backend, cloud_allowed=cloud_allowed, trace=trace,
            )
            # Write the rubric score back to the primary step's spec so the registry
            # ranking reflects real output quality (gap 2: eval_score writeback).
            if result.grade and result.grade.score is not None and execu.produced:
                try:
                    _, primary_key = execu.produced[-1]
                    primary_step = next(
                        (s for s in execu.plan.steps if s.output_key == primary_key), None
                    )
                    if primary_step and primary_step.agent_spec_id and registry is not None:
                        registry.store.update_eval_score(
                            primary_step.agent_spec_id, result.grade.score
                        )
                except Exception:
                    pass
        except Exception as exc:  # the grade is a sampled signal — its absence must not fail the run
            trace.append(f"model grade skipped ({type(exc).__name__}: {str(exc)[:60]})")
    return result


async def run_plan(
    plan: Plan,
    *,
    assemble: Assembler | None = None,
    persona=None,
    grade: bool = False,
    grade_objective: str | None = None,
    registry=None,
    **kwargs,
) -> Result:
    """Execute a hand-built step-DAG and project it into a typed :class:`Result`.

    Generic over *assembly*: ``assemble`` defaults to the BiltIQ map+compare+strategy projector so the
    Phase-2 deliverable is unchanged; pass :func:`assemble_generic` (or use :func:`run_dag`) to get a
    task-shape-agnostic Result for an arbitrary plan. ``persona`` (non-default) and ``grade`` opt into
    the finalize pass (TD-2/TD-3: audience-adapted prose + a sampled model grade) — both additive, so
    the default call is byte-identical to before. All other keyword args flow to :func:`_execute_plan`
    (seeds, base_seed, budget, cfg, backend, cloud_allowed, search_provider, two_tier, cache, use_cache,
    project_id, clock, trace)."""
    registry = _resolve_registry(plan, registry)
    # Strip keys _execute_plan doesn't accept (forwarded by run_dag / gate_proposal for post-run hooks).
    _exec_kwargs = {k: v for k, v in kwargs.items() if k not in ("user_id", "handoff_id")}
    execu = await _execute_plan(plan, registry=registry, **_exec_kwargs)
    project = assemble or _assemble_result
    result = project(
        execu.plan, execu.results, execu.produced,
        missing_inputs=execu.missing_inputs, degraded=execu.degraded,
    )
    if persona is not None or grade:
        result = await _finalize_result(
            result, execu, persona=persona, grade=grade, grade_objective=grade_objective,
            registry=registry, cfg=kwargs.get("cfg") or get_config(),
            backend=kwargs.get("backend"), cloud_allowed=kwargs.get("cloud_allowed", True),
            trace=kwargs.get("trace") if kwargs.get("trace") is not None else [],
        )
    return result


def _maybe_trigger_memory_crawl(entity: str, *, db_path=None) -> None:
    """Fire-and-forget: enqueue a high-priority crawl for *entity* if it has a source config.

    Completely fail-soft — any exception is swallowed so a live research run is never disrupted.
    Called at the start of :func:`run_dag` once the target entity string is known.
    """
    try:
        from sentinel.memory.scheduler import CrawlScheduler
        from pathlib import Path as _Path
        if db_path is None:
            from sentinel.config import load_config
            db_path = _Path(load_config().memory.db_path)
        CrawlScheduler(db_path).force_enqueue(entity, priority=10)
    except Exception:
        pass  # never break a live run


async def run_dag(plan: Plan, **kwargs) -> Result:
    """Execute **any** hand-built/planner-emitted ``Plan`` and return a task-shape-agnostic Result
    (SENTINEL-012 Step 13). Identical engine to :func:`run_plan` — only the projection is generic:
    the dashboard payload is ``{"artifacts": {output_key: artifact}}`` over whatever the plan produced,
    not the fixed BiltIQ slots. A structural fault (cycle / dangling dep) raises; runtime faults
    degrade. This is the entry the Phase-3 planner targets once it emits its own plans.

    **Episodic memory injection (SENTINEL-015 FR-01):** when ``cfg.memory.episodic_recall`` is on,
    recalled prior-session findings are appended to ``base_seed["memory_context"]`` so every DAG
    step's prompt receives the context block. Fail-soft: any recall error leaves kwargs unchanged.
    """
    cfg = kwargs.get("cfg") or get_config()
    mem_cfg = getattr(cfg, "memory", None)
    _entity_on = getattr(mem_cfg, "entity_memory", True)
    _episodic_on = getattr(mem_cfg, "episodic_recall", True)
    _kb_on = getattr(mem_cfg, "kb_context", True)
    if _entity_on or _episodic_on or _kb_on:
        try:
            base = dict(kwargs.get("base_seed") or {})
            project_id = kwargs.get("project_id")
            first_seed = next(iter((kwargs.get("seeds") or {}).values()), {})
            raw_target = (
                base.get("target")
                or str(first_seed.get("vertical_context") or "").split("\n")[0]
                or plan.task_id
                or ""
            )
            target = str(raw_target).strip()
            if target:
                _maybe_trigger_memory_crawl(target)
                ctx_parts: list[str] = []
                from sentinel.memory.context_budget import ContextBudget
                _ctx_budget = ContextBudget(
                    total=int(getattr(mem_cfg, "context_window_tokens", None) or 2400)
                )
                if _entity_on:
                    from sentinel.memory import DataBoundary, MemoryStore
                    _mem = MemoryStore()
                    # G-08/G-11: hot tier first; supplement with cold page if budget allows.
                    hot = _mem.recall(target, {DataBoundary.PUBLIC}, tier="hot",
                                      token_budget=_ctx_budget.slot("entity_hot"))
                    cold = _mem.recall(
                        target, {DataBoundary.PUBLIC},
                        tier="cold", page=0, page_size=10,
                        token_budget=_ctx_budget.slot("entity_cold"),
                    ) if not hot or len(hot) < 4 else []
                    recalled = hot + cold
                    relations = _mem.get_related(target, allowed_boundaries={DataBoundary.PUBLIC})
                    entity_ctx = orch._render_memory_context(recalled, relations=relations)
                    if entity_ctx:
                        ctx_parts.append(entity_ctx)
                if _episodic_on:
                    top_k = int(getattr(mem_cfg, "episodic_recall_top_k", 3))
                    episodes = RunStore().recall_episodes(target, top_k=top_k, project_id=project_id)
                    ep_ctx = orch._render_episodic_context(episodes)
                    if ep_ctx:
                        ctx_parts.append(ep_ctx)
                if _kb_on and project_id:
                    try:
                        from sentinel.kb.search import hybrid_search
                        hits = hybrid_search(project_id, data_dir(), target, rerank_top_k=5)
                        if hits:
                            from sentinel.security.sandbox import validate_tool_output as _vto
                            kb_lines = []
                            for _h in hits[:5]:
                                if not _h.text:
                                    continue
                                _sr = _vto(_h.text[:300], entity=target, context="kb")
                                kb_lines.append(f"- [{_h.url or 'kb'}] {_sr.sanitized}")
                            if kb_lines:
                                ctx_parts.insert(0,
                                    "\n\n## Knowledge base context (indexed documents for this project)\n"
                                    + "\n".join(kb_lines)
                                    + "\nUse this to supplement and verify your research."
                                )
                    except Exception:
                        pass  # KB unavailable → fail-soft, run continues without it
                # G-09: prospective memory — surface due follow-up tasks and fire them.
                try:
                    from sentinel.memory import MemoryStore as _MS
                    _ptasks = _MS().due_tasks(target, project_id=project_id)
                    if _ptasks:
                        lines = ["\n\n## Pending follow-ups (scheduled by prior sessions)"]
                        for t in _ptasks:
                            lines.append(
                                f"- [{t['due_at'][:10]}] {t['trigger_condition']}: {t['action_hint']}"
                            )
                        ctx_parts.append("\n".join(lines))
                        for t in _ptasks:
                            _MS().mark_fired(t["id"])
                except Exception:
                    pass  # fail-soft — prospective tasks are advisory
                if ctx_parts:
                    base["memory_context"] = base.get("memory_context", "") + "".join(ctx_parts)
                    kwargs = {**kwargs, "base_seed": base}
        except Exception:
            pass  # fail-soft: never let memory injection break a DAG run
    # G-04: persona cognitive framing — inject audience framing into base_seed["persona_framing"]
    # so _run_skill can pass it as instruction_suffix to the synthesizer agent. Fail-soft.
    try:
        from sentinel.artifacts.schemas import Persona as _Persona
        _persona = kwargs.get("persona")
        if _persona is not None and _persona != _Persona():
            _base = dict(kwargs.get("base_seed") or {})
            _pf = (
                f"\n\nAudience: synthesize for a '{_persona.name}' persona "
                f"(reading level: {_persona.reading_level}, tone: {_persona.tone}, "
                f"format: {_persona.format}"
            )
            if _persona.source_policy:
                _pf += f", source policy: {_persona.source_policy}"
            _pf += ")."
            _base["persona_framing"] = _pf
            kwargs = {**kwargs, "base_seed": _base}
    except Exception:
        pass
    # G-14: user profile — inject operator preferences into instruction_suffix. Fail-soft.
    try:
        _user_id = kwargs.get("user_id") or (kwargs.get("base_seed") or {}).get("user_id")
        if _user_id:
            from sentinel.memory.store import UserProfileStore, render_user_profile_context
            _profile = UserProfileStore().get(_user_id)
            _profile_ctx = render_user_profile_context(_profile)
            if _profile_ctx:
                _base = dict(kwargs.get("base_seed") or {})
                _base["persona_framing"] = (_base.get("persona_framing") or "") + "\n\n" + _profile_ctx
                kwargs = {**kwargs, "base_seed": _base}
    except Exception:
        pass  # fail-soft: user profile injection must never break a run
    _fwd = {k: v for k, v in kwargs.items() if k not in ("user_id", "handoff_id")}
    result = await run_plan(plan, assemble=assemble_generic, **_fwd)
    # G-07: procedural memory — record successful plan structures so the planner can reuse them.
    if not result.degraded:
        try:
            from sentinel.memory.store import SpecStore
            completed_caps = [s.capability for s in plan.steps if s.status == "done"]
            if completed_caps:
                domain = "+".join(sorted(set(completed_caps)))
                SpecStore().record_procedural_trace(
                    domain, completed_caps,
                    eval_score=result.grade.score if result.grade else None,
                    project_id=kwargs.get("project_id"),
                )
        except Exception:
            pass
        # G-15: skill curation — update per-capability performance stats. Fail-soft.
        try:
            from sentinel.memory.store import SkillCurationStore
            _score = result.grade.score if result.grade else None
            _curation = SkillCurationStore()
            for _cap in [s.capability for s in plan.steps if s.status == "done"]:
                _curation.record_outcome(_cap, _score)
        except Exception:
            pass
        # G-17: A2A cross-session coordination — mark the originating handoff done. Fail-soft.
        try:
            _hid = kwargs.get("handoff_id")
            if _hid:
                from sentinel.memory.store import SessionHandoffStore
                SessionHandoffStore().complete(_hid)
        except Exception:
            pass
    # G-14 render hint: stamp preferred_format from user profile so the render layer applies it
    # deterministically (hard switch) rather than relying on the soft synthesizer instruction alone.
    try:
        _user_id = kwargs.get("user_id") or (kwargs.get("base_seed") or {}).get("user_id")
        if _user_id:
            from sentinel.memory.store import UserProfileStore
            _pf = getattr(UserProfileStore().get(_user_id), "preferred_format", None)
            if _pf and _pf != "bullets":
                result.preferred_format = _pf
    except Exception:
        pass
    return result


def _mine_urls_from_artifact(art: dict) -> list[Source]:
    """Fallback citation extraction when the model leaves sources: [] empty.

    Walks known URL-bearing sub-fields and constructs Source objects from them:
    - Finding-shaped items in any list: {"text":…, "source":{"boundary":…,"label":…,"url":…}}
      covers Battlecard (strengths/weaknesses/pricing_signals/recent_developments),
      AccountBrief (public_signal/private_signal), SoftwareBrief, FinancialProfile, etc.
    - ProductResearch: products_found[].source_url (flat shape)
    - action_plan[].url
    - Any top-level string that is a bare URL"""
    found: list[Source] = []

    # Finding-shaped items: {"text": "...", "source": {"boundary": "...", "label": "...", "url": "..."}}
    # This is the serialised form of every domain artifact's list[Finding] fields.
    for _k, v in art.items():
        if not isinstance(v, list):
            continue
        for item in v:
            if not isinstance(item, dict):
                continue
            src = item.get("source")
            if not isinstance(src, dict):
                continue
            url = (src.get("url") or "").strip()
            if url and url.startswith("http"):
                raw_boundary = src.get("boundary", "public")
                boundary = raw_boundary if raw_boundary in ("public", "private") else "public"
                found.append(Source(
                    boundary=boundary,
                    label=src.get("label") or item.get("text", "")[:80] or _k,
                    url=url,
                ))

    # ProductResearch: products_found[].{name, source_url} (flat shape, no nested source dict)
    for p in (art.get("products_found") or []):
        if not isinstance(p, dict):
            continue
        url = (p.get("source_url") or "").strip()
        if url and url.startswith("http"):
            found.append(Source(
                boundary="public",
                label=f"{p.get('name', 'Product')} — {p.get('brand', '')}".strip(" —"),
                url=url,
            ))

    # GovernmentProposal: action_plan[].url
    for a in (art.get("action_plan") or []):
        if not isinstance(a, dict):
            continue
        url = (a.get("url") or a.get("source_url") or "").strip()
        if url and url.startswith("http"):
            found.append(Source(boundary="public", label=a.get("action", "Reference"), url=url))

    # Generic: any top-level string field that is a bare URL
    for _k, v in art.items():
        if isinstance(v, str) and v.startswith("http") and " " not in v and len(v) < 300:
            found.append(Source(boundary="public", label=_k, url=v))

    return found


def _union_citations(results: dict[str, dict], produced: list[tuple[str, str]]) -> list[Source]:
    """De-duplicated union of every produced artifact's citations (by boundary/label/url).

    Primary path: artifact.sources list[Source] from structured model output.
    Fallback: mine URL-bearing sub-fields the 26B model reliably fills
    (e.g. products_found[].source_url) when sources: [] is empty."""
    citations: list[Source] = []
    seen: set[tuple] = set()

    def _add(src: Source) -> None:
        sig = (src.boundary, src.label or "", src.url or "")
        if sig not in seen:
            seen.add(sig)
            citations.append(src)

    for _cap, key in produced:
        art = results[key]
        # Primary: explicit sources list
        for raw in (art.get("sources") or []):
            try:
                _add(Source.model_validate(raw))
            except Exception:
                continue
        # Fallback: mine URLs from sub-fields when primary is empty
        if not art.get("sources"):
            for src in _mine_urls_from_artifact(art):
                _add(src)

    return citations


def assemble_generic(
    plan: Plan, results: dict[str, dict], produced: list[tuple[str, str]],
    *, missing_inputs: list[str], degraded: bool,
) -> Result:
    """Task-shape-agnostic projection (Step 13): every produced artifact keyed by its ``output_key``.

    Where :func:`_assemble_result` knows the BiltIQ deliverable's named slots, this makes no assumption
    about *which* capabilities ran — it simply hands back what the DAG produced, so an arbitrary plan
    gets a faithful Result. Citations are unioned the same way; honesty flags are carried through."""
    artifacts = {key: results[key] for _cap, key in produced}
    caps = sorted({cap for cap, _ in produced})
    summary = (
        f"produced {len(produced)} artifact(s)" + (f" — {', '.join(caps)}" if caps else "")
        if produced else "no artifacts produced"
    )
    if degraded:
        summary += " (partial)"
    return Result(
        task_id=plan.task_id,
        summary=summary,
        artifacts=list(artifacts),
        citations=_union_citations(results, produced),
        dashboard_payload={"artifacts": artifacts},
        degraded=degraded,
        missing_inputs=missing_inputs,
    )


def _assemble_result(
    plan: Plan, results: dict[str, dict], produced: list[tuple[str, str]],
    *, missing_inputs: list[str], degraded: bool,
) -> Result:
    """Fold the produced artifacts into the Task deliverable: a dashboard payload (map + matrix set +
    strategy), the union of citations, and the honest ``degraded``/``missing_inputs`` flags."""
    profile = next((results[k] for cap, k in produced if cap == "self_profile"), None)
    matrices = [results[k] for cap, k in produced if cap == "compare"]
    strategy = next((results[k] for cap, k in produced if cap == PROGRAM_STRATEGY_CAP), None)

    citations = _union_citations(results, produced)

    bits = []
    if profile:
        bits.append(f"profiled {profile.get('org', 'us')}")
    if matrices:
        bits.append(f"{len(matrices)} comparison(s)")
    if strategy:
        bits.append("program strategy" + (" (partial)" if degraded else ""))
    summary = "; ".join(bits) or "no artifacts produced"

    return Result(
        task_id=plan.task_id,
        summary=summary,
        artifacts=[k for _cap, k in produced],
        citations=citations,
        dashboard_payload={"map": profile, "matrix": matrices, "strategy": strategy},
        degraded=degraded,
        missing_inputs=missing_inputs,
    )


def biltiq_program_plan(
    task_id: str, *, our_brand: str, rivals: Sequence[str], plan_id: str = "plan-biltiq",
) -> tuple[Plan, dict[str, dict]]:
    """Hand-build the map+compare+strategy DAG (the BiltIQ task shape) and the per-step literal seeds.

    Returns ``(plan, seeds)`` ready for :func:`run_plan`. One ``competitor → compare`` branch per
    rival, all joining at a single ``program_strategy`` step. The seeds carry each step's ``target``
    (self-profile our brand; each competitor its rival); the compare/strategy wiring is by
    ``Step.inputs`` (upstream output_key → state key the consumer reads)."""
    steps: list[Step] = [
        Step(id="s_profile", capability="self_profile", output_key="self_profile"),
    ]
    seeds: dict[str, dict] = {"s_profile": {"target": our_brand}}
    compare_ids: list[str] = []
    for i, rival in enumerate(rivals):
        comp_id, cmp_id = f"s_competitor_{i}", f"s_compare_{i}"
        steps.append(Step(id=comp_id, capability="competitor", output_key=f"battlecard_{i}"))
        seeds[comp_id] = {"target": rival}
        steps.append(Step(
            id=cmp_id, capability="compare", output_key=f"comparison_{i}",
            depends_on=["s_profile", comp_id],
            # producer output_key → the state key the compare prompt reads
            inputs={"self_profile": "self_profile", f"battlecard_{i}": "battlecard"},
        ))
        compare_ids.append(cmp_id)
    steps.append(Step(
        id="s_strategy", capability=PROGRAM_STRATEGY_CAP, output_key="program_strategy",
        depends_on=list(compare_ids),
        inputs={f"comparison_{i}": "comparisons" for i in range(len(rivals))},
    ))
    return Plan(id=plan_id, task_id=task_id, steps=steps), seeds
