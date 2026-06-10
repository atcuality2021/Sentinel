"""Per-turn telemetry events (SENTINEL-016 G-13).

Lightweight observability: each agent step records token counts and wall-clock
latency into a SQLite table. No external sink required — the dashboard and
cost-analysis tooling can query TelemetryStore directly.

Design: fail-soft throughout. A telemetry write must never break a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TelemetryEvent:
    """One instrumented agent step execution."""

    step: str
    model: str
    run_id: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    project_id: str | None = None
