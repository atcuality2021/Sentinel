"""SENTINEL-012 Phase 0 — engine refactor (role-derived two-pass partition + generic `run_step`).

Hermetic: LiteLlm is mocked (no network/secret); agents are introspected. Proves (AC-11) that the
Pass-2 set is derived from config *roles* (not the hardcoded literal) and matches the legacy partition,
and that `run_step` is a mode-free generic executor.
"""

from __future__ import annotations

import asyncio

from google.adk.agents.run_config import StreamingMode

from sentinel.agent import orchestrator as orch
from sentinel.config.defaults import build_default


# --- Step 1: the Pass-2 set is derived from config roles ---------------------------------- #


def test_reasoner_keys_are_role_derived_per_mode():
    cfg = build_default()
    assert orch._reasoner_output_keys("competitor", cfg) == {"battlecard", "strategy"}
    assert orch._reasoner_output_keys("client", cfg) == {"account_brief", "strategy"}
    # each mode's derived set is a subset of the legacy literal (no drift)
    assert orch._reasoner_output_keys("competitor", cfg) <= set(orch.REASONER_OUTPUT_KEYS)
    assert orch._reasoner_output_keys("client", cfg) <= set(orch.REASONER_OUTPUT_KEYS)


def test_partition_is_role_derived_not_hardcoded():
    """Flip roles and watch the partition follow — proves it keys on role, not a frozen key set."""
    cfg = build_default()
    cfg.agents["competitor.synthesizer"].role = "planner"        # demote the reasoner
    assert "battlecard" not in orch._reasoner_output_keys("competitor", cfg)
    cfg.agents["competitor.public_research"].role = "synthesizer"  # promote a tool-caller
    assert "public_findings" in orch._reasoner_output_keys("competitor", cfg)


def test_built_partition_matches_legacy(monkeypatch):
    """The role-derived partition of the *built* sub-agents equals the legacy output-key partition."""
    # Build real LiteLlm objects (offline — no network at construction); env key avoids "not-needed".
    monkeypatch.setenv("ATCUALITY_API_KEY", "k")
    monkeypatch.setenv("VLLM_API_KEY", "k")
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.strategy.enabled = True  # include the strategist (a reasoner)

    subs, reasoner_keys = orch._build_subagents(
        "competitor", "vllm", cfg, "", cloud_allowed=False, search_provider="duckduckgo",
    )
    new_pass1 = {s.name for s in subs if s.output_key not in reasoner_keys}
    new_pass2 = {s.name for s in subs if s.output_key in reasoner_keys}
    legacy_pass1 = {s.name for s in subs if s.output_key not in orch.REASONER_OUTPUT_KEYS}
    legacy_pass2 = {s.name for s in subs if s.output_key in orch.REASONER_OUTPUT_KEYS}

    assert new_pass1 == legacy_pass1
    assert new_pass2 == legacy_pass2
    assert {"competitor_planner", "competitor_public_research"} <= new_pass1
    assert {"battlecard_synthesizer", "competitor_strategist"} <= new_pass2


# --- Step 2: `run_step` is a mode-free generic executor ----------------------------------- #


def test_run_step_is_mode_free(monkeypatch):
    class FakeSession:
        def __init__(self, state):
            self.id = "s1"
            self.state = dict(state)

    class FakeSvc:
        def __init__(self):
            self._s: FakeSession | None = None

        async def create_session(self, *, app_name, user_id, state):
            self._s = FakeSession(state)
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            self._s.state["out"] = "ok"
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            if False:  # async generator that yields nothing
                yield None

    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunner)

    class _Agent:
        sub_agents: list = []

    final = asyncio.run(
        orch.run_step(
            _Agent(), message_text="any objective, no mode/target",
            seed_state={"seeded": 1}, streaming=StreamingMode.NONE, trace=[],
        )
    )
    assert final["seeded"] == 1   # seed_state carried through
    assert final["out"] == "ok"   # agent output captured generically
