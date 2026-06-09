from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import uuid


class SourceType(str, Enum):
    WEB = "web"
    SOCIAL = "social"
    DOCUMENT = "document"


class CrawlStatus(str, Enum):
    PENDING = "pending"
    CRAWLING = "crawling"
    INDEXED = "indexed"
    FAILED = "failed"


@dataclass
class KBSource:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    url: str = ""
    source_type: SourceType = SourceType.WEB
    status: CrawlStatus = CrawlStatus.PENDING
    chunk_count: int = 0
    error: str | None = None


@dataclass
class KBChunk:
    id: str
    project_id: str
    source_id: str
    url: str
    title: str
    text: str
    source_type: str


@dataclass
class KBSearchResult:
    chunk_id: str
    url: str
    title: str
    text: str
    source_type: str
    score: float

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "source_type": self.source_type,
            "score": round(self.score, 4),
        }
