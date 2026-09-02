"""Phase 1: keyword -> PubMed PMIDs, with an IF prefilter and a History handle."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List

from .eutils import EutilsClient

# Cheap prefilter (step A in the brief): narrows Phase 1 to articles that at
# least *mention* the IF method. Detects mentions, not images -- Phase 2 does
# the real, figure-level check.
IF_PREFILTER_TERM = '("Fluorescent Antibody Technique"[MeSH Terms] OR immunofluorescence[tiab])'


@dataclass
class SearchResult:
    term: str
    count: int
    webenv: str
    query_key: str
    pmids: List[str]

    @property
    def truncated(self) -> bool:
        return self.count > len(self.pmids)


def build_term(keywords: str, apply_if_prefilter: bool = True) -> str:
    keywords = keywords.strip()
    if apply_if_prefilter:
        return f"({keywords}) AND {IF_PREFILTER_TERM}"
    return keywords


def phase1_search(
    client: EutilsClient,
    keywords: str,
    apply_if_prefilter: bool = True,
    retmax: int = 10000,
) -> SearchResult:
    term = build_term(keywords, apply_if_prefilter)
    resp = client.esearch(db="pubmed", term=term, usehistory="y", retmax=retmax, retmode="xml")
    root = ET.fromstring(resp.content)

    count = int(root.findtext("Count", default="0"))
    webenv = root.findtext("WebEnv") or ""
    query_key = root.findtext("QueryKey") or ""
    pmids = [el.text for el in root.findall("./IdList/Id") if el.text]

    return SearchResult(term=term, count=count, webenv=webenv, query_key=query_key, pmids=pmids)
