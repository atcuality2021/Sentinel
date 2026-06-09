"""Agent package.

Exposes ``root_agent`` for ADK tooling (``adk run`` / ``adk web``). Defaults to competitor
mode; client mode is available via the orchestrator or by importing build_client_agent.
"""

from sentinel.agent.modes.competitor import build_competitor_agent

# Constructing the agent only resolves a model id string — no network at import time.
root_agent = build_competitor_agent()

__all__ = ["root_agent", "build_competitor_agent"]
