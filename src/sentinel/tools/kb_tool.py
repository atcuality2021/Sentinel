"""KB function tool — wraps hybrid_search as an ADK-compatible callable.

Returns a plain Python function (ADK derives schema from signature + docstring).
The project_id is baked into the closure so agents just pass a query string.
"""
from __future__ import annotations

from typing import Any


def build_kb_tool(project_id: str) -> Any:
    """Return a search_knowledge_base function tool scoped to ``project_id``."""
    from sentinel.memory.store import data_dir as _dd

    def search_knowledge_base(query: str) -> list[dict]:
        """Search the project Knowledge Base built from indexed URLs, PDFs, and uploaded docs.

        Use this BEFORE web search when the query is about this project's domain, uploaded
        documents, or previously researched topics. Results are ranked by relevance.

        Args:
            query: Natural language question, e.g. "What are Assam's key IT challenges?"

        Returns:
            List of {url, title, text, score} chunks, best match first.
        """
        try:
            from sentinel.kb.search import hybrid_search
            hits = hybrid_search(project_id, str(_dd() / "kb"), query, rerank_top_k=5)
            if not hits:
                return [{"status": "no_results", "message": "Nothing indexed yet for this project."}]
            return [h.to_dict() for h in hits]
        except Exception as exc:  # pragma: no cover
            return [{"status": "error", "message": str(exc)[:200]}]

    return search_knowledge_base
