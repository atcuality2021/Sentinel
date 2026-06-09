"""SENTINEL-003 — Settings UI tests (AC-1..AC-10).

Two layers: pure helpers (`web/settings.py`) and routes (`web/app.py` via TestClient with a
tmp config path). No live LLM. Routes use an isolated `SENTINEL_CONFIG_PATH` + `reset_config`
per test so a save writes a throwaway YAML, never the repo's `sentinel.config.yaml`.
"""

from __future__ import annotations

import pytest

from sentinel.config import SentinelConfig
from sentinel.config.schema import GenerationConfig
from sentinel.web import settings as S


# --------------------------------------------------------------------------- #
# Step 1 — pure helpers
# --------------------------------------------------------------------------- #
def _cfg() -> SentinelConfig:
    return SentinelConfig.default()


# parse_generation -----------------------------------------------------------
def test_parse_generation_good_values():
    gen = S.parse_generation(
        {"temperature": "0.5", "max_output_tokens": "1500", "top_p": "0.9", "top_k": "30"},
        allow_blank=False,
    )
    assert gen == GenerationConfig(temperature=0.5, max_output_tokens=1500, top_p=0.9, top_k=30)


def test_parse_generation_blank_inherits_when_allowed():
    gen = S.parse_generation(
        {"temperature": "0.5", "max_output_tokens": "", "top_p": "", "top_k": ""},
        allow_blank=True,
    )
    assert gen.temperature == 0.5
    assert gen.max_output_tokens is None and gen.top_p is None and gen.top_k is None


def test_parse_generation_blank_rejected_when_required():
    with pytest.raises(ValueError, match="required"):
        S.parse_generation(
            {"temperature": "", "max_output_tokens": "2048", "top_p": "0.9", "top_k": "40"},
            allow_blank=False,
        )


@pytest.mark.parametrize(
    "form",
    [
        {"temperature": "3.0", "max_output_tokens": "2048", "top_p": "0.9", "top_k": "40"},
        {"temperature": "0.5", "max_output_tokens": "0", "top_p": "0.9", "top_k": "40"},
        {"temperature": "0.5", "max_output_tokens": "2048", "top_p": "1.5", "top_k": "40"},
        {"temperature": "0.5", "max_output_tokens": "2048", "top_p": "0.9", "top_k": "0"},
    ],
)
def test_parse_generation_out_of_range_rejected(form):
    with pytest.raises(ValueError):
        S.parse_generation(form, allow_blank=False)


def test_parse_generation_non_numeric_rejected():
    with pytest.raises(ValueError, match="number"):
        S.parse_generation(
            {"temperature": "warm", "max_output_tokens": "2048", "top_p": "0.9", "top_k": "40"},
            allow_blank=False,
        )


# apply_backends -------------------------------------------------------------
def test_apply_backends_updates_copy():
    cfg = _cfg()
    new = S.apply_backends(
        cfg, default="vllm", gemini_model="gemini-2.5-pro",
        vllm_model="meta/llama", vllm_api_base="http://gpu:8000/v1",
    )
    assert new.backend.default == "vllm"
    assert new.backend.gemini.model == "gemini-2.5-pro"
    assert new.backend.vllm.model == "meta/llama"
    assert cfg.backend.default == "gemini"  # original untouched (deep copy)


def test_apply_backends_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Backend must be one of"):
        S.apply_backends(_cfg(), default="azure", gemini_model="g", vllm_model="v",
                         vllm_api_base="http://x/v1")


# apply_agent ----------------------------------------------------------------
def test_apply_agent_updates_known_key():
    cfg = _cfg()
    gen = GenerationConfig(temperature=0.9)
    new = S.apply_agent(cfg, "competitor.synthesizer", enabled=False,
                        model="gemini-2.5-pro", pin_gemini=True, gen=gen)
    a = new.agents["competitor.synthesizer"]
    assert a.enabled is False and a.model == "gemini-2.5-pro" and a.pin_gemini is True
    assert a.generation.temperature == 0.9


def test_apply_agent_blank_model_inherits():
    new = S.apply_agent(_cfg(), "competitor.planner", enabled=True, model="  ",
                        pin_gemini=False, gen=GenerationConfig())
    assert new.agents["competitor.planner"].model is None


def test_apply_agent_unknown_key_raises():
    with pytest.raises(ValueError, match="Unknown agent"):
        S.apply_agent(_cfg(), "nope.nope", enabled=True, model=None,
                      pin_gemini=False, gen=GenerationConfig())


# apply_prompt / reset_prompt ------------------------------------------------
def test_apply_prompt_valid_saves_and_keeps_default():
    cfg = _cfg()
    key = "competitor.synthesizer"
    original_default = cfg.prompts[key].default_template
    edited = "Edited battlecard for {target} from {public_findings}. Be sharp."
    new = S.apply_prompt(cfg, key, edited)
    assert new.prompts[key].template == edited
    assert new.prompts[key].default_template == original_default  # reset still possible (AC-6)


def test_apply_prompt_missing_required_var_rejected():
    cfg = _cfg()
    key = "competitor.synthesizer"  # requires {target} and {public_findings}
    with pytest.raises(ValueError):
        S.apply_prompt(cfg, key, "No variables at all.")
    # original unchanged (helper returns a copy; we never committed)
    assert "{public_findings}" in cfg.prompts[key].template


def test_apply_prompt_unknown_var_rejected():
    with pytest.raises(ValueError):
        S.apply_prompt(_cfg(), "competitor.planner", "Plan using {mystery}.")


def test_reset_prompt_restores_default():
    cfg = _cfg()
    key = "competitor.synthesizer"
    default = cfg.prompts[key].default_template
    edited = S.apply_prompt(cfg, key, "Edited {target} {public_findings}.")
    assert edited.prompts[key].template != default
    restored = S.reset_prompt(edited, key)
    assert restored.prompts[key].template == default


# apply_memory ---------------------------------------------------------------
def test_apply_memory_updates():
    new = S.apply_memory(_cfg(), entity_memory=False, retention_days=90, inject_org_prefs=False)
    assert new.memory.entity_memory is False
    assert new.memory.retention_days == 90
    assert new.memory.inject_org_prefs is False


def test_apply_memory_rejects_bad_retention():
    with pytest.raises(ValueError):
        S.apply_memory(_cfg(), entity_memory=True, retention_days="zero", inject_org_prefs=True)


# --------------------------------------------------------------------------- #
# Steps 3-6 — routes (TestClient + isolated config path)
# --------------------------------------------------------------------------- #
from fastapi.testclient import TestClient  # noqa: E402

from sentinel.agent.modes.competitor import build_competitor_agent  # noqa: E402
from sentinel.config import config_path, load_config, reset_config  # noqa: E402
from sentinel.web import app as web_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    # Isolate config + data so a save writes a throwaway YAML, never the repo's config.
    monkeypatch.setenv("SENTINEL_CONFIG_PATH", str(tmp_path / "cfg.yaml"))
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    reset_config()
    yield TestClient(web_app.app)
    reset_config()


def _stored():
    """Read the persisted config fresh from disk (post-reset)."""
    reset_config()
    return load_config(config_path())


# AC-1 / NFR-1 ---------------------------------------------------------------
def test_get_settings_renders_all_sections(client):
    r = client.get("/settings")
    assert r.status_code == 200
    body = r.text
    assert "Settings" in body
    assert "Backends" in body and "Generation defaults" in body
    assert "Memory" in body and "Agents — competitor" in body and "Prompts" in body
    # a known prompt + agent key surfaced
    assert "competitor.synthesizer" in body
    # backend default reflected (radio checked)
    assert "id='sb-gemini' name='default' value='gemini' checked" in body


def test_get_settings_never_shows_secret(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "super-secret-value-123")
    reset_config()
    r = client.get("/settings")
    assert "super-secret-value-123" not in r.text
    assert "GOOGLE_API_KEY:" in r.text and "set" in r.text  # boolean pill only


# AC-2 -----------------------------------------------------------------------
def test_post_backends_persists(client):
    r = client.post("/settings/backends", data={
        "default": "vllm", "gemini_model": "gemini-2.5-pro",
        "vllm_model": "meta/llama-3", "vllm_api_base": "http://gpu:8000/v1",
    })
    assert r.status_code == 200 and "saved" in r.text.lower()
    cfg = _stored()
    assert cfg.backend.default == "vllm"
    assert cfg.backend.gemini.model == "gemini-2.5-pro"
    assert cfg.backend.vllm.model == "meta/llama-3"


# AC-3 -----------------------------------------------------------------------
def test_post_generation_valid_persists(client):
    r = client.post("/settings/generation", data={
        "temperature": "0.7", "max_output_tokens": "1234", "top_p": "0.8", "top_k": "20"})
    assert "saved" in r.text.lower()
    cfg = _stored()
    assert cfg.generation.temperature == 0.7 and cfg.generation.max_output_tokens == 1234


def test_post_generation_out_of_range_leaves_config_unchanged(client):
    before = _stored().generation
    r = client.post("/settings/generation", data={
        "temperature": "9.9", "max_output_tokens": "1234", "top_p": "0.8", "top_k": "20"})
    assert r.status_code == 200
    assert "between 0.0 and 2.0" in r.text  # error banner
    assert _stored().generation == before  # YAML unchanged (NFR-2)


# AC-4 -----------------------------------------------------------------------
def test_post_agent_updates(client):
    r = client.post("/settings/agents/competitor.synthesizer", data={
        "enabled": "1", "model": "gemini-2.5-pro", "pin_gemini": "1",
        "temperature": "0.9", "max_output_tokens": "", "top_p": "", "top_k": ""})
    assert "saved" in r.text.lower()
    a = _stored().agents["competitor.synthesizer"]
    assert a.model == "gemini-2.5-pro" and a.pin_gemini is True
    assert a.generation.temperature == 0.9
    assert a.generation.max_output_tokens is None  # blank ⇒ inherit


def test_post_agent_unknown_key_errors_no_crash(client):
    r = client.post("/settings/agents/does.not.exist", data={
        "enabled": "1", "model": "", "pin_gemini": "",
        "temperature": "", "max_output_tokens": "", "top_p": "", "top_k": ""})
    assert r.status_code == 200
    assert "Unknown agent" in r.text


def test_post_agent_unchecked_box_disables(client):
    # enabled box omitted ⇒ disabled
    client.post("/settings/agents/competitor.planner", data={
        "model": "", "temperature": "", "max_output_tokens": "", "top_p": "", "top_k": ""})
    assert _stored().agents["competitor.planner"].enabled is False


# AC-5 / AC-6 ----------------------------------------------------------------
def test_post_prompt_invalid_rejected_unchanged(client):
    key = "competitor.synthesizer"
    before = _stored().prompts[key].template
    r = client.post(f"/settings/prompts/{key}", data={"template": "No required vars here."})
    assert r.status_code == 200
    assert "missing required" in r.text.lower() or "must appear" in r.text.lower()
    assert _stored().prompts[key].template == before


def test_post_prompt_valid_saves_keeps_default(client):
    key = "competitor.synthesizer"
    default = _stored().prompts[key].default_template
    edited = "Edited card for {target} from {public_findings}."
    r = client.post(f"/settings/prompts/{key}", data={"template": edited})
    assert "saved" in r.text.lower()
    cfg = _stored()
    assert cfg.prompts[key].template == edited
    assert cfg.prompts[key].default_template == default  # AC-6


# AC-7 -----------------------------------------------------------------------
def test_post_prompt_reset_restores_default(client):
    key = "competitor.synthesizer"
    default = _stored().prompts[key].default_template
    client.post(f"/settings/prompts/{key}", data={
        "template": "Edited {target} {public_findings}."})
    r = client.post(f"/settings/prompts/{key}/reset")
    assert "reset" in r.text.lower()
    assert _stored().prompts[key].template == default


# AC-8 -----------------------------------------------------------------------
def test_post_memory_updates(client):
    r = client.post("/settings/memory", data={"retention_days": "90"})  # both boxes unchecked
    assert "saved" in r.text.lower()
    cfg = _stored()
    assert cfg.memory.retention_days == 90
    assert cfg.memory.entity_memory is False and cfg.memory.inject_org_prefs is False


# AC-9 — a saved prompt edit is reflected in the next agent build (no restart) ---
def test_prompt_edit_reflected_in_agent_build(client):
    key = "competitor.synthesizer"
    edited = "NEWLY EDITED synthesizer for {target} using {public_findings}."
    client.post(f"/settings/prompts/{key}", data={"template": edited})
    # build with no explicit config ⇒ reads the live (cache-updated) config
    agent = build_competitor_agent(memory_context="")
    synth = next(s for s in agent.sub_agents if s.name == "battlecard_synthesizer")
    assert "NEWLY EDITED" in synth.instruction


# AC-10 — no secret ever written to the YAML file -------------------------------
def test_no_secret_written_to_yaml(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "leak-me-if-you-can")
    reset_config()
    client.post("/settings/backends", data={
        "default": "gemini", "gemini_model": "gemini-2.5-flash",
        "vllm_model": "google/gemma-3-4b-it", "vllm_api_base": "http://localhost:8000/v1"})
    text = config_path().read_text("utf-8")
    assert "leak-me-if-you-can" not in text
    assert "GOOGLE_API_KEY" not in text


# --------------------------------------------------------------------------- #
# Unified config — "one center, no override": the displayed/active default is the
# config store, never env. Locks the SENTINEL-003 R-2 split-brain shut.
# --------------------------------------------------------------------------- #
def test_active_default_comes_from_config_not_env(client, monkeypatch):
    # env disagrees with the saved config on purpose...
    monkeypatch.setenv("SENTINEL_LLM_BACKEND", "gemini")
    reset_config()
    client.post("/settings/backends", data={
        "default": "vllm", "gemini_model": "gemini-2.5-flash",
        "vllm_model": "gemma-4-12B", "vllm_api_base": "https://gemma.atcuality.com/v1"})

    # ...the UI must reflect the CONFIG (vllm), not the env (gemini)
    s = client.get("/settings").text
    assert "name='default' value='vllm'" in s and "value='vllm' checked" in s
    assert "Backend: <b>vllm</b>" in s            # topbar pill = config default
    assert "Backend: <b>gemini</b>" not in s
    # and the same value drives every other page's shell
    assert "Backend: <b>vllm</b>" in client.get("/accounts").text


def test_vllm_key_pill_is_honest_about_placeholder(client, monkeypatch):
    monkeypatch.setenv("VLLM_API_KEY", "not-needed")  # the unauthenticated placeholder
    reset_config()
    assert "VLLM_API_KEY: <b>not set</b>" in client.get("/settings").text
    monkeypatch.setenv("VLLM_API_KEY", "dummy-present-value")
    assert "VLLM_API_KEY: <b>set</b>" in client.get("/settings").text


def test_settings_states_the_one_rule(client):
    # the page must teach the single source of truth, not the old env-driven story
    s = client.get("/settings").text
    assert "One source of truth" in s
    assert "no env override" in s


# --------------------------------------------------------------------------- #
# SENTINEL-011 — Models (role tiering) + Coordinator sections (AC-13)
# --------------------------------------------------------------------------- #
# apply_models (pure helper) -------------------------------------------------
def test_apply_models_builds_role_map():
    new = S.apply_models(_cfg(), {
        "planner": {"model": "gemma-4-12B", "api_base": "https://gemma.atcuality.com/v1"},
        "synthesizer": {"model": "gemma-4-26B", "api_base": "https://omni.atcuality.com/v1"},
    })
    assert new.backend.roles["planner"].model == "gemma-4-12B"
    assert new.backend.roles["synthesizer"].api_base == "https://omni.atcuality.com/v1"


def test_apply_models_blank_model_unmapped_and_empty_is_none():
    # a blank model drops that role; if nothing maps, roles is None (tiering off, no regression)
    new = S.apply_models(_cfg(), {"planner": {"model": "  ", "api_base": "x"}})
    assert new.backend.roles is None


def test_apply_models_rejects_unknown_role():
    with pytest.raises(ValueError, match="Unknown role"):
        S.apply_models(_cfg(), {"wizard": {"model": "gemma-4-12B"}})


# apply_coordinator (pure helper) --------------------------------------------
def test_apply_coordinator_toggles_enabled():
    new = S.apply_coordinator(_cfg(), enabled=True)
    assert new.coordinator.enabled is True
    assert new.coordinator.remote_private is False  # Phase 2 stays gated


def test_apply_agent_preserves_role():
    # editing an agent's knobs must NOT reset its capability tier (SENTINEL-011)
    new = S.apply_agent(_cfg(), "competitor.public_research", enabled=True, model=None,
                        pin_gemini=True, gen=GenerationConfig())
    assert new.agents["competitor.public_research"].role == "public_research"


# routes ---------------------------------------------------------------------
def test_post_models_persists_and_no_secret(client, monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "super-secret-atc-key")
    r = client.post("/settings/models", data={
        "model__planner": "gemma-4-12B", "api_base__planner": "https://gemma.atcuality.com/v1",
        "model__synthesizer": "gemma-4-26B", "api_base__synthesizer": "https://omni.atcuality.com/v1",
    })
    assert r.status_code == 200 and "saved" in r.text.lower()
    assert "super-secret-atc-key" not in r.text  # key never rendered (NFR-1)
    cfg = _stored()
    assert cfg.backend.roles["planner"].model == "gemma-4-12B"
    assert cfg.backend.roles["synthesizer"].model == "gemma-4-26B"
    # secret never persisted to YAML
    assert "super-secret-atc-key" not in config_path().read_text()


def test_post_models_bad_role_errors_no_crash(client):
    r = client.post("/settings/models", data={"model__wizard": "x"})
    assert r.status_code == 200
    assert "Unknown role" in r.text


def test_post_coordinator_persists(client):
    r = client.post("/settings/coordinator", data={"enabled": "on"})
    assert r.status_code == 200 and "saved" in r.text.lower()
    assert _stored().coordinator.enabled is True
    # unchecked box disables
    client.post("/settings/coordinator", data={})
    assert _stored().coordinator.enabled is False


def test_settings_renders_models_and_coordinator_sections(client, monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "x")
    reset_config()
    s = client.get("/settings").text
    assert "Gemma-4 role tiering" in s and "Coordinator" in s
    assert "ATCUALITY_API_KEY:" in s            # boolean pill
    assert "Phase 2" in s                        # remote-private gated control labelled
