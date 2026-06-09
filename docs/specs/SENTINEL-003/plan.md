# SENTINEL-003 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered steps; each ends green. Test IDs map to spec ACs. No live LLM in any step.
Settings is a *consumer* of the SENTINEL-001 config API — no changes under `config/`.

---

### Step 1 — `web/settings.py` (pure helpers)
`parse_generation(form_like, *, allow_blank)`, `apply_backends`, `apply_agent`, `apply_prompt`,
`reset_prompt`, `apply_memory`. Bounds: temp [0,2], max_tokens [1,32768], top_p [0,1], top_k ≥1.
All operate on `cfg.model_copy(deep=True)` and return a new config; raise `ValueError` (human msg) on
bad input. `apply_prompt` runs `render_prompt`; `apply_agent` raises on unknown key.
**Test (AC-3/4/5/7):** good/blank/out-of-range/non-numeric generation; bad prompt raises + unchanged;
reset restores `default_template`; unknown agent key raises.

### Step 2 — `render.settings_page` + nav + CSS
New `settings_page(cfg, *, backend, gemini_key_set, ok, err)`. Add `cog` icon, nav entry
`("settings","Settings","cog","/settings")`, and a `textarea` style. Sections: Backends, Generation,
Memory, Agents (7 cards, grouped), Prompts (`<details>` + textarea + vars hint + Save/Reset). Banner
card tinted ok/err. Escape all cfg-derived text. Key shown as a boolean pill only.
**Test (AC-1, NFR-1):** page renders all sections; the literal `GOOGLE_API_KEY` value never appears.

### Step 3 — `GET /settings`
Route reads `get_config()`, `active_backend()`, `bool(os.getenv("GOOGLE_API_KEY"))` → `settings_page`.
Accept `?ok=`/`?err=` for post-redirect banners.
**Test (AC-1):** `GET /settings` 200 + contains "Settings", backend default, a known prompt snippet.

### Step 4 — `POST /settings/backends` + `/generation` + `/memory`
Each: deep-copy live cfg, apply via helper (try/except → err banner), `set_config(cfg, persist=True)`,
re-render with success. Reads back via `get_config`.
**Test (AC-2/3/8):** valid backend/generation/memory POST persists (assert `load_config(path)` shows
new values after `reset_config`); out-of-range generation → err banner + YAML unchanged.

### Step 5 — `POST /settings/agents/{key}`
Parse enabled/model/pin + per-agent generation (`allow_blank=True`); `apply_agent`; commit. Unknown
key → err banner (no crash).
**Test (AC-4):** valid agent POST updates model+gen; blank gen field ⇒ inherits; unknown key → error.

### Step 6 — `POST /settings/prompts/{key}` + `/prompts/{key}/reset`
Validate template via `apply_prompt` (render_prompt) → commit or err; reset via `reset_prompt`.
**Test (AC-5/6/7/9):** invalid template → err + unchanged; valid → saved (default_template kept);
reset restores default; after editing `competitor.synthesizer`, `build_competitor_agent()` instruction
contains the edit (no-restart pickup).

### Step 7 — Housekeeping
Wire the New Run / Backends pages to read `get_config()` where they currently read env, so Settings is
the visible source of truth (where cheap and non-breaking). Docstrings; update `MEMORY.md`.
**Test (AC-10):** full `pytest -q` green; no secret written to YAML (assert on saved file text).

---

## Definition of done
- AC-1..AC-10 covered by passing tests (helpers + routes via TestClient with a tmp config path).
- An admin can change backend/generation/agent/prompt/memory in the UI and the **next run uses it**
  with no restart (validated by the AC-9 build-reflects-edit test).
- Validation is fail-safe: a bad edit shows an error and never corrupts the stored config.
- No secret ever appears in the page HTML or the YAML file.
- Untouched config round-trips byte-equivalently (001 no-regression holds).

## Estimate
~7 atomic steps. Pure presentation/commit over the existing config API; the only real logic is the
validate-before-commit helpers (Step 1), which carry most of the tests.
