"""Eval runner (SENTINEL-012 §10.2, Step 12).

Run a candidate (a spec/prompt under test) over a golden set, ``code_grade`` + ``model_grade`` each
case, aggregate to one comparable score, and diff against a stored baseline → ``promote | block |
hold``. This is the improvement loop's gate: an improving change promotes, a regressing one blocks,
and any artifact that breaks a HARD code gate blocks outright regardless of the judge.

**Hermetic by injection.** The runner never calls a model or the network itself: the caller supplies
``produce`` (an async ``EvalCase -> artifact``) and, optionally, ``judge`` (an async
``(artifact, EvalCase) -> GradeReport`` — typically a thin wrapper around :func:`model_grade`). That
keeps the runner deterministic and unit-testable; the real wiring (run a skill / ``run_plan``) plugs
into ``produce`` later without touching this file (AP #1 — the runner is generic over how artifacts
are produced).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sentinel.artifacts.schemas import Boundary, GradeReport
from sentinel.eval.graders import code_grade

_SETS_DIR = Path(__file__).resolve().parent / "sets"

# A code hard-failure is unrecoverable: the artifact is broken (bad schema / dangling citation /
# boundary leak / non-sovereign), so its case scores zero no matter what the judge thinks.
_HARD_FAIL_SCORE = 0.0
# A code-clean case with no model grade scores a full pass — the code gate is all we asked of it.
_CODE_CLEAN_SCORE = 1.0


@dataclass(frozen=True)
class EvalCase:
    """One golden case: an objective + the input to produce an artifact from, plus grading context."""

    case_id: str
    domain: str
    capability: str
    objective: str
    input: dict = field(default_factory=dict)
    allowed_boundaries: tuple[Boundary, ...] | None = None
    expect: dict = field(default_factory=dict)

    @staticmethod
    def from_dict(raw: dict) -> "EvalCase":
        bounds = raw.get("allowed_boundaries")
        boundaries = tuple(Boundary(b) for b in bounds) if bounds is not None else None
        return EvalCase(
            case_id=raw["case_id"],
            domain=raw["domain"],
            capability=raw.get("capability", ""),
            objective=raw["objective"],
            input=raw.get("input", {}),
            allowed_boundaries=boundaries,
            expect=raw.get("expect", {}),
        )


@dataclass(frozen=True)
class CaseResult:
    """The graded outcome for one case: its code grade, optional model grade, and blended 0-1 score."""

    case_id: str
    code: GradeReport
    model: GradeReport | None
    score: float


@dataclass(frozen=True)
class EvalReport:
    """The aggregate verdict over a set: mean score vs baseline → promote | block | hold."""

    domain: str
    mean_score: float
    baseline_score: float | None
    verdict: str  # "promote" | "block" | "hold"
    results: list[CaseResult]
    regressions: list[str]  # case_ids that hard-failed the code gate

    def summary(self) -> str:
        base = "—" if self.baseline_score is None else f"{self.baseline_score:.3f}"
        tail = f" (regressions: {', '.join(self.regressions)})" if self.regressions else ""
        return (
            f"[{self.domain}] {self.verdict.upper()} — mean {self.mean_score:.3f} vs baseline {base} "
            f"over {len(self.results)} case(s){tail}"
        )


def load_eval_set(domain: str, *, root: Path | None = None) -> list[EvalCase]:
    """Load every ``*.json`` golden case under ``eval/sets/<domain>/``, sorted by filename.

    A file may hold one case object or a list of cases. Missing directory → empty list (a domain with
    no golden set yet is not an error — it just has nothing to gate on)."""
    base = (root or _SETS_DIR) / domain
    if not base.is_dir():
        return []
    cases: list[EvalCase] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text())
        rows = data if isinstance(data, list) else [data]
        cases.extend(EvalCase.from_dict(r) for r in rows)
    return cases


def _case_score(code: GradeReport, model: GradeReport | None) -> float:
    """Blend the two grades into one comparable scalar. A code hard-failure dominates (→ 0)."""
    if not code.passed:
        return _HARD_FAIL_SCORE
    if model is not None and model.score is not None:
        return model.score
    return _CODE_CLEAN_SCORE


def _verdict(mean_score: float, baseline: float | None, *, margin: float, any_hard_fail: bool) -> str:
    """promote if clearly better than baseline; block if clearly worse or any hard gate broke; else hold."""
    if any_hard_fail:
        return "block"
    if baseline is None:
        return "promote"  # first run establishes the baseline
    if mean_score > baseline + margin:
        return "promote"
    if mean_score < baseline - margin:
        return "block"
    return "hold"


async def run_eval_set(
    cases: Sequence[EvalCase],
    produce: Callable[[EvalCase], Awaitable[object]],
    *,
    judge: Callable[[object, EvalCase], Awaitable[GradeReport]] | None = None,
    baseline: float | None = None,
    margin: float = 0.0,
    resolver: Callable[[str], bool] | None = None,
    cloud_allowed: bool = True,
) -> EvalReport:
    """Drive ``produce`` over ``cases``, grade each, and diff the mean against ``baseline``.

    ``judge`` is the optional model grader (omit for a code-only gate). ``margin`` is the dead-band
    that keeps noise from flapping the verdict — only a move beyond ±margin promotes/blocks. ``resolver``
    flows into ``code_grade`` so the runner path can enforce real citation reachability."""
    results: list[CaseResult] = []
    for case in cases:
        artifact = await produce(case)
        code = code_grade(
            artifact, allowed_boundaries=case.allowed_boundaries,
            resolver=resolver, cloud_allowed=cloud_allowed,
        )
        model = await judge(artifact, case) if judge is not None else None
        results.append(CaseResult(case.case_id, code, model, _case_score(code, model)))

    domain = cases[0].domain if cases else "—"
    mean_score = round(sum(r.score for r in results) / len(results), 4) if results else 0.0
    regressions = [r.case_id for r in results if not r.code.passed]
    verdict = _verdict(mean_score, baseline, margin=margin, any_hard_fail=bool(regressions))
    return EvalReport(
        domain=domain, mean_score=mean_score, baseline_score=baseline,
        verdict=verdict, results=results, regressions=regressions,
    )
