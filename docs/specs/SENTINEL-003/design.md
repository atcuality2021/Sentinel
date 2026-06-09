# SENTINEL-003 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture overview

Pure presentation + a thin commit path over the SENTINEL-001 config store. No new persistence, no
new models. Each settings section is an independent HTML `<form>` that POSTs to its own endpoint; the
endpoint loads the live config, applies the section's edits to a **deep copy**, validates, and only
then commits via `set_config(cfg, persist=True)`. Validation failure re-renders with an error banner
and never touches the stored config (NFR-2).

```
GET /settings ─▶ render settings_page(get_config())            (AC-1; no secrets, key shown as bool)

POST /settings/<section> ─▶ cfg = get_config().model_copy(deep=True)
                          ─▶ apply edits to cfg.<section>
                          ─▶ validate (render_prompt / numeric bounds)   ──fail──▶ re-render + error
                          ─▶ set_config(cfg, persist=True)  (cache + YAML) ─ok──▶ re-render + success
```

`set_config(persist=True)` already exists (001): it replaces the process cache and writes YAML. Since
the orchestrator and builders read `get_config()` when no explicit config is passed, the **next run
picks up the change with no restart** (AC-9).

## 2. Routes (`web/app.py`)

| Method | Path | Body | Effect |
|---|---|---|---|
| GET | `/settings` | — | render all sections |
| POST | `/settings/backends` | default, gemini_model, vllm_model, vllm_api_base | update `cfg.backend` |
| POST | `/settings/generation` | temperature, max_output_tokens, top_p, top_k | update `cfg.generation` |
| POST | `/settings/agents/{key}` | enabled, model, pin_gemini, temperature, max_output_tokens, top_p, top_k | update `cfg.agents[key]` |
| POST | `/settings/prompts/{key}` | template | validate + update `cfg.prompts[key].template` |
| POST | `/settings/prompts/{key}/reset` | — | restore `template = default_template` |
| POST | `/settings/memory` | entity_memory, retention_days, inject_org_prefs | update `cfg.memory` |

All POSTs return the re-rendered `/settings` HTML with a `?ok=...` / `?err=...` banner (PRG-style:
the handlers render directly for simplicity, matching the existing `/run` pattern).

Unknown `{key}` → render the page with an error banner (no crash, AC-4).

## 3. Validation helpers (`web/settings.py` — new, pure)

Keep parsing/validation out of the route bodies and unit-testable:

```python
def parse_generation(form, *, allow_blank: bool) -> GenerationConfig   # bounds-checked; blank→None
def apply_backends(cfg, default, gemini_model, vllm_model, vllm_api_base) -> SentinelConfig
def apply_agent(cfg, key, enabled, model, pin_gemini, gen) -> SentinelConfig   # KeyError → ValueError
def apply_prompt(cfg, key, template) -> SentinelConfig   # runs render_prompt; ValueError on bad edit
def reset_prompt(cfg, key) -> SentinelConfig
def apply_memory(cfg, entity_memory, retention_days, inject_org_prefs) -> SentinelConfig
```

- **Bounds:** temperature ∈ [0, 2], max_output_tokens ∈ [1, 32768], top_p ∈ [0, 1], top_k ≥ 1.
  Out-of-range / non-numeric → `ValueError` with a human message.
- `parse_generation(allow_blank=True)` (per-agent): blank field ⇒ `None` (inherit global).
  `allow_blank=False` (global defaults): all four required and concrete.
- `apply_prompt` calls `render_prompt(PromptTemplate(template=..., variables=existing.variables))` so
  an edit that drops a required `{var}` or adds an unknown one is rejected (AC-5); on success it keeps
  the original `variables` and `default_template` (AC-6, reset still works).
- Every `apply_*` returns a **new** config (operates on `model_copy(deep=True)`); the caller commits.

## 4. Rendering (`web/render.py`)

One new function `settings_page(cfg, *, backend, gemini_key_set, ok="", err="")`. Sections rendered
as `.card`s reusing existing form CSS (`label.lbl`, `input`, `select`, `.row2`, `.seg`, `.btn`):

- **Backends** — segmented Cloud/On-prem default (reuse `.seg`), gemini model, vllm model + api_base,
  a read-only "GOOGLE_API_KEY: set/not set" pill (boolean only — NFR-1).
- **Generation defaults** — 4 number inputs in a grid.
- **Memory** — entity_memory checkbox, retention_days, inject_org_prefs checkbox.
- **Agents** — one compact `.card` per agent key (7) with enabled/pin checkboxes, model input, and 4
  generation inputs (blank = inherit). Grouped under "Competitor" / "Client" headings.
- **Prompts** — one `<details>` per agent prompt (collapsed) with a `<textarea>`, an allowed-`{vars}`
  hint, a Save button, and a Reset-to-default button (separate form). The two builder notes
  (`client.private_note_*`) are shown read-only / or editable too — editable, they're real prompts.

Add a `textarea` style to CSS and a `cog` icon + `("settings","Settings","cog","/settings")` to
`_NAV`. Banner: a small `.card` tinted ok/err at the top of the content.

All `cfg`-derived strings escaped via `html.escape` (NFR-5).

## 5. File-by-file

| File | Change |
|---|---|
| `src/sentinel/web/settings.py` | NEW — pure parse/apply/validate helpers |
| `src/sentinel/web/render.py` | NEW `settings_page` + `cog` icon + textarea CSS + nav entry |
| `src/sentinel/web/app.py` | 7 routes (1 GET, 6 POST); read `get_config()`; commit via `set_config` |
| `tests/test_settings.py` | NEW — AC-1..AC-10 (helpers + routes via TestClient) |

No changes to `config/` (001) — Settings is a consumer of its existing API.

## 6. Testing strategy

- **Helpers (pure, fast):** `parse_generation` bounds (good/blank/out-of-range/non-numeric);
  `apply_prompt` good vs bad (`render_prompt` raises); `reset_prompt`; `apply_agent` unknown key.
- **Routes (TestClient + tmp config):** set `SENTINEL_CONFIG_PATH` to a tmp file and `reset_config()`
  per test; GET renders; each POST persists (assert YAML on disk + `load_config` reflects it); invalid
  POST leaves config unchanged + shows error; **no-secret** assertion (`GOOGLE_API_KEY` value never in
  HTML or YAML).
- **No-regression / AC-9:** after editing the competitor synthesizer prompt via POST, building the
  competitor agent yields the edited instruction.

## 7. Risks & mitigations

- **R-1 brick-via-bad-save:** validate-before-commit + per-prompt Reset + `get_config` fail-soft.
- **R-2 backend display drift:** Settings edits `cfg.backend.default` (authoritative for runs); the
  cosmetic env-driven topbar pill reconciliation is a noted follow-up, called out in the page copy.

## 8. Rollback

Additive. Deleting the routes/page leaves 001/002 untouched. `reset_config()` + deleting
`sentinel.config.yaml` restores shipped defaults.
