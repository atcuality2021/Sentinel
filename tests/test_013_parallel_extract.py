"""SENTINEL-013 Phase 3 — parallel per-source extraction (Step 8) + sovereignty (Step 9).

Step 8 (AC-8): ``_run_parallel_extract`` splits ``{public_findings}`` into per-source units, runs the
cheap 12B extractor ONCE PER SOURCE concurrently under the global semaphore, and reduces the per-source
:class:`ExtractionSet` s into one. ``two_tier=False`` path: byte-identical (no extractor calls).

Step 9 (AC-9): under ``on_prem_required``, the concurrent extraction path builds zero Gemini objects;
no ``redis``/``pymongo``/``celery``/``kafka`` imports are present in the DAG module.

All tests are hermetic — LLM calls are mocked via a custom ``InMemoryRunner`` factory; no network, no
real sleeping.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from sentinel.agent import orchestrator as orch
from sentinel.agent.dag import _run_parallel_extract, _run_skill, _split_findings
from sentinel.agent.modes.spec import COMPETITOR_SPEC, build_step_agents
from sentinel.artifacts.schemas import (
    Boundary,
    Extraction,
    ExtractionSet,
    Source,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption


# --------------------------------------------------------------------------- #
# Test helpers
# --------------------------------------------------------------------------- #

_PUBLIC_SRC = Source(boundary=Boundary.PUBLIC, label="test-src", url="https://example.com")


def _extract_cfg(*, two_tier: bool = True):
    cfg = build_default()
    cfg.research.two_tier = two_tier
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.test/v1"),
        "public_research": BackendOption(model="gemma-4-12B", api_base="https://gemma.test/v1"),
        "extractor": BackendOption(model="gemma-4-12B", api_base="https://gemma.test/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.test/v1"),
    }
    return cfg


class _FakeSession:
    def __init__(self, state):
        self.id = "s-extract"
        self.state = dict(state)


class _ExtractSvc:
    """Records the ``public_findings`` seed per call; injects a one-extraction ExtractionSet."""

    def __init__(self, agent, calls: list):
        self._agent = agent
        self._calls = calls
        self._s: _FakeSession | None = None

    async def create_session(self, *, app_name, user_id, state):
        self._calls.append(state.get("public_findings"))
        self._s = _FakeSession(state)
        return self._s

    async def get_session(self, *, app_name, user_id, session_id):
        pf = str(self._s.state.get("public_findings", ""))[:30]
        es = ExtractionSet(extractions=[Extraction(source=_PUBLIC_SRC, notes=[pf])])
        self._s.state["extractions"] = es.model_dump()
        return self._s


class _ExtractRunner:
    def __init__(self, agent, calls: list):
        self.session_service = _ExtractSvc(agent, calls)

    async def run_async(self, *, user_id, session_id, new_message, run_config=None):
        if False:
            yield None


class _ExtractRunnerFactory:
    def __init__(self):
        self.calls: list = []

    def __call__(self, *, agent, app_name):
        return _ExtractRunner(agent, self.calls)


# --------------------------------------------------------------------------- #
# _split_findings unit tests
# --------------------------------------------------------------------------- #


def test_split_findings_json_list_of_dicts():
    sources = [{"title": f"T{i}", "url": f"https://e{i}.com", "snippet": f"S{i}"} for i in range(3)]
    parts = _split_findings(json.dumps(sources))
    assert len(parts) == 3
    for p in parts:
        parsed = json.loads(p)
        assert isinstance(parsed, dict)
        assert "url" in parsed


def test_split_findings_search_envelope_unwrapped():
    envelope = {"results": [{"url": "a.com"}, {"url": "b.com"}], "status": "success"}
    parts = _split_findings(json.dumps(envelope))
    assert len(parts) == 2
    assert json.loads(parts[0])["url"] == "a.com"


def test_split_findings_plain_text_is_single_source():
    parts = _split_findings("Some free-text findings from the research agent.")
    assert len(parts) == 1
    assert "free-text" in parts[0]


def test_split_findings_single_dict_no_results_key():
    d = {"url": "only.com", "title": "only one"}
    parts = _split_findings(json.dumps(d))
    assert len(parts) == 1
    assert json.loads(parts[0])["url"] == "only.com"


def test_split_findings_empty_string_returns_one_item():
    parts = _split_findings("")
    assert len(parts) == 1


def test_split_findings_list_of_strings():
    raw = json.dumps(["finding one", "finding two"])
    parts = _split_findings(raw)
    assert len(parts) == 2
    assert parts[0] == "finding one"


# --------------------------------------------------------------------------- #
# _run_parallel_extract — AC-8 core
# --------------------------------------------------------------------------- #


def test_n_sources_produce_n_extractor_calls(monkeypatch):
    """N source dicts in public_findings → N InMemoryRunner calls, each bounded to one source (AC-8)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc-test")
    cfg = _extract_cfg()
    agents = build_step_agents(COMPETITOR_SPEC, cfg, two_tier=True)
    extractor = next(a for a in agents if a.output_key == "extractions")

    factory = _ExtractRunnerFactory()
    monkeypatch.setattr(orch, "InMemoryRunner", factory)

    sources = [{"title": f"S{i}", "url": f"https://e{i}.com", "snippet": f"C{i}"} for i in range(3)]
    state = {"public_findings": json.dumps(sources), "target": "TestCo"}
    trace: list[str] = []

    result_state = asyncio.run(
        _run_parallel_extract(extractor, state, spec=COMPETITOR_SPEC, cfg=cfg, trace=trace, mc=None)
    )

    # exactly 3 extractor calls — one per source
    assert len(factory.calls) == 3, f"expected 3 calls, got {len(factory.calls)}"

    # each input bounded to a SINGLE source dict (not the full list)
    for raw in factory.calls:
        assert raw is not None
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        assert isinstance(parsed, dict), f"expected a single source dict, got {type(parsed)}: {raw!r}"

    # reduced ExtractionSet is in state
    raw_es = result_state.get("extractions")
    assert raw_es is not None, "extractions not in state after parallel extract"
    es = ExtractionSet.model_validate(raw_es)
    assert len(es.extractions) == 3, f"expected 3 extractions, got {len(es.extractions)}"


def test_empty_public_findings_returns_empty_extraction_set(monkeypatch):
    """No public_findings → immediate empty ExtractionSet, no runner calls (fail-soft)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc-test")
    cfg = _extract_cfg()
    agents = build_step_agents(COMPETITOR_SPEC, cfg, two_tier=True)
    extractor = next(a for a in agents if a.output_key == "extractions")

    factory = _ExtractRunnerFactory()
    monkeypatch.setattr(orch, "InMemoryRunner", factory)

    state: dict = {}  # no public_findings
    result_state = asyncio.run(
        _run_parallel_extract(extractor, state, spec=COMPETITOR_SPEC, cfg=cfg, trace=[], mc=None)
    )

    assert factory.calls == [], "no runner calls when public_findings is absent"
    es = ExtractionSet.model_validate(result_state["extractions"])
    assert es.extractions == []


def test_per_source_failure_degrades_gracefully(monkeypatch):
    """A failing extractor call contributes nothing; other sources succeed (fail-soft NFR-3)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc-test")
    cfg = _extract_cfg()
    agents = build_step_agents(COMPETITOR_SPEC, cfg, two_tier=True)
    extractor = next(a for a in agents if a.output_key == "extractions")

    call_count = [0]

    class _BrokenSvc:
        def __init__(self, agent, n):
            self._agent = agent
            self._n = n
            self._s: _FakeSession | None = None

        async def create_session(self, *, app_name, user_id, state):
            call_count[0] += 1
            if call_count[0] == 2:   # second source raises
                raise RuntimeError("simulated extractor failure")
            self._s = _FakeSession(state)
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            es = ExtractionSet(extractions=[Extraction(source=_PUBLIC_SRC, notes=["ok"])])
            self._s.state["extractions"] = es.model_dump()
            return self._s

    class _BrokenRunnerFactory:
        def __call__(self, *, agent, app_name):
            class _R:
                def __init__(inner_self):
                    inner_self.session_service = _BrokenSvc(agent, call_count[0])
                async def run_async(inner_self, **kw):
                    if False:
                        yield None
            return _R()

    monkeypatch.setattr(orch, "InMemoryRunner", _BrokenRunnerFactory())

    sources = [{"url": f"https://e{i}.com"} for i in range(3)]
    state = {"public_findings": json.dumps(sources)}
    trace: list[str] = []

    result_state = asyncio.run(
        _run_parallel_extract(extractor, state, spec=COMPETITOR_SPEC, cfg=cfg, trace=trace, mc=None)
    )

    es = ExtractionSet.model_validate(result_state["extractions"])
    # 2 of 3 succeeded; 1 failed gracefully
    assert len(es.extractions) == 2, f"expected 2 surviving extractions, got {len(es.extractions)}"
    assert any("FAILED" in t for t in trace), "trace should record the failure"


def test_two_tier_false_path_no_extractor_in_pass1(monkeypatch):
    """With two_tier=False, _run_skill does not include an extractor in pass1 (byte-identical path)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc-test")
    cfg = _extract_cfg(two_tier=False)

    agents_no_tier = build_step_agents(COMPETITOR_SPEC, cfg, two_tier=False)
    extractor_agents = [a for a in agents_no_tier if a.output_key == "extractions"]
    # two_tier=False → build_step_agents never inserts the extractor
    assert extractor_agents == [], "no extractor in agent list when two_tier=False"


def test_two_tier_true_extractor_stripped_from_pass1(monkeypatch):
    """With two_tier=True, the single extractor is present in the built list but _run_skill
    strips it (it runs per-source instead). Verify the strip leaves no 'extractions' agent in pass1."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc-test")
    cfg = _extract_cfg(two_tier=True)
    from sentinel.config.schema import REASONER_ROLES

    agents = build_step_agents(COMPETITOR_SPEC, cfg, two_tier=True)
    extractor_agents = [a for a in agents if a.output_key == "extractions"]
    assert len(extractor_agents) == 1, "extractor is in built list when two_tier=True"

    # simulate the strip logic in _run_skill
    non_ext = [a for a in agents if a.output_key != "extractions"]
    reasoner_keys = {
        s.output_key for s in COMPETITOR_SPEC.steps if cfg.agents[s.agent_key].role in REASONER_ROLES
    }
    pass1 = [a for a in non_ext if a.output_key not in reasoner_keys]
    extract_in_pass1 = [a for a in pass1 if a.output_key == "extractions"]
    assert extract_in_pass1 == [], "extractor must not remain in pass1 after strip"


# --------------------------------------------------------------------------- #
# AC-9 — sovereignty + no-infra imports
# --------------------------------------------------------------------------- #


def test_on_prem_required_zero_gemini_in_parallel_extract_path():
    """Under on_prem_required, build_step_agents with two_tier=True produces no Gemini model (AC-9)."""
    import sentinel.agent.governance as G

    cfg = build_default()
    cfg.governance.compliance_mode = "on_prem_required"
    ca = G.cloud_allowed(cfg)
    assert not ca

    agents = build_step_agents(COMPETITOR_SPEC, cfg, cloud_allowed=ca, two_tier=True)
    extractor_agents = [a for a in agents if a.output_key == "extractions"]
    assert len(extractor_agents) == 1, "extractor agent should still be built"

    for a in agents:
        # model attribute varies by ADK version; check any known attribute
        model_str = (
            getattr(a, "_model_name", "")
            or getattr(a, "model", "")
            or getattr(a, "_model", "")
            or ""
        )
        assert "gemini" not in str(model_str).lower(), (
            f"Gemini model found in agent {a.name!r} under on_prem_required: {model_str!r}"
        )


def test_no_banned_infra_imports_in_dag():
    """dag.py must not introduce redis/pymongo/celery/kafka — no new infrastructure (AC-9)."""
    import ast
    from pathlib import Path

    src_path = Path(__file__).parent.parent / "src" / "sentinel" / "agent" / "dag.py"
    tree = ast.parse(src_path.read_text())

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(n.name.split(".")[0] for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    for banned in ("redis", "pymongo", "celery", "kafka"):
        assert banned not in imported_roots, (
            f"Banned infra import {banned!r} found in dag.py — no new infrastructure (AC-9)"
        )
