"""SENTINEL-012 Phase 1 Step 5 — code-based grader (AC-18).

Hermetic: pure function, no LLM/network. Proves hard failures (schema/citations/boundary/sovereign)
block, soft failures (banned vocab) only flag, and the sovereign introspection catches a Gemini
model object under on_prem.
"""

from __future__ import annotations

from sentinel.artifacts.schemas import Battlecard, Boundary, Finding, Source
from sentinel.eval.graders import code_grade


def _public_source() -> Source:
    return Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://t.co/x")


def _clean_card(summary="A solid competitor.") -> Battlecard:
    return Battlecard(
        target="Datadog", one_line_summary=summary, positioning="Observability leader",
        strengths=[Finding(text="Strong APM", source=_public_source())],
        sources=[_public_source()],
    )


# --- the happy path ------------------------------------------------------------------------- #


def test_clean_artifact_passes():
    g = code_grade(_clean_card(), allowed_boundaries={Boundary.PUBLIC})
    assert g.passed is True
    assert g.hard_failures == []
    assert all(g.checks.values())  # every check green on a clean card


# --- HARD failures block -------------------------------------------------------------------- #


def test_malformed_artifact_hard_fails_schema():
    # model_construct bypasses validation; an int target makes the re-validation fail.
    bad = Battlecard.model_construct(target=123, one_line_summary="x", positioning="y", sources=[_public_source()])
    g = code_grade(bad)
    assert g.passed is False
    assert "schema_valid" in g.hard_failures


def test_missing_citations_hard_fails():
    card = _clean_card()
    card.sources = []
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC})
    assert g.passed is False
    assert "citations_present" in g.hard_failures


def test_boundary_violation_hard_fails():
    # a PRIVATE source inside an artifact allowed only PUBLIC (e.g. competitor mode) → hard fail
    card = _clean_card()
    card.sources.append(Source(boundary=Boundary.PRIVATE, label="CRM", url=None))
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC})
    assert g.passed is False
    assert "boundary_clean" in g.hard_failures


# --- SOFT failures only flag ---------------------------------------------------------------- #


def test_banned_vocab_flags_but_does_not_block():
    card = _clean_card(summary="A revolutionary, cutting-edge platform.")
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC})
    assert g.passed is True                       # soft → does not block
    assert g.checks["no_banned_vocab"] is False   # but it IS flagged


# --- sovereign introspection (AC-18) -------------------------------------------------------- #


class _FakeVllm:
    """Stands in for a LiteLlm — an on-prem model object naming a gemma id."""
    model = "hosted_vllm/gemma-4-12B"


def test_sovereign_catches_gemini_under_on_prem():
    card = _clean_card()
    # a bare model-id string is what gateway.build_model returns for the Gemini (cloud) backend
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC},
                   models=["gemini-2.5-flash"], cloud_allowed=False)
    assert g.passed is False
    assert "sovereign" in g.hard_failures


def test_sovereign_passes_for_vllm_models_under_on_prem():
    card = _clean_card()
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC},
                   models=[_FakeVllm(), _FakeVllm()], cloud_allowed=False)
    assert g.passed is True
    assert g.checks["sovereign"] is True


def test_sovereign_not_enforced_when_cloud_allowed():
    card = _clean_card()
    g = code_grade(card, models=["gemini-2.5-flash"], cloud_allowed=True)
    assert g.checks["sovereign"] is True  # cloud is policy-permitted
