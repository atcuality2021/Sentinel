# src/sentinel/web/render/memory_config.py
"""Helpers for the entity source-config API routes (Task 8 — memory-brain API)."""
from __future__ import annotations

import html
import json
import re
import sqlite3
from pathlib import Path

from sentinel.memory.schema import normalize_entity, utcnow

# Allow common Gmail / search-operator characters: word chars, @, dot, colon,
# whitespace, double-quote, single-quote, hyphen, plus, parens, pipe.
# Rejects shell-injection sequences that contain semicolons, backticks, $ etc.
_SAFE_EMAIL_FILTER = re.compile(
    r'^[\w@\.\s:\"\'\-\+\(\)\|]+$', re.IGNORECASE
)


def _validate_email_filter(value: str) -> str:
    """Return the stripped value or raise ValueError for unsafe input."""
    stripped = value.strip()
    if not _SAFE_EMAIL_FILTER.match(stripped):
        raise ValueError("Invalid email_filter characters")
    return stripped


def get_source_config(db_path: Path, entity_slug: str) -> dict[str, object]:
    """Return the stored source config for *entity_slug*, or sensible defaults."""
    entity = normalize_entity(entity_slug.replace("-", " "))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM entity_source_config WHERE entity=?", (entity,)
        ).fetchone()
    if not row:
        return {
            "entity": entity,
            "priority": "medium",
            "sources_enabled": ["website"],
            "website_url": "",
            "youtube_channel": "",
            "social_handles": "{}",
            "email_filter": "",
        }
    d = dict(row)
    d["sources_enabled"] = json.loads(d.get("sources_enabled") or '["website"]')
    return d


def save_source_config(db_path: Path, entity_slug: str, payload: dict[str, object]) -> None:
    """Persist *payload* as the source config for *entity_slug*."""
    entity = normalize_entity(entity_slug.replace("-", " "))
    priority = str(payload.get("priority", "medium"))
    if priority not in ("high", "medium", "low"):
        priority = "medium"
    email_filter = ""
    if payload.get("email_filter"):
        email_filter = _validate_email_filter(str(payload["email_filter"]))
    sources_enabled = json.dumps(payload.get("sources_enabled", ["website"]))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO entity_source_config "
            "(entity, priority, website_url, youtube_channel, social_handles, "
            "email_filter, sources_enabled, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                entity,
                priority,
                html.escape(str(payload.get("website_url", ""))),
                html.escape(str(payload.get("youtube_channel", ""))),
                str(payload.get("social_handles", "{}")),
                email_filter,
                sources_enabled,
                utcnow().isoformat(),
            ),
        )
        conn.commit()
