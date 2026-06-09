"""SENTINEL-005 — Governance & Pluggable Search tests (AC-1..AC-11).

Three layers, all offline (no live LLM, no real network — httpx is mocked):
  - governance helpers (pure functions over SentinelConfig),
  - the pluggable search provider layer (function tools + fail-soft),
  - the structural no-cloud guarantee (introspect built agents → zero Gemini in on_prem_required),
  - the orchestrator trace + Settings routes (FastAPI TestClient with a throwaway config).

The load-bearing invariant: in ``on_prem_required`` NO Gemini object is ever constructed and
``google_search`` is never attached — proven by introspection, not by reading a prompt.
"""

from __future__ import annotations

import httpx
import pytest

from sentinel.agent import governance as G
from sentinel.agent.modes._build import resolve_model
from sentinel.agent.modes.competitor import build_competitor_agent
from sentinel.config import SentinelConfig
from sentinel.tools.public import web_search


def _cfg(mode: str = "cloud_ok", *, provider: str = "gemini",
         block_private: bool = False) -> SentinelConfig:
    cfg = SentinelConfig.default()
    cfg.governance.compliance_mode = mode  # type: ignore[assignment]
    cfg.governance.block_cloud_on_private = block_private
    cfg.search.provider = provider  # type: ignore[assignment]
    cfg.backend.default = "gemini"  # type: ignore[assignment]
    return cfg


# --------------------------------------------------------------------------- #
# AC-1 — cloud_allowed
# --------------------------------------------------------------------------- #
def test_cloud_allowed_only_false_for_on_prem_required():
    assert G.cloud_allowed(_cfg("cloud_ok")) is True
    assert G.cloud_allowed(_cfg("on_prem_preferred")) is True
    assert G.cloud_allowed(_cfg("on_prem_required")) is False


# --------------------------------------------------------------------------- #
# AC-8 — effective_backend honors policy
# --------------------------------------------------------------------------- #
def test_effective_backend_on_prem_required_forces_vllm():
    assert G.effective_backend(_cfg("on_prem_required"), "gemini") == "vllm"


def test_effective_backend_block_cloud_on_private_forces_vllm_for_private_run():
    cfg = _cfg("cloud_ok", block_private=True)
    assert G.effective_backend(cfg, "gemini", private=True) == "vllm"
    # a public (non-private) run under the same policy is untouched
    assert G.effective_backend(cfg, "gemini", private=False) == "gemini"


def test_effective_backend_cloud_ok_passes_request_through():
    assert G.effective_backend(_cfg("cloud_ok"), "vllm") == "vllm"
    assert G.effective_backend(_cfg("cloud_ok"), "gemini") == "gemini"


# --------------------------------------------------------------------------- #
# AC-5 — effective_search_provider never gemini when no cloud
# --------------------------------------------------------------------------- #
def test_effective_search_provider_falls_back_off_gemini_on_prem():
    cfg = _cfg("on_prem_required", provider="gemini")
    cfg.search.onprem_fallback = "brave"  # type: ignore[assignment]
    assert G.effective_search_provider(cfg, allow_cloud=False) == "brave"


def test_effective_search_provider_keeps_noncloud_provider():
    cfg = _cfg("on_prem_required", provider="duckduckgo")
    assert G.effective_search_provider(cfg, allow_cloud=False) == "duckduckgo"


def test_effective_search_provider_keeps_gemini_when_cloud_ok():
    assert G.effective_search_provider(_cfg("cloud_ok", provider="gemini"),
                                       allow_cloud=True) == "gemini"


# --------------------------------------------------------------------------- #
# AC-2 / AC-3 — resolve_model honors cloud_allowed (structural no-Gemini)
# --------------------------------------------------------------------------- #
def test_resolve_model_pin_gemini_ignored_when_no_cloud(monkeypatch):
    monkeypatch.setenv("VLLM_API_KEY", "k")
    cfg = _cfg("on_prem_required")
    ac = cfg.agents["competitor.public_research"]  # pin_gemini=True
    assert ac.pin_gemini is True
    model = resolve_model(cfg, ac, None, cloud_allowed=False)
    assert not isinstance(model, str)             # NOT a Gemini model-id string
    assert type(model).__name__ == "LiteLlm"      # forced on-prem


def test_resolve_model_pin_gemini_stays_gemini_when_cloud_ok():
    cfg = _cfg("cloud_ok")
    ac = cfg.agents["competitor.public_research"]
    model = resolve_model(cfg, ac, None, cloud_allowed=True)
    assert isinstance(model, str)                 # Gemini model-id string, unchanged (AC-3)


def test_on_prem_required_competitor_builds_zero_gemini(monkeypatch):
    """Every agent's model is a vLLM object; no sub-agent holds a Gemini model-id string (AC-2)."""
    monkeypatch.setenv("VLLM_API_KEY", "k")
    cfg = _cfg("on_prem_required", provider="duckduckgo")
    agent = build_competitor_agent(config=cfg, cloud_allowed=False, search_provider="duckduckgo")
    for sub in agent.sub_agents:
        assert not isinstance(sub.model, str), f"{sub.name} got a Gemini model-id string"
        assert type(sub.model).__name__ == "LiteLlm"


# --------------------------------------------------------------------------- #
# AC-4 — public-research tool is the configured provider
# --------------------------------------------------------------------------- #
def _public_tools(agent):
    pr = next(s for s in agent.sub_agents if s.name == "competitor_public_research")
    return pr.tools or []


def test_gemini_provider_attaches_google_search():
    agent = build_competitor_agent(config=_cfg("cloud_ok"), cloud_allowed=True,
                                   search_provider="gemini")
    tools = _public_tools(agent)
    assert any(type(t).__name__ == "GoogleSearchTool" for t in tools)


def test_on_prem_attaches_function_tool_not_google_search(monkeypatch):
    monkeypatch.setenv("VLLM_API_KEY", "k")
    agent = build_competitor_agent(config=_cfg("on_prem_required", provider="duckduckgo"),
                                   cloud_allowed=False, search_provider="duckduckgo")
    tools = _public_tools(agent)
    assert not any(type(t).__name__ == "GoogleSearchTool" for t in tools)  # no cloud search
    assert any(callable(t) and getattr(t, "__name__", "") == "search" for t in tools)


def test_get_search_tool_registry():
    assert type(web_search.get_search_tool("gemini")).__name__ == "GoogleSearchTool"
    for p in ("duckduckgo", "brave", "serpapi"):
        tool = web_search.get_search_tool(p, results=3)
        assert callable(tool) and tool.__name__ == "search"
    with pytest.raises(ValueError, match="Unknown search provider"):
        web_search.get_search_tool("bing")


# --------------------------------------------------------------------------- #
# AC-6 / AC-7 — provider tools: env keys, parsing, fail-soft, timeout
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, payload: dict | None = None, *, text: str = ""):
        self._payload = payload or {}
        self.text = text          # the DDG lite path reads .text (HTML); Brave/Serp read .json()

    def raise_for_status(self):  # no-op = 200 OK
        return None

    def json(self):
        return self._payload


# A representative DuckDuckGo *lite* SERP fragment (href-first, single-quoted class — the real shape):
# two results, each a redirector-wrapped result-link anchor followed by a result-snippet cell.
_DDG_LITE_HTML = """
<table>
<tr><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fex.com%2Facme&rut=x"
    class='result-link'>Acme makes anvils</a></td></tr>
<tr><td class='result-snippet'>Acme Corp manufactures anvils and other heavy goods.</td></tr>
<tr><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fex.com%2Fc&rut=y"
    class='result-link'>Acme Corp profile</a></td></tr>
<tr><td class='result-snippet'>A company that makes things.</td></tr>
</table>
"""


def test_brave_requires_env_key(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    out = web_search.get_search_tool("brave")("openai")
    assert out["status"] == "error" and "BRAVE_API_KEY" in out["message"]


def test_serpapi_requires_env_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    out = web_search.get_search_tool("serpapi")("openai")
    assert out["status"] == "error" and "SERPAPI_API_KEY" in out["message"]


def test_brave_parses_results_and_sends_key_and_timeout(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "dummy-brave-key")
    captured: dict = {}

    def fake_get(url, **kw):
        captured.update(kw)
        captured["url"] = url
        return _FakeResp({"web": {"results": [
            {"title": "Acme raises $50M", "url": "https://ex.com/a", "description": "Series C"},
        ]}})

    monkeypatch.setattr(httpx, "get", fake_get)
    out = web_search.get_search_tool("brave", results=5)("acme funding")
    assert out["status"] == "success"
    # snippet is fenced as source material (Step 17); title/url stay clean for citation.
    assert out["results"][0] == {"title": "Acme raises $50M", "url": "https://ex.com/a",
                                 "snippet": web_search.wrap_source_material("Series C")}
    # secret travels in the header, never the result; timeout is explicit (NFR-3)
    assert captured["headers"]["X-Subscription-Token"] == "dummy-brave-key"
    assert captured["timeout"] == web_search._TIMEOUT_S
    assert "dummy-brave-key" not in str(out)


def test_serpapi_parses_results(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "dummy-serp-key")

    def fake_get(url, **kw):
        return _FakeResp({"organic_results": [
            {"title": "Acme", "link": "https://ex.com/s", "snippet": "profile"},
        ]})

    monkeypatch.setattr(httpx, "get", fake_get)
    out = web_search.get_search_tool("serpapi")("acme")
    assert out["status"] == "success"
    assert out["results"][0]["url"] == "https://ex.com/s"


def test_searxng_parses_results_from_env_url(monkeypatch):
    """SENTINEL-013: the sovereign SearXNG provider queries the self-hosted instance (URL from env)
    and parses its JSON into citeable rows; the snippet is fenced as source material."""
    monkeypatch.setenv("SEARXNG_URL", "http://searx.internal:8888/")
    captured: dict = {}

    def fake_get(url, **kw):
        captured["url"] = url
        captured.update(kw)
        return _FakeResp({"results": [
            {"title": "Acme Corp", "url": "https://ex.com/acme", "content": "Acme makes anvils."},
            {"title": "Acme news", "url": "https://ex.com/n", "content": "Series C raised."},
        ]})

    monkeypatch.setattr(httpx, "get", fake_get)
    out = web_search.get_search_tool("searxng", results=5)("acme")
    assert out["status"] == "success"
    assert captured["url"] == "http://searx.internal:8888/search"   # trailing slash trimmed + /search
    assert captured["params"] == {"q": "acme", "format": "json"}
    assert captured["timeout"] == web_search._TIMEOUT_S
    assert [r["url"] for r in out["results"]] == ["https://ex.com/acme", "https://ex.com/n"]
    assert out["results"][0]["snippet"] == web_search.wrap_source_material("Acme makes anvils.")


def test_searxng_requires_env_url(monkeypatch):
    """No `SEARXNG_URL` ⇒ a typed fail-soft error (the URL is config, read from env, never an arg)."""
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    out = web_search.get_search_tool("searxng")("acme")
    assert out["status"] == "error" and "SEARXNG_URL" in out["message"] and out["results"] == []


def test_duckduckgo_parses_lite_serp(monkeypatch):
    """SENTINEL-013 AC-1: the DDG path parses the **lite SERP** into real, URL-bearing web results
    (not the old Instant-Answer abstracts) — and unwraps the redirector to the true target URL."""
    captured: dict = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured.update(kw)
        return _FakeResp(text=_DDG_LITE_HTML)

    monkeypatch.setattr(httpx, "post", fake_post)
    out = web_search.get_search_tool("duckduckgo", results=5)("acme")
    assert out["status"] == "success"
    assert captured["url"] == web_search._DDG_ENDPOINT and captured["data"] == {"q": "acme"}
    assert captured["timeout"] == web_search._TIMEOUT_S          # explicit timeout (NFR-3)
    # two real results, redirector unwrapped to the target URL, snippet fenced as source material.
    assert [r["url"] for r in out["results"]] == ["https://ex.com/acme", "https://ex.com/c"]
    assert out["results"][0]["title"] == "Acme makes anvils"
    assert "anvils" in out["results"][0]["snippet"]
    assert out["results"][0]["snippet"] == web_search.wrap_source_material(
        "Acme Corp manufactures anvils and other heavy goods."
    )


def test_duckduckgo_empty_serp_is_clean_gap(monkeypatch):
    """A garbled/empty lite page yields an honest empty success, never a raise (AC-1/AC-3)."""
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _FakeResp(text="<html>no results</html>"))
    out = web_search.get_search_tool("duckduckgo")("acme")
    assert out["status"] == "success" and out["results"] == []


def test_provider_tool_fails_soft_on_network_error(monkeypatch):
    def boom(url, **kw):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", boom)        # DDG lite POSTs; a network error degrades to a gap
    out = web_search.get_search_tool("duckduckgo")("acme")
    assert out["status"] == "error"          # degrades to a gap, never raises (AC-3)
    assert out["results"] == []


def test_empty_query_is_rejected_softly():
    out = web_search.get_search_tool("duckduckgo")("   ")
    assert out["status"] == "error"


def test_search_tool_enforces_call_budget(monkeypatch):
    """After ``max_calls`` searches the tool soft-stops (``budget_reached``) instead of fetching
    again — bounding the over-searching loop that bloated the 26B synthesizer input. The fetcher is
    stubbed so the cap is asserted without touching the network (hermetic)."""
    calls = {"n": 0}

    def fake_fetch(query, results):
        calls["n"] += 1
        return {"status": "success", "provider": "duckduckgo",
                "results": [{"title": "t", "url": "u", "snippet": "s"}]}

    monkeypatch.setitem(web_search._FETCHERS, "duckduckgo", fake_fetch)
    tool = web_search.get_search_tool("duckduckgo", max_calls=2)
    assert tool("a")["status"] == "success"
    assert tool("b")["status"] == "success"
    stopped = tool("c")
    assert stopped["status"] == "budget_reached"
    assert stopped["results"] == []
    assert "synthesize" in stopped["message"].lower()
    assert calls["n"] == 2  # the 3rd call never reached the fetcher


def test_search_tool_staggers_consecutive_calls(monkeypatch):
    """SENTINEL-013 AC-2: consecutive `search()` calls are spaced by `stagger_s`, asserted with an
    injected fake clock + recording sleep — **zero real sleeping** in the suite."""
    monkeypatch.setitem(
        web_search._FETCHERS, "duckduckgo",
        lambda q, r: {"status": "success", "provider": "duckduckgo", "results": []},
    )
    clock = {"t": 100.0}
    slept: list[float] = []
    tool = web_search.get_search_tool(
        "duckduckgo", stagger_s=1.5,
        now=lambda: clock["t"], sleep=lambda s: slept.append(s),
    )
    tool("a")                       # first call: no prior fetch → no sleep
    assert slept == []
    clock["t"] += 0.4               # only 0.4s elapsed since the first call
    tool("b")                       # must wait the remaining 1.1s
    assert slept == [pytest.approx(1.1)]
    clock["t"] += 5.0               # plenty of time has passed
    tool("c")                       # no wait needed
    assert slept == [pytest.approx(1.1)]


def test_search_tool_no_stagger_when_zero(monkeypatch):
    """`stagger_s=0` (the default / keyed-provider case) never sleeps — byte-identical to before."""
    monkeypatch.setitem(
        web_search._FETCHERS, "duckduckgo",
        lambda q, r: {"status": "success", "provider": "duckduckgo", "results": []},
    )
    slept: list[float] = []
    tool = web_search.get_search_tool("duckduckgo", stagger_s=0.0, sleep=lambda s: slept.append(s))
    tool("a"); tool("b"); tool("c")
    assert slept == []


def test_default_search_staggers_duckduckgo(monkeypatch):
    """The keyless DDG first-boot default carries a >0 stagger; gemini stays 0 (no spacing needed)."""
    from sentinel.config.defaults import _default_search

    monkeypatch.setenv("SENTINEL_SEARCH_PROVIDER", "duckduckgo")
    assert _default_search().stagger_s > 0
    monkeypatch.setenv("SENTINEL_SEARCH_PROVIDER", "gemini")
    assert _default_search().stagger_s == 0.0


def test_search_tool_unbounded_when_max_calls_zero(monkeypatch):
    """``max_calls=0`` disables the cap — legacy unbounded behaviour (no regression)."""
    monkeypatch.setitem(
        web_search._FETCHERS, "duckduckgo",
        lambda q, r: {"status": "success", "provider": "duckduckgo", "results": []},
    )
    tool = web_search.get_search_tool("duckduckgo", max_calls=0)
    for _ in range(5):
        assert tool("q")["status"] != "budget_reached"


# --------------------------------------------------------------------------- #
# AC-10 — orchestrator derives + traces governance, builds no Gemini on-prem
# --------------------------------------------------------------------------- #
def _install_fake_runner(monkeypatch, output_key: str, artifact: dict):
    """Replace InMemoryRunner with an offline fake that returns a pre-baked artifact in state."""
    from sentinel.agent import orchestrator as orch

    class FakeSession:
        def __init__(self, state):
            self.id = "sess-1"
            self.state = dict(state)

    class FakeSvc:
        def __init__(self):
            self._sess: FakeSession | None = None

        async def create_session(self, *, app_name, user_id, state):
            self._sess = FakeSession(state)
            return self._sess

        async def get_session(self, *, app_name, user_id, session_id):
            self._sess.state[output_key] = artifact
            return self._sess

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.agent = agent
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            # run_config carries the SSE streaming mode the orchestrator now requires (the 26B
            # reasoner endpoint 524s on non-streamed long generations). Accepted and ignored here.
            if False:  # make this an async generator that yields nothing
                yield None

    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunner)


def test_run_trace_records_effective_backend_and_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VLLM_API_KEY", "k")
    from sentinel.agent import orchestrator as orch

    _install_fake_runner(monkeypatch, "battlecard", {
        "target": "Acme", "one_line_summary": "x", "positioning": "y",
    })
    cfg = _cfg("on_prem_required", provider="gemini")  # gemini requested → must fall back
    cfg.search.onprem_fallback = "duckduckgo"  # type: ignore[assignment]

    result = orch.run("Acme", "competitor", config=cfg)

    assert result.backend == "vllm"
    assert "backend=vllm" in result.trace
    assert "compliance=on_prem_required" in result.trace
    assert "cloud_allowed=False" in result.trace
    assert "search=duckduckgo" in result.trace        # fell back off gemini (AC-5/AC-10)
    # the built agents carried no Gemini model-id string
    for sub in result_trace_agent_models(result):
        assert "gemini" not in sub.lower()


def result_trace_agent_models(result) -> list[str]:
    return [line for line in result.trace if line.startswith("agent ")]


def test_cloud_ok_run_trace_is_unchanged_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data2"))
    from sentinel.agent import orchestrator as orch

    _install_fake_runner(monkeypatch, "battlecard", {
        "target": "Acme", "one_line_summary": "x", "positioning": "y",
    })
    cfg = _cfg("cloud_ok", provider="gemini")
    result = orch.run("Acme", "competitor", config=cfg)
    assert result.backend == "gemini"
    assert "search=gemini" in result.trace
    assert "compliance=cloud_ok" in result.trace


# --------------------------------------------------------------------------- #
# AC-9 — Settings: Governance + Search sections + routes (TestClient)
# --------------------------------------------------------------------------- #
from fastapi.testclient import TestClient  # noqa: E402

from sentinel.config import config_path, load_config, reset_config  # noqa: E402
from sentinel.web import app as web_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SENTINEL_CONFIG_PATH", str(tmp_path / "cfg.yaml"))
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    reset_config()
    yield TestClient(web_app.app)
    reset_config()


def _stored() -> SentinelConfig:
    reset_config()
    return load_config(config_path())


def test_settings_renders_governance_and_search_sections(client):
    body = client.get("/settings").text
    assert "Governance" in body and "sovereignty policy" in body
    assert "Public search provider" in body
    assert "compliance_mode" in body and "provider" in body and "onprem_fallback" in body


def test_post_governance_persists_to_yaml(client):
    r = client.post("/settings/governance", data={
        "compliance_mode": "on_prem_required", "audit_log": "1",
        "block_cloud_on_private": "1",
    })
    assert r.status_code == 200
    cfg = _stored()
    assert cfg.governance.compliance_mode == "on_prem_required"
    assert cfg.governance.block_cloud_on_private is True


def test_post_governance_bad_enum_rejected(client):
    r = client.post("/settings/governance", data={"compliance_mode": "no_such_mode"})
    assert "compliance_mode must be one of" in r.text
    # nothing persisted: default mode unchanged
    assert _stored().governance.compliance_mode == "cloud_ok"


def test_post_search_persists_to_yaml(client):
    r = client.post("/settings/search", data={
        "provider": "brave", "results": "8", "onprem_fallback": "serpapi",
    })
    assert r.status_code == 200
    cfg = _stored()
    assert cfg.search.provider == "brave"
    assert cfg.search.results == 8
    assert cfg.search.onprem_fallback == "serpapi"


def test_post_search_bad_provider_rejected(client):
    r = client.post("/settings/search", data={"provider": "bing", "results": "5",
                                              "onprem_fallback": "duckduckgo"})
    assert "Search provider must be one of" in r.text


def test_post_search_results_out_of_range_rejected(client):
    r = client.post("/settings/search", data={"provider": "duckduckgo", "results": "99",
                                              "onprem_fallback": "duckduckgo"})
    assert "results must be" in r.text


def test_provider_key_pill_never_shows_value(client, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "super-secret-brave-value")
    reset_config()
    body = client.get("/settings").text
    assert "super-secret-brave-value" not in body   # never the value
    assert "BRAVE_API_KEY" in body                  # only the pill name


def test_no_secret_written_to_yaml_on_search_save(client, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "leak-me")
    reset_config()
    client.post("/settings/search", data={"provider": "brave", "results": "5",
                                          "onprem_fallback": "duckduckgo"})
    raw = (config_path()).read_text()
    assert "leak-me" not in raw


# AC-9 (UI) — New-run form reflects sovereign mode honestly -------------------
def test_new_run_form_disables_gemini_when_sovereign(client):
    client.post("/settings/governance", data={"compliance_mode": "on_prem_required"})
    body = client.get("/new").text
    assert "Sovereign — " in body and "cloud blocked by governance" in body
    # the Gemini radio is disabled and on-prem is forced selected
    assert "id='b-gemini' name='backend' value='gemini'  disabled" in body
    assert "id='b-vllm' name='backend' value='vllm' checked" in body


def test_new_run_form_has_no_sovereign_chip_when_cloud_ok(client):
    body = client.get("/new").text
    assert "cloud blocked by governance" not in body
    assert "disabled" not in body
