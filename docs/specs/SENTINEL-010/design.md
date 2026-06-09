# SENTINEL-010 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture

A pure-Python scoring layer over the data SENTINEL-002/004 already persist. No LLM, no network. One
registry, one engine, one persisted snapshot, one read surface.

```
/focus  (web)
  └─ for entity in RunStore().entities():                       ← SENTINEL-004 read-model
        score = compute_account_priority(entity, allowed_boundaries={PUBLIC,PRIVATE})
                  ├─ ctx = PriorityContext(runs=RunStore.runs_for(e),
                  │                         memory=MemoryStore.recall(e, allowed_boundaries),  ← boundary choke-point (AC-10)
                  │                         now=utcnow())
                  ├─ for name,(weight,fn,default) in REGISTRY:  ← single source of truth (AC-6)
                  │        try:  raw = fn(ctx)            # ∈ [0,1]
                  │        except: raw = default; note failure (AC-4)
                  │        breakdown[name] = raw
                  ├─ score = clamp( Σ (raw · normalized_weight) · 100 , 0, 100)   (AC-3,5)
                  ├─ tier  = hot|warm|cold  by config thresholds
                  └─ reasons = templated from the cited findings/memory behind the top signals (AC-9)
        PriorityStore.save(record)                              ← persisted, auditable (AC-11)
     sort desc by score → render ranked list + per-row reasons + breakdown drill-down
```

**The boundary guarantee is inherited, not re-implemented (NFR-3/AC-10):** signals only ever see
`ctx.memory`, which came from `MemoryStore.recall(entity, allowed_boundaries)` — the *same* choke-point
that enforces the SENTINEL-002 invariant. A public-only call passes `{PUBLIC}`; `private_engagement`
then sees zero PRIVATE entries and contributes 0, and no private fact can reach a reason string.

## 2. Registry + primitives (`priority/signals.py`, NEW)

```python
SignalFn = Callable[["PriorityContext"], float]   # returns a raw score in [0,1]

@dataclass(frozen=True)
class _Signal:
    name: str
    weight: float
    fn: SignalFn
    default: float = 0.0

REGISTRY: dict[str, _Signal] = {}                 # the ONE registry (AC-6)

def register_signal(name, weight, fn, *, default=0.0) -> None:
    REGISTRY[name] = _Signal(name, weight, fn, default)

# --- reusable primitives (AC-7) ---
def normalize(value, low, high, invert=False) -> float:
    if high == low: return 0.0
    x = (value - low) / (high - low)
    x = min(1.0, max(0.0, x))
    return 1.0 - x if invert else x

def half_life_decay(age_days, half_life) -> float:   # 1.0 at age 0, 0.5 at one half-life
    return 0.5 ** (age_days / half_life) if half_life > 0 else 0.0
```

**Weights are config-overridable:** `register_signal` sets a *default* weight; the engine overlays
`cfg.priority.weights[name]` when present (admin tuning, no redeploy — NFR-5).

### Seed signals (AC-8) — all over existing data

| Signal | Raw score | Source | Boundary |
|---|---|---|---|
| `recency` | `half_life_decay(days_since_last_run, cfg.recency_half_life_days)` | `RunStore.latest_for` | public |
| `new_material` | `normalize(len(latest.finding_texts not in prior), 0, 8)` | `RunStore.runs_for` (delta) | public |
| `volume` | `normalize(entity_summary.runs, 0, 10)` | `EntitySummary` | public |
| `private_engagement` | `normalize(count of PRIVATE ctx.memory, 0, 10)` | `ctx.memory` (filtered) | **private-gated** |
| `competitor_move` | recency of `recent_developments`-type findings | `ctx.memory` (FINDING) | public |

Each signal is a tiny function `def _recency(ctx) -> float: ...`, registered at import. A bad/empty
input returns the neutral default rather than raising (belt-and-suspenders with the engine's isolation).

## 3. Engine (`priority/engine.py`, NEW)

```python
@dataclass
class PriorityContext:
    entity: str
    runs: list[RunRecord]                 # newest-first
    memory: list[MemoryEntry]             # already boundary-filtered
    now: datetime

class Reason(BaseModel):
    text: str                             # templated, e.g. "No new research in 34 days"
    signal: str
    source_label: str = ""
    source_url: str | None = None
    boundary: DataBoundary = DataBoundary.PUBLIC

class PriorityScore(BaseModel):
    entity: str
    score: float                          # 0-100
    tier: Literal["hot", "warm", "cold"]
    breakdown: dict[str, float]           # signal → raw [0,1]
    reasons: list[Reason]
    computed_at: datetime

def compute_account_priority(entity, *, allowed_boundaries=frozenset({PUBLIC, PRIVATE}),
                             now=None, config=None) -> PriorityScore:
    ...
```

- **Normalization (AC-3):** `total = sum(effective_weights); w_i /= total`. Empty registry ⇒ score 0.
- **Isolation (AC-4):** per-signal `try/except` → `default`, append a `Reason(text="signal X
  unavailable", signal=X)` only to the trace/breakdown note, not the user reasons.
- **Clamp (AC-5):** `score = min(100.0, max(0.0, weighted_sum * 100))`.
- **Tiering:** `hot` if `score >= cfg.hot_threshold`, `warm` if `>= cfg.warm_threshold`, else `cold`.
- **Reasons (AC-9):** generated by each signal's small reason-template using the cited datum behind it
  (e.g. recency → the last run date; private_engagement → "N private touchpoints", boundary=PRIVATE).
  Only the top-contributing signals produce user-facing reasons (keeps the row readable).

## 4. Persistence (`priority/store.py`, NEW — same SQLite file, OQ-1)

A `priority` table in the SENTINEL-002 DB (`data_dir()/...`): `entity, score, tier, breakdown(json),
reasons(json), computed_at`. `PriorityStore.save(PriorityScore)` and `latest_for(entity)`. Reuses the
`_connect`/`_ensure_schema` pattern from `memory/store.py`. Auditable history = one row per compute.

## 5. Config (`config/schema.py`, `defaults.py`)

```python
class PriorityConfig(BaseModel):
    enabled: bool = True
    weights: dict[str, float] = Field(default_factory=dict)     # name → override; empty = registry defaults
    hot_threshold: float = 66.0
    warm_threshold: float = 33.0
    recency_half_life_days: float = 14.0

# SentinelConfig gains:  priority: PriorityConfig = Field(default_factory=PriorityConfig)
```
No new prompts, no new agent keys (this increment has **no LLM**). No secrets.

## 6. Read surface (`web/app.py`, `web/render.py`)

- **`/focus`** route: compute (or read latest) every entity's score, sort desc, render rows:
  `display_name · score · tier · top reasons`, each reason linking to its finding/run; a "breakdown"
  expander shows the per-signal raw × weight. Reuses the SENTINEL-004 Accounts read-model + styling.
- **Dashboard card** "Top 5 to focus on" linking to `/focus` (OQ-2).
- The operator view passes full `{PUBLIC,PRIVATE}`; a future public export passes `{PUBLIC}` and the
  same code drops private reasons (AC-10) — no separate path.

## 7. File-by-file

| File | Change |
|---|---|
| `priority/__init__.py` | NEW — exports `compute_account_priority`, `register_signal`, primitives |
| `priority/signals.py` | NEW — `REGISTRY`, `register_signal`, `normalize`, `half_life_decay`, seed signals |
| `priority/engine.py` | NEW — `PriorityContext`, `Reason`, `PriorityScore`, `compute_account_priority` |
| `priority/store.py` | NEW — `PriorityStore` (same DB), `save`/`latest_for` |
| `config/schema.py` | NEW `PriorityConfig`; add `priority` to `SentinelConfig` |
| `config/defaults.py` | (no prompts/agents) — `priority` via default factory; optional env seed for `enabled` |
| `web/app.py`, `web/render.py` | `/focus` route + dashboard card + breakdown drill-down |
| `tests/test_priority.py` | NEW — AC-1..AC-13 |

## 8. Testing

Pure functions ⇒ fast, hermetic, no mocks beyond a seeded tmp DB + injected `now`.
- **AC-2** repeated `compute_account_priority` on a fixed seeded DB ⇒ identical `score`.
- **AC-3** register two signals weight {2,2}; assert score == same signals at {1,1}.
- **AC-4** register a signal whose fn raises ⇒ engine returns a score, breakdown notes the failure.
- **AC-5** weights/values that would exceed 100 ⇒ clamped to 100.
- **AC-7** `normalize`/`half_life_decay` boundary values (0, mid, >range, invert; age 0 → 1, age =
  half_life → 0.5).
- **AC-10** seed PRIVATE memory for an entity; `compute_account_priority(e, {PUBLIC})` ⇒ no PRIVATE
  reason + `private_engagement == 0`; `{PUBLIC,PRIVATE}` ⇒ it contributes.
- **AC-11** `PriorityStore.save` then `latest_for` round-trips breakdown+reasons.
- **AC-12** time the single-entity compute < 200 ms (generous; pure code).
- **AC-13** full suite green; SENTINEL-002 boundary + 004 index tests untouched; `/focus` returns 200.

## 9. Rollback

Additive. `/focus` is a new route; no existing page or schema changes behaviour. `priority.enabled`
can hide the dashboard card. Removing the route + `priority/` package returns the system to
SENTINEL-009 exactly (the new SQLite table is inert if unused).
