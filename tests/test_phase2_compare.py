"""SENTINEL-012 Phase 2 Step 8 — the `compare` domain skill (AC-6).

Hermetic: LiteLlm built offline + introspected; the reasoner is driven through a FakeRunner. Proves
`compare` is a tool-free reasoner (the build-time guard holds), registered under domain `market`,
sovereign under tiering (26B, zero Gemini on_prem), and that it yields a schema-valid
`ComparisonMatrix` carrying win/lose/parity verdicts from our two prior artifacts.
"""

from __future__ import annotations

import asyncio

import pytest
from google.adk.agents.run_config import StreamingMode

from sentinel.agent import orchestrator as orch
from sentinel.agent.modes._build import make_agent
from sentinel.agent.modes.spec import COMPARE_SPEC, SKILL_SPECS, build_step_agents
from sentinel.artifacts.schemas import (
    Boundary,
    ComparisonAxis,
    ComparisonMatrix,
    SelfProfile,
    Source,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption
from sentinel.tools.public.web_search import get_search_tool


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


# --- registration + shape ------------------------------------------------------------------ #


def test_compare_registered_under_market():
    assert SKILL_SPECS["compare"] is COMPARE_SPEC
    assert COMPARE_SPEC.domain == "market"
    assert COMPARE_SPEC.capability == "compare"
    assert COMPARE_SPEC.output_schema is ComparisonMatrix


def test_compare_is_single_toolfree_reasoner_step():
    assert len(COMPARE_SPEC.steps) == 1                 # no planner/research — reasons over inputs
    (step,) = COMPARE_SPEC.steps
    assert step.role == "synthesize"
    assert step.tool is None
    assert COMPARE_SPEC.has_private is False


# --- AC-6: sovereign reasoner build (26B, zero Gemini) ------------------------------------- #


def test_compare_builds_sovereign_reasoner(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    agents = build_step_agents(
        COMPARE_SPEC, cfg, "vllm", cloud_allowed=False, search_provider="duckduckgo",
    )
    (agent,) = agents
    assert agent.name == "compare_synthesizer"
    assert not isinstance(agent.model, str)             # no Gemini model-id string
    assert type(agent.model).__name__ == "LiteLlm"
    assert "26B" in agent.model.model                   # reasoner tier
    assert agent.output_schema is ComparisonMatrix
    assert not getattr(agent, "tools", None)            # tool-free


def test_toolfree_guard_holds_for_compare(monkeypatch):
    """Handing the compare reasoner a tool under tiering is a build-time ValueError (AC-6 guard)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    with pytest.raises(ValueError, match="reasoner"):
        make_agent(
            cfg, "compare.synthesizer", name="compare_synthesizer",
            output_key="comparison_matrix", mode_backend="vllm", cloud_allowed=False,
            output_schema=ComparisonMatrix,
            tools=[get_search_tool("duckduckgo", results=3, max_calls=0)],
        )


# --- AC-6: schema-valid ComparisonMatrix with verdicts via FakeRunner ---------------------- #


def test_compare_yields_matrix_with_verdicts_via_fakerunner(monkeypatch):
    pub = Source(boundary=Boundary.PUBLIC, label="biltiq.ai", url="https://biltiq.ai")
    matrix = ComparisonMatrix(
        subject="BiltIQ Sentinel", rival="Datadog",
        axes=[
            ComparisonAxis(axis="sovereignty", ours="air-gapped Gemma", theirs="cloud-only",
                           verdict="win"),
            ComparisonAxis(axis="ecosystem", ours="emerging", theirs="mature", verdict="lose"),
            ComparisonAxis(axis="pricing", ours="usage-based", theirs="usage-based",
                           verdict="parity"),
        ],
        sources=[pub],
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
            self._s.state["comparison_matrix"] = matrix
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            if False:
                yield None

    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunner)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    (agent,) = build_step_agents(
        COMPARE_SPEC, cfg, "vllm", cloud_allowed=False, search_provider="duckduckgo",
    )
    # the two prior artifacts the compare skill reads from seed-state
    seed = {
        "self_profile": SelfProfile(org="BiltIQ", sources=[pub]).model_dump(),
        "battlecard": {"target": "Datadog", "one_line_summary": "Observability leader"},
    }
    final = asyncio.run(
        orch.run_step(
            agent, message_text="compare BiltIQ vs Datadog", seed_state=seed,
            streaming=StreamingMode.SSE, trace=[],
        )
    )
    out = ComparisonMatrix.model_validate(final["comparison_matrix"])
    assert {a.verdict for a in out.axes} == {"win", "lose", "parity"}
    assert final["self_profile"]["org"] == "BiltIQ"     # seed inputs carried through
