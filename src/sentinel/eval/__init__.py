"""Evaluation & grading (SENTINEL-012 §10).

Two graders judge an artifact: a deterministic, code-based grader (``code_grade``) — no network, no
LLM, fast, safe on every produced artifact — and an LLM-as-judge (``model_grade``, Step 12) that
scores it on a five-axis rubric via an independent judge model. ``runner.run_eval_set`` drives a
candidate over a golden set, aggregates both grades, and diffs against a baseline → promote|block.
"""

from sentinel.eval.graders import (
    BANNED_VOCAB,
    HARD_CHECKS,
    RUBRIC_KEY,
    code_grade,
    model_grade,
    rubric_to_score,
)
from sentinel.eval.runner import (
    CaseResult,
    EvalCase,
    EvalReport,
    load_eval_set,
    run_eval_set,
)

__all__ = [
    "code_grade", "model_grade", "rubric_to_score", "BANNED_VOCAB", "HARD_CHECKS", "RUBRIC_KEY",
    "load_eval_set", "run_eval_set", "EvalCase", "CaseResult", "EvalReport",
]
