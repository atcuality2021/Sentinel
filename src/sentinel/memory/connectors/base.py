# src/sentinel/memory/connectors/base.py
"""SourceConnector ABC and SourceFinding contract for the memory brain."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from sentinel.memory.schema import DataBoundary

SOURCE_TYPES = Literal["website", "youtube", "email", "social"]

TRUST_SCORES: dict[str, float] = {
    "email":   0.95,
    "website": 0.80,
    "youtube": 0.70,
    "social":  0.50,
}

assert set(TRUST_SCORES) == set(get_args(SOURCE_TYPES)), "TRUST_SCORES keys must match SOURCE_TYPES"


class SourceFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    text:         str
    boundary:     DataBoundary
    source_type:  SOURCE_TYPES
    source_url:   str
    source_label: str
    trust_score:  float = Field(ge=0.0, le=1.0)


class SourceConnector(ABC):
    """Base class for all memory source connectors."""

    @property
    @abstractmethod
    def source_type(self) -> SOURCE_TYPES:
        ...

    @abstractmethod
    async def fetch(self, entity: str, config: dict[str, object]) -> list[SourceFinding]:
        """Fetch raw content for entity and return extracted SourceFindings."""
