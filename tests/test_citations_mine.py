"""Tests for _mine_urls_from_artifact citation fallback (citations=0 bug fix).

The 26B model reliably populates Finding.source.url within list fields but never
fills the top-level sources: [] field on the artifact. _mine_urls_from_artifact
is the fallback that rescues those URLs.
"""

from sentinel.agent.dag import _mine_urls_from_artifact


# ── Finding-shaped items (the common case for all domain artifacts) ────────── #

def test_finding_shaped_items_extracted():
    """Battlecard / AccountBrief / SoftwareBrief shape: list fields of Finding-like dicts."""
    art = {
        "strengths": [
            {
                "text": "Strong enterprise sales motion",
                "source": {"boundary": "public", "label": "TechCrunch", "url": "https://techcrunch.com/a"},
            },
            {
                "text": "Good docs",
                "source": {"boundary": "public", "label": "HN", "url": "https://news.ycombinator.com/b"},
            },
        ],
        "weaknesses": [
            {
                "text": "Slow onboarding",
                "source": {"boundary": "public", "label": "G2", "url": "https://g2.com/c"},
            }
        ],
        "sources": [],  # model left this empty
    }
    results = _mine_urls_from_artifact(art)
    urls = [r.url for r in results]
    assert "https://techcrunch.com/a" in urls
    assert "https://news.ycombinator.com/b" in urls
    assert "https://g2.com/c" in urls
    assert len(results) == 3


def test_private_boundary_preserved():
    """Private findings keep their boundary tag."""
    art = {
        "private_signal": [
            {
                "text": "Deal stalled at procurement",
                "source": {"boundary": "private", "label": "CRM note", "url": "https://crm.internal/deal/42"},
            }
        ],
    }
    results = _mine_urls_from_artifact(art)
    assert len(results) == 1
    assert results[0].boundary == "private"
    assert results[0].url == "https://crm.internal/deal/42"


def test_unknown_boundary_defaults_to_public():
    """An unrecognised boundary value falls back to 'public' safely."""
    art = {
        "findings": [
            {"text": "claim", "source": {"boundary": "classified", "label": "X", "url": "https://example.com/x"}},
        ]
    }
    results = _mine_urls_from_artifact(art)
    assert results[0].boundary == "public"


def test_label_falls_back_to_truncated_text():
    """When source.label is missing, the finding text is used (truncated to 80 chars)."""
    art = {
        "market_dynamics": [
            {"text": "A" * 100, "source": {"boundary": "public", "url": "https://example.com/md"}},
        ]
    }
    results = _mine_urls_from_artifact(art)
    assert results[0].label == "A" * 80


def test_finding_without_url_skipped():
    """Finding items with no source.url are silently dropped."""
    art = {
        "strengths": [
            {"text": "claim", "source": {"boundary": "public", "label": "Internal", "url": ""}},
            {"text": "other", "source": {"boundary": "public", "label": "Blog", "url": "https://blog.com/x"}},
        ]
    }
    results = _mine_urls_from_artifact(art)
    assert len(results) == 1
    assert results[0].url == "https://blog.com/x"


def test_finding_without_source_dict_skipped():
    """Items without a dict-shaped 'source' field are ignored."""
    art = {
        "strengths": [
            {"text": "claim", "source": "TechCrunch"},  # wrong shape
            {"text": "other", "source": {"boundary": "public", "label": "Blog", "url": "https://blog.com/y"}},
        ]
    }
    results = _mine_urls_from_artifact(art)
    assert len(results) == 1


# ── ProductResearch flat shape ─────────────────────────────────────────────── #

def test_products_found_source_url():
    """ProductResearch: flat source_url field is still mined."""
    art = {
        "products_found": [
            {"name": "Laptop A", "brand": "ASUS", "source_url": "https://store.com/a"},
            {"name": "Laptop B", "brand": "HP", "source_url": ""},
        ],
        "sources": [],
    }
    results = _mine_urls_from_artifact(art)
    urls = [r.url for r in results]
    assert "https://store.com/a" in urls
    assert len([r for r in results if r.url == "https://store.com/a"]) == 1


def test_action_plan_url():
    """GovernmentProposal: action_plan[].url is mined."""
    art = {
        "action_plan": [
            {"action": "Set up relief camp", "url": "https://ndma.gov.in/plan"},
        ]
    }
    results = _mine_urls_from_artifact(art)
    assert any(r.url == "https://ndma.gov.in/plan" for r in results)


def test_top_level_url_string():
    """A bare URL string at the top level is captured."""
    art = {"website": "https://example.com/company"}
    results = _mine_urls_from_artifact(art)
    assert any(r.url == "https://example.com/company" for r in results)


def test_empty_artifact_returns_empty():
    assert _mine_urls_from_artifact({}) == []


def test_non_list_fields_ignored():
    """Scalar and dict fields that aren't lists are not walked for Finding shapes."""
    art = {
        "summary": "some text",
        "meta": {"url": "https://example.com"},  # dict, not in a list
    }
    results = _mine_urls_from_artifact(art)
    assert results == []
