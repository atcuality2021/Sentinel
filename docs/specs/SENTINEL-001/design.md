# SENTINEL-001 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture overview

Introduce a `sentinel.config` package that owns a typed `SentinelConfig`. The orchestrator and
mode builders stop hardcoding models/prompts and instead **build agents from config**. The gateway
becomes a pure model factory (`(backend, model_id) -> model object`). Nothing else in the data-flow
changes; boundary separation and the per-run backend toggle are preserved.

```
get_config() ──▶ SentinelConfig ──┐
                                   ├─▶ build_competitor_agent(cfg) ─▶ Agent(model, instruction, generate_content_config)
gateway.build_model(backend,id) ──┘                                   (one per pipeline step)
```

## 2. New package: `src/sentinel/config/`

### 2.1 `schema.py` (pydantic models, no `Any`)

```python
class GenerationConfig(BaseModel):
    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    def merge(self, override: "GenerationConfig") -> "GenerationConfig": ...  # override wins per-field

class BackendOption(BaseModel):
    model: str
    api_base: str | None = None

class BackendConfig(BaseModel):
    default: Literal["gemini", "vllm"] = "gemini"
    gemini: BackendOption = BackendOption(model="gemini-2.5-flash")
    vllm: BackendOption = BackendOption(model="google/gemma-3-4b-it",
                                        api_base="http://localhost:8000/v1")

class PromptTemplate(BaseModel):
    template: str
    variables: list[str] = []          # required {vars} the template must contain
    default_template: str | None = None  # shipped default, for "reset"

class AgentConfig(BaseModel):
    enabled: bool = True
    model: str | None = None           # None → backend default (pinned to gemini for public_research)
    pin_gemini: bool = False           # public_research = True (grounding is native)
    generation: GenerationConfig = GenerationConfig()  # per-agent override

class MemoryConfig(BaseModel):         # stub; filled in SENTINEL-002
    entity_memory: bool = True
    retention_days: int = 365
    inject_org_prefs: bool = True

class GovernanceConfig(BaseModel):     # stub; filled in SENTINEL-005
    compliance_mode: Literal["cloud_ok","on_prem_preferred","on_prem_required"] = "cloud_ok"
    audit_log: bool = True
    block_cloud_on_private: bool = False

class SentinelConfig(BaseModel):
    version: int = 1
    backend: BackendConfig = BackendConfig()
    generation: GenerationConfig = GenerationConfig(temperature=0.3, max_output_tokens=2048,
                                                    top_p=0.95, top_k=40)
    agents: dict[str, AgentConfig]     # keys: planner, public_research, private_research, synthesizer
    prompts: dict[str, PromptTemplate] # same keys
    memory: MemoryConfig = MemoryConfig()
    governance: GovernanceConfig = GovernanceConfig()

    @classmethod
    def default(cls) -> "SentinelConfig": ...  # see 2.3
```

Agent keys are shared between competitor and client pipelines where names match; client adds
`private_research`. We key by the **canonical step name** (`planner`, `public_research`,
`private_research`, `synthesizer`) and both modes reuse the relevant subset.

### 2.2 `defaults.py`

Holds the **current** prompt strings (lifted verbatim from `competitor.py`/`client.py`) and the
current model choices, assembled into `SentinelConfig.default()`. Lifting them here is what
guarantees AC-1 (no behaviour change). Each `PromptTemplate.default_template == template` initially.

Default per-agent generation:
| agent | temperature | max_output_tokens |
|---|---|---|
| planner | 0.2 | 1024 |
| public_research | 0.3 | 2048 |
| private_research | 0.3 | 2048 |
| synthesizer | 0.4 | 3072 |

(top_p/top_k inherit global.)

### 2.3 `store.py`

```python
def config_path() -> Path            # SENTINEL_CONFIG_PATH or ./sentinel.config.yaml
def load_config(path=None) -> SentinelConfig   # file → model; if absent, default() + save once
def save_config(cfg, path=None)      # model → YAML (yaml.safe_dump of cfg.model_dump())
def get_config() -> SentinelConfig   # cached singleton (lru/global); reads file once
def set_config(cfg)                  # replace singleton + persist (used by tests + future UI)
def reset_config()                   # clear cache (tests)
```

Env seeding (OQ-1, proposed): on first `default()`, read `SENTINEL_GEMINI_MODEL` / `VLLM_MODEL` /
`SENTINEL_LLM_BACKEND` to seed initial values, then the file is authoritative. `SENTINEL_LLM_BACKEND`
remains honoured as a per-process override in `active_backend()`.

### 2.4 `render.py` (prompt rendering)

```python
def render_prompt(tmpl: PromptTemplate, *, allow_state_vars=True) -> str
```
Validates every declared `variables` entry appears as `{var}` in the template and that the template
contains no undeclared `{var}` except a reserved allow-list per agent (ADK state keys like
`{target}`, `{research_plan}`, `{public_findings}`, `{private_findings}`, `{vertical_context}`).
Returns the template string unchanged for ADK (ADK does the `{state}` injection at run time) — our
job is **validation**, not substitution.

## 3. Gateway refactor (`llm/gateway.py`)

Add a pure factory; keep existing functions as thin wrappers for back-compat:

```python
def build_model(backend: str, model_id: str, api_base: str | None = None) -> object:
    if backend == "vllm":
        return LiteLlm(model=f"hosted_vllm/{model_id}",
                       api_base=api_base or os.getenv("VLLM_API_BASE", ...),
                       api_key=os.getenv("VLLM_API_KEY", "not-needed"))
    return model_id  # gemini → id string

# get_model(backend) keeps working (reads config defaults); resolve_backend/active_backend unchanged
```

## 4. Mode-builder refactor

`build_competitor_agent(backend=None, config=None)` and `build_client_agent(...)`:

For each step, a helper:
```python
def _make_agent(cfg, step, *, mode_backend, name, output_key, tools=None, output_schema=None):
    ac = cfg.agents[step]
    backend = "gemini" if ac.pin_gemini else resolve_backend(mode_backend or cfg.backend.default)
    model_id = ac.model or (cfg.backend.gemini.model if backend=="gemini" else cfg.backend.vllm.model)
    gen = cfg.generation.merge(ac.generation)
    return Agent(
        name=name,
        model=build_model(backend, model_id, cfg.backend.vllm.api_base),
        instruction=render_prompt(cfg.prompts[step]),
        generate_content_config=_to_genai(gen),     # types.GenerateContentConfig(...)
        tools=tools, output_schema=output_schema, output_key=output_key,
    )
```
`_to_genai(gen)` builds `types.GenerateContentConfig` skipping `None` fields. For the synthesizer,
`output_schema` is set and `tools` is None (unchanged), so structured output is preserved (AC-8).
`public_research` config has `pin_gemini=True` and `tools=[google_search]` (AC-7).

## 5. Generation → ADK mapping

`types.GenerateContentConfig(temperature=..., max_output_tokens=..., top_p=..., top_k=...)`, omitting
`None`. ADK passes this to the model. For the vLLM/LiteLlm path, ADK forwards supported fields;
unsupported ones are ignored by LiteLlm (R-1) — acceptable, documented.

## 6. File-by-file change list

| File | Change |
|---|---|
| `src/sentinel/config/__init__.py` | exports `get_config`, `set_config`, `load_config`, `save_config`, `SentinelConfig` |
| `src/sentinel/config/schema.py` | NEW — pydantic models |
| `src/sentinel/config/defaults.py` | NEW — default prompts + `SentinelConfig.default()` |
| `src/sentinel/config/store.py` | NEW — load/save/get/set + path + env seeding |
| `src/sentinel/config/render.py` | NEW — prompt validation/render |
| `src/sentinel/llm/gateway.py` | ADD `build_model`; keep wrappers |
| `src/sentinel/agent/modes/competitor.py` | build from config via `_make_agent` |
| `src/sentinel/agent/modes/client.py` | build from config via `_make_agent` |
| `src/sentinel/agent/orchestrator.py` | pass `config` through; trace shows per-agent model |
| `.gitignore` | add `sentinel.config.yaml` (it's local state, like `.env`) |
| `.env.example` | note `SENTINEL_CONFIG_PATH` |
| `tests/test_config.py` | NEW — AC-1..AC-6, AC-9 |
| `tests/test_boundary.py` | extend for AC-7 (public pinned to gemini via config) |

## 7. Testing strategy

- **Golden/no-regression (AC-1):** build agents from `default()`; assert each sub-agent's
  `instruction` and resolved model id equal the pre-refactor literals (capture them as constants).
- **Round-trip (AC-2/3):** save→load equality; absent-file self-seed writes once.
- **Resolution (AC-4/5/6):** set per-agent model + generation override; assert applied; assert
  prompt-variable validation raises on a missing required var.
- **Boundary (AC-7):** `public_research` model is the gemini id even when `backend.default=vllm`.
- **Structured output (AC-8):** synthesizer still has `output_schema` set and no tools.
- **Override (AC-9):** per-run `backend="vllm"` beats `config.backend.default="gemini"` for
  non-pinned agents.

## 8. Risks & mitigations

Carried from spec §10: R-1 LiteLlm field support (set supported fields, verify on smoke test,
document), R-2 output_schema+generation (test), R-3 prompt `{var}` breakage (validation + reserved
allow-list). All have tests or documented fallbacks.

## 9. Rollback

Pure refactor behind `default()`. If config loading fails, `get_config()` falls back to
`SentinelConfig.default()` and logs — the agent always builds.
