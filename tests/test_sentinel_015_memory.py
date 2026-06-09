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
    assert bc.max_turns == 30
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


def test_governance_ddg_stays_ddg_without_key():
    """Without BRAVE_API_KEY, duckduckgo provider is unchanged."""
    cfg = SentinelConfig.default()
    cfg.search.provider = "duckduckgo"  # type: ignore[assignment]
    env = {k: v for k, v in os.environ.items() if k != "BRAVE_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = effective_search_provider(cfg, allow_cloud=True)
    assert result == "duckduckgo"
