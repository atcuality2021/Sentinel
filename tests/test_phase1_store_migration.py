"""SENTINEL-012 Phase 1 Step 4 — store migration (ADR-0003).

Hermetic: each test gets its own SQLite file under tmp_path (no SENTINEL_DATA_DIR, no network).
Covers the ADR-0003 test plan: CRUD, no-regression (read + write byte-identity), positive
project_id write (AC-1), memory provenance (cross-project dedup), orphan integrity (purge_project +
defensive reads), and migration idempotency on a pre-012 DB.
"""

from __future__ import annotations

import sqlite3

from sentinel.artifacts.schemas import Domain, Persona, Plan, Project, Step, Task
from sentinel.memory.schema import DataBoundary, MemoryEntry, RunRecord
from sentinel.memory.store import MemoryStore, ProjectStore, RunStore


def _run(entity="Datadog", project_id=None, run_seq=1) -> RunRecord:
    return RunRecord(
        entity=entity, target=entity, mode="competitor", backend="vllm", kind="battlecard",
        public=2, private=0, gaps=0, reference="ref", finding_texts=["f1"],
        run_seq=run_seq, project_id=project_id,
    )


# --- CRUD round-trip (AC-1) ----------------------------------------------------------------- #


def test_project_task_plan_crud(tmp_path):
    ps = ProjectStore(tmp_path / "s.db")
    proj = Project(id="p1", name="BiltIQ", website="https://biltiq.ai", created_at="2026-06-08T00:00:00Z")
    ps.save_project(proj)
    assert ps.get_project("p1") == proj
    assert [p.id for p in ps.list_projects()] == ["p1"]

    task = Task(id="t1", project_id="p1", objective="map", domain=Domain(name="market"),
                persona=Persona(), created_at="2026-06-08T00:01:00Z")
    ps.save_task(task)
    assert ps.get_task("t1") == task
    assert [t.id for t in ps.tasks_for_project("p1")] == ["t1"]

    plan = Plan(id="pl1", task_id="t1", steps=[Step(id="s1", capability="self_profile", output_key="sp")])
    ps.save_plan(plan)
    assert ps.get_plan("pl1") == plan
    assert ps.plan_for_task("t1") == plan


# --- positive write (AC-1) + run-side scoping ----------------------------------------------- #


def test_run_project_scoping(tmp_path):
    rs = RunStore(tmp_path / "s.db")
    rs.save(_run("Datadog", project_id="p1"))
    rs.save(_run("Splunk", project_id="p2"))
    rs.save(_run("Grafana", project_id=None))  # legacy/unscoped

    assert rs.latest_for("Datadog", project_id="p1") is not None
    assert rs.latest_for("Datadog", project_id="p2") is None  # wrong project → not found
    assert {r.entity for r in rs.all(project_id="p1")} == {"datadog"}
    assert rs.count(project_id="p1") == 1
    assert rs.count() == 3  # no filter sees everything (incl. legacy)
    assert {e.entity for e in rs.entities(project_id="p2")} == {"splunk"}
    assert len(rs.runs_for("Datadog", project_id="p1")) == 1


# --- no-regression: legacy NULL rows + write byte-identity ---------------------------------- #


def test_legacy_null_rows_unaffected(tmp_path):
    rs = RunStore(tmp_path / "s.db")
    original = _run("Grafana", project_id=None)
    rs.save(original)
    # no-filter reads return the legacy row unchanged
    assert len(rs.all()) == 1
    assert len(rs.runs_for("Grafana")) == 1
    back = rs.latest_for("Grafana")
    assert back is not None and back.project_id is None
    # write byte-identity: a project_id=None run round-trips equal to what we saved (proxy for the
    # golden/characterization no-regression gate — adding the column changed no existing value).
    assert back == original


# --- memory provenance: dedup is project-agnostic; recall is unscoped ------------------------ #


def test_memory_provenance_first_writer_and_recall_unscoped(tmp_path):
    ms = MemoryStore(tmp_path / "s.db")
    e1 = MemoryEntry(entity="Datadog", boundary=DataBoundary.PUBLIC, content="raised a round", project_id="p1")
    ms.write(e1)
    # second project writes the SAME fact → dedup to one row; project_id stays the first writer (p1)
    e2 = MemoryEntry(entity="Datadog", boundary=DataBoundary.PUBLIC, content="raised a round", project_id="p2")
    ms.write(e2)
    assert ms.count("Datadog") == 1
    # recall does NOT filter by project — the operator gets their own fact regardless of project
    got = ms.recall("Datadog", {DataBoundary.PUBLIC})
    assert len(got) == 1 and got[0].project_id == "p1"


# --- orphan integrity: purge_project cascade + defensive reads ------------------------------ #


def test_purge_project_cascade_and_orphan_tolerant_reads(tmp_path):
    db = tmp_path / "s.db"
    ps, rs, ms = ProjectStore(db), RunStore(db), MemoryStore(db)
    ps.save_project(Project(id="p1", name="X", created_at="2026-06-08T00:00:00Z"))
    ps.save_task(Task(id="t1", project_id="p1", objective="o", domain=Domain(name="market"),
                      created_at="2026-06-08T00:00:00Z"))
    ps.save_plan(Plan(id="pl1", task_id="t1"))
    rs.save(_run("Datadog", project_id="p1"))
    ms.write(MemoryEntry(entity="Datadog", boundary=DataBoundary.PUBLIC, content="x", project_id="p1"))

    ps.purge_project("p1")

    # project + tasks + plans deleted
    assert ps.get_project("p1") is None
    assert ps.tasks_for_project("p1") == []
    assert ps.plan_for_task("t1") is None
    # runs + memory SURVIVE, project_id cleared to None (entity-owned, not project-owned)
    run = rs.latest_for("Datadog")
    assert run is not None and run.project_id is None
    assert ms.count("Datadog") == 1


def test_reads_tolerate_missing_parent(tmp_path):
    """A task/plan whose parent row is gone reads back cleanly (no crash) — defense in depth."""
    ps = ProjectStore(tmp_path / "s.db")
    # task references a project that was never saved; plan references that task — both orphaned
    ps.save_task(Task(id="t9", project_id="ghost", objective="o", domain=Domain(name="market"),
                      created_at="2026-06-08T00:00:00Z"))
    ps.save_plan(Plan(id="pl9", task_id="t9"))
    assert ps.get_project("ghost") is None
    assert ps.get_task("t9").id == "t9"      # orphaned task still readable
    assert ps.get_plan("pl9").task_id == "t9"  # orphaned plan still readable


# --- migration idempotency on a pre-012 DB -------------------------------------------------- #

_OLD_RUN_SCHEMA = """
CREATE TABLE run_records (
    id TEXT PRIMARY KEY, entity TEXT NOT NULL, target TEXT NOT NULL, mode TEXT NOT NULL,
    backend TEXT NOT NULL, kind TEXT NOT NULL, public INTEGER NOT NULL, private INTEGER NOT NULL,
    gaps INTEGER NOT NULL, reference TEXT NOT NULL, finding_texts TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]', run_seq INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
"""


def test_migration_adds_project_id_to_old_db(tmp_path):
    db = tmp_path / "old.db"
    # hand-build a pre-012 run_records table with NO project_id column + a legacy row
    conn = sqlite3.connect(str(db))
    conn.executescript(_OLD_RUN_SCHEMA)
    conn.execute(
        "INSERT INTO run_records (id, entity, target, mode, backend, kind, public, private, gaps, "
        "reference, finding_texts, created_at) VALUES "
        "('r1','datadog','Datadog','competitor','vllm','battlecard',1,0,0,'ref','[\"f\"]','2026-01-01T00:00:00Z')"
    )
    conn.commit()
    conn.close()

    # opening a store runs _ensure_schema → ALTERs in project_id + creates the new tables
    rs = RunStore(db)
    back = rs.latest_for("Datadog")
    assert back is not None and back.project_id is None  # legacy row reads back, column defaulted
    cols = {r[1] for r in sqlite3.connect(str(db)).execute("PRAGMA table_info(run_records)")}
    assert "project_id" in cols
    # new tables exist + are usable
    ProjectStore(db).save_project(Project(id="p1", name="X", created_at="2026-06-08T00:00:00Z"))
    assert ProjectStore(db).get_project("p1").id == "p1"
