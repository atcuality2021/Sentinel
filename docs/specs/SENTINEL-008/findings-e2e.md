# SENTINEL-008 — End-to-End Test Findings (2026-06-07)

Live e2e run against the real backends (Gemma-4-12B @ `gemma.atcuality.com`, Gemini `gemini-2.5-flash`
for `google_search` grounding). These are findings the **hermetic** test suite cannot surface because
they only appear with a real model + real web snippets.

## What passed (single-tier — the default, ships on)

| Run | Mode | Backend | Result |
|---|---|---|---|
| 1 | competitor / Stripe | vLLM Gemma-12B (+ Gemini grounding) | ✅ battlecard written, 12 public findings stored, priority **hot (74)**, "first run" |
| 2 | competitor / Stripe (repeat) | same | ✅ battlecard, 17 findings, delta **+17 / −12**, priority **hot (80)**, `run_seq → 2` |

The whole production path works live end-to-end: planner → public_research (Gemini-grounded search) →
synthesizer (Gemma) → deterministic memory persist → "since last run" delta → deterministic priority
recompute → artifact write. Sovereignty routing, the boundary split, and provenance all held.

## Findings (two-tier path — ships **dark**, needs hardening before enable)

Two-tier (`research.two_tier=True`) is wired correctly — the extractor *does* fire — but the live run
exposed three failure modes, all of which currently **abort the whole run** instead of degrading:

- **F1 — extractor output truncation.** At `max_output_tokens=2048`, Gemma's `ExtractionSet` JSON was
  cut off mid-string over ~9 sources. ADK's `validate_schema` (inside `__maybe_save_output_to_state`)
  then raised `pydantic.ValidationError` — *before* our fail-soft `_merge_extraction_gaps` could run.
- **F2 — context-window overflow.** Bumping the budget to 4096 overflowed Gemma's **16,384-token**
  context when DuckDuckGo returned verbose snippets (input 12,289 + output 4,096 > 16,384) →
  `litellm.ContextWindowExceededError`. So neither 2048 nor 4096 is correct in isolation; the real fix
  bounds the extractor's **input**, not just its output.
- **F3 — no graceful degrade.** Any extractor failure (F1, F2, a 503, or malformed JSON) aborts the
  run. Because the two-tier synthesizer reads only `{extractions}`, there is no fallback to raw
  `{public_findings}`. **This is the load-bearing fix:** two-tier must degrade to single-tier on any
  extractor error, so enabling it can never make a run *less* reliable than the default.

Adjacent findings (not two-tier-specific):

- **F4 — transient Gemini 503s abort the run.** `gemini-2.5-flash` returned `503 UNAVAILABLE` ("high
  demand") on the grounding step with no model-level retry/fallback. A production agent should retry
  with backoff and/or fall back to a non-Gemini search provider.
- **F5 — pre-008 persisted configs lack the new agent keys.** A `sentinel.config.yaml` written before
  008 has no `competitor.extractor` / `client.extractor` entries, so enabling two_tier on it
  `KeyError`s in `make_agent`. Need a config-migration/back-fill step (merge missing default agents +
  prompts on load).

## Recommended hardening increment (SENTINEL-008.1, before enabling two-tier)

1. **Fail-soft two-tier (F3, highest value).** Wrap the extractor step so an extractor error makes the
   pipeline fall back to single-tier (synthesizer reads `{public_findings}`). Probably: keep the
   single-tier synthesizer prompt available and select it at merge time when `{extractions}` is absent
   or unparseable. Net effect: two-tier is a pure upside — never a new failure surface.
2. **Bound extractor input (F1/F2).** Cap `{public_findings}` fed to the extractor (e.g. top-N sources
   / char budget tied to the model context window) so input + output always fit. Surface the cap in
   the trace (no silent truncation).
3. **Model-call resilience (F4).** Retry transient 5xx with backoff; honor `search.onprem_fallback` to
   swap providers when the cloud grounding model is unavailable.
4. **Config back-fill (F5).** On load, merge any missing default agent/prompt keys into an older config.

Until these land, **two-tier stays dark** and the single-tier default — proven above — is what ships.

## SENTINEL-008.1 — hardening landed (2026-06-07, 272 tests green)

- **F3 fixed (the umbrella).** `orchestrator.run_async` now factors the build+run into `_execute_pipeline`
  and wraps it: if a two-tier run raises for *any* reason, it retries **once** with two-tier forced off
  (`cfg.model_copy(deep=True)`, `research.two_tier=False`) and records `two-tier failed (…); fell back to
  single-tier` in the trace. Because the fallback catches every exception class, it neutralises the
  *user-facing* impact of **F1, F2, and F4** — an extractor problem can no longer abort a run; the worst
  case is one wasted attempt then a normal single-tier brief. A single-tier run has no fallback and
  propagates (proven by `test_single_tier_failure_propagates`).
- **F5 fixed.** `config.store.load_config` runs `_backfill_defaults`: any default agent/prompt key missing
  from a loaded (e.g. pre-008) config is added via `setdefault` — never overwriting an admin edit. An old
  config can now enable two-tier without a `KeyError`.
- **Still open (smaller, not blocking enable):** bounding the extractor's *input* (F1/F2 at the source, so
  the happy path doesn't even need the fallback) and explicit model-call retry/backoff (F4). Tracked for a
  follow-up; the fail-soft net makes them optimisations rather than correctness fixes.

With F3+F5 in, two-tier is safe to enable: it can only ever match or improve the single-tier result.
