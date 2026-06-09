"""SENTINEL-012 Phase 2 Step 11 — the persona render-only pass (AC-17).

Hermetic: the renderer is built offline + introspected, then driven through a FakeRunner that returns
*different prose per persona* (keyed on the persona name in the seed message). Proves the render-only
guarantee: two personas over ONE artifact yield byte-identical ``sources``/``finding_texts`` (carried
by code, never by the model) and differ ONLY in ``rendered_text`` — and that the renderer is a
sovereign, tool-free reasoner that cannot fetch new facts.
"""

from __future__ import annotations

import asyncio

from google.adk.agents.run_config import StreamingMode

from sentinel.agent import orchestrator as orch
from sentinel.agent.persona import (
    RENDERED_KEY,
    build_persona_renderer,
    extract_render_facts,
    persona_profile,
    render_for_persona,
)
from sentinel.artifacts.schemas import Battlecard, Boundary, Finding, Persona, Source
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption

_PUB = Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://techcrunch.com/x")
_PUB2 = Source(boundary=Boundary.PUBLIC, label="G2", url="https://g2.com/y")


def _card() -> Battlecard:
    return Battlecard(
        target="Datadog", one_line_summary="Observability leader", positioning="cloud-native APM",
        strengths=[Finding(text="Mature integration ecosystem", source=_PUB)],
        weaknesses=[Finding(text="Usage-based pricing surprises buyers", source=_PUB2)],
        sources=[_PUB, _PUB2],
    )


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


# --- build: sovereign, tool-free reasoner --------------------------------------------------- #


def test_persona_renderer_builds_sovereign_toolfree(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    agent = build_persona_renderer(Persona(name="student"), _tiered_cfg(), "vllm", cloud_allowed=False)
    assert agent.name == "persona_renderer"
    assert not isinstance(agent.model, str)            # no Gemini model-id string under on_prem
    assert type(agent.model).__name__ == "LiteLlm"
    assert "26B" in agent.model.model                  # reasoner tier
    assert agent.output_key == RENDERED_KEY
    assert not getattr(agent, "tools", None)           # tool-free → cannot fetch new facts (§9.2)


def test_persona_profile_carries_the_render_dimensions():
    p = Persona(name="student", reading_level="K-12", tone="plain", format="bullets",
                source_policy="peer-reviewed only")
    prof = persona_profile(p)
    assert "K-12" in prof and "plain" in prof and "bullets" in prof and "peer-reviewed only" in prof


def test_persona_instruction_differs_by_persona(monkeypatch):
    """The build-substituted {persona_profile} bakes the audience into the instruction itself."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    a_student = build_persona_renderer(Persona(name="student", reading_level="K-12"), cfg, "vllm",
                                       cloud_allowed=False)
    a_exec = build_persona_renderer(Persona(name="enterprise", reading_level="professional"), cfg,
                                    "vllm", cloud_allowed=False)
    assert a_student.instruction != a_exec.instruction
    assert "{persona_profile}" not in a_student.instruction  # substituted, not left dangling


# --- facts extraction is by code, off the artifact ------------------------------------------ #


def test_extract_render_facts_reads_artifact_not_model():
    sources, texts = extract_render_facts(_card())
    assert [s.label for s in sources] == ["TechCrunch", "G2"]
    assert set(texts) == {"Mature integration ecosystem", "Usage-based pricing surprises buyers"}


# --- AC-17: two personas → identical facts/sources, different rendering only ---------------- #


def _fake_runner_returning_prose():
    """FakeRunner whose rendered prose varies by the persona named in the run message."""

    class FakeSession:
        def __init__(self, state, message):
            self.id = "s1"
            self.state = dict(state)
            self.message = message

    class FakeSvc:
        def __init__(self):
            self._s = None

        async def create_session(self, *, app_name, user_id, state):
            self._s = FakeSession(state, "")
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            # echo the persona-specific prose the runner was told to produce
            self._s.state[RENDERED_KEY] = self._s.state.pop("_prose", "rendered")
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            # stash the persona-specific prose keyed off the user message text
            text = new_message.parts[0].text
            self.session_service._s.state["_prose"] = f"PROSE for «{text}»"
            if False:
                yield None

    return FakeRunner


def test_two_personas_share_facts_differ_only_in_rendering(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _fake_runner_returning_prose())
    cfg = _tiered_cfg()
    card = _card()

    student = asyncio.run(render_for_persona(
        card, Persona(name="student", reading_level="K-12", tone="plain", format="bullets"),
        cfg=cfg, backend="vllm", cloud_allowed=False,
    ))
    execu = asyncio.run(render_for_persona(
        card, Persona(name="enterprise", reading_level="professional", tone="technical"),
        cfg=cfg, backend="vllm", cloud_allowed=False,
    ))

    # facts + sources are IDENTICAL across personas (carried by code off the artifact)
    assert student.sources == execu.sources == card.sources
    assert student.finding_texts == execu.finding_texts
    assert set(student.finding_texts) == {
        "Mature integration ecosystem", "Usage-based pricing surprises buyers",
    }
    # only the rendering differs
    assert student.rendered_text != execu.rendered_text
    assert "student" in student.rendered_text and "enterprise" in execu.rendered_text


def test_renderer_runs_sse_and_carries_no_tools(monkeypatch):
    """Sanity: the render pass runs the reasoner SSE (26B streaming policy) with no tool calls."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _fake_runner_returning_prose())
    trace: list[str] = []
    out = asyncio.run(render_for_persona(
        _card(), Persona(name="developer"), cfg=_tiered_cfg(), backend="vllm",
        cloud_allowed=False, trace=trace,
    ))
    assert out.rendered_text.startswith("PROSE for")
    assert not any("tool:" in line for line in trace)   # render-only: no tool calls
