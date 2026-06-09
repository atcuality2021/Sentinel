"""SENTINEL-012 Phase 3 Step 14 — AgentRegistry + SpecStore migration (AC-12 / AC-21, ADR-0004).

Two halves:
- **Migration (ADR-0004 test plan):** the ``agent_specs`` table round-trips an ``AgentSpec``, and a
  *pre-014* DB (ADR-0003's three-table schema, no ``agent_specs``) gains the table on open without
  disturbing its existing ``projects`` rows — additive, idempotent.
- **Registry (AC-12/21):** ``resolve`` reuses the best-scoring active spec (no duplicate); a
  tool-bearing reasoner and an off-allow-list tool are each rejected; ``build_from_spec`` builds a
  sovereign, tool-free reasoner under on_prem (no Gemini object — introspection).

Hermetic: every store is a tmp-file SQLite DB; ``build_from_spec`` is introspected offline (no
inference, no network).
"""

from __future__ import annotations

import sqlite3

import pytest

from sentinel.agent.registry import (
    ALLOWED_TOOLS,
    AgentRegistry,
    SpecValidationError,
    seed_specs,
    spec_violations,
    validate_agent_spec,
)
from sentinel.artifacts.schemas import AgentSpec, Boundary, Project
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption
from sentinel.memory.store import SpecStore


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
        "strategist": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def _spec(spec_id, capability="compare", domain="market", *, role="synthesizer",
          tools=None, schema_ref="ComparisonMatrix", score=None, version=1, active=True,
          origin="created") -> AgentSpec:
    return AgentSpec(
        id=spec_id, name=spec_id, capability=capability, domain=domain, role=role,
        skill_prompt="Emit the artifact from seed-state.", tools=tools or [],
        output_schema_ref=schema_ref, boundaries=[Boundary.PUBLIC], origin=origin,
        version=version, eval_score=score, active=active,
    )


# --------------------------------------------------------------------------- #
# Migration — the agent_specs table (ADR-0004)
# --------------------------------------------------------------------------- #


def test_spec_store_crud_round_trip(tmp_path):
    store = SpecStore(tmp_path / "s.db")
    spec = _spec("sp-1", score=0.82)
    store.save_spec(spec)
    back = store.get_spec("sp-1")
    assert back == spec                                  # full-model equality via data JSON
    assert [s.id for s in store.list_specs()] == ["sp-1"]


def test_active_specs_filters_inactive(tmp_path):
    store = SpecStore(tmp_path / "s.db")
    store.save_spec(_spec("a", active=True))
    store.save_spec(_spec("b", active=False))
    ids = {s.id for s in store.active_specs("compare", "market")}
    assert ids == {"a"}                                  # inactive excluded from candidates
    store.deactivate("a")
    assert store.active_specs("compare", "market") == []


def test_pre_014_db_gains_table_additively(tmp_path):
    """A DB created before ADR-0004 (only a projects table, a real row) gains agent_specs on open
    with its existing rows intact — additive + idempotent, the ADR-0003 migration property."""
    path = tmp_path / "legacy.db"
    proj = Project(id="p1", name="Acme", created_at="2026-06-08T00:00:00Z")
    # Simulate a pre-014 schema: projects table only, NO agent_specs.
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, data TEXT, created_at TEXT)")
    conn.execute("INSERT INTO projects VALUES (?,?,?,?)",
                 ("p1", "Acme", proj.model_dump_json(), proj.created_at))
    conn.commit()
    conn.close()

    # Opening a SpecStore runs _ensure_schema → CREATE TABLE IF NOT EXISTS agent_specs.
    store = SpecStore(path)
    store.save_spec(_spec("sp-1"))
    assert store.get_spec("sp-1") is not None            # new table usable

    # The legacy project row survived the schema upgrade untouched.
    from sentinel.memory.store import ProjectStore
    assert ProjectStore(path).get_project("p1") == proj

    # Idempotent: re-opening doesn't drop the table or its row.
    assert SpecStore(path).get_spec("sp-1") is not None


# --------------------------------------------------------------------------- #
# validate_agent_spec — the AC-12 gate
# --------------------------------------------------------------------------- #


def test_reasoner_with_tool_is_rejected():
    bad = _spec("r-tool", role="synthesizer", tools=["search"])
    problems = spec_violations(bad)
    assert any("tool-free" in p for p in problems)
    with pytest.raises(SpecValidationError, match="tool-free"):
        validate_agent_spec(bad)


def test_off_allow_list_tool_is_rejected():
    bad = _spec("r-evil", role="planner", tools=["shell"])   # planner may hold tools, but not 'shell'
    problems = spec_violations(bad)
    assert any("off-allow-list" in p for p in problems)
    assert "shell" not in ALLOWED_TOOLS
    with pytest.raises(SpecValidationError):
        validate_agent_spec(bad)


def test_unknown_schema_ref_is_rejected():
    bad = _spec("r-noschema", schema_ref="NotARealSchema")
    with pytest.raises(SpecValidationError, match="output_schema_ref"):
        validate_agent_spec(bad)


def test_clean_spec_passes_validation():
    ok = _spec("r-ok")
    assert spec_violations(ok) == []
    validate_agent_spec(ok)                               # does not raise

    tool_caller = _spec("r-tc", role="public_research", tools=["search"], schema_ref="Battlecard")
    assert spec_violations(tool_caller) == []             # a tool-caller MAY hold an allow-list tool


# --------------------------------------------------------------------------- #
# resolve — reuse-by-score (AC-21)
# --------------------------------------------------------------------------- #


def test_resolve_reuses_best_scoring_active_spec(tmp_path):
    reg = AgentRegistry(SpecStore(tmp_path / "s.db"), seed=False)
    reg.register(_spec("low", score=0.6))
    reg.register(_spec("high", score=0.9))
    chosen = reg.resolve("compare", "market")
    assert chosen.id == "high"                            # highest eval_score wins
    # resolve is a read — it created no extra row beyond the two registered.
    assert len(reg.store.list_specs()) == 2


def test_resolve_falls_back_to_version_when_ungraded(tmp_path):
    reg = AgentRegistry(SpecStore(tmp_path / "s.db"), seed=False)
    reg.register(_spec("v1", score=None, version=1))
    reg.register(_spec("v2", score=None, version=2))
    assert reg.resolve("compare", "market").id == "v2"   # ungraded → newest version breaks the tie


def test_resolve_unknown_capability_returns_none(tmp_path):
    reg = AgentRegistry(SpecStore(tmp_path / "s.db"), seed=False)
    assert reg.resolve("no-such-cap", "market") is None  # a planner miss → Step 15 mints one


def test_registry_seeds_shipped_skills_idempotently(tmp_path):
    store = SpecStore(tmp_path / "s.db")
    reg = AgentRegistry(store)                            # seed=True
    assert reg.resolve("competitor", "market") is not None
    assert reg.resolve("self_profile", "market") is not None
    n = len(store.list_specs())
    assert n == len(seed_specs())                         # 4 shipped skills
    AgentRegistry(store)                                  # re-seed
    assert len(store.list_specs()) == n                   # deterministic ids ⇒ no duplicates


def test_seed_specs_all_validate():
    # the seed population must itself satisfy the AC-12 invariants (tool-free synthesizers, known schemas)
    for s in seed_specs():
        assert spec_violations(s) == []


# --------------------------------------------------------------------------- #
# build_from_spec — sovereign, tool-free under on_prem (AC-12)
# --------------------------------------------------------------------------- #


def test_build_from_spec_is_sovereign_and_toolfree(monkeypatch, tmp_path):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    reg = AgentRegistry(SpecStore(tmp_path / "s.db"), seed=False)
    spec = _spec("built", role="synthesizer", schema_ref="ComparisonMatrix")
    agent = reg.build_from_spec(spec, _tiered_cfg(), backend="vllm", cloud_allowed=False)

    assert not isinstance(agent.model, str)              # no Gemini model-id string under on_prem
    assert type(agent.model).__name__ == "LiteLlm"
    assert "26B" in agent.model.model                    # reasoner tier (gemma-4-26B)
    assert not getattr(agent, "tools", None)             # tool-free reasoner


def test_build_from_spec_rejects_invalid_before_building(monkeypatch, tmp_path):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    reg = AgentRegistry(SpecStore(tmp_path / "s.db"), seed=False)
    bad = _spec("bad", role="synthesizer", tools=["search"])  # reasoner + tool
    with pytest.raises(SpecValidationError):
        reg.build_from_spec(bad, _tiered_cfg(), backend="vllm", cloud_allowed=False)
