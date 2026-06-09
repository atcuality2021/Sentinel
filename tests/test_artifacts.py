"""Artifact schema + writer tests (SRS FR-07, FR-08, FR-09)."""

from __future__ import annotations

from sentinel.artifacts.schemas import (
    AccountBrief,
    Battlecard,
    Boundary,
    Finding,
    Gap,
    Source,
    SCHEMA_FOR_MODE,
)
from sentinel.artifacts.writer import MarkdownArtifactWriter, render_markdown


def _pub(text: str) -> Finding:
    return Finding(text=text, source=Source(boundary=Boundary.PUBLIC, label="News", url="https://x"))


def _priv(text: str) -> Finding:
    return Finding(text=text, source=Source(boundary=Boundary.PRIVATE, label="CRM"))


def test_schema_for_mode_mapping():
    assert SCHEMA_FOR_MODE["competitor"] is Battlecard
    assert SCHEMA_FOR_MODE["client"] is AccountBrief


def test_battlecard_validates_and_renders():
    bc = Battlecard(
        target="Stripe",
        one_line_summary="Payments leader",
        positioning="Developer-first payments",
        strengths=[_pub("Best-in-class API")],
        weaknesses=[_pub("Premium pricing")],
        how_to_win=["Lead with on-prem sovereignty"],
        gaps=[Gap(boundary=Boundary.PUBLIC, what_was_missing="filings", impact="no financials")],
    )
    md = render_markdown(bc)
    assert "# Battlecard — Stripe" in md
    assert "public" in md  # provenance tag rendered
    assert "How to win" in md


def test_account_brief_keeps_boundary_separation():
    ab = AccountBrief(
        account="Acme",
        one_line_summary="Warm account, stalled deal",
        public_signal=[_pub("Hiring surge")],
        private_signal=[_priv("Deal stuck at proposal")],
        merged_insights=["Hiring surge + stalled deal → expansion re-engage"],
    )
    # public_signal must be public-boundary; private_signal must be private-boundary
    assert all(f.source.boundary is Boundary.PUBLIC for f in ab.public_signal)
    assert all(f.source.boundary is Boundary.PRIVATE for f in ab.private_signal)
    md = render_markdown(ab)
    assert "Merged insights" in md


def test_markdown_writer_persists_file(tmp_path):
    bc = Battlecard(target="Acme Co", one_line_summary="x", positioning="y")
    writer = MarkdownArtifactWriter(out_dir=tmp_path)
    result = writer.write(bc)
    assert result.backend == "markdown"
    assert result.bytes_written and result.bytes_written > 0
    written = (tmp_path / "battlecard-acme-co.md").read_text()
    assert "Battlecard" in written
