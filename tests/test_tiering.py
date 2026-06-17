"""Gemma-4 model tiering tests (SENTINEL-011 / ADR-0001).

Hermetic — no live LLM or network. ``LiteLlm`` is mocked to capture kwargs (AC-1); built agents are
introspected for the role→model map (AC-4/6), the zero-Gemini sovereignty guarantee (AC-5), and the
reasoner-tool-free guard (AC-7). The secret is asserted to be env-only — never in args or config.
"""

from __future__ import annotations

import google.adk.models.lite_llm as lite
import pytest

from sentinel.agent.modes._build import make_agent, resolve_model
from sentinel.config.defaults import build_default
from sentinel.config.schema import (
    REASONER_ROLES,
    TOOL_CALLER_ROLES,
    BackendOption,
    SentinelConfig,
)
from sentinel.llm import gateway


def _tiered_cfg() -> SentinelConfig:
    """Default config with a Gemma-4 role map turned on (12B tool-callers / 26B reasoners)."""
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "coordinator": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(
            model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"
        ),
        "private_research": BackendOption(
            model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"
        ),
        "extractor": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
        "strategist": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg

# Expected role per default agent key (SENTINEL-011): planners/researchers tool-call, synths reason.
_EXPECTED_ROLES = {
    "competitor.planner": "planner",
    "competitor.public_research": "public_research",
    "competitor.synthesizer": "synthesizer",
    "client.planner": "planner",
    "client.public_research": "public_research",
    "client.private_research": "private_research",
    "client.synthesizer": "synthesizer",
}


def _capture_litellm(monkeypatch) -> dict:
    """Patch LiteLlm to record the kwargs build_model hands it, without touching the network."""
    captured: dict = {}

    class FakeLiteLlm:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(lite, "LiteLlm", FakeLiteLlm)
    return captured


# --- AC-1: gateway auth by endpoint host ------------------------------------------------- #


def test_all_vllm_hosts_use_vllm_key(monkeypatch):
    """All vLLM endpoints — atcuality.com, omni, LAN — use the single VLLM_API_KEY."""
    captured = _capture_litellm(monkeypatch)
    monkeypatch.setenv("VLLM_API_KEY", "mk-unified-secret")

    gateway.build_model("vllm", "gemma-4-12B", "https://gemma.atcuality.com/v1")
    assert captured["api_key"] == "mk-unified-secret"

    gateway.build_model("vllm", "gemma-4-26B", "https://omni.atcuality.com/v1")
    assert captured["api_key"] == "mk-unified-secret"

    gateway.build_model("vllm", "google/gemma-3-4b-it", "http://localhost:8000/v1")
    assert captured["api_key"] == "mk-unified-secret"


def test_key_falls_back_to_not_needed_when_all_keys_unset(monkeypatch):
    # All three key env vars absent → "not-needed" (keyless dev server)
    captured = _capture_litellm(monkeypatch)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    monkeypatch.delenv("ATCUALITY_API_KEY", raising=False)
    monkeypatch.delenv("BILTIQ_LLM_KEY", raising=False)

    gateway.build_model("vllm", "gemma-4-12B", "https://gemma.atcuality.com/v1")
    assert captured["api_key"] == "not-needed"
    gateway.build_model("vllm", "local", "http://localhost:8000/v1")
    assert captured["api_key"] == "not-needed"


def test_atcuality_key_never_appears_in_model_args(monkeypatch):
    """The secret is read from env only — it is never the model id or the api_base."""
    captured = _capture_litellm(monkeypatch)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc-secret")

    gateway.build_model("vllm", "gemma-4-12B", "https://gemma.atcuality.com/v1")
    assert "atc-secret" not in captured["model"]
    assert "atc-secret" not in (captured["api_base"] or "")


# --- AC-2/3: Role + role map in schema/defaults ------------------------------------------ #


def test_default_config_has_no_role_map():
    """Tiering ships dark: the default config leaves backend.vllm.roles unset (no regression)."""
    cfg = build_default()
    assert cfg.backend.roles is None


def test_default_agents_have_correct_roles():
    """Each shipped agent carries the right capability tier; tool-callers and reasoners disjoint."""
    cfg = build_default()
    for key, expected in _EXPECTED_ROLES.items():
        assert cfg.agents[key].role == expected, key
    # every assigned role is classified into exactly one tier
    for key, expected in _EXPECTED_ROLES.items():
        in_caller = expected in TOOL_CALLER_ROLES
        in_reasoner = expected in REASONER_ROLES
        assert in_caller ^ in_reasoner, (key, expected)


def test_role_and_role_map_round_trip_through_yaml():
    """role + backend.vllm.roles survive a model_dump → model_validate round-trip (YAML-safe)."""
    cfg = build_default()
    from sentinel.config.schema import BackendOption

    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    restored = SentinelConfig.model_validate(cfg.model_dump())
    assert restored.backend.roles["planner"].model == "gemma-4-12B"
    assert restored.backend.roles["synthesizer"].api_base == "https://omni.atcuality.com/v1"
    assert restored.agents["competitor.planner"].role == "planner"


# --- AC-4/6: resolve_model picks the per-role vLLM option --------------------------------- #


def test_tool_caller_role_resolves_to_12b(monkeypatch):
    """A tool-caller role (planner) resolves to gemma-4-12B at the atcuality endpoint."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    model = resolve_model(cfg, cfg.agents["competitor.planner"], None, cloud_allowed=False)
    assert type(model).__name__ == "LiteLlm"
    assert model.model == "hosted_vllm/gemma-4-12B"


def test_reasoner_role_resolves_to_26b(monkeypatch):
    """A reasoner role (synthesizer) resolves to gemma-4-26B at the omni endpoint."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    model = resolve_model(cfg, cfg.agents["competitor.synthesizer"], None, cloud_allowed=False)
    assert model.model == "hosted_vllm/gemma-4-26B"


def test_unmapped_role_falls_back_to_flat_vllm(monkeypatch):
    """When a role is absent from the map, resolve_model uses the flat vllm option (no regression)."""
    monkeypatch.setenv("VLLM_API_KEY", "k")
    cfg = _tiered_cfg()
    del cfg.backend.roles["planner"]  # drop one mapping
    model = resolve_model(cfg, cfg.agents["competitor.planner"], None, cloud_allowed=False)
    assert model.model == "hosted_vllm/" + cfg.backend.vllm.model


def test_per_agent_model_override_still_wins(monkeypatch):
    """ac.model overrides the role map's model id (per-agent knob beats the tier default)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    cfg.agents["competitor.planner"].model = "gemma-4-12B-custom"
    model = resolve_model(cfg, cfg.agents["competitor.planner"], None, cloud_allowed=False)
    assert model.model == "hosted_vllm/gemma-4-12B-custom"


# --- AC-5: zero Gemini under tiering + on_prem ------------------------------------------- #


def test_tiering_never_builds_a_gemini_object(monkeypatch):
    """Even with the role map on, cloud_allowed=False yields a LiteLlm for every role (no Gemini)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    for key, ac in cfg.agents.items():
        model = resolve_model(cfg, ac, None, cloud_allowed=False)
        assert not isinstance(model, str), f"{key} got a Gemini model-id string"
        assert type(model).__name__ == "LiteLlm", key


# --- AC-7: reasoners are structurally tool-free ------------------------------------------ #


def test_make_agent_rejects_tools_on_reasoner_role(monkeypatch):
    """Building a reasoner-role agent with tools raises — the 26B is never given a toolset."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    with pytest.raises(ValueError, match="tool-free"):
        make_agent(
            cfg,
            "competitor.synthesizer",  # role=synthesizer (reasoner)
            name="synth",
            output_key="battlecard",
            tools=["dummy_tool"],
            cloud_allowed=False,
        )


def _model_id(agent) -> str:
    """The resolved on-prem model id of a built agent (strips the 'hosted_vllm/' prefix)."""
    return getattr(agent.model, "model", "").removeprefix("hosted_vllm/")


def test_full_competitor_pipeline_builds_under_tiering(monkeypatch):
    """Wiring check: the real competitor pipeline builds under tiering — tool-callers→12B,
    synthesizer→26B and tool-free — and carries NO MCP/private tool (boundary, AC-11 precursor)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    from sentinel.agent.modes.competitor import build_competitor_agent

    agent = build_competitor_agent(
        "vllm", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    by_name = {s.name: s for s in agent.sub_agents}
    assert _model_id(by_name["competitor_planner"]) == "gemma-4-12B"
    assert _model_id(by_name["competitor_public_research"]) == "gemma-4-12B"
    assert _model_id(by_name["battlecard_synthesizer"]) == "gemma-4-26B"
    # the reasoner carries no tools; no agent in a competitor run holds a private/MCP toolset
    assert not getattr(by_name["battlecard_synthesizer"], "tools", None)


def test_full_client_pipeline_builds_under_tiering(monkeypatch):
    """Wiring check: the client pipeline builds under tiering with the same tier split, and the
    synthesizer (26B) stays tool-free even while a tool-caller holds the search tool."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    from sentinel.agent.modes.client import build_client_agent

    agent = build_client_agent(
        "vllm", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    by_name = {s.name: s for s in agent.sub_agents}
    assert _model_id(by_name["account_planner"]) == "gemma-4-12B"
    assert _model_id(by_name["account_public_research"]) == "gemma-4-12B"
    assert _model_id(by_name["account_brief_synthesizer"]) == "gemma-4-26B"
    assert not getattr(by_name["account_brief_synthesizer"], "tools", None)


def test_make_agent_allows_tools_on_tool_caller_role(monkeypatch):
    """A tool-caller role may carry tools — the guard is reasoner-only."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()

    def dummy_tool() -> str:
        """A no-op function tool (ADK accepts plain callables)."""
        return "ok"

    agent = make_agent(
        cfg,
        "competitor.planner",  # role=planner (tool-caller)
        name="planner",
        output_key="research_plan",
        tools=[dummy_tool],
        cloud_allowed=False,
    )
    assert agent is not None


# --- structured output: vLLM schema-bound agents get response_format (server-gaps fix) ----- #


def test_structured_vllm_agent_gets_response_format(monkeypatch):
    """A schema-bound agent on vLLM is handed ``response_format=json_schema`` so the endpoint
    guided-decodes valid, terminating JSON — without it the gemma-4-26B reasoner free-generates and
    degenerates into a whitespace loop that truncates at max_output_tokens (verified live 2026-06-08)."""
    from sentinel.artifacts.schemas import Battlecard

    captured = _capture_litellm(monkeypatch)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    resolve_model(
        cfg, cfg.agents["competitor.synthesizer"], None,
        cloud_allowed=False, output_schema=Battlecard,
    )
    rf = captured.get("response_format")
    assert rf is not None, "schema-bound vLLM agent must carry a response_format"
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "Battlecard"
    assert rf["json_schema"]["schema"] == Battlecard.model_json_schema()


def test_unstructured_vllm_agent_has_no_response_format(monkeypatch):
    """A tool-caller with no ``output_schema`` gets NO response_format — byte-identical to before."""
    captured = _capture_litellm(monkeypatch)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    resolve_model(cfg, cfg.agents["competitor.planner"], None, cloud_allowed=False)
    assert "response_format" not in captured


def test_gemini_agent_never_gets_litellm_response_format(monkeypatch):
    """The Gemini path returns the model-id string and builds no LiteLlm — ADK sets Gemini's native
    response_schema from output_schema, so our vLLM-only response_format must not leak there."""
    from sentinel.artifacts.schemas import Battlecard

    captured = _capture_litellm(monkeypatch)
    cfg = _tiered_cfg()
    ac = cfg.agents["competitor.synthesizer"]
    ac.pin_gemini = True
    model = resolve_model(cfg, ac, None, cloud_allowed=True, output_schema=Battlecard)
    assert isinstance(model, str)            # a Gemini model-id, not a LiteLlm
    assert "response_format" not in captured  # no LiteLlm was constructed at all


# --- Gemini thinking-token floor (2026-06-11 thin-results bug) ---------------------------- #


def test_gemini_synthesizer_gets_thinking_token_floor(monkeypatch):
    """gemini-2.5-flash spends hidden *thinking* tokens from the same max_output_tokens budget, so
    the synthesizer's vLLM-tuned 3072 cap truncated its JSON mid-object → ValidationError → empty
    findings (live 2026-06-11). On a Gemini-resolved agent the cap is floored at 8192."""
    from sentinel.agent.modes._build import GEMINI_MIN_OUTPUT_TOKENS

    cfg = _tiered_cfg()
    assert cfg.agents["self_profile.synthesizer"].generation.max_output_tokens == 3072  # the trap
    agent = make_agent(
        cfg, "self_profile.synthesizer", name="synth", output_key="self_profile",
        mode_backend="gemini", cloud_allowed=True,
    )
    assert agent.generate_content_config.max_output_tokens == GEMINI_MIN_OUTPUT_TOKENS


def test_vllm_synthesizer_cap_is_untouched(monkeypatch):
    """The floor is Gemini-only: the vLLM path has no thinking budget (and the 26B synthesizes in
    chunks), so its configured cap must stay byte-identical."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    agent = make_agent(
        cfg, "self_profile.synthesizer", name="synth", output_key="self_profile",
        mode_backend="vllm", cloud_allowed=True,
    )
    assert agent.generate_content_config.max_output_tokens == 3072


def test_sovereign_run_never_inflates_the_cap(monkeypatch):
    """cloud_allowed=False forces vLLM even on a pin_gemini agent — the resolved backend (not the
    requested one) decides, so a sovereign run keeps its configured cap."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    cfg.agents["self_profile.synthesizer"].pin_gemini = True
    agent = make_agent(
        cfg, "self_profile.synthesizer", name="synth", output_key="self_profile",
        mode_backend="gemini", cloud_allowed=False,
    )
    assert agent.generate_content_config.max_output_tokens == 3072


def test_generous_gemini_cap_is_not_lowered():
    """An agent already configured above the floor keeps its own (larger) budget — the floor only
    raises, never clamps."""
    from sentinel.agent.modes._build import GEMINI_MIN_OUTPUT_TOKENS
    cfg = _tiered_cfg()
    above_floor = GEMINI_MIN_OUTPUT_TOKENS * 2  # clearly above floor → must not be clamped
    cfg.agents["self_profile.synthesizer"].generation.max_output_tokens = above_floor
    agent = make_agent(
        cfg, "self_profile.synthesizer", name="synth", output_key="self_profile",
        mode_backend="gemini", cloud_allowed=True,
    )
    assert agent.generate_content_config.max_output_tokens == above_floor
