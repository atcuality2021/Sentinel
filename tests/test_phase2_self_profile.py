"""SENTINEL-012 Phase 2 Step 7 — the `self_profile` domain skill (AC-6).

Hermetic: no network/secret — LiteLlm objects are constructed offline and introspected, and the
synthesizer is exercised through a FakeRunner. Proves the new skill (a) is registered under domain
`market`, (b) builds under role-tiering (planner/research → 12B tool-callers, synth → 26B reasoner)
with **zero Gemini objects** under on_prem, (c) keeps the reasoner tool-free, and (d) yields a
schema-valid `SelfProfile` through the generic `run_step` executor.
"""

from __future__ import annotations

import asyncio

from google.adk.agents.run_config import StreamingMode

from sentinel.agent import orchestrator as orch
from sentinel.agent.modes.spec import (
    SELF_PROFILE_SPEC,
    SKILL_SPECS,
    build_step_agents,
)
from sentinel.artifacts.schemas import Boundary, SelfProfile, Source
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption


def _tiered_cfg():
    """A vLLM config with the role map active (tool-callers → 12B, reasoners → 26B)."""
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(
            model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


# --- registration (design §2.1: the mode library is the skill registry) -------------------- #


def test_self_profile_registered_under_market():
    assert SKILL_SPECS["self_profile"] is SELF_PROFILE_SPEC
    assert SELF_PROFILE_SPEC.domain == "market"
    assert SELF_PROFILE_SPEC.capability == "self_profile"
    assert SELF_PROFILE_SPEC.output_schema is SelfProfile


def test_self_profile_topology_is_plan_research_synthesize():
    roles = [s.role for s in SELF_PROFILE_SPEC.steps]
    assert roles == ["plan", "research", "synthesize"]
    # exactly one search-bearing step (public research); no private boundary on this skill
    assert [s.tool for s in SELF_PROFILE_SPEC.steps] == [None, "search", None]
    assert SELF_PROFILE_SPEC.has_private is False


# --- AC-6: sovereign build under tiering (zero Gemini on_prem) ------------------------------ #


def test_self_profile_builds_sovereign_under_tiering(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    agents = build_step_agents(
        SELF_PROFILE_SPEC, cfg, "vllm", cloud_allowed=False, search_provider="duckduckgo",
    )
    by_name = {a.name: a for a in agents}
    # every agent is an on-prem LiteLlm — no Gemini model-id string anywhere (the introspection seam)
    for a in agents:
        assert not isinstance(a.model, str), f"{a.name} got a Gemini model-id string"
        assert type(a.model).__name__ == "LiteLlm"
    # role tiering routed the tool-callers to the 12B and the reasoner to the 26B
    assert "12B" in by_name["self_profile_planner"].model.model
    assert "12B" in by_name["self_profile_public_research"].model.model
    assert "26B" in by_name["self_profile_synthesizer"].model.model


def test_synthesizer_is_schema_bound_and_tool_free(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    agents = build_step_agents(
        SELF_PROFILE_SPEC, cfg, "vllm", cloud_allowed=False, search_provider="duckduckgo",
    )
    synth = next(a for a in agents if a.name == "self_profile_synthesizer")
    assert synth.output_schema is SelfProfile
    assert not getattr(synth, "tools", None)          # reasoner carries no tools
    research = next(a for a in agents if a.name == "self_profile_public_research")
    assert research.tools                              # the tool-caller does


# --- AC-6: schema-valid output through the generic executor (FakeRunner) -------------------- #


def test_self_profile_schema_valid_output_via_fakerunner(monkeypatch):
    """run_step is mode-free: drive the synthesizer with a fake runner that writes a SelfProfile to
    state under its output_key, and confirm the captured value round-trips through the schema."""
    valid = SelfProfile(
        org="BiltIQ",
        sources=[Source(boundary=Boundary.PUBLIC, label="biltiq.ai", url="https://biltiq.ai")],
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
            self._s.state["self_profile"] = valid     # the synthesizer's output_key
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            if False:                                  # async generator that yields nothing
                yield None

    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunner)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    agents = build_step_agents(
        SELF_PROFILE_SPEC, cfg, "vllm", cloud_allowed=False, search_provider="duckduckgo",
    )
    synth = next(a for a in agents if a.name == "self_profile_synthesizer")

    final = asyncio.run(
        orch.run_step(
            synth, message_text="BiltIQ", seed_state={}, streaming=StreamingMode.SSE, trace=[],
        )
    )
    # the captured artifact validates as a SelfProfile (the skill's typed contract holds)
    profile = SelfProfile.model_validate(final["self_profile"])
    assert profile.org == "BiltIQ"
    assert profile.sources[0].boundary == Boundary.PUBLIC
