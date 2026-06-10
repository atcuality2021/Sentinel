"""ADK compatibility shim — forward-safe wrappers for deprecated ADK constructs.

ADK 2.2 deprecated ``SequentialAgent`` in favour of the new graph-based ``google.adk.Workflow``
(edge-declared DAG).  Full migration requires restructuring every pipeline as an explicit node
graph; that refactor is tracked as SENTINEL-017 and is safe to do after the challenge submission.

Until then, all ADK call-sites import from here instead of ``google.adk.agents`` directly.
The shim suppresses the deprecation at instantiation so the API surface stays identical.
"""

from __future__ import annotations

import warnings as _warnings

from google.adk.agents import Agent  # re-exported for convenience
from google.adk.agents import SequentialAgent as _DeprecatedSequentialAgent


def SequentialAgent(**kwargs) -> _DeprecatedSequentialAgent:
    """Construct a SequentialAgent without the ADK 2.2 deprecation noise.

    Accepts any kwargs the underlying class accepts (name, sub_agents, description, …).
    Migration path (SENTINEL-017): replace callers with ``google.adk.Workflow`` edge graphs
    once the challenge deadline has passed.
    """
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", DeprecationWarning)
        return _DeprecatedSequentialAgent(**kwargs)


__all__ = ["Agent", "SequentialAgent"]
