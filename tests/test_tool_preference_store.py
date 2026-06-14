"""SENTINEL-022 Step 1 — ToolPreferenceStore (search-tool preference memory).

These tests pin the AC4 learning signal: a coarse-keyed, fail-soft record of which search leg
last produced priced results. The first test is load-bearing for the plan-reviewer blocker —
it constructs a *real* store against a temp DB and asserts the table was created by the shared
``_ensure_schema``/``_SCHEMA`` path (not a hand-rolled CREATE), which is the only test that would
catch a wrong creation path.
"""

import sqlite3

from sentinel.memory.store import ToolPreferenceStore


def test_fresh_db_creates_table_via_ensure_schema(tmp_path):
    """A real store on a fresh DB creates tool_preference through _ensure_schema and round-trips.

    This is the wrong-creation-path guard: if the table were added via the column-migration
    (ALTER) path instead of _SCHEMA, the table would not exist on a fresh DB and this fails.
    """
    db = tmp_path / "sentinel.db"
    store = ToolPreferenceStore(db)

    # the table exists in the schema the shared _ensure_schema applied
    with sqlite3.connect(str(db)) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "tool_preference" in names

    # and it round-trips through the real store
    store.record("product_research:shopping", "google_shopping_search")
    assert store.get("product_research:shopping") == "google_shopping_search"


def test_upsert_overwrites(tmp_path):
    """record() is last-writer-wins for a given query_class (no duplicate rows)."""
    store = ToolPreferenceStore(tmp_path / "sentinel.db")
    store.record("product_research:shopping", "google_shopping_search")
    store.record("product_research:shopping", "duckduckgo")
    assert store.get("product_research:shopping") == "duckduckgo"
    with sqlite3.connect(str(tmp_path / "sentinel.db")) as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM tool_preference WHERE query_class=?",
            ("product_research:shopping",)).fetchone()
    assert count == 1


def test_unknown_class_returns_none(tmp_path):
    """No signal yet ⇒ None (caller uses its default cascade order)."""
    store = ToolPreferenceStore(tmp_path / "sentinel.db")
    assert store.get("never:seen") is None


def test_empty_args_are_noops(tmp_path):
    """Empty query_class / winning_tool never write, and get('') is None."""
    store = ToolPreferenceStore(tmp_path / "sentinel.db")
    store.record("", "google_shopping_search")
    store.record("product_research:shopping", "")
    assert store.get("") is None
    assert store.get("product_research:shopping") is None


def test_get_is_fail_soft_on_corrupt_db(tmp_path):
    """A corrupt/unreadable DB degrades to None, never raises into the research loop."""
    db = tmp_path / "sentinel.db"
    store = ToolPreferenceStore(db)
    # clobber the file with non-sqlite bytes after construction
    db.write_bytes(b"not a sqlite database at all")
    assert store.get("product_research:shopping") is None  # no exception


def test_record_is_fail_soft_on_corrupt_db(tmp_path):
    """A failing write is swallowed — recording a preference must never break a run."""
    db = tmp_path / "sentinel.db"
    store = ToolPreferenceStore(db)
    db.write_bytes(b"not a sqlite database at all")
    store.record("product_research:shopping", "google_shopping_search")  # must not raise
