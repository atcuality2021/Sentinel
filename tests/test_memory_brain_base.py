from __future__ import annotations
import re

import pytest

from sentinel.memory.connectors.base import SourceConnector, SourceFinding
from sentinel.memory.schema import DataBoundary


def test_source_finding_fields():
    f = SourceFinding(
        text="BiltIQ raised ₹3Cr seed.",
        boundary=DataBoundary.PUBLIC,
        source_type="website",
        source_url="https://biltiq.ai/about",
        source_label="BiltIQ website — /about",
        trust_score=0.8,
    )
    assert f.text == "BiltIQ raised ₹3Cr seed."
    assert f.boundary == DataBoundary.PUBLIC
    assert f.trust_score == 0.8


def test_source_finding_requires_valid_source_type():
    with pytest.raises(Exception):
        SourceFinding(
            text="x", boundary=DataBoundary.PUBLIC,
            source_type="invalid",  # not in allowed set
            source_url="https://x", source_label="x", trust_score=0.5,
        )


def test_source_finding_trust_score_range():
    with pytest.raises(Exception):
        SourceFinding(
            text="x", boundary=DataBoundary.PUBLIC,
            source_type="website", source_url="x", source_label="x",
            trust_score=1.5,  # > 1.0
        )


def test_source_connector_is_abstract():
    with pytest.raises(TypeError):
        SourceConnector()  # cannot instantiate ABC directly


def test_email_connector_trust_is_highest():
    from sentinel.memory.connectors.base import TRUST_SCORES
    assert TRUST_SCORES["email"] > TRUST_SCORES["website"]
    assert TRUST_SCORES["website"] > TRUST_SCORES["youtube"]
    assert TRUST_SCORES["youtube"] > TRUST_SCORES["social"]
