# SENTINEL-008 — Research Depth (Two-Tier Extract→Synthesize + Declarative Modes)

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** SENTINEL-001 (`make_agent`/config), 002 (`RunStore`/provenance/delta), 004 (entity
page + "since last run"), 005 (governance — extractor obeys `cloud_allowed`)
**Blocks:** nothing (sequenced last — depth, lower demo-visibility than 009/010)
**Source:** [`../../intelligence-to-action/srs.md`](../../intelligence-to-action/srs.md) FR-081..086 ·
[`business-analysis.md`](../../intelligence-to-action/business-analysis.md) US-A1..A3

---

## 1. Context / problem

Today each mode's `public_research` agent both **gathers** sources and **writes free-text notes** in
one pass, and the synthesizer reads those raw notes (`{public_findings}`) to build the artifact. Two
problems: (1) the synthesizer reasons over unstructured, unbounded text — quality and token cost
suffer, and a single weak source can pollute the synthesis; (2) adding a new research mode means
editing the pipeline builders, not just config. LeadFlow solved (1) with a **two-tier** flow —
a small/cheap model extracts each source into typed notes *before* a stronger model synthesizes — and
(2) by treating a research mode as **data** (sources + prompts + schema + model roles), so a new mode
is a config, not code. We port both patterns — sovereign (the extractor obeys `on_prem_required`) and
**without regression**: with the new path off, competitor and client produce byte-identical output to
SENTINEL-004.

> **Not a solution restatement:** the ask is not "add a model call." It is "ground synthesis in
> structured, per-source extractions (so one bad source can't poison the brief), and make a new
> research mode a declarative config rather than a pipeline edit — all sovereign and regression-free."

## 2. Goal / non-goals

**Goal:**
1. A **two-tier** path: a cheap `extractor` turns gathered sources into typed `Extraction` notes
   **before** synthesis; the synthesizer reads only those structured extractions, never raw page text.
2. **Per-source fail-soft:** a source that can't be extracted becomes a recorded `Gap`; the run
   continues.
3. A **declarative `ResearchModeSpec`** (ordered steps, output schema, model roles); adding a mode
   requires no change to the pipeline engine. Express competitor & client as two specs.
4. **Run versioning/provenance:** persist each run's sources + a version, extending the SENTINEL-002
   run log and the SENTINEL-004 "since last run" delta.
5. Honor SENTINEL-005: the extractor is built via `resolve_model(cloud_allowed=)` (vLLM in
   `on_prem_required`). Two-tier model roles: cheap+strong in cloud, one Gemma on-prem (OQ/A-5).
6. **Ship dark:** `research.two_tier=False` (default) ⇒ the pipeline + every artifact is byte-identical
   to SENTINEL-004 (FR-084 / NFR-7).

**Non-goals:** new external data sources/connectors (006); parallel per-source agent fan-out (single
structured extractor pass this increment — true per-source parallelism is a fast-follow); changing the
artifact schemas (008 changes *how* findings are produced, not their shape); a mode-authoring UI.

## 3. Personas

P1 **Analyst** — a brief grounded in facts, not raw HTML; "what changed since last time". P2 **Admin**
— add a research mode by config. P3 **Compliance** — extraction obeys `on_prem_required`. Engineering
— reuse LeadFlow's shape without its free-text-JSON repair debt (we use pydantic structured output).

## 4. Acceptance criteria (testable, binary)

- [ ] **AC-1** An `Extraction{source: Source, notes: list[str]}` pydantic model exists; the extractor
  agent's `output_schema` yields `list[Extraction]` (via a wrapper model) into state key
  `extractions`. (FR-081)
- [ ] **AC-2** With `research.two_tier=True`, the mode pipeline inserts an `extractor` step **between**
  research and synthesis; the synthesizer prompt reads `{extractions}` (not `{public_findings}`). (FR-081)
- [ ] **AC-3** The extractor model is the configured **cheap** role (`*.extractor` agent; cloud default
  a flash-class model, on-prem the same Gemma); built via `resolve_model(cloud_allowed=)`. (FR-081, FR-099-style)
- [ ] **AC-4** A source the extractor cannot parse is emitted as a `Gap` (boundary preserved), and the
  run completes — proven by a test feeding one good + one unparseable source. (FR-082)
- [ ] **AC-5** A `ResearchModeSpec{name, steps:[StepSpec], output_schema, roles}` exists; a generic
  `build_pipeline(spec, cfg, ...)` builds the `SequentialAgent` from it with no mode-specific code. (FR-083)
- [ ] **AC-6** competitor & client are expressed as two `ResearchModeSpec`s; with `two_tier=False` the
  built pipeline is structurally identical to today (same sub-agent names, order, schemas, tools) and
  produces **byte-identical** output (reuse the SENTINEL-001 no-regression assertion). (FR-084)
- [ ] **AC-7** Adding a third spec (a test-only `notes` mode) yields a working pipeline **without
  editing** `build_pipeline` — asserted by building + introspecting it. (FR-083)
- [ ] **AC-8** Each `RunRecord` persists its `sources: list[Source]` and a `run_seq`/`version`; the
  entity page's "since last run" delta still computes (SENTINEL-004 path intact). (FR-085)
- [ ] **AC-9** Every `Extraction.notes` carries its source's citation + boundary unchanged; the
  boundary invariant (002) holds end-to-end (extractor never crosses boundaries). (FR-086, C-3)
- [ ] **AC-10** In `on_prem_required`, the extractor builds a vLLM object (no Gemini) —
  introspection-proven, like SENTINEL-005. (NFR-3)
- [ ] **AC-11** All existing tests pass; SENTINEL-002 boundary + 003/004 surfaces unchanged; `two_tier`
  off is the default and a no-op. (NFR-7)

## 5. Functional requirements

- **FR-1** `artifacts/schemas.py`: `Extraction` + an `ExtractionSet` wrapper (`extractions:
  list[Extraction]`, `gaps: list[Gap]`) for the extractor's `output_schema`.
- **FR-2** `agent/modes/spec.py` (NEW): `StepSpec`, `ResearchModeSpec`; `build_pipeline(spec, cfg,
  backend, *, cloud_allowed, search_provider, memory_context)` → `SequentialAgent`.
- **FR-3** Express competitor & client as `ResearchModeSpec`s (replacing the bespoke builders' bodies;
  thin builders delegate to `build_pipeline` for back-compat).
- **FR-4** `config/schema.py`: `ResearchConfig{two_tier=False, extract_*}`; add `research` to
  `SentinelConfig`. `defaults.py`: add `*.extractor` agent keys + prompts (cheap role; no `pin_gemini`).
- **FR-5** `config/render.py`: add `extractions` to `RESERVED_VARS`; synthesizer prompts gain a
  variant that reads `{extractions}` when two-tier is on (selected at build time).
- **FR-6** `memory/schema.py`: `RunRecord` gains `sources: list[Source]` + `run_seq:int`;
  `orchestrator._persist_run` populates them; `RunStore` migration adds the columns.
- **FR-7** `web/render.py`: entity page shows the persisted sources/version (additive).

## 6. Non-functional

- **NFR-1** Two-tier adds exactly **one** LLM call (the extractor) per run when enabled. (SRS A-1)
- **NFR-2** Sovereignty structural: extractor via `resolve_model(cloud_allowed=)`; no Gemini in
  `on_prem_required` (introspection). (SRS NFR-3)
- **NFR-3** Deterministic-first/fail-soft: a failed extraction degrades to a Gap; a failed extractor
  call degrades to the legacy single-tier path or a gap-rich artifact — never breaks a run. (SRS NFR-5)
- **NFR-4** Typed; no `Any`, no unjustified `# type: ignore`.
- **NFR-5** Modes are data (declarative); a new mode needs no engine change. (SRS NFR-6)

## 7. Risks

- **R-1 No-regression is hard** — refactoring the builders risks drift. *Mitigation:* `build_pipeline`
  reproduces today's graph exactly when `two_tier=False`; AC-6 asserts byte-identical via the existing
  SENTINEL-001 default-output test. Land the refactor (off) before enabling two-tier.
- **R-2 Extractor adds latency/cost.** *Mitigation:* cheap role (flash/one-Gemma); opt-in; ≤1 call.
- **R-3 Single-pass extractor ≠ true per-source isolation.** *Mitigation:* the extractor records a Gap
  per unparseable source (AC-4); per-source parallel fan-out flagged as a fast-follow, not blocking.
- **R-4 RunRecord migration** on an existing DB. *Mitigation:* additive columns with defaults; reuse
  the `_ensure_schema` pattern; old rows read with empty sources.
- **R-5 Sovereignty regression** via the new extractor. *Mitigation:* built through the 005 seam;
  AC-10 introspection test.

## 8. Open questions

- **OQ-1** Cheap extractor model in cloud — `gemini-2.5-flash` (already the default) vs a smaller
  flash-lite? *Proposed:* reuse `gemini-2.5-flash`; on-prem one Gemma for both tiers (A-5).
- **OQ-2** Single structured-extractor pass vs per-source loop now? *Proposed:* single pass this
  increment (simpler, ≤1 call); per-source fan-out as a fast-follow.
- **OQ-3** Keep the thin `build_competitor_agent`/`build_client_agent` wrappers or have the
  orchestrator call `build_pipeline(spec)` directly? *Proposed:* keep the wrappers (delegating) for a
  smaller diff and stable call sites / tests.
