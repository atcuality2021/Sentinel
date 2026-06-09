# SENTINEL-008 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered; each step ends green. No live LLM/network (state seeded, models introspected). Test
IDs → spec ACs. **Land the output-preserving refactor (Steps 1-2) before enabling two-tier.** Baseline
assumes SENTINEL-009 + 010 green.

---

### Step 1 — Declarative spec + generic `build_pipeline` (output-preserving)
NEW `agent/modes/spec.py`: `StepSpec`, `ResearchModeSpec`, `build_pipeline(spec, cfg, backend, *,
cloud_allowed, search_provider, memory_context)`; define `COMPETITOR_SPEC`, `CLIENT_SPEC`. **No
behaviour change yet** — `build_pipeline` reproduces the current graph.
**Test (AC-5):** `build_pipeline(COMPETITOR_SPEC, ...)` returns a `SequentialAgent` with sub-agents
named/ordered exactly as today; `CLIENT_SPEC` adds `private_research` iff boundary configured.

### Step 2 — Delegate the bespoke builders + prove byte-identical
`competitor.py`/`client.py` bodies call `build_pipeline(SPEC, ...)`; signatures unchanged.
**Test (AC-6):** built pipelines equal the pre-refactor structure; synthesizer instruction
byte-identical to the SENTINEL-001 default (reuse that no-regression test); full suite green
(zero behaviour change merged before any flag work).

### Step 3 — Extraction schemas
`artifacts/schemas.py`: `Extraction{source, notes}`, `ExtractionSet{extractions, gaps}`. Artifact
schemas untouched.
**Test (AC-1):** models construct; `ExtractionSet` defaults empty; `Extraction.source` carries a
`Boundary`.

### Step 4 — Config + extractor agents/prompts + reserved var
`config/schema.py`: `ResearchConfig{two_tier=False, extract_max_notes_per_source}` + `research` on
`SentinelConfig`. `defaults.py`: `competitor.extractor`/`client.extractor` agents (cheap, no
`pin_gemini`) + extractor prompts + synthesizer-2t prompt variants; seed `research` from env.
`render.py`: `RESERVED_VARS += extractions`.
**Test (AC-11):** default cfg `research.two_tier is False`, round-trips YAML; new prompts validate;
default-output test still byte-identical.

### Step 5 — Inject extractor when two_tier (opt-in)
`build_pipeline`: when `cfg.research.two_tier`, insert the `<mode>.extractor` step
(`output_schema=ExtractionSet`, no tools, `cloud_allowed`) before synthesis, and select the
synthesizer-2t prompt that reads `{extractions}`.
**Test (AC-2/3/10):** `two_tier=True` → extractor between research and synth, cheap key, no tools,
`output_schema is ExtractionSet`; synth reads `{extractions}`; in `on_prem_required` extractor model
is vLLM (introspection), no Gemini.

### Step 6 — Orchestrator coerces extractions + fail-soft
`orchestrator`: when two_tier, read `extractions` state, coerce to `ExtractionSet`; on missing/bad,
degrade (trace note) to the legacy path or a gap-rich artifact — never raise. (The synthesizer
already consumed extractions in-graph; this step is the coerce/trace + fail-soft guard.)
**Test (AC-4):** an `ExtractionSet` with one good + one gap → run completes, gap surfaced; a malformed
extractions state → trace note, run not broken.

### Step 7 — Run versioning / provenance
`memory/schema.py`: `RunRecord.sources: list[Source]` + `run_seq:int`. `memory/store.py`: additive
columns in `_ensure_schema`; `_row_to_run` backfill; `save` computes `run_seq`. `orchestrator
._persist_run`: populate sources/run_seq. `web/render.py`: entity page shows them.
**Test (AC-8):** `RunStore` round-trips sources+run_seq; `run_seq` increments per entity; `compute_delta`
("since last run") unchanged; old-row read defaults empty/0.

### Step 8 — Declarative-mode proof + housekeeping + no-regression
Add a test-only third `ResearchModeSpec` (`notes` mode) built with no `build_pipeline` edit (AC-7).
Docstrings; update `MEMORY.md`, `specs/README.md` (008 → Built; program complete), `.remember`.
**Test (AC-7/11):** third spec builds + introspects valid; full `SENTINEL_DATA_DIR=$(mktemp -d)
.venv/bin/python -m pytest -q` green; SENTINEL-002 boundary + 003/004 untouched.

---

## Definition of done

AC-1..AC-11 green. A new research mode is a declarative spec (no engine edit). With
`research.two_tier=True`, synthesis is grounded in typed per-source `Extraction`s (one bad source →
a Gap, not a poisoned brief), produced by a cheap model that in `on_prem_required` runs on
Gemma/vLLM with zero Gemini. Each run persists its sources + version; the "since last run" delta still
works. With the flag off (default) the system is byte-identical to SENTINEL-009/004.

## Estimate

~8 steps. Heaviest + riskiest: the output-preserving `build_pipeline` refactor (Steps 1-2) — land it
green and byte-identical *before* the extractor. Two-tier + versioning (Steps 5-7) are additive and
dark. Sequenced last (depth, low demo-visibility); 009/010 carry the challenge story.
