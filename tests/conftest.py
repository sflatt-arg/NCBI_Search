"""Shared fixtures: an AppTest factory and a canned PipelineResult."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import List, Optional

import pytest
from streamlit.testing.v1 import AppTest

from src.pipeline import ArticleOutcome, PipelineResult
from src.search import SearchResult

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


@pytest.fixture
def app():
    """Returns a factory for a booted AppTest, optionally with credentials set."""

    def _make(with_credentials: bool = True) -> AppTest:
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        if with_credentials:
            at.session_state["credentials"] = {"email": "tester@example.org", "api_key": ""}
        return at

    return _make


@pytest.fixture
def run_record():
    """A canned run record, as the Run page would store it."""

    def _make(outcomes: Optional[List[ArticleOutcome]] = None, count: int = 3, pmids=("1", "2")):
        if outcomes is None:
            outcomes = [
                ArticleOutcome("1", "PMC1", "passed", "if_caption_matched", ["dapi"], "A DAPI caption"),
                ArticleOutcome("2", None, "uninspectable", "not_in_pmc"),
            ]
        return {
            "result": PipelineResult(
                search=SearchResult(term="(q) AND if", count=count, webenv="", query_key="", pmids=list(pmids)),
                outcomes=outcomes,
            ),
            "keywords": "hepatocyte organoid",
            "params": {
                "retmax": 20,
                "apply_if_prefilter": True,
                "elink_chunk_size": 200,
                "efetch_chunk_size": 100,
                "if_keywords": ["dapi"],
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
        }

    return _make
