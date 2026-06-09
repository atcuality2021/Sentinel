"""Web presentation layer for Sentinel.

A thin FastAPI app over the existing orchestrator. It exists for the *demo*: judges (and
real evaluators) get a live URL where they can run the agent and see every finding tagged
with the boundary it came from. No business logic lives here — it calls
``sentinel.agent.orchestrator.run_async`` and renders the returned artifact.
"""
