"""SENTINEL-016 G-13 — Telemetry hooks: per-turn token + latency tests."""

from __future__ import annotations

from sentinel.telemetry import TelemetryEvent
from sentinel.memory.store import TelemetryStore


def test_record_and_events_for_run_roundtrip(tmp_path):
    """record() persists an event; events_for_run() returns it correctly."""
    store = TelemetryStore(tmp_path / "sentinel.db")
    ev = TelemetryEvent(
        step="self_profile_p1", model="gemma-4-12B", run_id="run-001",
        latency_ms=342.5, tokens_in=512, tokens_out=128,
    )
    store.record(ev)
    events = store.events_for_run("run-001")
    assert len(events) == 1
    assert events[0]["step"] == "self_profile_p1"
    assert events[0]["latency_ms"] == 342.5
    assert events[0]["tokens_in"] == 512


def test_latency_is_positive(tmp_path):
    """Recorded latency must always be a positive number."""
    store = TelemetryStore(tmp_path / "sentinel.db")
    store.record(TelemetryEvent(step="s", model="m", run_id="r", latency_ms=0.01))
    events = store.events_for_run("r")
    assert events[0]["latency_ms"] > 0


def test_unknown_run_returns_empty_list(tmp_path):
    """events_for_run on an unseen run_id returns [] without error."""
    store = TelemetryStore(tmp_path / "sentinel.db")
    assert store.events_for_run("nonexistent-run") == []
