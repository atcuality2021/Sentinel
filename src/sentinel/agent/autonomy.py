"""SENTINEL-012 Phase 3, Step 16 — the autonomy gate (design §3d, AC-4 / AC-13).

A :class:`~sentinel.agent.orchestrator_planner.PlanProposal` is *inert* until it passes this gate.
The gate is the one place that decides whether a plan **executes**, and it is biased to safety:

- ``propose`` (the project default, ``ProjectSettings.autonomy``): return the proposal for human
  approval and run **nothing**. The plan's status is left ``proposed``; no agent is invoked.
- ``autonomous`` (explicit per-project opt-in): execute the staffed plan on the generic DAG runner
  (``run_dag``) and return its ``Result``.

The gate controls *execution*, not *persistence* — the planner already validated and stored any
created specs (Step 15). Separating the two keeps the safety boundary crisp: the question "did this
plan run?" has exactly one answer-site, here, and it defaults to "no".

Scope note (Step 16): an autonomous plan whose steps are all **seeded** capabilities runs fully
through ``run_dag`` (staffed via ``SKILL_SPECS``). A step on a **created** capability degrades
fail-soft until the staffing-path unification (``build_from_spec`` into the DAG runner) lands — the
gate is correct either way; it just can't yet *execute* a brand-new specialist.
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.agent.dag import run_dag
from sentinel.agent.orchestrator_planner import PlanProposal
from sentinel.artifacts.schemas import Result
from sentinel.config.schema import Autonomy


@dataclass
class GateOutcome:
    """What the gate decided. ``result`` is ``None`` exactly when nothing ran (propose mode); ``ran``
    is the unambiguous "did this plan execute?" flag the UI and audit log read."""

    autonomy: Autonomy
    proposal: PlanProposal
    result: Result | None
    ran: bool

    @property
    def created_count(self) -> int:
        return len(self.proposal.created_specs)


async def gate_proposal(
    proposal: PlanProposal,
    *,
    autonomy: Autonomy = "propose",
    seeds: dict[str, dict] | None = None,
    trace: list[str] | None = None,
    **run_kwargs,
) -> GateOutcome:
    """Put a proposal through the autonomy gate (AC-13).

    ``propose`` ⇒ run nothing, return the proposal for approval (the SAFE default). ``autonomous`` ⇒
    execute the staffed plan via ``run_dag`` and return its ``Result``. ``seeds`` / ``**run_kwargs``
    are forwarded to ``run_dag`` only on the autonomous path (cfg, backend, cloud_allowed,
    search_provider, use_cache, …) — in propose mode they are deliberately untouched, because nothing
    runs.
    """
    if autonomy == "propose":
        proposal.plan.status = "proposed"
        return GateOutcome(autonomy="propose", proposal=proposal, result=None, ran=False)

    # autonomous: the explicit opt-in. Execute the staffed DAG.
    result = await run_dag(
        proposal.plan,
        seeds=seeds or {},
        trace=trace if trace is not None else [],
        **run_kwargs,
    )
    return GateOutcome(autonomy="autonomous", proposal=proposal, result=result, ran=True)
