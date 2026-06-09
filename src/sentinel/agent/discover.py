"""Competitor discovery — the breadth step that feeds the depth Battlecard.

Sentinel's `competitor` mode profiles a *named* rival. Discovery is the missing inverse: given one
of OUR products (name + description), it names ≥N real rivals, each of which is then run through the
existing Battlecard. The two are different task shapes — discovery is breadth (product → list),
Battlecard is depth (rival → profile) — so they're separate specialists, breadth feeding depth.

**On-demand specialist factory (the "create a sub-agent on the go" pattern).** ``build_discovery_specialist``
constructs a fresh discovery agent *per product at runtime* — role/prompt/schema bound to that product
— rather than a statically-declared sub-agent. It's governance-correct by construction: the model is
resolved through ``resolve_model(cloud_allowed=)`` (so ``on_prem_required`` builds no Gemini object) and
it carries the ``CompetitorList`` ``output_schema`` so vLLM guided-decodes valid JSON (see the
``response_format`` path in the gateway). It is tool-free and tiered to the fast 12B (``role="planner"``):
the deep web research happens later in the Battlecard, so discovery only needs the model's market
knowledge to name plausible rivals — cheap and fast.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

from sentinel.agent.modes._build import resolve_model, to_genai
from sentinel.artifacts.schemas import CompetitorList
from sentinel.config import get_config
from sentinel.config.schema import AgentConfig, GenerationConfig

_APP = "sentinel_discovery"
_USER = "operator"

_INSTRUCTION = """You are a competitive-intelligence discovery analyst. You are given ONE product and \
must name its strongest real-world competitors.

Product: {product}
What it does: {description}

Return AT LEAST {n} *real, currently-operating* competitors — named companies or products that a buyer \
would realistically evaluate instead of this product. Prefer well-known, verifiable players in the same \
category. For each, give the market category and a one-sentence reason it competes. Do not invent names; \
do not list our own product. Output strictly as the required schema."""


def build_discovery_specialist(
    product: str,
    description: str,
    *,
    n: int = 3,
    cfg=None,
    backend: str | None = None,
    cloud_allowed: bool = True,
) -> Agent:
    """Construct a per-product discovery specialist at runtime (the on-demand factory).

    Tool-free + ``output_schema=CompetitorList`` → vLLM guided-decodes valid JSON. ``role="planner"``
    tiers it to the fast 12B under the role map; sovereignty flows through ``resolve_model``.
    """
    cfg = cfg or get_config()
    # max_output_tokens is generous (4096): gemini-2.5-flash is a *thinking* model and thinking tokens
    # count against this budget, so a tight cap truncates the JSON mid-object (a 1024 cap cut it at
    # line 7). 4096 leaves ample room after thinking for a short competitor list on both Gemini and the 12B.
    ac = AgentConfig(role="planner", generation=GenerationConfig(temperature=0.4, max_output_tokens=4096))
    model = resolve_model(cfg, ac, backend, cloud_allowed=cloud_allowed, output_schema=CompetitorList)
    instruction = _INSTRUCTION.format(product=product, description=description, n=n)
    return Agent(
        name="competitor_discovery",
        model=model,
        instruction=instruction,
        output_key="competitors",
        output_schema=CompetitorList,
        generate_content_config=to_genai(cfg.generation.merge(ac.generation)),
    )


async def discover_competitors(
    product: str,
    description: str,
    *,
    n: int = 3,
    cfg=None,
    backend: str | None = None,
    cloud_allowed: bool = True,
) -> CompetitorList:
    """Run the discovery specialist for one product and return the validated rival list.

    Runs NON-streamed (``StreamingMode.NONE``): discovery is a short, single structured call on the
    fast 12B/Gemini, so there is no Cloudflare 524 risk (that only bites the slow 26B), and Gemini's
    progressive-SSE path validates a *truncated partial* against ``output_schema`` — so streaming here
    breaks the JSON. Non-streamed returns the complete aggregated response, then ADK validates it.
    """
    agent = build_discovery_specialist(
        product, description, n=n, cfg=cfg, backend=backend, cloud_allowed=cloud_allowed,
    )
    runner = InMemoryRunner(agent=agent, app_name=_APP)
    session = await runner.session_service.create_session(
        app_name=_APP, user_id=_USER, state={"product": product},
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text=f"Find at least {n} competitors for our product: {product}")],
    )
    async for event in runner.run_async(
        user_id=_USER, session_id=session.id, new_message=message,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        if getattr(event, "partial", False):
            continue
    final = await runner.session_service.get_session(app_name=_APP, user_id=_USER, session_id=session.id)
    raw = final.state.get("competitors")
    if raw is None:
        raise RuntimeError(f"Discovery produced no competitors for {product!r}. State: {list(final.state)}")
    if isinstance(raw, CompetitorList):
        return raw
    if isinstance(raw, dict):
        return CompetitorList.model_validate(raw)
    import json

    return CompetitorList.model_validate(json.loads(raw))
