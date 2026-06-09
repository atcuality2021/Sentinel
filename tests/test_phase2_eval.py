"""SENTINEL-012 Phase 2 Step 12 — model-grader + eval runner + citation resolution (AC-18/19/20).

Hermetic: the judge is built offline + introspected (sovereign, tool-free) and driven through a
FakeRunner that injects a canned RubricScore (no inference). The runner is driven with injected
``produce``/``judge`` callables (no network), proving the promote/block gate. The new code-grade
checks (``citations_resolve``/``claim_support``) are pure and tested directly.

Proves:
- AC-18 : a dangling public citation hard-fails ``citations_resolve``; an orphan finding flags
          ``claim_support`` (soft); the judge is a sovereign, tool-free 26B reasoner.
- AC-19 : ``model_grade`` returns a five-axis rubric → a model ``GradeReport`` (mocked judge).
- AC-20 : the runner promotes an improving candidate, blocks a regressing one, and blocks outright
          when an artifact breaks a HARD code gate.
"""

from __future__ import annotations

import asyncio

from sentinel.agent import orchestrator as orch
from sentinel.agent.modes._build import make_agent
from sentinel.artifacts.schemas import (
    Battlecard,
    Boundary,
    Finding,
    RubricScore,
    Source,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption
from sentinel.eval.graders import RUBRIC_KEY, code_grade, model_grade, rubric_to_score
from sentinel.eval.runner import EvalCase, load_eval_set, run_eval_set

_PUB = Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://techcrunch.com/x")
_PUB2 = Source(boundary=Boundary.PUBLIC, label="G2", url="https://g2.com/y")


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def _clean_card() -> Battlecard:
    return Battlecard(
        target="Datadog", one_line_summary="Observability leader", positioning="cloud-native APM",
        strengths=[Finding(text="Mature integrations", source=_PUB)],
        weaknesses=[Finding(text="Pricing surprises", source=_PUB2)],
        sources=[_PUB, _PUB2],
    )


# --------------------------------------------------------------------------- #
# AC-18: new deterministic citation checks
# --------------------------------------------------------------------------- #


def test_dangling_public_citation_hard_fails_citations_resolve():
    card = _clean_card()
    card.sources = [Source(boundary=Boundary.PUBLIC, label="Blog", url=None)]  # public, no URL → dangling
    card.strengths = []
    card.weaknesses = []
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC})
    assert g.passed is False
    assert "citations_resolve" in g.hard_failures


def test_malformed_url_hard_fails_citations_resolve():
    card = _clean_card()
    card.sources = [Source(boundary=Boundary.PUBLIC, label="Blog", url="not-a-url")]
    card.strengths = []
    card.weaknesses = []
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC})
    assert "citations_resolve" in g.hard_failures


def test_private_source_needs_no_url_for_citations_resolve():
    # a PRIVATE source legitimately has no URL — it must NOT trip the public-URL check
    card = _clean_card()
    card.sources = [Source(boundary=Boundary.PRIVATE, label="CRM: Acme", url=None), _PUB]
    g = code_grade(card)  # no boundary constraint → boundary_clean passes
    assert g.checks["citations_resolve"] is True


def test_resolver_enforces_reachability_on_runner_path():
    # the default code_grade is format-only; passing a resolver opts into real reachability
    card = _clean_card()
    dead = code_grade(card, allowed_boundaries={Boundary.PUBLIC}, resolver=lambda u: False)
    assert "citations_resolve" in dead.hard_failures
    live = code_grade(card, allowed_boundaries={Boundary.PUBLIC}, resolver=lambda u: True)
    assert live.checks["citations_resolve"] is True


def test_orphan_finding_flags_claim_support_softly():
    # a finding citing a source the artifact never declares in sources[] → claim_support flags, soft
    card = _clean_card()
    orphan = Source(boundary=Boundary.PUBLIC, label="Reddit", url="https://reddit.com/z")
    card.strengths = [Finding(text="A claim from nowhere", source=orphan)]
    g = code_grade(card, allowed_boundaries={Boundary.PUBLIC})
    assert g.checks["claim_support"] is False  # flagged
    assert g.passed is True                     # but soft → does not block
    assert "claim_support" not in g.hard_failures


def test_clean_card_passes_both_new_checks():
    g = code_grade(_clean_card(), allowed_boundaries={Boundary.PUBLIC})
    assert g.checks["citations_resolve"] is True
    assert g.checks["claim_support"] is True
    assert g.passed is True


# --------------------------------------------------------------------------- #
# AC-18: the judge is a sovereign, tool-free reasoner
# --------------------------------------------------------------------------- #


def test_judge_builds_sovereign_toolfree(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    judge = make_agent(
        _tiered_cfg(), "eval.judge", name="eval_judge", output_key=RUBRIC_KEY,
        mode_backend="vllm", output_schema=RubricScore, cloud_allowed=False,
    )
    assert not isinstance(judge.model, str)             # no Gemini model-id string under on_prem
    assert type(judge.model).__name__ == "LiteLlm"
    assert "26B" in judge.model.model                   # reasoner tier
    assert not getattr(judge, "tools", None)            # tool-free → judges only what it is shown


# --------------------------------------------------------------------------- #
# AC-19: model_grade returns a rubric → a model GradeReport
# --------------------------------------------------------------------------- #


def _fake_judge_runner(rubric: RubricScore):
    """A FakeRunner whose session ends with ``rubric`` injected under RUBRIC_KEY (no inference)."""

    class FakeSession:
        def __init__(self, state):
            self.id = "s1"
            self.state = dict(state)

    class FakeSvc:
        def __init__(self):
            self._s = None

        async def create_session(self, *, app_name, user_id, state):
            self._s = FakeSession(state)
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            self._s.state[RUBRIC_KEY] = rubric.model_dump()
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            if False:
                yield None

    return FakeRunner


def test_model_grade_returns_rubric_score(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    rubric = RubricScore(relevance=5, faithfulness=4, completeness=4, actionability=3, persona_fit=4,
                         justification="Well-sourced and on-objective; actionability a touch thin.")
    monkeypatch.setattr(orch, "InMemoryRunner", _fake_judge_runner(rubric))
    trace: list[str] = []

    grade = asyncio.run(model_grade(
        _clean_card(), objective="Profile Datadog for a competitive battlecard.",
        sources=[_PUB, _PUB2], cfg=_tiered_cfg(), backend="vllm", cloud_allowed=False, trace=trace,
    ))

    assert grade.grader == "model"
    assert grade.score == rubric_to_score(rubric)       # (5+4+4+3+4)/25 = 0.8
    assert grade.score == 0.8
    assert grade.checks["actionability"] is True        # 3 ≥ 3
    assert grade.notes.startswith("Well-sourced")
    assert grade.passed is True                          # 0.8 ≥ default 0.6 threshold
    assert not any("tool:" in line for line in trace)    # judge fetches nothing


def test_model_grade_fails_below_threshold(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    weak = RubricScore(relevance=2, faithfulness=2, completeness=2, actionability=2, persona_fit=2,
                       justification="Thin and weakly sourced throughout.")
    monkeypatch.setattr(orch, "InMemoryRunner", _fake_judge_runner(weak))
    grade = asyncio.run(model_grade(
        _clean_card(), objective="x", sources=[_PUB], cfg=_tiered_cfg(), backend="vllm",
        cloud_allowed=False,
    ))
    assert grade.score == 0.4
    assert grade.passed is False
    assert all(v is False for v in grade.checks.values())  # every axis < 3


# --------------------------------------------------------------------------- #
# AC-20: the runner promote/block gate
# --------------------------------------------------------------------------- #


def _cases() -> list[EvalCase]:
    return [
        EvalCase(case_id="c1", domain="market", capability="compare", objective="o1",
                 allowed_boundaries=(Boundary.PUBLIC,)),
        EvalCase(case_id="c2", domain="market", capability="compare", objective="o2",
                 allowed_boundaries=(Boundary.PUBLIC,)),
    ]


async def _produce_clean(case):
    return _clean_card()


def _judge_returning(score_axes: int):
    async def judge(artifact, case):
        from sentinel.artifacts.schemas import GradeReport
        s = round(score_axes / 5.0, 4)
        return GradeReport(passed=s >= 0.6, grader="model", score=s, checks={}, notes="mock")
    return judge


def test_runner_promotes_improving_change():
    report = asyncio.run(run_eval_set(
        _cases(), _produce_clean, judge=_judge_returning(5), baseline=0.7,  # 1.0 mean > 0.7
    ))
    assert report.mean_score == 1.0
    assert report.verdict == "promote"
    assert report.regressions == []


def test_runner_blocks_regressing_change():
    report = asyncio.run(run_eval_set(
        _cases(), _produce_clean, judge=_judge_returning(2), baseline=0.7,  # 0.4 mean < 0.7
    ))
    assert report.mean_score == 0.4
    assert report.verdict == "block"


def test_runner_holds_inside_margin():
    report = asyncio.run(run_eval_set(
        _cases(), _produce_clean, judge=_judge_returning(4), baseline=0.8, margin=0.05,  # 0.8 == base
    ))
    assert report.verdict == "hold"


def test_runner_blocks_on_hard_code_failure():
    async def produce_broken(case):
        card = _clean_card()
        card.sources = [Source(boundary=Boundary.PUBLIC, label="Blog", url=None)]  # dangling
        card.strengths = []
        card.weaknesses = []
        return card

    # even with a generous judge, a HARD code-gate failure blocks and is listed as a regression
    report = asyncio.run(run_eval_set(
        _cases(), produce_broken, judge=_judge_returning(5), baseline=0.5,
    ))
    assert report.verdict == "block"
    assert set(report.regressions) == {"c1", "c2"}
    assert report.mean_score == 0.0


def test_runner_first_run_establishes_baseline():
    report = asyncio.run(run_eval_set(_cases(), _produce_clean, judge=_judge_returning(4), baseline=None))
    assert report.verdict == "promote"  # no baseline yet → adopt this candidate


# --------------------------------------------------------------------------- #
# Golden set loads
# --------------------------------------------------------------------------- #


def test_load_market_eval_set():
    cases = load_eval_set("market")
    assert len(cases) >= 2
    by_id = {c.case_id for c in cases}
    assert "market-self-profile-biltiq" in by_id
    compare = next(c for c in cases if c.capability == "compare")
    assert compare.allowed_boundaries == (Boundary.PUBLIC,)
    assert compare.objective  # non-empty


def test_unknown_domain_returns_empty():
    assert load_eval_set("no-such-domain") == []
