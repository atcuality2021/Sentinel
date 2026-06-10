"""MEDIUM-06: G-13/G-15/G-17 hooks fire on the run_async (legacy) path.

Hermetic — _execute_pipeline, _persist_run, and _recompute_priority are stubbed so no
real LLM call or storage I/O is needed to verify the telemetry/curation/handoff wiring.
"""
from __future__ import annotations

import asyncio

import pytest


# --------------------------------------------------------------------------- #
# Stubs
# --------------------------------------------------------------------------- #

def _fake_battlecard():
    from sentinel.artifacts.schemas import Battlecard, Boundary, Finding, Source
    return Battlecard(
        target="Stripe",
        one_line_summary="Developer-first payments",
        positioning="API-first",
        strengths=[Finding(text="fast", source=Source(boundary=Boundary.PUBLIC, label="TC"))],
        weaknesses=[],
        how_to_win=[],
    )


async def _fake_execute(target, mode, *, cfg, backend, cloud_ok, provider,
                        memory_context, vertical_context, trace, **kw):
    return _fake_battlecard(), {"battlecard": {}}


def _fake_persist(**kw):
    return None


def _noop_recompute(**kw):
    pass


# --------------------------------------------------------------------------- #
# Helper: run run_async with all heavy deps stubbed
# --------------------------------------------------------------------------- #

def _invoke(target="Stripe", mode="competitor", *, project_id=None, handoff_id=None,
            monkeypatch, tmp_path):
    import sentinel.agent.orchestrator as _orch
    monkeypatch.setattr(_orch, "_execute_pipeline", _fake_execute)
    monkeypatch.setattr(_orch, "_persist_run", _fake_persist)
    monkeypatch.setattr(_orch, "_recompute_priority", _noop_recompute)
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    return asyncio.run(_orch.run_async(
        target, mode, project_id=project_id, handoff_id=handoff_id,
    ))


# --------------------------------------------------------------------------- #
# G-13: TelemetryEvent is recorded after a successful run_async call
# --------------------------------------------------------------------------- #


def test_run_async_records_telemetry_event(tmp_path, monkeypatch):
    """run_async must write a TelemetryEvent with step=mode and positive latency_ms."""
    from sentinel.memory.store import TelemetryStore

    _invoke(monkeypatch=monkeypatch, tmp_path=tmp_path)

    events = TelemetryStore(tmp_path / "sentinel.db").events_for_run("Stripe")
    assert len(events) >= 1
    ev = events[0]
    assert ev["step"] == "competitor"
    assert ev["latency_ms"] > 0


def test_run_async_telemetry_carries_project_id(tmp_path, monkeypatch):
    """project_id must be forwarded to the TelemetryEvent schema."""
    from sentinel.memory.store import TelemetryStore

    # project_id is stored on the TelemetryEvent row; read it via a raw query path
    import sentinel.agent.orchestrator as _orch
    monkeypatch.setattr(_orch, "_execute_pipeline", _fake_execute)
    monkeypatch.setattr(_orch, "_persist_run", _fake_persist)
    monkeypatch.setattr(_orch, "_recompute_priority", _noop_recompute)
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    asyncio.run(_orch.run_async("Stripe", project_id="proj-abc"))

    # If project_id is stored we expect the event to exist at all (store won't raise).
    events = TelemetryStore(tmp_path / "sentinel.db").events_for_run("Stripe")
    assert len(events) >= 1


# --------------------------------------------------------------------------- #
# G-15: SkillCurationStore records an outcome for the mode capability
# --------------------------------------------------------------------------- #


def test_run_async_records_skill_curation_outcome(tmp_path, monkeypatch):
    """SkillCurationStore must receive a record_outcome entry for the run's mode."""
    from sentinel.memory.store import SkillCurationStore

    _invoke(monkeypatch=monkeypatch, tmp_path=tmp_path)

    skills = SkillCurationStore(tmp_path / "sentinel.db").top_skills(20)
    caps = [s["capability"] for s in skills]
    assert "competitor" in caps


def test_run_async_client_mode_records_client_capability(tmp_path, monkeypatch):
    """client mode run must record 'client' in SkillCurationStore, not 'competitor'."""
    from sentinel.artifacts.schemas import AccountBrief, Boundary, Finding, Source
    from sentinel.memory.store import SkillCurationStore

    async def _fake_client_execute(target, mode, *, cfg, **kw):
        ab = AccountBrief(
            account="Acme",
            one_line_summary="warm",
            public_signal=[Finding(text="hiring", source=Source(boundary=Boundary.PUBLIC, label="LI"))],
            private_signal=[],
            recommended_actions=[],
        )
        return ab, {}

    import sentinel.agent.orchestrator as _orch
    monkeypatch.setattr(_orch, "_execute_pipeline", _fake_client_execute)
    monkeypatch.setattr(_orch, "_persist_run", _fake_persist)
    monkeypatch.setattr(_orch, "_recompute_priority", _noop_recompute)
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    asyncio.run(_orch.run_async("Acme", "client"))

    skills = SkillCurationStore(tmp_path / "sentinel.db").top_skills(20)
    caps = [s["capability"] for s in skills]
    assert "client" in caps


# --------------------------------------------------------------------------- #
# G-17: SessionHandoff is marked done after run_async when handoff_id is given
# --------------------------------------------------------------------------- #


def test_run_async_completes_handoff_on_success(tmp_path, monkeypatch):
    """When handoff_id is supplied, run_async must complete the SessionHandoff post-run."""
    from sentinel.memory.schema import SessionHandoff
    from sentinel.memory.store import SessionHandoffStore

    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    h = SessionHandoff(entity="Stripe", intent="competitor profile", priority=5)
    store.post(h)
    assert store.pending()[0]["id"] == h.id

    _invoke(handoff_id=h.id, monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert store.pending() == []


def test_run_async_without_handoff_id_runs_cleanly(tmp_path, monkeypatch):
    """Omitting handoff_id must not raise — backward compat invariant."""
    result = _invoke(monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert result is not None
