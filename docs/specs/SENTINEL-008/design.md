# SENTINEL-008 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture

Two changes, both gated to preserve byte-identical default behaviour: (1) a declarative
`ResearchModeSpec` + generic `build_pipeline` that *reproduces today's graph* when two-tier is off;
(2) an optional `extractor` step that grounds synthesis in structured per-source notes.

```
build_pipeline(spec, cfg, backend, *, cloud_allowed, search_provider, memory_context)
  steps = spec.steps                                  # declarative (AC-5)
  if cfg.research.two_tier and spec.extractor_step:   # opt-in (AC-2)
        insert extractor before synthesizer
  → SequentialAgent(name=spec.name, sub_agents=[make_agent(step) for step in steps])

two_tier = False  (default):  [planner, public_research, (private_research), synthesizer]   ← today, byte-identical (AC-6)
two_tier = True            :  [planner, public_research, (private_research), extractor, synthesizer']
                                                            │                    │           │
                              research writes raw {public_findings} ──▶ extractor reads them, emits
                              typed {extractions}+gaps (cheap model) ──▶ synthesizer' reads ONLY {extractions} (AC-2,9)
```

**No-regression is the load-bearing property.** `build_pipeline` with `two_tier=False` must emit the
*same* `make_agent(...)` calls (same keys, names, order, tools, schemas, suffixes) the current
`competitor.py`/`client.py` emit. We land that refactor first (pure restructuring, output unchanged),
verified by the SENTINEL-001 default-output test, *then* turn on the extractor behind the flag.

> **As-built reconciliation (2026-06-07).** This triad was authored before SENTINEL-009 (strategist
> in the graph) and SENTINEL-011b (the coordinator's `build_competitor_subagents`/`build_client_subagents`
> split) landed, so two of its assumptions needed adjusting at build time — resolved with a best-of-both
> hybrid that keeps every original guarantee:
>
> 1. **The generic constructor is `build_step_agents`, not `build_pipeline`.** `build_step_agents(spec, …, two_tier=)`
>    is the single source that turns a spec into the flat `list[Agent]`; `build_pipeline` is now a thin
>    wrapper that puts that list in a `SequentialAgent`. This matters because the 011b coordinator needs the
>    *agents*, not the SequentialAgent — so `build_competitor_subagents`/`build_client_subagents` (the
>    coordinator's source) **delegate** to `build_step_agents(two_tier=False)` and map the flat list into
>    their dataclass by `output_key`. The coordinator code is untouched ⇒ zero 011b regression, and there is
>    still exactly one place that constructs `competitor.planner` et al. (Anti-Pattern #1, AC-7 intact).
> 2. **The 009 strategist is appended at the mode-builder level, not as a step.** It is an overlay that reads
>    the finished artifact, not a research step, so it never appears in `ResearchModeSpec.steps`;
>    `competitor.py`/`client.py` append `maybe_strategist(...)` after `build_step_agents(...)`, exactly as
>    before 008. Default graph stays byte-identical (AC-6) whether or not strategy is enabled.
> 3. **Scope:** two-tier is wired for the `SequentialAgent` path. Two-tier *inside* the coordinator's
>    specialists is an explicit fast-follow (the coordinator currently consumes `two_tier=False`).

## 2. Schemas (`artifacts/schemas.py`)

```python
class Extraction(BaseModel):
    source: Source                                  # provenance + boundary preserved (AC-9)
    notes: list[str] = Field(description="Typed, atomic notes distilled from THIS one source.")

class ExtractionSet(BaseModel):                      # the extractor's output_schema (AC-1)
    extractions: list[Extraction] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)    # one per unparseable source (AC-4)
```

Artifact schemas (`Battlecard`/`AccountBrief`) are **unchanged** — 008 changes how findings are
produced, not their shape (keeps 009's overlay + 004's render stable).

## 3. Declarative modes (`agent/modes/spec.py`, NEW)

```python
@dataclass(frozen=True)
class StepSpec:
    agent_key: str                  # e.g. "competitor.planner"
    name: str                       # ADK sub-agent name (stable for tests/trace)
    output_key: str
    tool: Literal["search", "private", None] = None
    output_schema: type[BaseModel] | None = None
    reads_extractions: bool = False # synthesizer variant flag (FR-5)
    role: Literal["plan", "research", "extract", "synthesize"] = "research"

@dataclass(frozen=True)
class ResearchModeSpec:
    name: str                       # "sentinel_competitor" | "sentinel_client"
    steps: list[StepSpec]
    output_schema: type[BaseModel]
    has_private: bool = False        # client: add private_research when boundary configured

COMPETITOR_SPEC = ResearchModeSpec(name="sentinel_competitor", output_schema=Battlecard, steps=[
    StepSpec("competitor.planner", "competitor_planner", "research_plan", role="plan"),
    StepSpec("competitor.public_research", "competitor_public_research", "public_findings",
             tool="search", role="research"),
    StepSpec("competitor.synthesizer", "battlecard_synthesizer", "battlecard",
             output_schema=Battlecard, role="synthesize"),
])
CLIENT_SPEC = ResearchModeSpec(name="sentinel_client", output_schema=AccountBrief, has_private=True, steps=[...])
```

`build_pipeline` walks `steps`, calling the existing `make_agent` with the right tool
(`get_search_tool(provider)` for `search`, `build_private_toolset()` for `private`), schema, and the
`memory_context` suffix on the synthesizer — *exactly* as the bespoke builders do today. The extractor
step is injected from `spec`'s synthesize step (it knows the cheap agent key `<mode>.extractor`).

## 4. Extractor wiring

- New agent keys `competitor.extractor` / `client.extractor` (cheap role, `_gen(0.2, 2048)`, **no**
  `pin_gemini`). Prompt: *"From the gathered notes in `{public_findings}`, produce an ExtractionSet:
  for each distinct source, a list of atomic, factual notes with its Source (boundary + label + url).
  If a source is unreadable, add a Gap with that source's boundary instead of inventing notes."*
- Synthesizer **variant**: when `two_tier`, the builder selects a synthesizer prompt that reads
  `{extractions}` instead of `{public_findings}`. Implemented as a second prompt key
  (`competitor.synthesizer_2t`) or a `note_substitution` swapping the source-of-truth phrase — chosen
  to keep the `two_tier=False` template byte-identical. `RESERVED_VARS += {"extractions"}`.
- Built via `make_agent(cfg, "<mode>.extractor", ..., output_schema=ExtractionSet,
  cloud_allowed=cloud_allowed)` → vLLM in `on_prem_required` (AC-10), no tools.

## 5. Run versioning / provenance (`memory/schema.py`, `store.py`, `orchestrator.py`)

```python
# RunRecord gains:
sources: list[Source] = Field(default_factory=list)   # the run's cited sources (AC-8)
run_seq: int = 0                                       # 1-based per-entity sequence
```
- `RunStore._ensure_schema`: additive columns (`sources` json, `run_seq` int) — old rows default
  empty/0; `_row_to_run` backfills.
- `RunStore.save`: compute `run_seq = len(runs_for(entity)) + 1` (only when `not rec.run_seq`, so an
  explicitly-set seq is preserved); serialize `sources`.
- `orchestrator._persist_run`: collect `artifact.sources` into the record. The "since last run" delta
  (`compute_delta`) is unchanged — it already diffs `finding_texts`.
- Entity page (`web/render.py`): timeline gains a leading `#` (run_seq) column and a trailing `Sources`
  column (additive); a pre-008 row (`run_seq=0`, no sources) shows a neutral dash, never `#0`.

## 6. Config (`config/schema.py`, `defaults.py`)

```python
class ResearchConfig(BaseModel):
    two_tier: bool = False                 # ships dark (AC-6/11)
    extract_max_notes_per_source: int = 8  # bound synthesis input size (AC-A1.2)
# SentinelConfig gains:  research: ResearchConfig = Field(default_factory=ResearchConfig)
```
`defaults.py`: add `competitor.extractor`/`client.extractor` agents + prompts + the synthesizer-2t
prompt variants; seed `research.two_tier` from `SENTINEL_TWO_TIER` (first-boot, default off).

## 7. File-by-file

| File | Change |
|---|---|
| `artifacts/schemas.py` | NEW `Extraction`, `ExtractionSet` (artifacts unchanged) |
| `agent/modes/spec.py` | NEW `StepSpec`, `ResearchModeSpec`, `build_step_agents` (the single constructor) + `build_pipeline` wrapper, COMPETITOR/CLIENT specs |
| `agent/modes/competitor.py`, `client.py` | `build_*_agent` builds via `build_step_agents(SPEC, two_tier=cfg.research.two_tier)` then appends `maybe_strategist`; `build_*_subagents` (011b coordinator source) delegate to `build_step_agents(two_tier=False)` and map the flat list by `output_key` — coordinator untouched |
| `config/schema.py` | NEW `ResearchConfig`; add `research` to `SentinelConfig` |
| `config/defaults.py` | `*.extractor` agents + prompts + synthesizer-2t variants; seed `research` |
| `config/render.py` | `RESERVED_VARS += extractions` |
| `memory/schema.py`, `memory/store.py` | `RunRecord.sources` + `run_seq`; additive migration |
| `agent/orchestrator.py` | populate sources/run_seq on persist (delta path unchanged) |
| `web/render.py` | entity page renders sources + version |
| `tests/test_research_pipeline.py` | NEW — AC-1..AC-11 |

## 8. Testing

No live LLM/network. Extractor/synthesizer outputs seeded into state; pipeline introspected.
- **AC-6 (the critical one)** build competitor/client via `build_pipeline` with `two_tier=False`;
  assert sub-agent names/order/schemas/tools equal the pre-refactor builders, and the synthesizer
  instruction is byte-identical to the SENTINEL-001 default (reuse that existing test).
- **AC-2/3** `two_tier=True` → extractor present between research and synth; extractor `output_schema
  is ExtractionSet`, cheap agent key, no tools; synthesizer reads `{extractions}`.
- **AC-4** feed an `ExtractionSet` with one good + one gap → orchestrator coerces, run completes,
  artifact reflects the gap.
- **AC-5/7** a test-only third `ResearchModeSpec` builds a valid pipeline with no `build_pipeline` edit.
- **AC-8** `RunStore` round-trips `sources`+`run_seq`; `run_seq` increments per entity; delta intact.
- **AC-9/10** extraction notes keep source boundary; in `on_prem_required` extractor model is vLLM
  (introspection), no Gemini.
- **AC-11** full suite green; SENTINEL-002/003/004 untouched; default config = no-op.

## 9. Rollback

Two-stage and additive. Stage 1 (the `build_pipeline` refactor) is output-preserving — verified
byte-identical before merge. Stage 2 (extractor) is behind `research.two_tier=False`. With the flag
off the system is SENTINEL-009 exactly; the new RunRecord columns are inert if unread.
