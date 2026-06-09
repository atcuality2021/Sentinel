"""Playbook loader — parse an admin-editable Markdown playbook (SENTINEL-009).

Format: YAML frontmatter between the first two ``---`` fences, then a Markdown body (framework +
output template + house rules). Parsing is **fail-soft**: a missing file, missing frontmatter, bad
YAML, or a wrong ``mode`` yields ``None`` so the caller records a gap and the run continues
(NFR-3) — a malformed playbook must never break a run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError


class Playbook(BaseModel):
    name: str
    mode: Literal["competitor", "client"]
    description: str = ""
    body: str  # everything after the frontmatter — framework, output template, house rules


def _split_frontmatter(text: str) -> tuple[dict, str] | None:
    """Split ``---\\n<yaml>\\n---\\n<body>`` into (meta, body). None if no valid frontmatter."""
    if not text.lstrip().startswith("---"):
        return None
    # find the opening fence and the next closing fence
    stripped = text.lstrip("\n")
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            front = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:]).strip()
            try:
                meta = yaml.safe_load(front) or {}
            except yaml.YAMLError:
                return None
            if not isinstance(meta, dict):
                return None
            return meta, body
    return None


def load_playbook(path: str | Path) -> Playbook | None:
    """Parse frontmatter + body. Fail-soft: missing/malformed → None (caller records a gap)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    parsed = _split_frontmatter(text)
    if parsed is None:
        return None
    meta, body = parsed
    try:
        return Playbook(
            name=str(meta.get("name") or p.stem),
            mode=meta.get("mode"),
            description=str(meta.get("description") or ""),
            body=body,
        )
    except ValidationError:
        return None


def discover_playbooks(directory: str | Path) -> list[Playbook]:
    """List valid playbooks in a directory (for the Settings picker). Skips malformed files."""
    d = Path(directory)
    if not d.is_dir():
        return []
    out: list[Playbook] = []
    for f in sorted(d.glob("*.md")):
        pb = load_playbook(f)
        if pb is not None:
            out.append(pb)
    return out
