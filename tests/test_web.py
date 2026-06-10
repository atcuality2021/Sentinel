"""Web layer tests (SRS FR-09 presentation, Demo artifact).

These run with NO API key: the form, health probe, and HTML renderers are exercised
directly, and ``/run`` is tested against a stubbed orchestrator. The point is to prove the
demo surface renders the boundary provenance correctly — not to make a live model call.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentinel.artifacts.schemas import AccountBrief, Battlecard, Boundary, Finding, Gap, Source
from sentinel.web import app as web_app
from sentinel.web import render


def _pub(text: str) -> Finding:
    return Finding(text=text, source=Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://x"))


def _priv(text: str) -> Finding:
    return Finding(text=text, source=Source(boundary=Boundary.PRIVATE, label="CRM: Acme deal"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(web_app.app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"


def test_dashboard_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Dashboard" in r.text
    assert "Signal provenance" in r.text or "No runs yet" in r.text  # chart or empty state
    assert "Sovereign Intelligence Agent" in r.text  # sidebar brand


def test_dashboard_has_sidebar_nav(client):
    r = client.get("/")
    # collapsible sidebar — project-first nav (Build: Dashboard/Projects/Agents; Govern: Backends/Settings)
    assert "navToggle" in r.text
    for href in ("/projects", "/backends", "/agents"):
        assert f"href='{href}'" in r.text
    for group in ("Build", "Govern"):
        assert group in r.text
    # New Run and global Artifacts are no longer in the sidebar (moved inside project scope)
    assert "href='/new'" not in r.text


def test_agents_page_renders_roster_and_flow(client):
    """The Agents page introspects the real specs: both modes, every role, and the dark stages."""
    r = client.get("/agents")
    assert r.status_code == 200
    assert "Agent Intelligence" in r.text or "Competitor Intelligence" in r.text
    # core pipeline roles surface as nodes
    for name in ("competitor_planner", "battlecard_synthesizer", "account_brief_synthesizer"):
        assert name in r.text
    # flagged-off stages are shown as architecture (dark), not hidden
    assert "competitor_extractor" in r.text          # two-tier (off by default) still documented
    assert "competitor_strategist" in r.text         # strategy overlay (off by default)
    assert "Execution topology" in r.text            # sequential vs coordinator explainer
    assert "Recompute priority" in r.text            # deterministic rail


def test_new_run_renders_form(client):
    r = client.get("/new")
    assert r.status_code == 200
    assert "Run Sentinel" in r.text


def test_new_run_has_backend_toggle(client):
    r = client.get("/new")
    assert "name='backend'" in r.text
    assert "value='gemini'" in r.text
    assert "value='vllm'" in r.text
    assert "On-prem" in r.text and "Gemma" in r.text


def test_secondary_pages_render(client):
    for path in ("/artifacts", "/backends"):
        r = client.get(path)
        assert r.status_code == 200, path


def test_run_rejects_empty_target(client):
    r = client.post("/run", data={"target": "  ", "mode": "competitor"})
    assert r.status_code == 200
    assert "Target is required" in r.text


def test_run_renders_battlecard_via_stub(client, monkeypatch):
    bc = Battlecard(
        target="Stripe",
        one_line_summary="Developer-first payments leader",
        positioning="API-first payments",
        strengths=[_pub("Best-in-class API")],
        weaknesses=[_pub("Premium pricing")],
        how_to_win=["Lead with on-prem sovereignty"],
        gaps=[Gap(boundary=Boundary.PUBLIC, what_was_missing="filings", impact="no financials")],
    )

    class _Write:
        backend = "markdown"
        reference = "artifacts_out/battlecard-stripe.md"

    class _Result:
        artifact = bc
        backend = "gemini"
        write = _Write()
        trace = ["backend=gemini", "mode=competitor"]

    async def _fake_run(target, mode, *, vertical_context=None, backend=None):
        return _Result()

    monkeypatch.setattr(web_app, "run_async", _fake_run)
    r = client.post("/run", data={"target": "Stripe", "mode": "competitor"})
    assert r.status_code == 200
    assert "Battlecard — Stripe" in r.text
    assert "How to win" in r.text
    # provenance badge rendered
    assert "badge public" in r.text


def test_run_forwards_backend_choice(client, monkeypatch):
    captured = {}

    async def _fake_run(target, mode, *, vertical_context=None, backend=None):
        captured["backend"] = backend
        raise RuntimeError("stop after capture")  # we only assert the forwarded value

    monkeypatch.setattr(web_app, "run_async", _fake_run)
    client.post("/run", data={"target": "Acme", "mode": "client", "backend": "vllm"})
    assert captured["backend"] == "vllm"


def test_run_rejects_unknown_backend(client):
    r = client.post("/run", data={"target": "Acme", "mode": "client", "backend": "azure"})
    assert r.status_code == 200
    assert "Unknown backend" in r.text


# --- HIGH-03: /run accepts domain modes (finance, academic, software, nutrition, travel) ---- #


def test_run_rejects_unknown_mode(client):
    r = client.post("/run", data={"target": "Acme", "mode": "unknown_xyz"})
    assert r.status_code == 200
    assert "Unknown mode" in r.text


@pytest.mark.parametrize("domain", ["finance", "academic", "software", "nutrition", "travel"])
def test_run_domain_mode_routes_through_dag(client, monkeypatch, domain):
    """Domain modes must reach gate_proposal with autonomy=autonomous and render a result."""
    from sentinel.agent.autonomy import GateOutcome
    from sentinel.artifacts.schemas import Result

    captured: dict = {}

    async def _fake_gate(proposal, *, autonomy, seeds, **kw):
        captured["autonomy"] = autonomy
        captured["capability"] = proposal.plan.steps[0].capability
        result = Result(
            task_id=proposal.plan.task_id,
            summary=f"{domain} research done",
            artifacts=[],
            citations=[],
            dashboard_payload={"artifacts": {}},
            degraded=False,
        )
        return GateOutcome(autonomy="autonomous", proposal=proposal, result=result, ran=True)

    import sentinel.web.app as _app
    monkeypatch.setattr(_app, "gate_proposal", _fake_gate)

    r = client.post("/run", data={"target": "test-target", "mode": domain})
    assert r.status_code == 200
    assert "Unknown mode" not in r.text
    assert captured.get("autonomy") == "autonomous"
    assert captured.get("capability") == domain


def test_run_domain_mode_seeds_target_and_vertical(client, monkeypatch):
    """Seeds passed to gate_proposal carry the submitted target and vertical_context."""
    from sentinel.agent.autonomy import GateOutcome
    from sentinel.artifacts.schemas import Result

    captured: dict = {}

    async def _fake_gate(proposal, *, autonomy, seeds, **kw):
        captured["seeds"] = seeds
        result = Result(task_id=proposal.plan.task_id, summary="ok", artifacts=[], citations=[],
                        dashboard_payload={}, degraded=False)
        return GateOutcome(autonomy="autonomous", proposal=proposal, result=result, ran=True)

    import sentinel.web.app as _app
    monkeypatch.setattr(_app, "gate_proposal", _fake_gate)

    client.post("/run", data={"target": "HDFC Bank", "mode": "finance", "vertical": "BFSI"})
    seeds = captured.get("seeds", {})
    assert any(v.get("target") == "HDFC Bank" for v in seeds.values())
    assert any("BFSI" in (v.get("vertical_context") or "") for v in seeds.values())


def test_run_domain_mode_surfaces_gate_error(client, monkeypatch):
    """If gate_proposal raises, the route must render an error page — not a 500."""
    async def _explode(proposal, *, autonomy, seeds, **kw):
        raise RuntimeError("vllm timeout")

    import sentinel.web.app as _app
    monkeypatch.setattr(_app, "gate_proposal", _explode)

    r = client.post("/run", data={"target": "Acme Corp", "mode": "software"})
    assert r.status_code == 200
    assert "RuntimeError" in r.text or "vllm timeout" in r.text


def test_renderers_tag_boundaries():
    # public findings get the public badge; private findings get the private badge
    bc = Battlecard(target="X", one_line_summary="s", positioning="p", strengths=[_pub("a")])
    html = render.render_battlecard(bc, backend="gemini", reference="r", trace=[])
    assert "badge public" in html
    assert "badge private" not in html  # no private finding present

    ab = AccountBrief(
        account="Acme",
        one_line_summary="warm",
        public_signal=[_pub("hiring")],
        private_signal=[_priv("deal stalled")],
        merged_insights=["expand"],
    )
    html2 = render.render_account_brief(ab, backend="gemini", reference="r", trace=[])
    assert "badge public" in html2
    assert "badge private" in html2
    assert "Merged insights" in html2


def test_render_escapes_untrusted_text():
    # a finding containing HTML must not render as live markup (no stored XSS)
    evil = Finding(text="<script>alert(1)</script>", source=Source(boundary=Boundary.PUBLIC, label="x"))
    bc = Battlecard(target="X", one_line_summary="s", positioning="p", strengths=[evil])
    html = render.render_battlecard(bc, backend="g", reference="r", trace=[])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- HIGH-04: preferred_format is a hard render-layer switch, not a soft prompt ----------- #


def test_findings_to_table_converts_ul_to_table():
    """_findings_to_table must replace <ul class='find'>…</ul> with a <table> element."""
    html = ("<div><b>Strengths</b><ul class='find'>"
            "<li>item A</li><li>item B</li></ul></div>")
    out = render._findings_to_table(html)
    assert "<table" in out
    assert "<ul" not in out
    assert "item A" in out
    assert "item B" in out


def test_findings_to_prose_converts_ul_to_paragraph():
    """_findings_to_prose must replace <ul class='find'>…</ul> with a <p> element."""
    html = ("<div><b>Weaknesses</b><ul class='find'>"
            "<li>weak A</li><li>weak B</li></ul></div>")
    out = render._findings_to_prose(html)
    assert "<p" in out
    assert "<ul" not in out
    assert "weak A" in out


def test_findings_to_table_leaves_non_find_ul_alone():
    """Only <ul class='find'> blocks should be transformed; other ULs must be untouched."""
    html = "<ul class='nav'><li>nav item</li></ul>"
    out = render._findings_to_table(html)
    assert "<ul class='nav'>" in out  # unchanged


def test_result_card_applies_table_format(monkeypatch):
    """_result_card must apply _findings_to_table when result.preferred_format='table'."""
    from sentinel.artifacts.schemas import Result, Source, Boundary

    art = {
        "one_line_summary": "test",
        "strengths": [{"text": "fast"}],
        "weaknesses": [],
        "pricing_signals": [],
        "recent_developments": [],
    }
    result = Result(
        task_id="t1",
        summary="done",
        artifacts=[],
        citations=[],
        dashboard_payload={"artifacts": {"battlecard": art}},
        degraded=False,
        preferred_format="table",
    )
    html = render._result_card(result)
    assert "<table" in html
    assert "<ul class='find'>" not in html


def test_result_card_applies_prose_format(monkeypatch):
    """_result_card must apply _findings_to_prose when result.preferred_format='prose'."""
    from sentinel.artifacts.schemas import Result

    art = {
        "financial_summary": "strong",
        "one_line_summary": "solid",
        "key_metrics": [{"text": "revenue up 30%"}],
        "market_position": [],
        "risk_signals": [],
        "recent_developments": [],
    }
    result = Result(
        task_id="t1", summary="done", artifacts=[], citations=[],
        dashboard_payload={"artifacts": {"finance": art}},
        degraded=False,
        preferred_format="prose",
    )
    html = render._result_card(result)
    assert "<p class='note'" in html
    assert "<ul class='find'>" not in html


def test_result_card_default_bullets_unchanged():
    """Without preferred_format, _result_card renders findings as <ul class='find'> bullets."""
    from sentinel.artifacts.schemas import Result

    art = {
        "one_line_summary": "test",
        "strengths": [{"text": "reliable"}],
        "weaknesses": [],
        "pricing_signals": [],
        "recent_developments": [],
    }
    result = Result(
        task_id="t1", summary="done", artifacts=[], citations=[],
        dashboard_payload={"artifacts": {"battlecard": art}},
        degraded=False,
    )
    html = render._result_card(result)
    assert "<ul class='find'>" in html


def test_result_preferred_format_round_trips():
    """Result.preferred_format serialises and deserialises without loss."""
    from sentinel.artifacts.schemas import Result
    r = Result(task_id="t", summary="s", preferred_format="table")
    r2 = Result.model_validate(r.model_dump())
    assert r2.preferred_format == "table"


def test_run_dag_stamps_preferred_format_on_result(tmp_path, monkeypatch):
    """run_dag must set result.preferred_format when the user profile has a non-default format."""
    import asyncio
    from sentinel.memory.schema import UserProfile
    from sentinel.memory.store import UserProfileStore

    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    UserProfileStore(tmp_path / "sentinel.db").upsert(UserProfile(
        user_id="u1", verbosity=3, citation_density=3, domain_level="analyst",
        preferred_format="table",
    ))

    from sentinel.agent import dag as _dag

    async def _fake_run_plan(plan, *, assemble, **kw):
        from sentinel.artifacts.schemas import Result
        for s in plan.steps:
            s.status = "done"
        return Result(task_id=plan.task_id, summary="ok", artifacts=[], citations=[],
                      dashboard_payload={}, degraded=False)

    monkeypatch.setattr(_dag, "run_plan", _fake_run_plan)

    from sentinel.artifacts.schemas import Plan, Step
    plan = Plan(id="ph4", task_id="th4", steps=[
        Step(id="finance", capability="finance", output_key="finance"),
    ])
    from sentinel.config.defaults import build_default
    from sentinel.config.schema import BackendOption
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma", api_base="http://localhost/v1")
    }
    result = asyncio.run(_dag.run_dag(
        plan, cfg=cfg, backend="vllm", cloud_allowed=False, use_cache=False,
        user_id="u1",
    ))
    assert result.preferred_format == "table"
