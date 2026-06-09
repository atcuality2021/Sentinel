"""Program-level strategy (SENTINEL-012 §9.6) — the top of the BiltIQ value chain.

Distinct from the per-artifact strategist (``maybe_strategist``): that overlays tactics onto ONE
finished Battlecard/AccountBrief; this consumes the **set** of ``ComparisonMatrix`` results across
every rival and reasons about leverage across the whole product line, emitting one ``ProgramStrategy``.

Three small pieces so the Step-10 DAG can drive it:

- :func:`build_program_strategist` — the tool-free reasoner (26B under tiering; sovereign via
  ``cloud_allowed`` like every other agent).
- :func:`program_strategy_seed` — the input ("merge") path: serialise the comparison set into the
  ``comparisons`` state key the strategist reads.
- :func:`finalize_program_strategy` — stamps ``ran_on_partial_data`` (§9.4) so a strategy synthesised
  while some comparisons were missing is never silently presented as complete.
"""

from __future__ import annotations

from collections.abc import Sequence

from google.adk.agents import Agent

from sentinel.agent.modes._build import make_agent
from sentinel.artifacts.schemas import ComparisonMatrix, ProgramStrategy
from sentinel.config import SentinelConfig, get_config

PROGRAM_STRATEGY_KEY = "program_strategy"   # state/output key the strategist writes
COMPARISONS_KEY = "comparisons"             # state key it reads (the merged comparison set)


def build_program_strategist(
    cfg: SentinelConfig | None = None,
    backend: str | None = None,
    *,
    cloud_allowed: bool = True,
) -> Agent:
    """Build the project-level program strategist (reasoner, tool-free).

    role=``strategist`` ⇒ the reasoner tier (26B when tiering is on) and the build-time tool-free
    guard. No ``pin_gemini``: strategy follows the reasoning backend/governance, so under
    ``on_prem_required`` (``cloud_allowed=False``) this builds a vLLM object — zero Gemini (AC-7/11)."""
    cfg = cfg or get_config()
    return make_agent(
        cfg, "program.strategist", name="program_strategist",
        output_key=PROGRAM_STRATEGY_KEY, mode_backend=backend,
        output_schema=ProgramStrategy, cloud_allowed=cloud_allowed,   # tools omitted → tool-free
    )


def program_strategy_seed(matrices: Sequence[ComparisonMatrix]) -> dict[str, object]:
    """The merge path: turn the comparison SET into the strategist's seed state.

    Serialises each matrix to a plain dict under ``comparisons`` (ADK renders state into the
    instruction's ``{comparisons}`` slot). Empty input yields an empty list — the strategist's prompt
    handles a thin set by saying so in its assessment, rather than this raising."""
    return {COMPARISONS_KEY: [m.model_dump() for m in matrices]}


def finalize_program_strategy(
    strategy: ProgramStrategy, *, missing: Sequence[str] | int = 0
) -> ProgramStrategy:
    """Stamp the §9.4 honesty flag onto a freshly-synthesised strategy.

    ``missing`` is whatever the orchestrator knows did NOT arrive (a list of rival/product names, or a
    count). Any truthy value flips ``ran_on_partial_data`` — the reasoner can't know what it never
    received, so this is set from degraded run state, not by the LLM. Mutates and returns in place."""
    strategy.ran_on_partial_data = bool(missing)
    return strategy
