"""Strategy & action-plan tests (SENTINEL-009).

Hermetic — no live LLM/network. Strategist output is faked by seeding session state or hand-building
a StrategyOverlay; agents are introspected. Covers schemas (AC-1/2), the playbook loader (AC-6/9),
config (AC-2), builder wiring + tool-free/sovereignty (AC-3/4/5/7/8/11), the deterministic merge
(AC-10), render (AC-13), and Settings (AC-14).
"""

from __future__ import annotations

from sentinel.artifacts.schemas import (
    AccountBrief,
    Battlecard,
    Objection,
    RecommendedAction,
    StrategyOverlay,
)


# --- AC-1/2: schemas ---------------------------------------------------------------------- #


def test_strategy_schemas_construct():
    overlay = StrategyOverlay(
        assessment="Stalled deal, strong public momentum — re-engage on expansion.",
        action_plan=[
            RecommendedAction(
                action="Book an exec sync", priority="high", timeline="this week",
                rationale="Hiring surge (public) + stalled stage (private) imply budget is moving.",
            )
        ],
        objection_handling=[Objection(objection="Too expensive", reframe="ROI from the merged insight.")],
    )
    assert overlay.action_plan[0].priority == "high"
    assert overlay.objection_handling[0].objection == "Too expensive"


def test_battlecard_strategy_fields_default_empty():
    bc = Battlecard(
        target="Acme", one_line_summary="x", positioning="y",
    )
    assert bc.assessment is None
    assert bc.action_plan == []
    assert not hasattr(bc, "objection_handling")  # competitor mode has no objection handling


def test_accountbrief_strategy_fields_default_empty():
    ab = AccountBrief(account="Acme", one_line_summary="x")
    assert ab.assessment is None
    assert ab.action_plan == []
    assert ab.objection_handling == []


def test_schema_for_mode_unchanged():
    from sentinel.artifacts.schemas import SCHEMA_FOR_MODE

    assert SCHEMA_FOR_MODE == {"competitor": Battlecard, "client": AccountBrief}


# --- AC-6/9: playbook loader -------------------------------------------------------------- #

from pathlib import Path  # noqa: E402

from sentinel.strategy import discover_playbooks, load_playbook  # noqa: E402

_PLAYBOOK_DIR = Path(__file__).resolve().parent.parent / "playbooks"


def test_shipped_playbooks_load():
    client_pb = load_playbook(_PLAYBOOK_DIR / "account-strategy.md")
    comp_pb = load_playbook(_PLAYBOOK_DIR / "competitor-counterplay.md")
    assert client_pb is not None and client_pb.mode == "client" and client_pb.body.strip()
    assert comp_pb is not None and comp_pb.mode == "competitor" and comp_pb.body.strip()
    # AC-12 house rule is present in the shipped client playbook (no raw private restatement)
    assert "PRIVATE" in client_pb.body and "merged insight" in client_pb.body


def test_load_playbook_malformed_returns_none(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("no frontmatter here, just text", encoding="utf-8")
    assert load_playbook(bad) is None
    # bad YAML in the fence → None, no raise
    badyaml = tmp_path / "badyaml.md"
    badyaml.write_text("---\nmode: : : oops\n---\nbody", encoding="utf-8")
    assert load_playbook(badyaml) is None
    # missing file → None
    assert load_playbook(tmp_path / "nope.md") is None
    # wrong mode value → None (validation)
    wrong = tmp_path / "wrong.md"
    wrong.write_text("---\nname: x\nmode: wizard\n---\nbody", encoding="utf-8")
    assert load_playbook(wrong) is None


def test_discover_playbooks_lists_only_valid(tmp_path):
    (tmp_path / "good.md").write_text(
        "---\nname: good\nmode: client\n---\nframework", encoding="utf-8"
    )
    (tmp_path / "broken.md").write_text("no frontmatter", encoding="utf-8")
    found = discover_playbooks(tmp_path)
    assert [p.name for p in found] == ["good"]
    # non-existent dir → empty, no raise
    assert discover_playbooks(tmp_path / "missing") == []


# --- AC-2: config (StrategyConfig + agents + prompts + reserved vars) --------------------- #

from sentinel.config.defaults import build_default  # noqa: E402
from sentinel.config.render import RESERVED_VARS, render_prompt  # noqa: E402
from sentinel.config.schema import SentinelConfig  # noqa: E402


def test_strategy_disabled_by_default_and_round_trips():
    cfg = build_default()
    assert cfg.strategy.enabled is False
    assert cfg.strategy.client_playbook == "account-strategy"
    cfg.strategy.enabled = True
    restored = SentinelConfig.model_validate(cfg.model_dump())
    assert restored.strategy.enabled is True


def test_strategist_agents_and_prompts_present():
    cfg = build_default()
    for key in ("competitor.strategist", "client.strategist"):
        assert cfg.agents[key].role == "strategist"
        assert cfg.agents[key].pin_gemini is False  # strategy never forces cloud
        assert key in cfg.prompts
    # prompts read the artifact state keys, which are now reserved
    assert "{battlecard}" in cfg.prompts["competitor.strategist"].template
    assert "{account_brief}" in cfg.prompts["client.strategist"].template
    assert "battlecard" in RESERVED_VARS and "account_brief" in RESERVED_VARS
    # the new prompts validate cleanly
    render_prompt(cfg.prompts["competitor.strategist"])
    render_prompt(cfg.prompts["client.strategist"])


# --- AC-3/4/5/7/8: builder wiring --------------------------------------------------------- #

from sentinel.agent.modes.client import build_client_agent  # noqa: E402
from sentinel.agent.modes.competitor import build_competitor_agent  # noqa: E402
from sentinel.artifacts.schemas import StrategyOverlay as _Overlay  # noqa: E402


def _enabled_cfg(playbook_dir=None):
    cfg = build_default()
    cfg.strategy.enabled = True
    if playbook_dir is not None:
        cfg.strategy.playbook_dir = str(playbook_dir)
    return cfg


def test_strategy_off_has_no_strategist():
    """AC-3: disabled ⇒ pipeline ends at the synthesizer, no strategist (byte-identical topology)."""
    agent = build_competitor_agent(config=build_default())  # strategy off
    names = [s.name for s in agent.sub_agents]
    assert "competitor_strategist" not in names
    assert names[-1] == "battlecard_synthesizer"


def test_strategy_on_appends_tool_free_strategist():
    """AC-4/5/7: enabled ⇒ last sub-agent is the strategist with StrategyOverlay schema, no tools."""
    agent = build_competitor_agent(config=_enabled_cfg())
    strat = agent.sub_agents[-1]
    assert strat.name == "competitor_strategist"
    assert strat.output_schema is _Overlay
    assert not getattr(strat, "tools", None)


def test_client_strategy_on_appends_strategist():
    agent = build_client_agent(config=_enabled_cfg())
    assert agent.sub_agents[-1].name == "client_strategist"
    assert agent.sub_agents[-1].output_schema is _Overlay


def test_playbook_body_injected_and_editable(tmp_path):
    """AC-8: the playbook body appears in the strategist instruction, and editing it changes it."""
    pb = tmp_path / "competitor-counterplay.md"
    pb.write_text(
        "---\nname: competitor-counterplay\nmode: competitor\n---\nUNIQUE-MARKER-V1",
        encoding="utf-8",
    )
    agent = build_competitor_agent(config=_enabled_cfg(tmp_path))
    assert "UNIQUE-MARKER-V1" in agent.sub_agents[-1].instruction
    pb.write_text(
        "---\nname: competitor-counterplay\nmode: competitor\n---\nUNIQUE-MARKER-V2",
        encoding="utf-8",
    )
    agent2 = build_competitor_agent(config=_enabled_cfg(tmp_path))
    assert "UNIQUE-MARKER-V2" in agent2.sub_agents[-1].instruction


def test_missing_playbook_falls_back_softly(tmp_path):
    """A missing playbook does not break the build — a default-judgement note is used instead."""
    agent = build_competitor_agent(config=_enabled_cfg(tmp_path))  # empty dir, no .md
    assert agent.sub_agents[-1].name == "competitor_strategist"
    assert "default judgement" in agent.sub_agents[-1].instruction


# --- AC-11: sovereignty (strategist obeys on_prem) --------------------------------------- #


def test_strategist_is_vllm_under_on_prem():
    cfg = _enabled_cfg()
    cfg.governance.compliance_mode = "on_prem_required"
    for build, mode in ((build_competitor_agent, "competitor"), (build_client_agent, "client")):
        agent = build(config=cfg, cloud_allowed=False, search_provider="duckduckgo")
        for sub in agent.sub_agents:
            assert not isinstance(sub.model, str), f"{sub.name} got a Gemini model-id string"
            assert type(sub.model).__name__ == "LiteLlm", sub.name


# --- AC-10: orchestrator merge ------------------------------------------------------------ #

from sentinel.agent.orchestrator import _merge_strategy  # noqa: E402


def _overlay():
    return StrategyOverlay(
        assessment="Re-engage on expansion.",
        action_plan=[
            RecommendedAction(action="Book sync", priority="high", timeline="this week",
                              rationale="Merged insight: hiring surge + stalled stage."),
        ],
        objection_handling=[Objection(objection="Price", reframe="ROI from insight.")],
    )


def test_merge_populates_account_brief():
    brief = AccountBrief(account="Acme", one_line_summary="x")
    note = _merge_strategy(brief, {"strategy": _overlay().model_dump()})
    assert brief.assessment == "Re-engage on expansion."
    assert brief.action_plan[0].action == "Book sync"
    assert brief.objection_handling[0].objection == "Price"
    assert note == "strategy: 1 actions"


def test_merge_competitor_ignores_objection_handling():
    bc = Battlecard(target="Acme", one_line_summary="x", positioning="y")
    _merge_strategy(bc, {"strategy": _overlay().model_dump()})
    assert bc.assessment == "Re-engage on expansion."
    assert bc.action_plan[0].priority == "high"
    assert not hasattr(bc, "objection_handling")  # competitor schema has none


def test_merge_missing_key_leaves_artifact_unchanged():
    brief = AccountBrief(account="Acme", one_line_summary="x")
    note = _merge_strategy(brief, {})  # no "strategy" key
    assert brief.assessment is None and brief.action_plan == []
    assert note == "strategy: none"


def test_merge_malformed_overlay_failsoft():
    brief = AccountBrief(account="Acme", one_line_summary="x")
    note = _merge_strategy(brief, {"strategy": 12345})  # not coercible to StrategyOverlay
    assert brief.assessment is None  # untouched
    assert note.startswith("strategy: skipped")


# --- AC-13: render (markdown + dashboard) ------------------------------------------------- #

from sentinel.artifacts.writer import render_markdown  # noqa: E402
from sentinel.web.render import render_account_brief, render_battlecard  # noqa: E402


def _brief_with_strategy():
    brief = AccountBrief(account="Acme", one_line_summary="x")
    _merge_strategy(brief, {"strategy": _overlay().model_dump()})
    return brief


def test_markdown_renders_strategy_when_present():
    md = render_markdown(_brief_with_strategy())
    assert "## Strategic assessment" in md
    assert "## Action plan" in md and "| Priority |" in md and "Book sync" in md
    assert "## Objection handling" in md and "Price" in md


def test_markdown_omits_strategy_when_empty():
    md = render_markdown(AccountBrief(account="Acme", one_line_summary="x"))
    assert "Strategic assessment" not in md
    assert "Action plan" not in md
    assert "Objection handling" not in md


def test_dashboard_renders_and_escapes_strategy():
    brief = AccountBrief(account="Acme", one_line_summary="x")
    _merge_strategy(brief, {"strategy": StrategyOverlay(
        assessment="<script>alert(1)</script>",
        action_plan=[RecommendedAction(action="A & B", priority="high", timeline="now",
                                       rationale="r")],
    ).model_dump()})
    html = render_account_brief(brief, backend="vllm", reference="x.md", trace=[])
    assert "Action plan" in html
    assert "<script>alert(1)</script>" not in html  # escaped
    assert "&lt;script&gt;" in html


def test_dashboard_omits_strategy_when_empty():
    html = render_battlecard(
        Battlecard(target="Acme", one_line_summary="x", positioning="y"),
        backend="vllm", reference="x.md", trace=[],
    )
    assert "Action plan" not in html and "Strategic assessment" not in html


# --- AC-14: Settings (apply_strategy + route) -------------------------------------------- #

import pytest  # noqa: E402

from sentinel.web import settings as S  # noqa: E402

_REAL_PB = str(_PLAYBOOK_DIR)  # the shipped playbooks dir


def test_apply_strategy_enable_with_valid_playbooks():
    new = S.apply_strategy(
        build_default(), enabled=True, playbook_dir=_REAL_PB,
        competitor_playbook="competitor-counterplay", client_playbook="account-strategy",
    )
    assert new.strategy.enabled is True
    assert new.strategy.playbook_dir == _REAL_PB


def test_apply_strategy_enable_with_missing_playbook_rejected():
    with pytest.raises(ValueError, match="not found"):
        S.apply_strategy(
            build_default(), enabled=True, playbook_dir=_REAL_PB,
            competitor_playbook="does-not-exist", client_playbook="account-strategy",
        )


def test_apply_strategy_disable_skips_validation():
    # disabling must not require valid stems (nothing runs)
    new = S.apply_strategy(
        build_default(), enabled=False, playbook_dir="nowhere",
        competitor_playbook="x", client_playbook="y",
    )
    assert new.strategy.enabled is False


# routes (reuse the test_settings client fixture pattern) --------------------
from fastapi.testclient import TestClient  # noqa: E402

from sentinel.config import config_path, load_config, reset_config  # noqa: E402
from sentinel.web import app as web_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_CONFIG_PATH", str(tmp_path / "cfg.yaml"))
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))
    reset_config()
    yield TestClient(web_app.app)
    reset_config()


def test_post_strategy_persists(client):
    r = client.post("/settings/strategy", data={
        "enabled": "on", "playbook_dir": _REAL_PB,
        "competitor_playbook": "competitor-counterplay", "client_playbook": "account-strategy",
    })
    assert r.status_code == 200 and "saved" in r.text.lower()
    reset_config()
    cfg = load_config(config_path())
    assert cfg.strategy.enabled is True
    # no secret persisted
    assert "API_KEY" not in config_path().read_text().upper() or "=" not in config_path().read_text()


def test_post_strategy_bad_playbook_errors(client):
    r = client.post("/settings/strategy", data={
        "enabled": "on", "playbook_dir": _REAL_PB,
        "competitor_playbook": "nope", "client_playbook": "account-strategy",
    })
    assert r.status_code == 200 and "not found" in r.text


def test_settings_renders_strategy_section(client):
    s = client.get("/settings").text
    assert "Strategy · action plan" in s
    assert "Playbook directory" in s


# --- End-to-end: a merged artifact is actually persisted (post-run path) ------------------ #


def test_merged_artifact_is_written_to_disk(tmp_path):
    """Mirror the orchestrator's post-run path: coerce → _merge_strategy → writer.write, and assert
    the durable file carries the action plan (the merge is not just in-memory)."""
    from sentinel.artifacts.writer import get_writer

    brief = AccountBrief(account="Acme", one_line_summary="x")
    note = _merge_strategy(brief, {"strategy": _overlay().model_dump()})
    assert note == "strategy: 1 actions"
    writer = get_writer("markdown", out_dir=tmp_path)
    result = writer.write(brief)
    written = (tmp_path / result.reference.split("/")[-1]).read_text(encoding="utf-8")
    assert "## Action plan" in written and "Book sync" in written
    assert "## Strategic assessment" in written
