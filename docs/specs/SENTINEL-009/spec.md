# SENTINEL-009 — Strategy & Action Plan (Sovereign Playbook Overlay)

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** SENTINEL-001 (config/`make_agent`), 002 (memory/boundary), 004 (artifact render),
005 (`resolve_model(cloud_allowed=)` governance seam)
**Blocks:** SENTINEL-010 (focus list can cite an action plan); demo "research → **action**" narrative
**Source:** [`../../intelligence-to-action/srs.md`](../../intelligence-to-action/srs.md) FR-091..099 ·
[`business-analysis.md`](../../intelligence-to-action/business-analysis.md) US-B1..B4

---

## 1. Context / problem

Sentinel today **produces an artifact and stops.** A run yields a cited, boundary-separated
`Battlecard` or `AccountBrief` that answers *"what did we find?"* — but not *"so what do I do?"*.
The pilot user (a BD lead at a regulated SMB) still reads the brief, decides the next move by gut,
and re-derives strategy every morning. Every cloud incumbent (Klue, Crayon, Clay, ZoomInfo, 6sense,
Kompyte) already ships recommended/next-best actions and objection handling — so this is **parity we
must reach to look credible**, not novelty. The *novelty* is delivering it **sovereign** (the action
layer never egresses to a cloud LLM in `on_prem_required`) and **editable as data** (an admin tunes
the strategy framework by editing a Markdown playbook — no redeploy), which none of them offer.

The artifact schema reflects the gap: `AccountBrief.recommended_actions` is `list[str]` (a flat list
of sentences, not sortable/schedulable items) and there is no `assessment`, no structured action
plan, and no objection handling. We close that without disturbing the (proven, cited) research half.

> **Not a solution restatement:** the ask is not "add a recommendations field." It is "make the
> agent's output executable — sortable, scheduled, with a cited rationale — and let an admin shape
> the judgment behind it without shipping code."

## 2. Goal / non-goals

**Goal:**
1. Add a structured, sortable **action plan** (`{action, priority, timeline, rationale}`) and a
   one-line **assessment** to both artifacts; add **objection handling** to client mode.
2. Produce them via a separate **tool-free `strategist` sub-agent** that reads the finished artifact
   and a runtime-loaded **Markdown playbook** (framework + output template + house rules).
3. Make the playbook **admin-editable without redeploy** — editing the `.md` changes the next run.
4. Honor SENTINEL-005 sovereignty: in `on_prem_required` the strategist runs on **vLLM/Gemma only**
   (zero Gemini), structurally — reuse `resolve_model(cloud_allowed=)`.
5. **Ship dark:** the strategy step is gated by `strategy.enabled` (default `False`); with it off, the
   pipeline + every artifact field is byte-identical to SENTINEL-004 (no regression).

**Non-goals:** auto-sending / writing outreach (006 connectors — here we *recommend*, a human acts);
a playbook authoring UI (edit the file; UI is a later increment); tool-using strategist that
re-researches (default is tool-free over already-gathered findings, OQ-6); priority scoring / focus
list (that is SENTINEL-010); deprecating the legacy `recommended_actions`/`how_to_win` fields (kept
this increment, flagged for a later migration).

## 3. Personas

P1 **Analyst / BD lead** — wants executable, sortable next moves with a cited reason, and (client)
anticipated objections with reframes. P2 **Admin** — encodes house strategy as editable playbooks.
P3 **Compliance** — the action layer must obey `on_prem_required` (no cloud egress, provable).

## 4. Acceptance criteria (testable, binary)

- [ ] **AC-1** `RecommendedAction{action:str, priority:Literal["high","med","low"], timeline:str,
  rationale:str}` and `Objection{objection:str, reframe:str}` exist as pydantic models. (FR-091/098)
- [ ] **AC-2** `Battlecard` and `AccountBrief` each gain `assessment: str|None=None` and
  `action_plan: list[RecommendedAction]=[]`; `AccountBrief` also gains
  `objection_handling: list[Objection]=[]`. All default-empty. (FR-091/092/098)
- [ ] **AC-3** With `strategy.enabled=False` (default), the built pipeline has **no** strategist
  sub-agent and the synthesized artifact is byte-identical to SENTINEL-004 (legacy fields only,
  new fields at their empty defaults). (NFR-7)
- [ ] **AC-4** With `strategy.enabled=True`, the mode pipeline appends a `strategist` sub-agent whose
  `output_key="strategy"` and whose toolset is empty (`tools` not set / `[]`). (FR-095, OQ-6)
- [ ] **AC-5** The strategist emits a `StrategyOverlay{assessment, action_plan, objection_handling}`
  via the agent's **pydantic `output_schema`** — no free-text-JSON repair layer. (FR-093)
- [ ] **AC-6** A **playbook** is a Markdown file with YAML frontmatter (`name`, `mode`, `description`)
  + body (framework + output template + house rules); `load_playbook(path)` parses it into a typed
  `Playbook{name, mode, description, body}`; a malformed/missing file fails soft to a recorded gap,
  never an exception that kills the run. (FR-094)
- [ ] **AC-7** The selected playbook's `body` is injected into the strategist instruction at build
  time (via the existing `instruction_suffix`/`note_substitutions` seam). (FR-095)
- [ ] **AC-8** Editing the playbook `.md` (no code change) changes the strategist's rendered
  instruction on the next build — proven by a test that edits a temp playbook and asserts the new
  text appears in the agent instruction. (FR-096)
- [ ] **AC-9** Two playbooks ship: `account-strategy.md` (client) and `competitor-counterplay.md`
  (competitor), discoverable from the configured `strategy.playbook_dir`. (FR-097)
- [ ] **AC-10** The orchestrator **deterministically merges** the `strategy` overlay onto the artifact
  before writing: `artifact.assessment`, `artifact.action_plan`, and (client) `objection_handling`
  are populated from the overlay; the synthesizer-produced findings/sources/gaps are unchanged. (FR-091/092)
- [ ] **AC-11** In `on_prem_required`, the strategist's resolved model is a vLLM object (no Gemini
  object constructed) — provable by introspection, identical guarantee to SENTINEL-005. (FR-099, NFR-3)
- [ ] **AC-12** The strategist respects the boundary invariant: in competitor mode the overlay is
  derived from PUBLIC-only findings; in client mode a house rule forbids copying a raw PRIVATE fact
  into the (public-renderable) `assessment`/`action_plan` text without it already being a merged
  insight. (C-3)
- [ ] **AC-13** The Markdown artifact writer + the dashboard render `assessment`, `action_plan` (as a
  priority/timeline/rationale table) and `objection_handling` when present; absent ⇒ those sections
  are omitted (no empty headers). (FR-091/092/098)
- [ ] **AC-14** All existing tests pass; SENTINEL-002 boundary invariant + 003/004 surfaces unchanged.
  New Settings **Strategy** section persists `strategy.*` to YAML; no secret written. (NFR-7, NFR-4)

## 5. Functional requirements

- **FR-1** `artifacts/schemas.py`: add `RecommendedAction`, `Objection`, `StrategyOverlay`; extend
  `Battlecard`/`AccountBrief` with the default-empty fields (AC-1/2).
- **FR-2** `strategy/playbooks.py` (NEW): `Playbook` model, `load_playbook(path)` (frontmatter parse,
  fail-soft), `discover_playbooks(dir)`; ship `playbooks/account-strategy.md` +
  `playbooks/competitor-counterplay.md`.
- **FR-3** `config/schema.py`: `StrategyConfig{enabled=False, playbook_dir, competitor_playbook,
  client_playbook}`; add `strategy` to `SentinelConfig`. `defaults.py`: seed (off), add
  `competitor.strategist` / `client.strategist` agent keys + prompt templates.
- **FR-4** `agent/modes/_build.py` / `competitor.py` / `client.py`: when `strategy.enabled`, append a
  tool-free `strategist` built via `make_agent(..., output_schema=StrategyOverlay,
  instruction_suffix=<playbook body>, cloud_allowed=cloud_allowed)`.
- **FR-5** `config/render.py`: add `battlecard`, `account_brief` to `RESERVED_VARS` (strategist reads
  the finished artifact from state).
- **FR-6** `agent/orchestrator.py`: read the `strategy` state key, coerce to `StrategyOverlay`, merge
  onto the artifact before `writer.write`; add the strategist to the trace; fail-soft (overlay missing
  ⇒ artifact written without strategy, run not broken).
- **FR-7** `artifacts/writer.py` (markdown) + `web/render.py`: render the three new sections.
- **FR-8** `web/settings.py` + `app.py` + `render.py`: Settings **Strategy** section (enabled toggle,
  playbook_dir, per-mode playbook select); POST `/settings/strategy`.

## 6. Non-functional

- **NFR-1** ≤ 1 extra LLM call per brief (one strategist turn, tool-free). (SRS NFR-1)
- **NFR-2** Sovereignty is **structural**: strategist built through `resolve_model(cloud_allowed=)`;
  `on_prem_required` ⇒ no Gemini object — introspection-proven, not prompt. (SRS NFR-3)
- **NFR-3** Deterministic-first: a strategist LLM failure degrades to the artifact **without** a
  strategy overlay (run still ships); never breaks a completed research run. (SRS NFR-5)
- **NFR-4** No secrets in config/code/HTML (playbooks carry no secrets; `strategy.*` is non-secret).
- **NFR-5** Typed contracts; no `Any`, no unjustified `# type: ignore`.
- **NFR-6** Playbooks editable without redeploy (the differentiator). (SRS NFR-6)

## 7. Risks

- **R-1 Schema drift breaks no-regression.** New artifact fields could change synthesizer output.
  *Mitigation:* fields are default-empty and populated **only** by the separate strategist+merge, never
  the synthesizer; AC-3 asserts byte-identical output when disabled.
- **R-2 Sovereignty regression** — strategist sneaks a cloud model in. *Mitigation:* built via the
  SENTINEL-005 seam; AC-11 introspection test per this increment.
- **R-3 Private leak via strategy text** (client mode). *Mitigation:* house rule in the playbook +
  AC-12; the strategist reasons over the *already boundary-tagged* merged brief, mirroring
  `merged_insights`.
- **R-4 Playbook overlay vs ADK tool loop** — overlay bypasses tools (cleaner reasoning, staler
  context). *Mitigation:* tool-free is the recorded default (OQ-6 / A-2); a tool-enabled variant is a
  later option if briefs lack fresh data.
- **R-5 Gemma weak at structured strategy.** *Mitigation:* same `output_schema` + function-calling
  path SENTINEL-005 already proved on Gemma; assessment kept short; fail-soft (NFR-3).

## 8. Open questions

- **OQ-1** Deprecate legacy `recommended_actions: list[str]` (AccountBrief) / `how_to_win: list[str]`
  (Battlecard) now, or keep for one increment? *Proposed:* **keep**, flag in a docstring; migrate when
  the dashboard fully consumes `action_plan`.
- **OQ-2** Playbook storage: repo `playbooks/` vs data-dir (seeded)? *Proposed:* repo-level
  `playbooks/`, path configurable via `strategy.playbook_dir`; simplest path to "edit → next run."
- **OQ-3** Per-mode single playbook vs a selectable set? *Proposed:* one per mode this increment
  (config names the file); a picker on the run form is a fast-follow.
