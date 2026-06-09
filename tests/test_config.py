"""SENTINEL-001 — Configurable Agent Runtime tests (AC-1..AC-9)."""

from __future__ import annotations

import pytest

from sentinel.agent.modes.client import build_client_agent
from sentinel.agent.modes.competitor import build_competitor_agent
from sentinel.config import SentinelConfig, load_config, save_config
from sentinel.config.render import render_prompt
from sentinel.config.schema import GenerationConfig, PromptTemplate


# --- AC-1: defaults reproduce the shipped behaviour (golden) ----------------------------- #
def test_default_competitor_agents_match_config():
    cfg = SentinelConfig.default()
    agent = build_competitor_agent(config=cfg)
    by_step = {
        "competitor_planner": "competitor.planner",
        "competitor_public_research": "competitor.public_research",
        "battlecard_synthesizer": "competitor.synthesizer",
    }
    for sub in agent.sub_agents:
        key = by_step[sub.name]
        assert sub.instruction == cfg.prompts[key].template
        assert sub.model == "gemini-2.5-flash"  # all default to the gemini flash model


def test_default_client_synth_substitutes_absent_note():
    # With no MCP connector, the synthesizer's {private_note} = the "absent" note (no regression).
    cfg = SentinelConfig.default()
    agent = build_client_agent(config=cfg)
    synth = next(s for s in agent.sub_agents if s.name == "account_brief_synthesizer")
    expected = cfg.prompts["client.synthesizer"].template.replace(
        "{private_note}", cfg.prompts["client.private_note_absent"].template
    )
    assert synth.instruction == expected
    assert "{private_note}" not in synth.instruction


# --- AC-2 / AC-3: persistence -------------------------------------------------------------- #
def test_config_yaml_roundtrips(tmp_path):
    cfg = SentinelConfig.default()
    p = save_config(cfg, tmp_path / "c.yaml")
    assert p.exists()
    loaded = load_config(p)
    assert loaded == cfg


def test_absent_file_self_seeds(tmp_path):
    p = tmp_path / "seed.yaml"
    assert not p.exists()
    cfg = load_config(p, write_if_absent=True)
    assert p.exists()  # seeded once
    assert cfg == SentinelConfig.default()


# --- AC-4 / AC-5: per-agent model + generation resolution --------------------------------- #
def test_per_agent_model_and_generation_override():
    cfg = SentinelConfig.default()
    cfg.agents["competitor.synthesizer"].model = "gemini-2.5-pro"
    cfg.agents["competitor.synthesizer"].generation = GenerationConfig(temperature=0.9)
    agent = build_competitor_agent(config=cfg)
    synth = next(s for s in agent.sub_agents if s.name == "battlecard_synthesizer")
    assert synth.model == "gemini-2.5-pro"
    gen = synth.generate_content_config
    assert gen.temperature == 0.9                 # per-agent override wins
    assert gen.max_output_tokens == 2048          # inherited from global (override left it None)
    assert gen.top_p == 0.95                       # inherited from global


def test_planner_generation_defaults_applied():
    cfg = SentinelConfig.default()
    agent = build_competitor_agent(config=cfg)
    planner = next(s for s in agent.sub_agents if s.name == "competitor_planner")
    assert planner.generate_content_config.temperature == 0.2
    assert planner.generate_content_config.max_output_tokens == 1024


# --- AC-6: prompt variable validation ------------------------------------------------------ #
def test_render_prompt_rejects_missing_required_var():
    with pytest.raises(ValueError, match="missing required"):
        render_prompt(PromptTemplate(template="No vars here", variables=["target"]))


def test_render_prompt_rejects_unknown_var():
    with pytest.raises(ValueError, match="unknown variable"):
        render_prompt(PromptTemplate(template="Hello {mystery}", variables=[]))


def test_render_prompt_accepts_reserved_var():
    out = render_prompt(PromptTemplate(template="For {target} now", variables=[]))
    assert out == "For {target} now"  # returned unchanged; ADK injects at run time


# --- AC-9: per-run backend override beats config default ----------------------------------- #
def test_per_run_backend_override_beats_config_default():
    cfg = SentinelConfig.default()  # default backend = gemini
    agent = build_competitor_agent(backend="vllm", config=cfg)
    planner = next(s for s in agent.sub_agents if s.name == "competitor_planner")
    public = next(s for s in agent.sub_agents if s.name == "competitor_public_research")
    # non-pinned reasoning agent moves to vLLM (LiteLlm object, not a string id)
    assert not isinstance(planner.model, str)
    assert type(planner.model).__name__ == "LiteLlm"
    # grounding stays on Gemini regardless
    assert public.model == cfg.backend.gemini.model
