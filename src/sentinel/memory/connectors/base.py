# src/sentinel/memory/connectors/base.py
"""SourceConnector ABC and SourceFinding contract for the memory brain."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

from sentinel.memory.schema import DataBoundary

SOURCE_TYPES = Literal["website", "youtube", "email", "social"]

TRUST_SCORES: dict[str, float] = {
    "email":   0.95,
    "website": 0.80,
    "youtube": 0.70,
    "social":  0.50,
}


class SourceFinding(BaseModel):
    text:         str
    boundary:     DataBoundary
    source_type:  SOURCE_TYPES
    source_url:   str
    source_label: str
    trust_score:  float = Field(ge=0.0, le=1.0)


class SourceConnector(ABC):
    """Base class for all memory source connectors."""

    source_type: str  # must be set by subclass

    @abstractmethod
    async def fetch(self, entity: str, config: dict) -> list[SourceFinding]:
        """Fetch raw content for entity and return extracted SourceFindings."""
