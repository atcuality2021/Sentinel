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
