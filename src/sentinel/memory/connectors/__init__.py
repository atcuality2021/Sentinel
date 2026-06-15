# src/sentinel/memory/connectors/__init__.py
from sentinel.memory.connectors.base import SourceConnector, SourceFinding, TRUST_SCORES


def get_connector(source_type: str) -> SourceConnector:
    if source_type == "website":
        from sentinel.memory.connectors.website import WebsiteConnector
        return WebsiteConnector()
    if source_type == "youtube":
        from sentinel.memory.connectors.youtube import YouTubeConnector
        return YouTubeConnector()
    if source_type == "email":
        from sentinel.memory.connectors.email import EmailConnector
        return EmailConnector()
    if source_type == "social":
        from sentinel.memory.connectors.social import SocialConnector
        return SocialConnector()
    raise ValueError(f"Unknown source_type: {source_type!r}")


__all__ = ["get_connector", "SourceConnector", "SourceFinding", "TRUST_SCORES"]
