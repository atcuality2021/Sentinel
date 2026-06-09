# SENTINEL-001 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered steps. Each ends green (tests pass) before the next. Test IDs map to spec ACs.

---

### Step 1 — Capture golden baselines (no code change yet)
Add `tests/test_config.py` constants snapshotting the **current** built agents' `instruction`
strings and resolved model ids (built via the existing builders) → these defend AC-1 through the
refactor.
**Test:** snapshot test passes against current code.

### Step 2 — `config/schema.py`
Add pydantic models from design §2.1 (`GenerationConfig.merge`, `BackendConfig`, `AgentConfig`,
`PromptTemplate`, `MemoryConfig`, `GovernanceConfig`, `SentinelConfig`). No I/O.
**Test:** instantiate; `GenerationConfig.merge` override-wins; model validates. (AC-5 unit)

### Step 3 — `config/defaults.py`
Lift the four prompt strings + model choices verbatim into `SentinelConfig.default()`. Per-agent
generation defaults per design §2.2. `default_template == template`.
**Test:** `default()` has all 4 prompt keys + agent keys; planner temp==0.2 etc.

### Step 4 — `config/render.py`
`render_prompt` + variable validation + reserved per-agent allow-list.
**Test:** missing required var raises; valid template returns unchanged; unknown `{var}` (not in
allow-list) raises. (AC-6)

### Step 5 — `config/store.py` + `__init__.py`
`config_path`, `load_config`, `save_config`, `get_config` (cached), `set_config`, `reset_config`;
env seeding; self-seed-on-absent.
**Test:** round-trip save/load equality (AC-2); absent file → default written once (AC-3);
`SENTINEL_CONFIG_PATH` honoured.

### Step 6 — `gateway.build_model`
Add the factory; refactor `get_model`/`_gemini`/`_vllm` to delegate; keep signatures.
**Test:** `build_model('gemini','x')=='x'`; `build_model('vllm','m')` → LiteLlm; existing
`test_gateway.py` still green.

### Step 7 — Refactor `competitor.py` to build from config
Introduce `_make_agent`; `build_competitor_agent(backend=None, config=None)`; defaults via
`get_config()`. `public_research` uses `pin_gemini` + `google_search`; synthesizer keeps
`output_schema`.
**Test:** golden test (Step 1) still passes (AC-1); synthesizer has output_schema + no tools (AC-8).

### Step 8 — Refactor `client.py` to build from config
Same pattern; `private_research` present only when connector configured (unchanged logic) and built
from config when present.
**Test:** golden test for client passes; boundary tests pass.

### Step 9 — Extend boundary test for config-pinned grounding
Assert `public_research` resolves to the gemini model id even with `config.backend.default='vllm'`.
**Test:** AC-7.

### Step 10 — Per-agent model + generation resolution tests
Set `agents['synthesizer'].model='gemini-2.5-pro'` and a generation override; assert applied to the
built agent's `model` and `generate_content_config`. Per-run `backend='vllm'` beats config default
for non-pinned agents.
**Test:** AC-4, AC-5, AC-9.

### Step 11 — Orchestrator threading
`run_async(..., config=None)`; pass to builders; add per-agent model to the trace line.
**Test:** trace includes resolved models; existing orchestrator path unaffected (smoke, no live call).

### Step 12 — Housekeeping
`.gitignore += sentinel.config.yaml`; `.env.example` notes `SENTINEL_CONFIG_PATH`; docstrings.
Update `MEMORY.md` (config backbone shipped).
**Test:** full `pytest -q` green (AC-10).

---

## Definition of done
- AC-1..AC-10 all covered by passing tests.
- Default config reproduces current behaviour (golden tests green).
- `sentinel.config.yaml` self-seeds and is gitignored; holds no secrets.
- No `Any`; pydantic validation with clear errors.
- Nothing in the run data-flow or boundary guarantees changed.

## Estimate
~12 atomic steps; foundation for 002/003. No live API calls needed to verify (all structural).
