# SENTINEL-009 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture

One new sub-agent (`strategist`), one new artifact-overlay schema, one new playbook loader, and a
deterministic merge in the orchestrator. The synthesizer, the boundary invariant, and the
SENTINEL-004 read path are **untouched**. Everything reads from `SentinelConfig` (the one center).

```
run_async(target, mode, ...)
  cfg.strategy.enabled?
   ├─ False → pipeline = [planner, public_research, (private_research), synthesizer]   ← today, byte-identical (AC-3)
   └─ True  → pipeline = [ ... , synthesizer(output_key=battlecard|account_brief),
                                  strategist(output_key="strategy") ]                   ← appended (AC-4)
        strategist:
          model   = resolve_model(cfg, agents["<mode>.strategist"], backend, cloud_allowed)  ← vLLM if on_prem (AC-11)
          tools   = (none — tool-free, OQ-6)
          schema  = StrategyOverlay                                                            ← pydantic out (AC-5)
          instr   = render_prompt("<mode>.strategist")  + "\n\n" + playbook.body               ← overlay seam (AC-7)
          reads   = {battlecard} | {account_brief}  from ADK state                             ← RESERVED_VARS (FR-5)

  after run:
     artifact = coerce(state[battlecard|account_brief], schema)            ← unchanged
     overlay  = coerce(state["strategy"], StrategyOverlay)  (fail-soft)    ← AC-10, NFR-3
     merge_overlay(artifact, overlay)   # deterministic, additive
     writer.write(artifact)                                               ← now carries strategy
```

**Why an overlay + merge, not an enriched synthesizer (the key decision).** If the synthesizer
emitted the strategy fields directly, (a) its output schema/prompt would change → AC-3 byte-identical
breaks, and (b) the LLM could rewrite the cited findings while "enriching." A separate strategist
that emits *only* `StrategyOverlay`, merged by pure code, keeps findings immutable and the disabled
path a true no-op.

## 2. Schemas (`artifacts/schemas.py`)

```python
class RecommendedAction(BaseModel):
    action: str = Field(description="The concrete next move, imperative voice.")
    priority: Literal["high", "med", "low"]
    timeline: str = Field(description="When, e.g. 'this week', 'next 30 days'.")
    rationale: str = Field(description="Why — tied to a finding/insight in the brief.")

class Objection(BaseModel):                       # client mode (FR-098)
    objection: str = Field(description="A likely buyer objection.")
    reframe: str = Field(description="Evidence-based reframe drawn from the brief.")

class StrategyOverlay(BaseModel):                 # the strategist's ONLY output (AC-5)
    assessment: str = Field(description="1-2 sentences: where the entity stands + best angle.")
    action_plan: list[RecommendedAction] = Field(default_factory=list)
    objection_handling: list[Objection] = Field(default_factory=list)  # empty in competitor mode

# Battlecard / AccountBrief each gain (default-empty ⇒ byte-identical when off, AC-2/3):
#   assessment: str | None = None
#   action_plan: list[RecommendedAction] = Field(default_factory=list)
# AccountBrief additionally gains:
#   objection_handling: list[Objection] = Field(default_factory=list)
# Legacy how_to_win / recommended_actions: kept, docstring-flagged "superseded by action_plan" (OQ-1)
```

## 3. Playbook loader (`strategy/playbooks.py`, NEW)

A playbook is a Markdown file — the unit an admin edits to reshape strategy without redeploy.

```markdown
---
name: account-strategy
mode: client
description: Default framework for turning an account brief into next moves.
---
## Framework
Rank moves by (deal impact × winnability). Lead with the highest-impact unblocked step...
## Output template
- assessment: standing + the single best angle, ≤ 2 sentences.
- action_plan: 3-5 actions, each {action, priority, timeline, rationale}; rationale cites a finding.
- objection_handling: the 2-3 most likely objections + an evidence-based reframe.
## House rules
- Never restate a raw PRIVATE fact in assessment/action text unless it is already a merged insight.
- No fabricated specifics (names, dates, numbers) not present in the brief.
```

```python
class Playbook(BaseModel):
    name: str
    mode: Literal["competitor", "client"]
    description: str = ""
    body: str                       # framework + output template + house rules (everything after frontmatter)

def load_playbook(path: str | Path) -> Playbook | None:
    """Parse frontmatter + body. Fail-soft: missing/malformed → None (caller records a gap)."""

def discover_playbooks(directory: str | Path) -> list[Playbook]:
    """List valid playbooks in a directory (for the Settings picker)."""
```

Frontmatter parse: split on the first two `---` fences; parse the block with `yaml.safe_load`
(pyyaml already a dependency — see `doctor`). No external dep. The builder injects `playbook.body`
into the strategist instruction via the existing `instruction_suffix` seam.

## 4. Config (`config/schema.py`, `config/defaults.py`)

```python
class StrategyConfig(BaseModel):
    enabled: bool = False                                  # ships dark (AC-3)
    playbook_dir: str = "playbooks"
    competitor_playbook: str = "competitor-counterplay"    # filename stem in playbook_dir
    client_playbook: str = "account-strategy"

# SentinelConfig gains:  strategy: StrategyConfig = Field(default_factory=StrategyConfig)
```

`defaults.py`:
- Seed `strategy.enabled` from `SENTINEL_STRATEGY` (first-boot only; default off).
- Add agent keys `competitor.strategist`, `client.strategist` (`_gen(0.4, 2048)`; **no** `pin_gemini`
  — strategy should follow the reasoning backend / governance, never force cloud).
- Add prompt templates `competitor.strategist` (reads `{battlecard}`), `client.strategist` (reads
  `{account_brief}`). The playbook body is appended at build time, not in the template.

Strategist prompt (client), illustrative:
```
You are a sales strategist. The finished account brief is in {account_brief}. Using ONLY the
facts in that brief, produce a StrategyOverlay: a 1-2 sentence assessment, a prioritized
action_plan, and objection_handling. Follow the framework, output template, and house rules below.
```

## 5. Builder wiring (`agent/modes/_build.py`, `competitor.py`, `client.py`)

A small shared helper keeps both modes DRY:

```python
# _build.py
def maybe_strategist(cfg, mode, *, backend, cloud_allowed) -> Agent | None:
    if not cfg.strategy.enabled:
        return None
    stem = cfg.strategy.competitor_playbook if mode == "competitor" else cfg.strategy.client_playbook
    pb = load_playbook(Path(cfg.strategy.playbook_dir) / f"{stem}.md")
    suffix = f"\n\n{pb.body}" if pb else "\n\n(No playbook loaded — use sound default judgement.)"
    return make_agent(
        cfg, f"{mode}.strategist", name=f"{mode}_strategist",
        output_key="strategy", mode_backend=backend, output_schema=StrategyOverlay,
        instruction_suffix=suffix, cloud_allowed=cloud_allowed,   # tools omitted → tool-free
    )
```

`build_competitor_agent` / `build_client_agent`: after assembling `sub_agents`, `s =
maybe_strategist(...)` and `if s: sub_agents.append(s)`. No other change; signatures already carry
`backend` + `cloud_allowed`.

`config/render.py`: `RESERVED_VARS |= {"battlecard", "account_brief"}`.

## 6. Orchestrator merge (`agent/orchestrator.py`)

```python
def _merge_strategy(artifact, state) -> str:
    """Deterministically merge the strategy overlay onto the artifact. Fail-soft → trace note."""
    raw = state.get("strategy")
    if raw is None:
        return "strategy: none"
    try:
        overlay = _coerce_artifact(raw, StrategyOverlay)
    except Exception as exc:
        return f"strategy: skipped ({type(exc).__name__})"
    artifact.assessment = overlay.assessment
    artifact.action_plan = overlay.action_plan
    if isinstance(artifact, AccountBrief):
        artifact.objection_handling = overlay.objection_handling
    return f"strategy: {len(overlay.action_plan)} actions"
```

Called between `_coerce_artifact(...)` and `writer.write(artifact)`, guarded by
`cfg.strategy.enabled`. The strategist sub-agent is already enumerated by the existing
`for sub in agent.sub_agents` trace loop, so its model label appears automatically (AC-11 visibility).

## 7. Render (`artifacts/writer.py` markdown, `web/render.py`)

Additive, conditional sections (omit when empty → AC-13):
- **Assessment** — one paragraph.
- **Action plan** — a table: Priority · Action · Timeline · Rationale (sorted high→low).
- **Objection handling** (client) — definition list: objection → reframe.

## 8. File-by-file

| File | Change |
|---|---|
| `artifacts/schemas.py` | NEW `RecommendedAction`, `Objection`, `StrategyOverlay`; extend `Battlecard`/`AccountBrief` (default-empty) |
| `strategy/__init__.py`, `strategy/playbooks.py` | NEW `Playbook`, `load_playbook`, `discover_playbooks` |
| `playbooks/account-strategy.md`, `playbooks/competitor-counterplay.md` | NEW shipped playbooks (AC-9) |
| `config/schema.py` | NEW `StrategyConfig`; add `strategy` to `SentinelConfig` |
| `config/defaults.py` | seed `strategy` (off); add `*.strategist` agent keys + prompts |
| `config/render.py` | `RESERVED_VARS += battlecard, account_brief` |
| `agent/modes/_build.py` | NEW `maybe_strategist` helper |
| `agent/modes/competitor.py`, `client.py` | append strategist when enabled |
| `agent/orchestrator.py` | `_merge_strategy` + call (guarded); trace note |
| `artifacts/writer.py` | render assessment/action_plan/objection_handling |
| `web/render.py`, `web/app.py`, `web/settings.py` | Strategy settings section + route + `apply_strategy` |
| `tests/test_strategy.py` | NEW — AC-1..AC-14 |

## 9. Testing

No live LLM/network. Strategist output is faked by seeding session state / a stub model, or by
unit-testing `_merge_strategy` against a hand-built `StrategyOverlay`. Key tests:
- **AC-3** build pipeline with `enabled=False` → no strategist sub-agent; `make_agent` synthesizer
  instruction byte-identical to SENTINEL-001 default (reuse the existing no-regression assertion).
- **AC-5/AC-4** with `enabled=True` → last sub-agent `name=="<mode>_strategist"`,
  `output_schema is StrategyOverlay`, no tools attached.
- **AC-6/AC-8** `load_playbook` on a tmp `.md` parses frontmatter+body; editing the file changes
  `maybe_strategist(...).instruction`; malformed file → `None` (no raise).
- **AC-10** `_merge_strategy(artifact, {"strategy": overlay})` populates fields; absent key → artifact
  unchanged + trace note (NFR-3).
- **AC-11** in `on_prem_required`, strategist model is a vLLM/LiteLlm object (introspection), no
  Gemini — mirror SENTINEL-005's governance test.
- **AC-12** house-rule presence in shipped client playbook + a merge test asserting a private-only
  fact is not duplicated into `assessment` (string check on a crafted overlay is the guard; the rule
  is enforced by prompt, asserted by the shipped playbook containing it).
- **AC-13/14** writer renders/omits sections; Settings POST persists `strategy.*`, no secret; full
  `pytest -q` green; SENTINEL-002/004 tests untouched.

## 10. Rollback

Additive and dark. Default `strategy.enabled=False` ⇒ no strategist is built, no schema field is
populated, the writer/dashboard skip the empty sections, and output is byte-identical to
SENTINEL-004. The increment is a no-op until an operator flips the toggle.
