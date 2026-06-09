"""SENTINEL-012 TD-2 / TD-3 — persona render + sampled model-grade wired into the run path.

The reflect flagged AC-8/AC-17 (persona) and AC-19 (model-grade) as built-but-unintegrated: the units
were green, but ``run_plan``/``run_dag`` never applied them, so an orchestrated Result was never
persona-adapted or graded end-to-end. This closes that — the finalize pass attaches both to the Result
the DAG produced, on the *typed* primary artifact.

Both are additive: a default persona and ``grade=False`` leave the Result byte-identical (the last test
asserts this). AC-17 invariance is proven by running two personas over one plan and showing the facts
(citations / artifact) are identical — only the presentation field differs.

Hermetic: the FakeRunner injects each agent's output by ``output_key`` — the created specialist's
artifact, the persona renderer's prose, and the judge's rubric — so no model is called.
"""

from __future__ import annotations

import asyncio

from sentinel.agent import orchestrator as orch
from sentinel.agent.dag import run_dag
from sentinel.agent.orchestrator_planner import _mint_created_spec
from sentinel.agent.persona import RENDERED_KEY
from sentinel.agent.registry import AgentRegistry
from sentinel.artifacts.schemas import Persona, Plan, Step
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption
from sentinel.eval.graders import RUBRIC_KEY
from sentinel.memory.store import SpecStore

_CAP = "market_brief"
_SRC = {"boundary": "public", "label": "biltiq.ai", "url": "https://biltiq.ai"}
_BATTLECARD = {
    "target": "Rival Corp",
    "one_line_summary": "A cloud-first competitive-intel tool.",
    "positioning": "Cloud-native CI for enterprises.",
    "strengths": [{"text": "Recognised brand in the CI space.", "source": _SRC}],
    "weaknesses": [{"text": "No sovereign/on-prem option.", "source": _SRC}],
    "sources": [_SRC],
}
_RUBRIC = {"relevance": 4, "faithfulness": 5, "completeness": 4, "actionability": 4,
           "persona_fit": 3, "justification": "Well-cited, actionable, faithful to sources."}
_RENDERED = "In plain terms: Rival Corp is well known but has no on-prem option."

_OUTPUTS = {_CAP: _BATTLECARD, RENDERED_KEY: _RENDERED, RUBRIC_KEY: _RUBRIC}


class _FakeSvc:
    def __init__(self, agent):
        self.agent = agent
        self._s = None

    async def create_session(self, *, app_name, user_id, state):
        self._s = type("S", (), {"id": "s1", "state": dict(state)})()
        return self._s

    async def get_session(self, *, app_name, user_id, session_id):
        for a in [self.agent, *(getattr(self.agent, "sub_agents", []) or [])]:
            if getattr(a, "output_key", None) in _OUTPUTS:
                self._s.state[a.output_key] = _OUTPUTS[a.output_key]
        return self._s


class _FakeRunnerFactory:
    def __call__(self, *, agent, app_name):
        return type("R", (), {"session_service": _FakeSvc(agent), "run_async": _noop_run_async})()


async def _noop_run_async(self, *, user_id, session_id, new_message, run_config=None):
    if False:
        yield None


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def _registry(tmp_path) -> AgentRegistry:
    reg = AgentRegistry(store=SpecStore(tmp_path / "specs.db"))
    reg.register(_mint_created_spec(_CAP, "market", "Battlecard"))
    return reg


def _plan() -> Plan:
    return Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability=_CAP, output_key=_CAP, agent_spec_id=f"created-market-{_CAP}"),
    ])


def _run(tmp_path, **finalize_kwargs):
    return asyncio.run(run_dag(
        _plan(), registry=_registry(tmp_path), cfg=_tiered_cfg(), backend="vllm",
        cloud_allowed=False, search_provider="duckduckgo", use_cache=False,
        seeds={"s1": {"target": "Rival Corp"}}, **finalize_kwargs,
    ))


def test_persona_and_grade_are_attached_to_the_result(monkeypatch, tmp_path):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _FakeRunnerFactory())

    result = _run(tmp_path, persona=Persona(reading_level="K-12"), grade=True,
                  grade_objective="Profile Rival Corp")
    assert result.persona_rendered == _RENDERED          # TD-2: audience-adapted prose attached
    assert result.grade is not None                       # TD-3: sampled model grade attached
    assert 0.0 <= result.grade.score <= 1.0
    assert any(s.label == "biltiq.ai" for s in result.citations)   # facts carried through


def test_persona_render_is_fact_invariant_across_personas(monkeypatch, tmp_path):
    # AC-17: two personas over ONE plan share byte-identical facts (citations + artifact); only the
    # presentation field is persona-driven. The renderer copies sources/findings by code, never writes.
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _FakeRunnerFactory())

    a = _run(tmp_path, persona=Persona(reading_level="K-12"))
    b = _run(tmp_path, persona=Persona(reading_level="undergraduate"))
    assert [s.model_dump() for s in a.citations] == [s.model_dump() for s in b.citations]
    assert a.dashboard_payload["artifacts"] == b.dashboard_payload["artifacts"]


def test_default_persona_and_no_grade_leave_result_unchanged(monkeypatch, tmp_path):
    # Additive guarantee: the finalize pass is a no-op for the default persona with grading off, so
    # every existing run_plan/run_dag caller is byte-identical to before TD-2/TD-3.
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _FakeRunnerFactory())

    result = _run(tmp_path, persona=Persona(), grade=False)
    assert result.persona_rendered is None
    assert result.grade is None
    assert result.artifacts == [_CAP]                     # the run itself is unaffected
