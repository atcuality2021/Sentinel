# Borrowed from BiltIQ Agent OS — design patterns for Sentinel

Source platform: `/home/atc/Desktop/biltiq-agent-os` (BiltIQ Agent OS). We **borrow patterns, not
code** — Sentinel is ADK-based, ~single-tenant, and stores to SQLite/files (no Mongo/Qdrant/Redis).
Owner direction (2026-06-07): borrow the **memory harness, agent behavior, and automatic skills**.

> Why borrow at all: these subsystems are battle-tested on a real platform. Re-deriving them would
> be slower and worse. We take the shapes that fit an ADK research agent and drop the multi-tenant /
> cluster machinery.

---

## 1. Memory harness  (→ SENTINEL-002)

### What they do
- **Four memory systems as one loop** (`docs/architecture/memory.md`): (1) Knowledge/RAG, (2) Agent
  memory (learnings), (3) Harness working memory (this turn), (4) Session/project memory (MEMORY.md).
  *The law of placement:* a write in the wrong system is the bug.
- **The loop:** turn-start → recall agent-memory + retrieve knowledge → inject into working memory →
  answer → turn-end capture + **extract learnings** + write-back; compaction **promotes** salient
  facts up instead of dropping them; reinforcement (SM-2/Leitner) decays unused memory.
- **Data model** (`memory/schemas.py` `MemoryEntry`): ULID id, `memory_type`
  (fact/preference/entity/relationship/decision/observation), `visibility`
  (**PRIVATE/SCOPE/TENANT**, default PRIVATE), CAS `version`, SM-2 state
  (strength/interval/ease), provenance, confidence, `linked_ids`, `quarantined`.
- **Extraction:** deterministic, zero-token regex `FactExtractor` at turn-end (single tier;
  ADR-012's Tier-2 local-vLLM extractor is *proposed*, not built). Off-latency.
- **Boundary enforcement (the crown jewel):** `store.py` `_entry_visible_to` / `_mongo_visibility_clause`
  filter **every read path** to the caller's allowed visibility + tenant, always excluding
  `quarantined`. Writes are **fail-closed**: an unclassified/tenant-less write is quarantined, never
  silently stored. This is proven anti-leakage discipline.
- **Reinforcement** (`memory/strength.py`): pure SM-2 kernel — POSITIVE diminishing-returns to a
  ceiling, NEGATIVE resets interval, NEUTRAL is a strict no-op (false-negative guard);
  `_reinforce_on_read` ranks by decayed strength, drops below a floor, returns top-k.
- **Working memory** (`agents/context.py` `ContextWindow`): 3-phase adaptive compaction
  (trim tool results @60% → seal completed exchanges @75% → drop oldest @85%).

### Borrow for Sentinel
- **Take:** the four-system mental model; `MemoryEntry` pydantic shape; deterministic regex
  extractor at turn-end; the extract→dedup→store `process_turn` pipeline; the SM-2 `strength` kernel
  + decay-rank-filter recall; `ContextWindow` 3-phase compaction; CAS `MemoryConflictError`.
- **Replace:** 3-value `MemoryVisibility` → **2-value `DataBoundary {PUBLIC, PRIVATE}`**, reusing the
  *exact* "fail-closed default + filter-every-read + quarantine-unclassified" discipline. This makes
  Sentinel's differentiator (public/private separation) enforced in the **memory layer too**, not
  just the tool layer — a finding tagged `private` can never be recalled into a public context.
- **Drop:** tenant_id/scope_id/RBAC, Mongo/Qdrant/Redis, the (unbuilt) LLM extractor tier — though a
  local-vLLM Tier-2 fits Sentinel's on-prem story later (off-latency, fail-soft).
- **Minimal ADK shape:** a `SqliteMemoryStore` + two ADK callbacks — `before_agent_callback`
  recall(query, boundary)→rank→token-budget→inject; `after_agent_callback` extract→dedup→write with
  boundary stamped. Decay/dream run as a scheduled job, not inline.

---

## 2. Agent behavior  (→ folds into SENTINEL-001)

### What they do
- **Declarative agent = `agent.yaml` + `SOUL.md`.** `agents/schema.py` `AgentDefinition` (pydantic):
  identity, `model` override, `soul_path`, `tools` + `tool_permissions`
  (enabled/requires_approval/max_calls_per_turn), `permission_mode`, `skills` + `skill_auto_create`,
  `delegation`, `memory`, budgets (`max_iterations`, `max_tokens_per_turn`, `max_wall_clock_seconds`,
  `max_tool_calls`).
- **SOUL.md** (`agents/soul.py`): markdown H2 sections (Identity / Principles / Style / Expertise /
  Constraints / Security) parsed to typed fields → `to_system_prompt()`. Behavior is editable prose,
  not code. (Sentinel's research-master SOUL already says "always cite sources; separate facts from
  analysis" — literally our requirement.)
- **Loader** (`agents/loader.py`): yaml→validate→merge `extends:` chains→load SOUL→cache.
- **Runtime** builds the system prompt as: SOUL → system_prompt → recalled memory → matched skills →
  user model; budgets + tool gates enforced in the harness turn loop.

### Borrow for Sentinel
- **Take:** `AgentDefinition` (pydantic) + `SOUL.md` typed-section pattern; the **budget** fields +
  a `Budget` model (`is_exhausted`, `subdivide`); the two-phase tool gate
  (enabled/requires_approval/max_calls_per_turn).
- **Drop:** ADK already runs the ReAct loop — do **not** rebuild `AgentHarness`. Drop
  `extends`/inheritance, tier RBAC, the 6-level model-resolution ladder, Tier-0 classifier.
- **Fit into SENTINEL-001:** our `SentinelConfig.agents[...]` becomes an `AgentDefinition`-lite, and
  each agent's prompt becomes a **SOUL-style** template (sections), fed to the ADK agent's
  `instruction`. Budgets map to ADK `before_model_callback`; tool gates to `before_tool_callback`.
  This upgrades 001 from "editable prompt string" to "editable SOUL + budgets + tool policy."

---

## 3. Automatic skills  (→ new SENTINEL-007)

### What they do
- **SKILL.md** = YAML frontmatter (`name`, `description`, `triggers: [...]`, `state`) + markdown
  procedure (`skills/loader.py`, e.g. `skills/web-research/SKILL.md`).
- **Matching** (`skills/registry.py`): triggers regex-matched (whitespace-flexible, case-insensitive)
  against user text, ACTIVE-only; semantic fallback via embeddings.
- **Injection:** matched skills rendered via `to_prompt_block()` and appended to the system prompt.
- **Auto-create** (`skills/creator.py` + `lifecycle.py`): after a run, **off the latency path**, a
  regex `SkillCreator` mines procedural steps from the transcript; if it clears floors (≥3 turns, ≥2
  steps, confidence ≥0.3) it writes a **DRAFT** skill (PRIVATE, provenance-stamped) to a registry +
  store. DRAFT→ACTIVE promotion is gated/manual. Global flag `BILTIQ_SKILLS__ENABLED` (fail-closed).
- **Store:** in-memory registry (fast match) + durable store (survives restart); skills carry SM-2
  strength like memory.

### Borrow for Sentinel
- **Take:** SKILL.md format; trigger-match→`to_prompt_block` injection; DRAFT→ACTIVE lifecycle;
  auto-create off-latency gated by a global flag; provenance stamping; registry + durable store split.
- **Drop:** Qdrant semantic search (use trigger-only or SQLite FTS first), cross-tenant `LearningGate`,
  Mongo store (use SQLite/JSON), skill spaced-repetition (optional).
- **Sentinel-fit move:** stamp each auto-created skill with the **public/private boundary** it was
  learned under (mirror their visibility+provenance), so a skill learned from private data can't be
  applied in a public-only run. ADK shape: `before_agent_callback` matches+injects;
  `after_agent_callback` mines+writes DRAFT SKILL.md + SQLite index; promotion via CLI.

---

## Files to model from (reference, do not copy)
- Runtime: `agents/schema.py`, `agents/loader.py`, `agents/soul.py`, `core/schemas.py` (Budget).
- Skills: `skills/schemas.py`, `skills/loader.py`, `skills/creator.py`, `skills/registry.py`, `skills/lifecycle.py`.
- Memory: `memory/schemas.py`, `memory/store.py` (esp. `_entry_visible_to`, write guard), `memory/extraction.py`, `memory/strength.py`, `memory/dedup.py`, `memory/dream.py`, `agents/context.py`.

## Net effect on the Sentinel backlog
- **SENTINEL-001** gains SOUL.md-style prompts + budgets + tool policy (richer than a bare prompt string).
- **SENTINEL-002** memory harness = the borrowed design above, with `DataBoundary` replacing `MemoryVisibility` (boundary enforced in memory, not just tools).
- **SENTINEL-007 (new)** Automatic Skills.
