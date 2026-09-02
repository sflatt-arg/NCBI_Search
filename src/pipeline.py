"""Orchestrates Phase 1 (search) + Phase 2 (PMC caption filter) and reports
an explicit outcome for every input article, so PMC-OA coverage loss is
visible rather than silently dropped."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from .eutils import EutilsClient
from .filter_pmc import fetch_pmc_articles, find_matching_captions, link_pmids_to_pmcids
from .search import SearchResult, phase1_search

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_UNINSPECTABLE = "uninspectable"

REASON_NOT_IN_PMC = "not_in_pmc"
REASON_PMC_NO_FULLTEXT = "pmc_no_fulltext"  # in PMC but access-restricted / EFetch returned nothing
REASON_NO_IF_CAPTION = "no_if_caption"
REASON_IF_CAPTION_MATCHED = "if_caption_matched"


@dataclass
class ArticleOutcome:
    pmid: str
    pmcid: Optional[str]
    status: str
    reason: str
    matched_keywords: List[str] = field(default_factory=list)
    sample_caption: str = ""


@dataclass
class PipelineResult:
    search: SearchResult
    outcomes: List[ArticleOutcome]

    def summary(self) -> dict:
        counts = Counter(o.status for o in self.outcomes)
        total = len(self.outcomes)
        in_pmc = sum(1 for o in self.outcomes if o.pmcid)
        return {
            "total_articles": total,
            "pubmed_total_hits": self.search.count,
            "search_truncated": self.search.truncated,
            "linked_to_pmc": in_pmc,
            "linked_to_pmc_pct": round(100 * in_pmc / total, 1) if total else 0.0,
            "passed": counts.get(STATUS_PASSED, 0),
            "failed": counts.get(STATUS_FAILED, 0),
            "uninspectable": counts.get(STATUS_UNINSPECTABLE, 0),
        }

    def stepwise_summary(self) -> dict:
        """Funnel counts at each pipeline stage, each expressed as a
        percentage of the stage right before it (not of the original total)."""

        def pct(n: int, d: int) -> float:
            return round(100 * n / d, 1) if d else 0.0

        total = len(self.outcomes)
        reasons = Counter(o.reason for o in self.outcomes)
        statuses = Counter(o.status for o in self.outcomes)

        linked = sum(1 for o in self.outcomes if o.pmcid)
        not_in_pmc = reasons.get(REASON_NOT_IN_PMC, 0)

        fetched = sum(1 for o in self.outcomes if o.pmcid and o.reason != REASON_PMC_NO_FULLTEXT)
        no_fulltext = reasons.get(REASON_PMC_NO_FULLTEXT, 0)

        passed = statuses.get(STATUS_PASSED, 0)
        failed = statuses.get(STATUS_FAILED, 0)
        uninspectable = statuses.get(STATUS_UNINSPECTABLE, 0)

        return {
            "phase1_search": {
                "search_term": self.search.term,
                "pubmed_hits": self.search.count,
                "pmids_retrieved": total,
                "pmids_retrieved_pct_of_hits": pct(total, self.search.count),
                "truncated_by_retmax": self.search.truncated,
            },
            "phase2_elink": {
                "base": total,
                "linked_to_pmc": linked,
                "linked_to_pmc_pct": pct(linked, total),
                "not_in_pmc": not_in_pmc,
                "not_in_pmc_pct": pct(not_in_pmc, total),
            },
            "phase2_efetch": {
                "base": linked,
                "fetched_fulltext": fetched,
                "fetched_fulltext_pct": pct(fetched, linked),
                "no_fulltext": no_fulltext,
                "no_fulltext_pct": pct(no_fulltext, linked),
            },
            "phase2_caption_match": {
                "base": fetched,
                "passed": passed,
                "passed_pct": pct(passed, fetched),
                "failed": failed,
                "failed_pct": pct(failed, fetched),
            },
            "final": {
                "base": total,
                "passed": passed,
                "passed_pct": pct(passed, total),
                "failed": failed,
                "failed_pct": pct(failed, total),
                "uninspectable": uninspectable,
                "uninspectable_pct": pct(uninspectable, total),
            },
        }


def run_pipeline(
    client: EutilsClient,
    keywords: str,
    apply_if_prefilter: bool = True,
    retmax: int = 10000,
    elink_chunk_size: int = 200,
    efetch_chunk_size: int = 100,
) -> PipelineResult:
    search_result = phase1_search(client, keywords, apply_if_prefilter=apply_if_prefilter, retmax=retmax)

    if not search_result.pmids:
        return PipelineResult(search=search_result, outcomes=[])

    pmid_to_pmcid = link_pmids_to_pmcids(client, search_result.pmids, chunk_size=elink_chunk_size)
    pmcids = sorted({pmcid for pmcid in pmid_to_pmcid.values() if pmcid})
    articles_by_pmcid = fetch_pmc_articles(client, pmcids, chunk_size=efetch_chunk_size)

    outcomes: List[ArticleOutcome] = []
    for pmid in search_result.pmids:
        pmcid = pmid_to_pmcid.get(pmid)

        if not pmcid:
            outcomes.append(
                ArticleOutcome(pmid=pmid, pmcid=None, status=STATUS_UNINSPECTABLE, reason=REASON_NOT_IN_PMC)
            )
            continue

        article_el = articles_by_pmcid.get(pmcid)
        if article_el is None:
            outcomes.append(
                ArticleOutcome(pmid=pmid, pmcid=pmcid, status=STATUS_UNINSPECTABLE, reason=REASON_PMC_NO_FULLTEXT)
            )
            continue

        matches = find_matching_captions(article_el)
        if matches:
            matched_keywords = sorted({kw for m in matches for kw in m["keywords"]})
            sample_caption = str(matches[0]["caption"])[:300]
            outcomes.append(
                ArticleOutcome(
                    pmid=pmid,
                    pmcid=pmcid,
                    status=STATUS_PASSED,
                    reason=REASON_IF_CAPTION_MATCHED,
                    matched_keywords=matched_keywords,
                    sample_caption=sample_caption,
                )
            )
        else:
            outcomes.append(
                ArticleOutcome(pmid=pmid, pmcid=pmcid, status=STATUS_FAILED, reason=REASON_NO_IF_CAPTION)
            )

    return PipelineResult(search=search_result, outcomes=outcomes)
