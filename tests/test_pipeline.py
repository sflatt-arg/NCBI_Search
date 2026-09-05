"""The one change made to the existing pipeline: the optional if_keywords arg."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from src import pipeline as P

ARTICLE_XML = """<article>
  <front><article-meta><article-id pub-id-type="pmc">PMC1</article-id></article-meta></front>
  <body><fig><caption><p>DAPI counterstain of the section</p></caption></fig></body>
</article>"""


@pytest.fixture
def stub_network(monkeypatch):
    """Replaces the three network calls run_pipeline makes with fixed data."""
    article = ET.fromstring(ARTICLE_XML)
    monkeypatch.setattr(
        P, "phase1_search",
        lambda *a, **k: P.SearchResult(term="t", count=1, webenv="", query_key="", pmids=["111"]),
    )
    monkeypatch.setattr(P, "link_pmids_to_pmcids", lambda *a, **k: {"111": "PMC1"})
    monkeypatch.setattr(P, "fetch_pmc_articles", lambda *a, **k: {"PMC1": article})


def test_default_keywords_unchanged(stub_network):
    """Omitting if_keywords must behave exactly as the CLI always has."""
    result = P.run_pipeline(MagicMock(), "x")
    outcome = result.outcomes[0]
    assert outcome.status == P.STATUS_PASSED
    assert outcome.matched_keywords == ["dapi"]


def test_explicit_none_matches_default(stub_network):
    assert P.run_pipeline(MagicMock(), "x", if_keywords=None).outcomes[0].matched_keywords == ["dapi"]


def test_custom_keywords_replace_the_default_list(stub_network):
    result = P.run_pipeline(MagicMock(), "x", if_keywords=["counterstain"])
    assert result.outcomes[0].matched_keywords == ["counterstain"]


def test_custom_keywords_can_exclude_a_default_match(stub_network):
    """A caption that passes by default must fail under a narrower list."""
    result = P.run_pipeline(MagicMock(), "x", if_keywords=["nonexistent-term"])
    assert result.outcomes[0].status == P.STATUS_FAILED
    assert result.outcomes[0].matched_keywords == []
