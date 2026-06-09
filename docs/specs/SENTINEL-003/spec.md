# SENTINEL-003 — Settings UI

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** SENTINEL-001 (`SentinelConfig` + persistence), SENTINEL-002 (`MemoryConfig`)
**Blocks:** — (quality-of-life; unlocks self-serve tuning for the pilot)

---

## 1. Context / problem

SENTINEL-001 externalized every runtime knob — backends, per-agent model/prompt/generation, memory
— into a persisted `SentinelConfig` (`sentinel.config.yaml`). But the **only** way to change it today
is to hand-edit YAML and restart. A pilot admin (non-engineer) cannot tune a prompt, switch the
default backend, raise a token limit, or turn entity memory off without touching files. The config
layer was built to be edited by a UI; that UI does not yet exist.

## 2. Goal / non-goals

**Goal:** A `/settings` page in the dashboard that **views and edits the live `SentinelConfig`** —
backends, global generation defaults, per-agent settings, prompts (with reset-to-default), and
memory — validates edits before saving, persists to YAML, and refreshes the running process so the
**next run uses the new config** without a restart.

**Non-goals:**
- No auth / multi-user / RBAC (single-operator pilot; SENTINEL-005 governance owns audit).
- No editing of secrets (API keys stay in env — the page *shows whether* a key is set, never its value).
- No new config fields — this edits what 001/002 already defined (governance editing → 005).
- No live model probing / "test this backend" button (could be a later nicety).

## 3. Personas

P2 **Admin** (primary — tunes the agent for the pilot), P1 **Analyst** (reads current settings to
understand why an output looks the way it does), P3 **Compliance** (sets memory retention / disables
entity memory).

## 4. User stories

- **US-3.1** As an Admin, I can change the **default backend** (Cloud·Gemini ⇄ On-prem·Gemma) and the
  model ids / vLLM API base, and the next run uses them.
- **US-3.2** As an Admin, I can edit the **global generation defaults** (temperature, max tokens,
  top_p, top_k) within safe bounds.
- **US-3.3** As an Admin, I can edit a **per-agent** override (enabled, model, pin-to-Gemini, and that
  agent's generation) for any of the 7 agents.
- **US-3.4** As an Admin, I can **edit a prompt** for any agent and **reset it to the shipped default**;
  a broken edit (missing required `{var}` or unknown `{var}`) is rejected with a clear message and the
  old prompt is kept.
- **US-3.5** As a Compliance officer, I can toggle **entity memory** and set **retention days**.
- **US-3.6** As any user, I can see **whether `GOOGLE_API_KEY` is set** (boolean, never the value).

## 5. Acceptance criteria (testable, binary)

- [ ] **AC-1** `GET /settings` renders the current config: backend default + models, generation
  defaults, per-agent rows, every prompt, and memory settings. No secret values are shown.
- [ ] **AC-2** `POST /settings/backends` with a valid default+models persists to YAML **and** updates
  the in-process config; re-reading config (fresh process / `reset_config`) returns the new values.
- [ ] **AC-3** `POST /settings/generation` clamps/validates numbers (temperature 0–2, max_output_tokens
  1–32768, top_p 0–1, top_k ≥ 1); out-of-range or non-numeric input is rejected with an error and the
  stored config is unchanged.
- [ ] **AC-4** `POST /settings/agents/{key}` updates that agent's enabled/model/pin_gemini/generation;
  an unknown agent key is a 404-style error, not a crash.
- [ ] **AC-5** `POST /settings/prompts/{key}` with an **invalid** template (missing/unknown `{var}`)
  is rejected (`render_prompt` error surfaced), and the stored prompt is unchanged.
- [ ] **AC-6** `POST /settings/prompts/{key}` with a valid template saves it; `default_template` is
  preserved so reset still works.
- [ ] **AC-7** `POST /settings/prompts/{key}/reset` restores the prompt to its `default_template`.
- [ ] **AC-8** `POST /settings/memory` updates `entity_memory` / `retention_days` / `inject_org_prefs`.
- [ ] **AC-9** After any successful save, a subsequent agent build reflects the change (e.g. edited
  synthesizer prompt appears in the built agent's instruction).
- [ ] **AC-10** All existing tests still pass; saving never writes a secret to the YAML file.

## 6. Functional requirements

- **FR-1** Read the live config via `get_config()`; render an editable form per section.
- **FR-2** Each section has its own POST endpoint that mutates a copy, validates, then commits via
  `set_config(cfg, persist=True)` (updates cache + writes YAML).
- **FR-3** Prompt edits run through `render_prompt` for validation before commit (reuse 001).
- **FR-4** Generation inputs are coerced to numbers and bounds-checked; empty field ⇒ "inherit"
  (stored as `None`) for per-agent generation; global defaults must be concrete.
- **FR-5** Validation failure re-renders the page with the error banner and the **unsaved** edits in
  context; the persisted config is untouched.
- **FR-6** Success re-renders with a success banner.
- **FR-7** Settings nav item added to the sidebar.

## 7. Non-functional

- **NFR-1 (no secrets)** The YAML never contains keys; the page shows only a boolean "key set".
- **NFR-2 (fail-soft)** A corrupt save attempt never leaves the cache/file in a half-written state
  (validate fully before `set_config`).
- **NFR-3 (no-regression)** Untouched config round-trips byte-equivalently (001 YAML round-trip holds).
- **NFR-4** Server-rendered HTML forms, no JS framework (consistent with the existing dashboard).
- **NFR-5** Typed; no `Any`; all user text escaped (no XSS via a prompt/model field echoed back).

## 8. Out of scope

Auth, audit log (→005), governance editing (→005), connector/OAuth config (→006), live backend
health probe, prompt versioning/history.

## 9. Dependencies

SENTINEL-001 (`get_config`/`set_config`/`save_config`/`reset_config`, `render_prompt`,
`SentinelConfig` models), SENTINEL-002 (`MemoryConfig`), FastAPI form handling (already used).

## 10. Risks

- **R-1** A bad save bricks the agent. *Mitigation:* validate-before-commit; `get_config` already
  fails soft to `default()`; "reset to default" escape hatch per prompt.
- **R-2** Backend default in config vs the env-driven `active_backend()` display drift. *Mitigation:*
  Settings is explicit that it edits the *config default*; document the relationship; runs already use
  `cfg.backend.default`. Full reconciliation of the cosmetic topbar pill is a noted follow-up.

## 11. Open questions

- **OQ-1** One big "Save all" vs per-section saves? *Proposed:* per-section (smaller blast radius, a
  prompt typo doesn't lose backend edits).
- **OQ-2** Show prompt `variables`/`default_template` to the admin? *Proposed:* show the allowed
  `{vars}` as a hint under each editor; keep `default_template` behind the Reset button.
