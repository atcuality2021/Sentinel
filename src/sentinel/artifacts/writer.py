"""Artifact writers — durable output, not a chat reply (SRS FR-09).

Pluggable ``ArtifactWriter`` interface with three backends (decision Q-2):
  - MarkdownArtifactWriter  — always works, no external dependency (demo backbone)
  - GoogleDocArtifactWriter — writes to the user's Drive via the Workspace MCP (stretch)
  - CrmArtifactWriter       — writes to a CRM record via MCP (stretch)

Priority for the build: Markdown → Google Doc → CRM. The Doc/CRM writers go through the
*private* MCP boundary, so artifacts land in the user's own workspace and never transit a
third-party SaaS.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from sentinel.artifacts.schemas import AccountBrief, Battlecard


class WriteResult(BaseModel):
    backend: str
    reference: str  # filesystem path, Doc URL, or CRM record id
    bytes_written: int | None = None


class ArtifactWriter(ABC):
    """Strategy interface: turn a validated artifact into a durable, referenceable output."""

    @abstractmethod
    def write(self, artifact: BaseModel) -> WriteResult: ...


# --------------------------------------------------------------------------- #
# Rendering — shared Markdown rendering for any artifact type
# --------------------------------------------------------------------------- #
def render_markdown(artifact: BaseModel) -> str:
    if isinstance(artifact, Battlecard):
        return _render_battlecard(artifact)
    if isinstance(artifact, AccountBrief):
        return _render_account_brief(artifact)
    # Fallback: pretty JSON for any other schema.
    return f"```json\n{artifact.model_dump_json(indent=2)}\n```\n"


_PRIORITY_RANK = {"high": 0, "med": 1, "low": 2}


def _strategy_md(artifact) -> str:
    """Render the strategy overlay (assessment + action-plan table + objections). Empty → "".

    Additive and conditional (SENTINEL-009 AC-13): a strategy-off artifact has none of these fields
    populated, so this returns "" and no headers appear.
    """
    parts: list[str] = []
    if getattr(artifact, "assessment", None):
        parts.append(f"## Strategic assessment\n\n{artifact.assessment}\n")
    actions = getattr(artifact, "action_plan", None) or []
    if actions:
        parts.append("## Action plan\n")
        parts.append("| Priority | Action | Timeline | Rationale |")
        parts.append("|---|---|---|---|")
        for a in sorted(actions, key=lambda x: _PRIORITY_RANK.get(x.priority, 9)):
            parts.append(f"| {a.priority} | {a.action} | {a.timeline} | {a.rationale} |")
        parts.append("")
    objections = getattr(artifact, "objection_handling", None) or []
    if objections:
        parts.append("## Objection handling\n")
        for o in objections:
            parts.append(f"- **{o.objection}** → {o.reframe}")
        parts.append("")
    return ("\n".join(parts) + "\n") if parts else ""


def _findings(title: str, items) -> str:
    if not items:
        return ""
    lines = [f"## {title}\n"]
    for f in items:
        src = f.source
        cite = f"[{src.label}]({src.url})" if src.url else f"{src.label}"
        lines.append(f"- {f.text}  \n  _{src.boundary.value} · {cite}_")
    return "\n".join(lines) + "\n\n"


def _render_battlecard(b: Battlecard) -> str:
    parts = [f"# Battlecard — {b.target}\n"]
    if b.vertical_context:
        parts.append(f"_Vertical: {b.vertical_context}_\n")
    parts.append(f"> {b.one_line_summary}\n")
    parts.append(f"**Positioning:** {b.positioning}\n")
    parts.append(_findings("Strengths", b.strengths))
    parts.append(_findings("Weaknesses", b.weaknesses))
    parts.append(_findings("Pricing signals", b.pricing_signals))
    parts.append(_findings("Recent developments", b.recent_developments))
    if b.how_to_win:
        parts.append("## How to win against them\n")
        parts += [f"- {x}" for x in b.how_to_win]
        parts.append("")
    strat = _strategy_md(b)  # SENTINEL-009 — empty unless strategy ran
    if strat:
        parts.append(strat)
    if b.gaps:
        parts.append("## Gaps (sources unavailable)\n")
        parts += [f"- _{g.boundary.value}_: {g.what_was_missing} — {g.impact}" for g in b.gaps]
        parts.append("")
    return "\n".join(parts)


def _render_account_brief(a: AccountBrief) -> str:
    parts = [f"# Account Brief — {a.account}\n"]
    if a.vertical_context:
        parts.append(f"_Vertical: {a.vertical_context}_\n")
    parts.append(f"> {a.one_line_summary}\n")
    parts.append(_findings("Public signal", a.public_signal))
    parts.append(_findings("Private signal", a.private_signal))
    if a.merged_insights:
        parts.append("## Merged insights (public ⊕ private)\n")
        parts += [f"- {x}" for x in a.merged_insights]
        parts.append("")
    if a.recommended_actions:
        parts.append("## Recommended actions\n")
        parts += [f"- {x}" for x in a.recommended_actions]
        parts.append("")
    strat = _strategy_md(a)  # SENTINEL-009 — empty unless strategy ran
    if strat:
        parts.append(strat)
    if a.gaps:
        parts.append("## Gaps (sources unavailable)\n")
        parts += [f"- _{g.boundary.value}_: {g.what_was_missing} — {g.impact}" for g in a.gaps]
        parts.append("")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Backend: Markdown (demo backbone, always available)
# --------------------------------------------------------------------------- #
class MarkdownArtifactWriter(ArtifactWriter):
    def __init__(self, out_dir: str | Path = "artifacts_out") -> None:
        self.out_dir = Path(out_dir)

    def write(self, artifact: BaseModel) -> WriteResult:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        name = getattr(artifact, "target", None) or getattr(artifact, "account", "artifact")
        slug = "".join(c if c.isalnum() else "-" for c in str(name).lower()).strip("-")
        kind = type(artifact).__name__.lower()
        path = self.out_dir / f"{kind}-{slug}.md"
        text = render_markdown(artifact)
        path.write_text(text, encoding="utf-8")
        return WriteResult(backend="markdown", reference=str(path), bytes_written=len(text.encode()))


# --------------------------------------------------------------------------- #
# Backend: Google Doc via Workspace MCP (stretch — needs user OAuth)
# --------------------------------------------------------------------------- #
class GoogleDocArtifactWriter(ArtifactWriter):
    """Writes the artifact to the user's Drive via the Workspace MCP private boundary.

    Stub: wired once the Workspace MCP connector + OAuth are connected (decision Q-1).
    """

    def write(self, artifact: BaseModel) -> WriteResult:  # pragma: no cover - needs OAuth
        raise NotImplementedError(
            "GoogleDocArtifactWriter requires a connected Workspace MCP session. "
            "Falls back to MarkdownArtifactWriter until OAuth is wired."
        )


# --------------------------------------------------------------------------- #
# Backend: CRM record via MCP (stretch)
# --------------------------------------------------------------------------- #
class CrmArtifactWriter(ArtifactWriter):
    def write(self, artifact: BaseModel) -> WriteResult:  # pragma: no cover - needs connector
        raise NotImplementedError(
            "CrmArtifactWriter requires a connected CRM MCP session."
        )


def get_writer(backend: str = "markdown", **kwargs) -> ArtifactWriter:
    backends = {
        "markdown": MarkdownArtifactWriter,
        "gdoc": GoogleDocArtifactWriter,
        "crm": CrmArtifactWriter,
    }
    if backend not in backends:
        raise ValueError(f"Unknown writer backend {backend!r}; choose from {list(backends)}")
    return backends[backend](**kwargs) if backend == "markdown" else backends[backend]()
