"""SENTINEL-015 — Agent Memory & Harness Upgrade tests.

11 test cases, all offline (no live LLM, no network). Covers:
  - RunStore.recall_episodes: exact match, keyword match, empty DB, dedup, mode filter
  - _render_episodic_context: empty → "", format with heading + snippets
  - episodic_recall flag gates context injection
  - run_step retry policy: success on retry, propagate after max_retries
  - Schema defaults: MemoryConfig + BackendConfig new fields
  - governance: DDG → Brave auto-upgrade when BRAVE_API_KEY is set

AC-10 parity: every test that touches a context path verifies that when the flag is off,
the output is "" (byte-identical to pre-015 behaviour).
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentinel.agent.governance import effective_search_provider
from sentinel.agent.orchestrator import _render_episodic_context
from sentinel.config import SentinelConfig
from sentinel.config.schema import BackendConfig, MemoryConfig
from sentinel.memory import RunStore
from sentinel.memory.schema import RunRecord


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def store(tmp_path) -> RunStore:
    return RunStore(tmp_path / "sentinel.db")


def _run(entity: str, target: str, finding_texts: list[str], mode: str = "competitor") -> RunRecord:
    return RunRecord(
        entity=entity, target=target, mode=mode, backend="gemini",
        kind="Battlecard", public=3, private=0, gaps=0,
        reference="ref-1", finding_texts=finding_texts,
    )


# --------------------------------------------------------------------------- #
# Step 2: RunStore.recall_episodes
# --------------------------------------------------------------------------- #

def test_recall_episodes_exact_match(store):
    """Exact entity match returns the run for that entity, newest first."""
    store.save(_run("stripe", "stripe", ["stripe pricing model", "stripe revenue 2024"]))
    results = store.recall_episodes("stripe", top_k=3)
    assert len(results) == 1
    assert results[0].entity == "stripe"


def test_recall_episodes_keyword_match(store):
    """Keyword LIKE search finds runs whose finding_texts contain words from the target."""
    # Save a run for 'razorpay' (different entity) with keyword overlap
    store.save(_run("razorpay", "razorpay", ["payment gateway india razorpay", "fintech unicorn"]))
    # Query for 'razorpay fintech' — should match via keyword
    results = store.recall_episodes("razorpay fintech", top_k=3)
    assert any(r.entity == "razorpay" for r in results)


def test_recall_episodes_empty_on_no_records(store):
    """Empty DB always returns []."""
    assert store.recall_episodes("stripe") == []


def test_recall_episodes_deduped_by_entity(store):
    """Multiple runs for the same entity return only one entry (the most recent)."""
    store.save(_run("stripe", "stripe", ["first run"]))
    store.save(_run("stripe", "stripe", ["second run, more recent"]))
    results = store.recall_episodes("stripe", top_k=3)
    # Only one entry per entity
    entities = [r.entity for r in results]
    assert entities.count("stripe") == 1


def test_recall_episodes_mode_filter(store):
    """When mode is specified, only runs with that mode are returned via keyword path."""
    store.save(_run("stripe", "stripe", ["stripe card payments"], mode="competitor"))
    store.save(_run("stripe", "stripe", ["stripe account brief"], mode="client"))
    # Exact match returns both (no mode filter on exact) — top_k=1 returns 1
    results_all = store.recall_episodes("stripe", top_k=5)
    assert len(results_all) == 1  # deduped: only the most recent stripe run

    # A different entity with same keyword — mode filter on keyword path
    store.save(_run("braintree", "braintree", ["braintree card payments"], mode="client"))
    results_client = store.recall_episodes("braintree card", top_k=5, mode="client")
    assert all(r.mode == "client" for r in results_client)


def test_recall_episodes_fail_soft_on_bad_db(tmp_path):
    """Any storage error returns [] without raising."""
    bad_store = RunStore(tmp_path / "nonexistent" / "sentinel.db")
    result = bad_store.recall_episodes("stripe")
    assert result == []


# --------------------------------------------------------------------------- #
# Step 3: _render_episodic_context
# --------------------------------------------------------------------------- #

def test_render_episodic_context_empty():
    """Empty episode list returns "" — AC-10 parity (byte-identical to pre-015)."""
    assert _render_episodic_context([]) == ""


def test_render_episodic_context_format():
    """Non-empty episodes produce the expected heading and snippet lines."""
    run = _run("stripe", "stripe", ["Stripe processed $817B in 2023", "Stripe valuation at $65B"])
    context = _render_episodic_context([run])
    assert "## Episodic Memory" in context
    assert "Stripe processed" in context
    assert "Do not present" in context  # anti-hallucination instruction
    # Snippets are capped at 150 chars
    for line in context.splitlines():
        if line.startswith("- "):
            assert len(line) <= 152  # "- " prefix + 150 chars


# --------------------------------------------------------------------------- #
# Step 3: episodic_recall flag gates context
# --------------------------------------------------------------------------- #

def test_episodic_recall_gated_by_flag():
    """When episodic_recall=False, _recall_memory returns 0 episodes (AC-10 parity)."""
    from sentinel.agent.orchestrator import _recall_memory

    cfg = SentinelConfig.default()
    cfg.memory.episodic_recall = False
    cfg.memory.entity_memory = False  # also off so we don't need a real DB

    # RunStore.recall_episodes must NOT be called when flag is False.
    # Patch inside sentinel.memory (the lazy-imported namespace used by _recall_memory).
    with patch("sentinel.memory.RunStore") as MockRS:
        MockRS.return_value.latest_for.return_value = None
        memory_ctx, _prior, entity_count, episode_count = _recall_memory("stripe", "competitor", cfg)

    assert episode_count == 0
    assert "Episodic Memory" not in memory_ctx
    # recall_episodes was never called
    MockRS.return_value.recall_episodes.assert_not_called()


# --------------------------------------------------------------------------- #
# Step 4: run_step retry policy
# --------------------------------------------------------------------------- #

def test_run_step_retry_on_failure():
    """run_step retries on failure and succeeds once the runner recovers."""
    from google.adk.agents.run_config import StreamingMode
    from sentinel.agent.orchestrator import run_step

    counter = [0]  # mutable container so nested closures can mutate it

    def make_runner(*args, **kwargs):
        runner = MagicMock()
        session = MagicMock()
        session.id = "s1"
        session.state = {"result": "ok"}
        runner.session_service.create_session = AsyncMock(return_value=session)
        runner.session_service.get_session = AsyncMock(return_value=session)

        async def run_async_gen(*a, **kw):
            counter[0] += 1
            if counter[0] < 3:
                raise RuntimeError("vLLM 502 transient")
            event = MagicMock()
            event.partial = False
            event.content = None
            yield event

        runner.run_async = run_async_gen
        return runner

    async def _run():
        agent = MagicMock()
        agent.sub_agents = []
        trace: list[str] = []
        with patch("sentinel.agent.orchestrator.InMemoryRunner", side_effect=make_runner):
            state = await run_step(
                agent, message_text="test", seed_state={},
                streaming=StreamingMode.NONE, trace=trace,
                max_retries=3, base_retry_delay_s=0.0,
            )
        assert state == {"result": "ok"}
        assert counter[0] == 3
        retry_lines = [l for l in trace if "retry" in l.lower()]
        assert len(retry_lines) == 2  # attempt 1 failed + attempt 2 failed = 2 retry entries

    asyncio.run(_run())


def test_run_step_propagates_after_max_retries():
    """run_step re-raises after exhausting max_retries."""
    from google.adk.agents.run_config import StreamingMode
    from sentinel.agent.orchestrator import run_step

    def make_runner(*args, **kwargs):
        runner = MagicMock()
        session = MagicMock()
        session.id = "s1"
        runner.session_service.create_session = AsyncMock(return_value=session)

        async def always_fail(*a, **kw):
            raise RuntimeError("persistent 502")
            yield  # make it an async generator

        runner.run_async = always_fail
        return runner

    async def _run():
        agent = MagicMock()
        agent.sub_agents = []
        trace: list[str] = []
        with patch("sentinel.agent.orchestrator.InMemoryRunner", side_effect=make_runner):
            with pytest.raises(RuntimeError, match="persistent 502"):
                await run_step(
                    agent, message_text="test", seed_state={},
                    streaming=StreamingMode.NONE, trace=trace,
                    max_retries=2, base_retry_delay_s=0.0,
                )
        assert any("all 2 attempts failed" in l for l in trace)

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Schema defaults
# --------------------------------------------------------------------------- #

def test_memory_config_episodic_defaults():
    """New MemoryConfig fields have correct defaults."""
    mc = MemoryConfig()
    assert mc.episodic_recall is True
    assert mc.episodic_recall_top_k == 3


def test_backend_config_turn_defaults():
    """New BackendConfig fields have correct defaults."""
    bc = BackendConfig()
    assert bc.max_turns == 60
    assert bc.max_retries == 3
    assert bc.base_retry_delay_s == 1.0


# --------------------------------------------------------------------------- #
# Step 6: governance DDG → Brave auto-upgrade
# --------------------------------------------------------------------------- #

def test_governance_ddg_upgrades_to_brave_when_key_set():
    """When BRAVE_API_KEY is set and provider is duckduckgo, effective_search_provider returns brave."""
    cfg = SentinelConfig.default()
    cfg.search.provider = "duckduckgo"  # type: ignore[assignment]
    with patch.dict(os.environ, {"BRAVE_API_KEY": "test-key-abc"}):
        result = effective_search_provider(cfg, allow_cloud=True)
    assert result == "brave"


# --------------------------------------------------------------------------- #
# IDOR guard: RunStore.delete_run project_id scoping
# --------------------------------------------------------------------------- #

def _run_with_project(entity: str, project_id: str) -> RunRecord:
    return RunRecord(
        entity=entity, target=entity, mode="competitor", backend="gemini",
        kind="Battlecard", public=1, private=0, gaps=0,
        reference="ref-x", finding_texts=["finding"],
        project_id=project_id,
    )


def test_delete_run_with_matching_project_id_succeeds(store):
    """Deleting a run scoped to its own project_id removes the record."""
    r = _run_with_project("stripe", "proj-A")
    store.save(r)
    deleted = store.delete_run(str(r.id), project_id="proj-A")
    assert deleted is True
    assert store.all(project_id="proj-A") == []


def test_delete_run_with_wrong_project_id_is_blocked(store):
    """IDOR guard: supplying a different project_id returns False and leaves the record intact."""
    r = _run_with_project("stripe", "proj-A")
    store.save(r)
    # Attacker constructs a URL with proj-B but the run belongs to proj-A
    deleted = store.delete_run(str(r.id), project_id="proj-B")
    assert deleted is False
    assert len(store.all(project_id="proj-A")) == 1  # record still exists


def test_delete_run_without_project_id_works_for_global_admin(store):
    """The unscoped delete (used by the global /memory/episodes admin route) still works."""
    r = _run_with_project("stripe", "proj-A")
    store.save(r)
    deleted = store.delete_run(str(r.id))
    assert deleted is True
    assert store.all() == []


# --------------------------------------------------------------------------- #
# G-07: procedural memory — SpecStore trace save + retrieval
# --------------------------------------------------------------------------- #

def test_record_procedural_trace_and_retrieve(tmp_path):
    """record_procedural_trace saves a trace; best_traces_for returns it."""
    from sentinel.memory.store import SpecStore
    store = SpecStore(tmp_path / "sentinel.db")
    store.record_procedural_trace(
        "market", ["self_profile", "competitor", "compare"],
        eval_score=0.85, project_id="proj-A",
    )
    traces = store.best_traces_for("market")
    assert len(traces) == 1
    assert traces[0]["steps"] == ["self_profile", "competitor", "compare"]
    assert traces[0]["eval_score"] == pytest.approx(0.85)


def test_best_traces_for_orders_by_score_desc(tmp_path):
    """best_traces_for returns highest-scored traces first."""
    from sentinel.memory.store import SpecStore
    store = SpecStore(tmp_path / "sentinel.db")
    store.record_procedural_trace("market", ["a"], eval_score=0.5)
    store.record_procedural_trace("market", ["b"], eval_score=0.9)
    store.record_procedural_trace("market", ["c"], eval_score=0.7)
    traces = store.best_traces_for("market", top_k=3)
    scores = [t["eval_score"] for t in traces]
    assert scores == sorted(scores, reverse=True)


def test_best_traces_for_empty_on_unknown_domain(tmp_path):
    """No traces for an unseen domain → empty list, no error."""
    from sentinel.memory.store import SpecStore
    assert SpecStore(tmp_path / "sentinel.db").best_traces_for("unknown-domain") == []


def test_run_dag_records_procedural_trace_on_success(tmp_path, monkeypatch):
    """run_dag records a procedural trace via SpecStore after a non-degraded result."""
    import asyncio
    from sentinel.agent import dag as dag_mod
    from sentinel.memory.store import SpecStore

    monkeypatch.setattr(dag_mod, "run_plan", _fake_run_plan_success)

    from sentinel.artifacts.schemas import Plan, Step
    plan = Plan(id="p-tr", task_id="t-tr", steps=[
        Step(id="s1", capability="self_profile", output_key="out_s1"),
    ])
    plan.steps[0].status = "done"
    from sentinel.config.defaults import build_default
    from sentinel.config.schema import BackendOption
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    asyncio.run(dag_mod.run_dag(plan, cfg=cfg, backend="vllm", cloud_allowed=False,
                                use_cache=False, project_id="p-x"))

    # Verify via the real DB that the trace was saved.
    store = SpecStore(tmp_path / "sentinel.db")
    traces = store.best_traces_for("self_profile")
    assert len(traces) == 1
    assert traces[0]["steps"] == ["self_profile"]


async def _fake_run_plan_success(plan, *, assemble, **kw):
    from sentinel.artifacts.schemas import Result
    for s in plan.steps:
        s.status = "done"
    return Result(task_id=plan.task_id, summary="ok", artifacts=[], citations=[],
                  dashboard_payload={"artifacts": {}}, degraded=False)


def test_governance_ddg_stays_ddg_without_key():
    """Without BRAVE_API_KEY, duckduckgo provider is unchanged."""
    cfg = SentinelConfig.default()
    cfg.search.provider = "duckduckgo"  # type: ignore[assignment]
    env = {k: v for k, v in os.environ.items() if k != "BRAVE_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = effective_search_provider(cfg, allow_cloud=True)
    assert result == "duckduckgo"


# --------------------------------------------------------------------------- #
# G-05: episodic vector index — embed_and_index_run + semantic_search_run_ids
# --------------------------------------------------------------------------- #

def test_embed_and_index_run_upserts_to_chroma(tmp_path):
    """embed_and_index_run calls embed_one and upserts the document into the collection."""
    from unittest.mock import MagicMock, patch as _patch
    from sentinel.memory.episodic_vector import embed_and_index_run

    fake_vec = [0.1] * 8
    fake_col = MagicMock()
    with _patch("sentinel.memory.episodic_vector._episodic_col", return_value=fake_col), \
         _patch("sentinel.kb.embedder.embed_one", return_value=fake_vec):
        embed_and_index_run("run-1", "stripe", ["payment infra", "api sdks"], tmp_path,
                            project_id="proj-A")

    fake_col.upsert.assert_called_once()
    call_kwargs = fake_col.upsert.call_args[1]
    assert call_kwargs["ids"] == ["run-1"]
    assert "stripe" in call_kwargs["documents"][0]


def test_embed_and_index_run_fail_soft_on_embed_error(tmp_path):
    """embed_and_index_run swallows embed errors — the caller must not be affected."""
    from unittest.mock import patch as _patch
    from sentinel.memory.episodic_vector import embed_and_index_run

    with _patch("sentinel.kb.embedder.embed_one", side_effect=RuntimeError("server down")):
        embed_and_index_run("run-2", "stripe", ["finding"], tmp_path)  # must not raise


def test_semantic_search_returns_run_ids(tmp_path):
    """semantic_search_run_ids returns run IDs from Chroma metadata."""
    from unittest.mock import MagicMock, patch as _patch
    from sentinel.memory.episodic_vector import semantic_search_run_ids

    fake_col = MagicMock()
    fake_col.count.return_value = 2
    fake_col.query.return_value = {
        "metadatas": [[{"run_id": "run-a"}, {"run_id": "run-b"}]],
    }
    with _patch("sentinel.memory.episodic_vector._episodic_col", return_value=fake_col), \
         _patch("sentinel.kb.embedder.embed_one", return_value=[0.1] * 8):
        ids = semantic_search_run_ids("electric vehicles", tmp_path, top_k=2)

    assert ids == ["run-a", "run-b"]


def test_semantic_search_empty_collection_returns_empty(tmp_path):
    """semantic_search_run_ids returns [] immediately when the collection is empty."""
    from unittest.mock import MagicMock, patch as _patch
    from sentinel.memory.episodic_vector import semantic_search_run_ids

    fake_col = MagicMock()
    fake_col.count.return_value = 0
    with _patch("sentinel.memory.episodic_vector._episodic_col", return_value=fake_col):
        assert semantic_search_run_ids("anything", tmp_path) == []


def test_recall_episodes_strategy4_fires_on_semantic_miss(store, tmp_path, monkeypatch):
    """Strategy 4 (dense vector) surfaces runs that exact/keyword match misses."""
    # Save a run for a different entity so exact+keyword don't match our query.
    r = RunRecord(
        entity="spacex launch vehicle", target="spacex", mode="competitor",
        backend="gemini", kind="Battlecard", public=2, private=0, gaps=0,
        reference="ref-s", finding_texts=["reusable rocket", "falcon 9"],
    )
    # Patch embed_and_index_run so save() doesn't try to reach the embed server.
    monkeypatch.setattr(
        "sentinel.memory.episodic_vector.embed_and_index_run",
        lambda *a, **kw: None,
    )
    store.save(r)

    # Strategy 4: mock semantic_search_run_ids to return the spacex run id.
    monkeypatch.setattr(
        "sentinel.memory.episodic_vector.semantic_search_run_ids",
        lambda query, dd, top_k=5: [str(r.id)],
    )
    # Query with a semantically related but lexically different phrase.
    results = store.recall_episodes("reusable spacecraft propulsion", top_k=1)
    assert len(results) == 1
    assert results[0].entity == "spacex launch vehicle"
