"""Deterministic turn-end extraction (SENTINEL-002) — borrowed FactExtractor shape.

Walk a finished artifact's ``Finding`` lists and emit one ``MemoryEntry`` per finding, **stamped
with that finding's own ``source.boundary``** (public finding → PUBLIC entry, private → PRIVATE).
No LLM: extraction is deterministic so a private-derived insight can never be silently re-tagged
public (NFR-1). Derived prose (merged_insights / how_to_win / recommended_actions) is intentionally
*not* stored in v1 — it blends boundaries and a mis-tag there would be a boundary leak (see design
§2.4). A local-vLLM Tier-2 extractor is the noted follow-up.
"""

from __future__ import annotations

from sentinel.artifacts.schemas import AccountBrief, Battlecard, Finding
from sentinel.memory.schema import DataBoundary, MemoryEntry, MemoryType, normalize_entity


def _entry(entity: str, f: Finding) -> MemoryEntry:
    return MemoryEntry(
        entity=entity,
        boundary=f.source.boundary,
        memory_type=MemoryType.FINDING,
        content=f.text,
        source_label=f.source.label,
        source_url=f.source.url,
    )


def _all_findings(artifact) -> list[Finding]:
    """Walk every list field on a pydantic model and collect Finding instances."""
    out: list[Finding] = []
    for field_name in type(artifact).model_fields:
        val = getattr(artifact, field_name, None)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, Finding):
                    out.append(item)
    return out


def extract_entries(entity: str, artifact) -> list[MemoryEntry]:
    """One boundary-stamped entry per concrete finding in the artifact.

    Battlecard and AccountBrief use explicit field ordering (backward compat).
    All SENTINEL-014 domain artifacts (SoftwareBrief, FinancialProfile,
    AcademicBrief, NutritionBrief, TravelBrief) and any future types
    fall through to the generic model_fields walker.
    """
    entity = normalize_entity(entity)
    out: list[MemoryEntry] = []
    if isinstance(artifact, Battlecard):
        for lst in (
            artifact.strengths,
            artifact.weaknesses,
            artifact.pricing_signals,
            artifact.recent_developments,
        ):
            out.extend(_entry(entity, f) for f in lst)
    elif isinstance(artifact, AccountBrief):
        out.extend(_entry(entity, f) for f in artifact.public_signal)
        out.extend(_entry(entity, f) for f in artifact.private_signal)
    else:
        out.extend(_entry(entity, f) for f in _all_findings(artifact))
    return out


def finding_texts(artifact) -> list[str]:
    """The concrete finding texts of an artifact (drives the run record + delta)."""
    return [e.content for e in extract_entries("_", artifact)]


def boundary_counts(artifact) -> tuple[int, int]:
    """(public, private) count of stored findings — for the run record's provenance counters."""
    pub = priv = 0
    for e in extract_entries("_", artifact):
        if e.boundary == DataBoundary.PUBLIC:
            pub += 1
        else:
            priv += 1
    return pub, priv
