"""SENTINEL-012 — DAG step-input wiring (the multi-step data-flow fix found in the live e2e).

The planner emits ``depends_on`` but rarely ``Step.inputs``, and it names a step's ``output_key`` after
the capability (``competitor``) while the consumer skill reads the artifact's CANONICAL name
(``compare`` reads ``{self_profile}`` + ``{battlecard}``). Without bridging, a downstream step never
receives its inputs and fails with 'Context variable not found' (fail-soft → partial result).

``_dependency_state`` exposes each dependency's artifact under BOTH the producer's ``output_key`` and
the producing skill's canonical terminal key — so ``{self_profile}`` and ``{battlecard}`` both resolve.
"""

from __future__ import annotations

from sentinel.agent.dag import _dependency_state
from sentinel.artifacts.schemas import Plan, Step

_SELF = {"org": "BiltIQ"}
_RIVAL = {"target": "Rival Corp"}


def _plan() -> Plan:
    return Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile"),
        Step(id="s2", capability="competitor", output_key="competitor"),   # planner-named output_key
        Step(id="s3", capability="compare", output_key="comparison", depends_on=["s1", "s2"]),
    ])


def test_dependency_state_exposes_canonical_names_for_consumer():
    plan = _plan()
    by_id = {s.id: s for s in plan.steps}
    results = {"self_profile": _SELF, "competitor": _RIVAL}   # keyed by each producer's output_key

    pool = _dependency_state(by_id["s3"], by_id, results)

    # the compare skill reads {self_profile} and {battlecard}; both must be present...
    assert pool["self_profile"] == _SELF
    assert pool["battlecard"] == _RIVAL          # competitor's artifact bridged to its canonical name
    # ...and the producer's own output_key alias is kept too (so explicit wiring still works)
    assert pool["competitor"] == _RIVAL


def test_dependency_state_skips_unsatisfied_and_unknown_deps():
    plan = _plan()
    by_id = {s.id: s for s in plan.steps}
    results = {"self_profile": _SELF}            # s2 not produced yet

    pool = _dependency_state(by_id["s3"], by_id, results)
    assert pool == {"self_profile": _SELF}       # only the satisfied dep flows; no crash on the missing one


def test_dependency_state_created_dep_uses_output_key_only():
    # a created capability has no SKILL_SPECS entry → no canonical key; it flows under its output_key.
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="a", capability="novel_cap", output_key="novel_cap"),
        Step(id="b", capability="compare", output_key="cmp", depends_on=["a"]),
    ])
    by_id = {s.id: s for s in plan.steps}
    pool = _dependency_state(by_id["b"], by_id, {"novel_cap": {"x": 1}})
    assert pool == {"novel_cap": {"x": 1}}       # output_key only, no canonical alias, no crash
