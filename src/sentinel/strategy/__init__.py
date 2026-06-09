"""Strategy playbooks (SENTINEL-009) — admin-editable Markdown that shapes the strategist.

A playbook is the unit an operator edits to reshape house strategy without a redeploy. The loader
parses YAML frontmatter + a Markdown body; the body is injected into the strategist's instruction
via the existing ``instruction_suffix`` seam, so changing a ``.md`` changes the next run.
"""

from __future__ import annotations

from sentinel.strategy.playbooks import Playbook, discover_playbooks, load_playbook

__all__ = ["Playbook", "load_playbook", "discover_playbooks"]
