"""Graders (SENTINEL-012 §10.1) — the code grader (Step 5) and the LLM-as-judge (Step 12).

``code_grade(artifact, ...) -> GradeReport`` runs deterministic checks over a produced artifact.
No LLM and — by default — no network, so it is the fast half of the eval loop, safe on every
artifact. ``citations_resolve`` is a pure format check unless a ``resolver`` is supplied (the
eval-runner path), where it enforces real URL reachability; ``claim_support`` ties each finding to a
declared source. ``model_grade(...)`` is the slow half: an independent judge model scores the
artifact on a five-axis rubric (network/inference; used by the runner and on sampled production).

Checks split into HARD (block — a hard failure means the artifact must not be presented) and SOFT
(flag only). HARD = schema_valid, citations_present, boundary_clean, sovereign (design §10.1).

The grader is intentionally **artifact-shape-agnostic**: it scans the artifact's ``model_dump()``
recursively for boundary tags and text, so the same function grades a Battlecard today and a
ComparisonMatrix / SelfProfile in Phase 2 with no changes.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable

from pydantic import BaseModel

from sentinel.artifacts.schemas import Boundary, GradeReport, RubricScore

# Core banned vocabulary (AGENT_RULES.md § Banned vocabulary; canonical list with rationale lives in
# docs/architecture/anti-patterns.md). Soft check — a hype word flags but does not block.
BANNED_VOCAB: frozenset[str] = frozenset(
    {"cutting-edge", "revolutionary", "empowering", "seamless", "future-ready"}
)

# A failing HARD check sets ``passed=False`` and is listed in ``hard_failures``; soft checks only
# populate ``checks`` so a reviewer/UI can flag them.
#
# ``citations_resolve`` is HARD (design §10.1: citation integrity blocks) — a public citation that
# points nowhere is a dangling source and must not be presented. ``claim_support`` is SOFT: a real
# LLM may state a finding whose source object is not duplicated verbatim into the artifact-level
# ``sources[]``; we flag that for review rather than hard-blocking an otherwise-cited artifact.
HARD_CHECKS: frozenset[str] = frozenset(
    {"schema_valid", "citations_present", "citations_resolve", "boundary_clean", "sovereign"}
)


# --------------------------------------------------------------------------- #
# Recursive scanners over a plain (model_dump) structure
# --------------------------------------------------------------------------- #
def _collect_boundaries(obj) -> set[str]:
    """Every ``boundary`` value anywhere in the dumped artifact (sources + per-finding sources)."""
    found: set[str] = set()
    if isinstance(obj, dict):
        b = obj.get("boundary")
        if isinstance(b, str):
            found.add(b)
        for v in obj.values():
            found |= _collect_boundaries(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _collect_boundaries(v)
    return found


def _collect_strings(obj) -> list[str]:
    """Every string value anywhere in the dumped artifact (for the banned-vocab scan)."""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _collect_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _collect_strings(v)
    return out


def _collect_sources(obj) -> list[dict]:
    """Every Source-shaped dict anywhere in the dump (a dict carrying both ``boundary`` and ``label``).

    Catches artifact-level ``sources[]`` *and* per-finding ``source`` objects in one pass, so the
    citation checks are artifact-shape-agnostic exactly like the boundary/vocab scanners."""
    found: list[dict] = []
    if isinstance(obj, dict):
        if "boundary" in obj and "label" in obj:
            found.append(obj)
        for v in obj.values():
            found += _collect_sources(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _collect_sources(v)
    return found


def _collect_finding_sources(obj) -> list[dict]:
    """Every ``source`` dict that hangs off a Finding-shaped dict (one carrying ``text`` + ``source``)."""
    found: list[dict] = []
    if isinstance(obj, dict):
        if "text" in obj and isinstance(obj.get("source"), dict):
            found.append(obj["source"])
        for v in obj.values():
            found += _collect_finding_sources(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _collect_finding_sources(v)
    return found


def _source_key(src: dict) -> tuple:
    return (src.get("boundary"), src.get("label"), src.get("url"))


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #
def _check_schema_valid(artifact) -> bool:
    """The artifact is a pydantic model whose own dump re-validates. Catches a malformed artifact
    built via ``model_construct`` (validation bypassed) or a non-model passed by mistake."""
    if not isinstance(artifact, BaseModel):
        return False
    try:
        type(artifact).model_validate(artifact.model_dump())
        return True
    except Exception:
        return False


def _check_boundary_clean(dump: dict, allowed_boundaries: Iterable[Boundary] | None) -> bool:
    """No data crossed a boundary the artifact is not allowed to carry (e.g. a PRIVATE source in a
    competitor/public-only artifact). ``None`` ⇒ no constraint declared ⇒ pass."""
    if allowed_boundaries is None:
        return True
    allowed = {b.value if isinstance(b, Boundary) else str(b) for b in allowed_boundaries}
    return _collect_boundaries(dump) <= allowed


def _is_cloud_model(model) -> bool:
    """True if ``model`` is a cloud (Gemini) model object.

    ``gateway.build_model`` returns a bare model-id string for the Gemini backend and a ``LiteLlm``
    bound to a vLLM endpoint for on-prem. So a plain string is a cloud model; a LiteLlm whose
    underlying model id names gemini is too (defensive)."""
    if isinstance(model, str):
        return True
    return "gemini" in str(getattr(model, "model", "")).lower()


def _check_sovereign(models: Iterable[object] | None, cloud_allowed: bool) -> bool:
    """Under on_prem (``cloud_allowed=False``), NO built model may be a cloud/Gemini object.

    ``cloud_allowed=True`` ⇒ cloud is policy-permitted ⇒ pass. ``models=None`` ⇒ not introspected
    at this call site (runtime relies on the structural ``resolve_model`` guarantee; the eval path
    passes the built models to actually verify)."""
    if cloud_allowed or models is None:
        return True
    return not any(_is_cloud_model(m) for m in models)


def _is_wellformed_url(url) -> bool:
    """A public citation needs a real http(s) URL with a host — not empty, not a bare token."""
    if not isinstance(url, str):
        return False
    u = url.strip()
    return u.startswith(("http://", "https://")) and "." in u[8:]


def _check_citations_resolve(dump: dict, resolver: Callable[[str], bool] | None) -> bool:
    """Every PUBLIC source carries a resolvable citation; PRIVATE sources need no URL.

    Default (``resolver=None``) is a **pure, network-free** format check — a public source whose URL
    is missing/empty/malformed is a dangling citation and fails (this keeps ``code_grade`` safe to run
    on every artifact, AC-18). When a ``resolver`` is supplied (the eval-runner path), each public URL
    must additionally pass it (e.g. an HTTP HEAD < 400) — that is where real reachability is enforced.
    Vacuously True when the artifact cites no public sources."""
    publics = [s for s in _collect_sources(dump) if s.get("boundary") == Boundary.PUBLIC.value]
    if not publics:
        return True
    for s in publics:
        url = s.get("url")
        if not _is_wellformed_url(url):
            return False
        if resolver is not None and not resolver(url):
            return False
    return True


def _check_claim_support(dump: dict) -> bool:
    """Every finding's cited source is one the artifact actually lists in its top-level ``sources[]``.

    Catches a finding that cites a source the artifact never declares (an unsupported/orphan claim).
    Soft by design (see HARD_CHECKS note). Vacuously True when there are no findings."""
    finding_srcs = _collect_finding_sources(dump)
    if not finding_srcs:
        return True
    declared = {_source_key(s) for s in (dump.get("sources") or [])}
    return all(_source_key(s) in declared for s in finding_srcs)


def _check_required_fields(artifact, required_fields: Iterable[str] | None) -> bool:
    if required_fields is None:
        return True
    return all(getattr(artifact, name, None) not in (None, "", [], {}) for name in required_fields)


def _check_no_banned_vocab(strings: list[str], banned: Iterable[str] | None) -> bool:
    terms = {t.lower() for t in (banned if banned is not None else BANNED_VOCAB)}
    blob = " ".join(strings).lower()
    return not any(t in blob for t in terms)


# --------------------------------------------------------------------------- #
# Public entry
# --------------------------------------------------------------------------- #
def code_grade(
    artifact,
    *,
    allowed_boundaries: Iterable[Boundary] | None = None,
    required_fields: Iterable[str] | None = None,
    models: Iterable[object] | None = None,
    cloud_allowed: bool = True,
    banned_vocab: Iterable[str] | None = None,
    resolver: Callable[[str], bool] | None = None,
) -> GradeReport:
    """Deterministically grade ``artifact``. Returns a :class:`GradeReport` whose ``passed`` is True
    iff no HARD check failed. Pure by default: no LLM, no network (AC-18). Passing ``resolver`` opts
    the ``citations_resolve`` check into real URL reachability (the eval-runner path)."""
    dump = artifact.model_dump() if isinstance(artifact, BaseModel) else {}
    strings = _collect_strings(dump)

    checks: dict[str, bool] = {
        # HARD
        "schema_valid": _check_schema_valid(artifact),
        "citations_present": len(list(getattr(artifact, "sources", []) or [])) > 0,
        "citations_resolve": _check_citations_resolve(dump, resolver),
        "boundary_clean": _check_boundary_clean(dump, allowed_boundaries),
        "sovereign": _check_sovereign(models, cloud_allowed),
        # SOFT
        "claim_support": _check_claim_support(dump),
        "required_fields": _check_required_fields(artifact, required_fields),
        "gaps_recorded": isinstance(getattr(artifact, "gaps", None), list),
        "no_banned_vocab": _check_no_banned_vocab(strings, banned_vocab),
    }
    hard_failures = sorted(k for k in checks if k in HARD_CHECKS and not checks[k])
    return GradeReport(
        passed=not hard_failures, grader="code", hard_failures=hard_failures, checks=checks
    )


# --------------------------------------------------------------------------- #
# LLM-as-judge (the slow half of the eval loop — network/inference)
# --------------------------------------------------------------------------- #
RUBRIC_KEY = "rubric"                 # state/output key the judge writes its RubricScore under
_RUBRIC_AXES = ("relevance", "faithfulness", "completeness", "actionability", "persona_fit")


def rubric_to_score(rubric: RubricScore) -> float:
    """Collapse the five 1-5 axes into one 0-1 aggregate (mean axis ÷ 5). A perfect 5/5/5/5/5 → 1.0,
    an all-3 → 0.6. Used as the comparable scalar for baseline diffing in the runner."""
    total = sum(getattr(rubric, axis) for axis in _RUBRIC_AXES)
    return round(total / (5 * len(_RUBRIC_AXES)), 4)


async def model_grade(
    artifact,
    *,
    objective: str,
    sources: Iterable[object] | None = None,
    cfg=None,
    backend: str | None = None,
    cloud_allowed: bool = True,
    pass_threshold: float = 0.6,
    trace: list[str] | None = None,
) -> GradeReport:
    """LLM-as-judge: score ``artifact`` against ``objective`` + the ``sources`` it was allowed to cite.

    Builds an **independent** judge (its own ``eval.judge`` config key — anti self-grading, §10.1) as a
    tool-free reasoner that honours sovereignty exactly like every other agent (no Gemini object under
    ``cloud_allowed=False``; the judge can be the 26B on-prem). Returns a model :class:`GradeReport`
    whose ``score`` is the 0-1 rubric aggregate, ``checks`` flag each axis ≥3, and ``notes`` is the
    judge's justification. ``passed`` is ``score >= pass_threshold`` — soft by nature: the model grade
    informs promotion (Step 12 runner), it does not by itself block a Result the way ``code_grade`` does.
    """
    # Lazy imports: graders.py is imported by the orchestrator's Result path, so importing the agent
    # stack at module top would risk an import cycle. The judge is only built when actually grading.
    from sentinel.agent import orchestrator as orch
    from sentinel.agent.modes._build import make_agent
    from sentinel.config import get_config
    from google.adk.agents.run_config import StreamingMode

    cfg = cfg or get_config()
    trace = trace if trace is not None else []
    dump = artifact.model_dump() if isinstance(artifact, BaseModel) else artifact
    src_dumps = [s.model_dump() if isinstance(s, BaseModel) else s for s in (sources or [])]

    judge = make_agent(
        cfg, "eval.judge", name="eval_judge", output_key=RUBRIC_KEY,
        mode_backend=backend, output_schema=RubricScore, cloud_allowed=cloud_allowed,
    )  # tools omitted → tool-free: the judge cannot fetch new facts, it scores only what it is shown
    state = await orch.run_step(
        judge, message_text="Score the artifact against the objective.",
        seed_state={
            "objective": objective,
            "artifact_json": json.dumps(dump, default=str),
            "sources_json": json.dumps(src_dumps, default=str),
        },
        streaming=StreamingMode.SSE, trace=trace,
    )
    rubric = RubricScore.model_validate(state[RUBRIC_KEY])
    score = rubric_to_score(rubric)
    checks = {axis: getattr(rubric, axis) >= 3 for axis in _RUBRIC_AXES}
    return GradeReport(
        passed=score >= pass_threshold, grader="model", hard_failures=[],
        checks=checks, score=score, notes=rubric.justification,
    )
