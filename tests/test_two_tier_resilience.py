"""SENTINEL-008.1 — two-tier hardening (fail-soft degrade + config back-fill).

The e2e (docs/specs/SENTINEL-008/findings-e2e.md) showed that any extractor failure — JSON
truncation, 16K-context overflow, a transient 5xx — aborted the whole run. Two-tier is a pure
enhancement, so it must degrade to single-tier instead. These tests are hermetic: the pipeline
execution is stubbed; we assert the *orchestration* (one retry, the trace note, no double-merge).
"""

from __future__ import annotations

from sentinel.agent import orchestrator as orch
from sentinel.artifacts.schemas import Battlecard
from sentinel.artifacts.writer import ArtifactWriter, WriteResult
from sentinel.config.defaults import build_default


class _StubWriter(ArtifactWriter):
    def write(self, artifact) -> WriteResult:          # no filesystem residue
        return WriteResult(backend="stub", reference="mem://artifact")


def _two_tier_cfg():
    cfg = build_default()                              # has the *.extractor keys (post-008)
    cfg.research.two_tier = True
    return cfg


# --------------------------------------------------------------------------- #
# F3 — graceful degrade: a failing two-tier run retries once as single-tier.
# --------------------------------------------------------------------------- #
def test_two_tier_failure_falls_back_to_single_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))
    art = Battlecard(target="Acme", one_line_summary="x", positioning="y")
    seen: list[bool] = []

    async def fake_exec(target, mode, *, cfg, **kw):
        seen.append(cfg.research.two_tier)
        if cfg.research.two_tier:                       # the two-tier attempt blows up...
            raise RuntimeError("ContextWindowExceededError (simulated)")
        return art, {}                                 # ...the single-tier retry succeeds

    monkeypatch.setattr(orch, "_execute_pipeline", fake_exec)
    result = orch.run("Acme", "competitor", config=_two_tier_cfg(), writer=_StubWriter())

    assert seen == [True, False]                        # tried two-tier, then single-tier (one retry)
    assert result.artifact is art
    assert any("fell back to single-tier" in line for line in result.trace)
    assert any("ContextWindowExceededError" in line for line in result.trace)


def test_two_tier_success_does_not_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))
    art = Battlecard(target="Acme", one_line_summary="x", positioning="y")
    calls = 0

    async def fake_exec(target, mode, *, cfg, **kw):
        nonlocal calls
        calls += 1
        return art, {}

    monkeypatch.setattr(orch, "_execute_pipeline", fake_exec)
    result = orch.run("Acme", "competitor", config=_two_tier_cfg(), writer=_StubWriter())

    assert calls == 1                                   # no fallback when two-tier succeeds
    assert not any("fell back" in line for line in result.trace)


def test_single_tier_failure_propagates(tmp_path, monkeypatch):
    """A single-tier run has nothing to fall back to — the error must propagate, not be swallowed."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))

    async def boom(target, mode, *, cfg, **kw):
        raise RuntimeError("planner died")

    monkeypatch.setattr(orch, "_execute_pipeline", boom)
    cfg = build_default()                               # two_tier is False (default)
    try:
        orch.run("Acme", "competitor", config=cfg, writer=_StubWriter())
    except RuntimeError as exc:
        assert "planner died" in str(exc)
    else:
        raise AssertionError("single-tier failure should propagate, not fall back")


# --------------------------------------------------------------------------- #
# F5 — config back-fill: a pre-008 config gains the new agent/prompt keys on load.
# --------------------------------------------------------------------------- #
def test_load_config_backfills_missing_agent_and_prompt_keys(tmp_path):
    from sentinel.config.store import load_config, save_config

    legacy = build_default()                            # start from a full config...
    for key in ("competitor.extractor", "client.extractor"):   # ...strip the post-008 keys
        legacy.agents.pop(key, None)
        legacy.prompts.pop(key, None)
    path = tmp_path / "legacy.yaml"
    save_config(legacy, path)

    loaded = load_config(path)                           # load runs the back-fill
    for key in ("competitor.extractor", "client.extractor"):
        assert key in loaded.agents                      # agent restored from shipped defaults
        assert key in loaded.prompts                     # prompt restored too


def test_backfill_never_overwrites_an_admin_edit(tmp_path):
    from sentinel.config.store import load_config, save_config

    cfg = build_default()
    cfg.prompts["competitor.planner"].template = "EDITED — admin override {target}"
    path = tmp_path / "edited.yaml"
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.prompts["competitor.planner"].template.startswith("EDITED")   # setdefault, not overwrite
