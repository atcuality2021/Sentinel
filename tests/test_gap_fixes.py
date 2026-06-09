"""Tests for the 5 audit-gap fixes.

Gap 1 — extraction.py:  all SENTINEL-014 domain artifacts produce MemoryEntries.
Gap 2 — store.py:       SpecStore.update_eval_score writes back and is reflected in resolve().
Gap 4 — store.py:       FeedbackStore persists signals, reinforces / weakens memory.
Gap 5 — store.py:       recall_episodes accepts project_id, degrades silently when KB absent.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sentinel.artifacts.schemas import (
    AcademicBrief,
    Battlecard,
    Boundary,
    FinancialProfile,
    Finding,
    NutritionBrief,
    SoftwareBrief,
    Source,
    TravelBrief,
)
from sentinel.memory.extraction import _all_findings, extract_entries


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pub_src(label="test") -> Source:
    return Source(boundary=Boundary.PUBLIC, label=label, url=None)


def _finding(text="fact") -> Finding:
    return Finding(text=text, source=_pub_src())


# --------------------------------------------------------------------------- #
# Gap 1 — extraction.py generic walker
# --------------------------------------------------------------------------- #
class TestExtractAllDomainArtifacts:
    def test_software_brief_extracts_all_finding_lists(self):
        art = SoftwareBrief(
            target="pytest",
            one_line_summary="testing framework",
            category="test runner",
            tech_stack=[_finding("Python")],
            api_quality=[_finding("great DX")],
            community_health=[_finding("active")],
            maintenance_activity=[_finding("weekly releases")],
            integration_support=[_finding("CI/CD integrations")],
            pricing_model=[_finding("MIT license")],
        )
        entries = extract_entries("pytest", art)
        assert len(entries) == 6
        texts = {e.content for e in entries}
        assert "Python" in texts
        assert "great DX" in texts

    def test_financial_profile_extracts_findings(self):
        art = FinancialProfile(
            target="Acme Corp",
            one_line_summary="mid-cap SaaS",
            financial_summary="growing",
            key_metrics=[_finding("ARR $50M")],
            market_position=[_finding("top 5 CRM")],
            risk_signals=[_finding("concentration risk")],
            recent_developments=[_finding("Series C")],
        )
        entries = extract_entries("acme corp", art)
        assert len(entries) == 4
        assert all(e.entity == "acme corp" for e in entries)

    def test_academic_brief_extracts_key_findings(self):
        art = AcademicBrief(
            topic="spaced repetition",
            one_line_summary="improves retention",
            topic_overview="well-studied",
            key_findings=[_finding("SM-2 outperforms massed practice"), _finding("effect persists 6 months")],
        )
        entries = extract_entries("spaced repetition", art)
        assert len(entries) == 2

    def test_nutrition_brief_extracts_key_claims(self):
        art = NutritionBrief(
            topic="omega-3",
            one_line_summary="anti-inflammatory",
            evidence_quality="strong RCT",
            key_claims=[_finding("reduces inflammation")],
        )
        entries = extract_entries("omega-3", art)
        assert len(entries) == 1

    def test_travel_brief_extracts_all_finding_lists(self):
        art = TravelBrief(
            destination="Kyoto",
            one_line_summary="historic city",
            destination_overview="temples and gardens",
            practical_info=[_finding("JR pass valid")],
            highlights=[_finding("Arashiyama bamboo grove")],
            safety_notes=[_finding("very safe")],
        )
        entries = extract_entries("kyoto", art)
        assert len(entries) == 3

    def test_all_findings_helper_skips_non_finding_lists(self):
        art = SoftwareBrief(
            target="ruff",
            one_line_summary="fast linter",
            category="linter",
            alternatives=["flake8", "pylint"],  # list[str], not list[Finding]
        )
        findings = _all_findings(art)
        assert all(isinstance(f, Finding) for f in findings)
        assert not any(isinstance(f, str) for f in findings)

    def test_battlecard_still_uses_explicit_branch(self):
        art = Battlecard(
            target="RivalCo",
            one_line_summary="competitor",
            positioning="aggressive pricing",
            strengths=[_finding("low price"), _finding("fast onboarding")],
            weaknesses=[_finding("poor support")],
        )
        entries = extract_entries("rivalco", art)
        assert len(entries) == 3


# --------------------------------------------------------------------------- #
# Gap 2 — SpecStore.update_eval_score
# --------------------------------------------------------------------------- #
class TestUpdateEvalScore:
    def _make_store(self, tmp_path):
        from sentinel.memory.store import SpecStore
        return SpecStore(path=tmp_path / "db.sqlite")

    def test_update_writes_score_and_data_json(self, tmp_path):
        from sentinel.artifacts.schemas import AgentSpec

        store = self._make_store(tmp_path)
        spec = AgentSpec(
            id="test-spec-1",
            name="test",
            capability="research",
            domain="software",
            role="synthesizer",
            skill_prompt="test prompt",
            output_schema_ref="SoftwareBrief",
        )
        store.save_spec(spec)
        assert store.get_spec("test-spec-1").eval_score is None

        store.update_eval_score("test-spec-1", 0.87)

        reloaded = store.get_spec("test-spec-1")
        assert reloaded is not None
        assert abs(reloaded.eval_score - 0.87) < 1e-6

    def test_update_nonexistent_spec_is_noop(self, tmp_path):
        store = self._make_store(tmp_path)
        store.update_eval_score("does-not-exist", 1.0)  # must not raise

    def test_resolve_prefers_higher_score(self, tmp_path):
        from sentinel.artifacts.schemas import AgentSpec

        store = self._make_store(tmp_path)
        low = AgentSpec(id="low", name="low", capability="cap", domain="dom",
                        role="synthesizer", skill_prompt="p", output_schema_ref="Battlecard")
        high = AgentSpec(id="high", name="high", capability="cap", domain="dom",
                         role="synthesizer", skill_prompt="p", output_schema_ref="Battlecard")
        store.save_spec(low)
        store.save_spec(high)
        store.update_eval_score("low", 0.3)
        store.update_eval_score("high", 0.9)

        from sentinel.agent.registry import AgentRegistry
        registry = AgentRegistry(store=store, seed=False)
        resolved = registry.resolve("cap", "dom")
        assert resolved is not None
        assert resolved.id == "high"


# --------------------------------------------------------------------------- #
# Gap 4 — FeedbackStore
# --------------------------------------------------------------------------- #
class TestFeedbackStore:
    def _stores(self, tmp_path):
        from sentinel.memory.store import FeedbackStore, MemoryStore

        db = tmp_path / "db.sqlite"
        return FeedbackStore(path=db), MemoryStore(path=db)

    def test_save_persists_and_list_returns_it(self, tmp_path):
        fb_store, _ = self._stores(tmp_path)
        fb_id = fb_store.save(
            project_id="proj1", task_id="task1", run_id="run1",
            entity="Acme Corp", signal=1,
        )
        assert fb_id
        rows = fb_store.list_for_run("run1")
        assert len(rows) == 1
        assert rows[0]["signal"] == 1

    def test_aggregate_signal_sums_correctly(self, tmp_path):
        fb_store, _ = self._stores(tmp_path)
        fb_store.save(project_id="p", task_id="t1", run_id="r1", entity="entity", signal=1)
        fb_store.save(project_id="p", task_id="t2", run_id="r2", entity="entity", signal=1)
        fb_store.save(project_id="p", task_id="t3", run_id="r3", entity="entity", signal=-1)
        assert fb_store.aggregate_signal("entity") == 1

    def test_positive_signal_reinforces_memory(self, tmp_path):
        from sentinel.memory.schema import DataBoundary, MemoryEntry, MemoryType

        fb_store, mem_store = self._stores(tmp_path)
        entry = MemoryEntry(
            entity="acme corp", boundary=DataBoundary.PUBLIC,
            memory_type=MemoryType.FINDING, content="fact",
            source_label="web", source_url=None,
        )
        before_strength = entry.strength
        mem_store.write(entry)

        fb_store.save(project_id="p", task_id="t", run_id="r", entity="acme corp", signal=1)

        updated = mem_store.list_for_entity("acme corp")
        assert len(updated) == 1
        assert updated[0].strength > before_strength

    def test_negative_signal_weakens_memory(self, tmp_path):
        from sentinel.memory.schema import DataBoundary, MemoryEntry, MemoryType

        fb_store, mem_store = self._stores(tmp_path)
        entry = MemoryEntry(
            entity="badco", boundary=DataBoundary.PUBLIC,
            memory_type=MemoryType.FINDING, content="bad fact",
            source_label="web", source_url=None,
        )
        before_strength = entry.strength
        mem_store.write(entry)

        fb_store.save(project_id="p", task_id="t", run_id="r", entity="badco", signal=-1)

        updated = mem_store.list_for_entity("badco")
        assert len(updated) == 1
        assert updated[0].strength < before_strength

    def test_zero_signal_is_rejected(self, tmp_path):
        fb_store, _ = self._stores(tmp_path)
        # signal=0 is not in (1,-1) — save is a no-op because _apply_to_memory guards on signal==0
        fb_store.save(project_id="p", task_id="t", run_id="r", entity="e", signal=0)
        assert fb_store.aggregate_signal("e") == 0


# --------------------------------------------------------------------------- #
# Gap 5 — recall_episodes with project_id + KB-absent fail-soft
# --------------------------------------------------------------------------- #
class TestRecallEpisodesProjectId:
    def _run_store(self, tmp_path):
        from sentinel.memory.store import RunStore
        return RunStore(path=tmp_path / "db.sqlite")

    def test_accepts_project_id_kwarg_without_kb(self, tmp_path):
        from sentinel.memory.schema import RunRecord

        store = self._run_store(tmp_path)
        rec = RunRecord(entity="widgetco", target="widgetco", mode="competitor",
                        backend="gemini", kind="Battlecard",
                        public=3, private=0, gaps=0, reference="ref", finding_texts=["f1"])
        store.save(rec)

        # project_id given but KB not indexed — should degrade silently and return exact match
        results = store.recall_episodes("widgetco", top_k=3, project_id="nonexistent-project")
        assert len(results) == 1
        assert results[0].entity == "widgetco"

    def test_no_project_id_backward_compat(self, tmp_path):
        from sentinel.memory.schema import RunRecord

        store = self._run_store(tmp_path)
        rec = RunRecord(entity="legacyco", target="legacyco", mode="client",
                        backend="vllm", kind="AccountBrief",
                        public=1, private=1, gaps=0, reference="ref", finding_texts=["f"])
        store.save(rec)

        results = store.recall_episodes("legacyco", top_k=3)  # no project_id — original signature
        assert len(results) == 1
