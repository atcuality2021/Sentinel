"""SENTINEL-012 Phase 2 Step 9 — project-level ProgramStrategy component (AC-7).

Hermetic: LiteLlm built offline + introspected; the strategist driven through a FakeRunner. Proves
the program strategist is a sovereign tool-free reasoner DISTINCT from the per-artifact strategist,
that the merge path serialises the comparison SET, that the §9.4 partial-data flag is set from run
state (not the LLM), and that N comparisons yield a ProgramStrategy with a prioritised cross-product
action plan.
"""

from __future__ import annotations

import asyncio

from google.adk.agents.run_config import StreamingMode

from sentinel.agent import orchestrator as orch
from sentinel.agent.program_strategy import (
    COMPARISONS_KEY,
    PROGRAM_STRATEGY_KEY,
    build_program_strategist,
    finalize_program_strategy,
    program_strategy_seed,
)
from sentinel.artifacts.schemas import (
    ComparisonAxis,
    ComparisonMatrix,
    ProgramStrategy,
    RecommendedAction,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
        "strategist": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def _matrix(subject, rival, verdict) -> ComparisonMatrix:
    return ComparisonMatrix(
        subject=subject, rival=rival,
        axes=[ComparisonAxis(axis="sovereignty", ours="air-gapped", theirs="cloud", verdict=verdict)],
    )


# --- AC-7: sovereign tool-free reasoner, distinct from maybe_strategist --------------------- #


def test_program_strategist_builds_sovereign_reasoner(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    agent = build_program_strategist(_tiered_cfg(), "vllm", cloud_allowed=False)
    assert agent.name == "program_strategist"
    assert not isinstance(agent.model, str)            # no Gemini model-id string under on_prem
    assert type(agent.model).__name__ == "LiteLlm"
    assert "26B" in agent.model.model                  # reasoner tier
    assert agent.output_schema is ProgramStrategy      # NOT StrategyOverlay (per-artifact strategist)
    assert agent.output_key == PROGRAM_STRATEGY_KEY
    assert not getattr(agent, "tools", None)           # tool-free


def test_program_strategist_reads_the_comparison_set():
    """The strategist's prompt is keyed on the comparison SET, not a single artifact."""
    cfg = build_default()
    assert cfg.prompts["program.strategist"].variables == [COMPARISONS_KEY]


# --- merge path + §9.4 honesty flag -------------------------------------------------------- #


def test_program_strategy_seed_serialises_the_set():
    matrices = [_matrix("A", "R1", "win"), _matrix("B", "R2", "lose")]
    seed = program_strategy_seed(matrices)
    assert list(seed) == [COMPARISONS_KEY]
    assert len(seed[COMPARISONS_KEY]) == 2
    # each entry round-trips back into a ComparisonMatrix
    assert ComparisonMatrix.model_validate(seed[COMPARISONS_KEY][0]).rival == "R1"
    # empty input is tolerated (the prompt handles a thin set)
    assert program_strategy_seed([]) == {COMPARISONS_KEY: []}


def test_finalize_sets_partial_flag_from_run_state():
    strat = ProgramStrategy(assessment="x")
    assert finalize_program_strategy(strat, missing=0).ran_on_partial_data is False
    assert finalize_program_strategy(strat, missing=["Datadog"]).ran_on_partial_data is True
    assert finalize_program_strategy(strat, missing=2).ran_on_partial_data is True


# --- AC-7: N comparisons → a ProgramStrategy with a prioritised cross-product plan ---------- #


def test_program_strategy_via_fakerunner(monkeypatch):
    produced = ProgramStrategy(
        assessment="Strong on sovereignty across the line; weak ecosystem vs incumbents.",
        action_plan=[
            RecommendedAction(action="Lead every deal with the air-gap moat", priority="high",
                              timeline="this quarter", rationale="we 'win' sovereignty vs both rivals"),
            RecommendedAction(action="Close the integration gap", priority="med",
                              timeline="next 90 days", rationale="we 'lose' ecosystem vs Datadog"),
        ],
    ).model_dump()

    class FakeSession:
        def __init__(self, state):
            self.id = "s1"
            self.state = dict(state)

    class FakeSvc:
        def __init__(self):
            self._s: FakeSession | None = None

        async def create_session(self, *, app_name, user_id, state):
            self._s = FakeSession(state)
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            self._s.state[PROGRAM_STRATEGY_KEY] = produced
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            if False:
                yield None

    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunner)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    agent = build_program_strategist(_tiered_cfg(), "vllm", cloud_allowed=False)
    seed = program_strategy_seed([_matrix("Sentinel", "Datadog", "win"),
                                  _matrix("Sentinel", "Splunk", "win")])

    final = asyncio.run(
        orch.run_step(
            agent, message_text="synthesise program strategy", seed_state=seed,
            streaming=StreamingMode.SSE, trace=[],
        )
    )
    strat = ProgramStrategy.model_validate(final[PROGRAM_STRATEGY_KEY])
    assert len(strat.action_plan) >= 1                          # a cross-product plan
    assert {a.priority for a in strat.action_plan} <= {"high", "med", "low"}
    assert strat.action_plan[0].priority == "high"             # prioritised (high first)
    assert len(final[COMPARISONS_KEY]) == 2                     # the seeded set carried through
