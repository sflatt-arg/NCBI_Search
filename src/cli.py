from __future__ import annotations

import argparse
import csv
import sys

from .config import NCBIConfig, load_config
from .eutils import EutilsClient
from .pipeline import PipelineResult, run_pipeline


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search PubMed by keywords, then filter for articles with immunofluorescence images "
        "(PMC open-access caption match)."
    )
    parser.add_argument("--keywords", required=True, help='PubMed search term, e.g. "breast cancer AND organoid"')
    parser.add_argument("--retmax", type=int, default=1000, help="Max PMIDs to pull from Phase 1 (default: 1000)")
    parser.add_argument(
        "--no-prefilter",
        action="store_true",
        help="Skip the cheap IF term/MeSH prefilter and search on --keywords alone",
    )
    parser.add_argument("--output", default="results.csv", help="Path to write the per-article CSV report")
    parser.add_argument("--elink-chunk-size", type=int, default=200)
    parser.add_argument("--efetch-chunk-size", type=int, default=100)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the parameters used and a quantified breakdown of every pipeline step",
    )
    return parser.parse_args(argv)


def print_verbose_report(args: argparse.Namespace, config: NCBIConfig, result: PipelineResult) -> None:
    s = result.stepwise_summary()

    print("\n=== Parameters ===")
    print(f"  keywords            : {args.keywords!r}")
    print(f"  IF prefilter        : {'off' if args.no_prefilter else 'on'}")
    print(f"  retmax              : {args.retmax}")
    print(f"  elink chunk size    : {args.elink_chunk_size}")
    print(f"  efetch chunk size   : {args.efetch_chunk_size}")
    print(f"  output CSV          : {args.output}")
    print(f"  NCBI tool           : {config.tool}")
    print(f"  NCBI email          : {config.email}")
    key_state = "provided" if config.api_key else "not provided"
    print(f"  NCBI api key        : {key_state}")
    print(f"  rate limit          : {config.max_requests_per_second} req/s")

    p1 = s["phase1_search"]
    print("\n=== Step 0-1: Phase 1 - PubMed ESearch ===")
    print(f"  search term              : {p1['search_term']}")
    print(f"  PubMed hits (Count)      : {p1['pubmed_hits']}")
    print(
        f"  PMIDs retrieved (retmax) : {p1['pmids_retrieved']} "
        f"({p1['pmids_retrieved_pct_of_hits']}% of hits)"
        + (" [TRUNCATED by --retmax]" if p1["truncated_by_retmax"] else "")
    )

    e = s["phase2_elink"]
    print(f"\n=== Step 2: ELink pubmed->pmc (base: {e['base']} PMIDs) ===")
    print(f"  linked to a PMCID   : {e['linked_to_pmc']} ({e['linked_to_pmc_pct']}%)")
    print(f"  not in PMC          : {e['not_in_pmc']} ({e['not_in_pmc_pct']}%)  -> uninspectable")

    f = s["phase2_efetch"]
    print(f"\n=== Step 3: EFetch PMC full text (base: {f['base']} linked PMCIDs) ===")
    print(f"  full text fetched       : {f['fetched_fulltext']} ({f['fetched_fulltext_pct']}%)")
    print(f"  access-restricted/failed: {f['no_fulltext']} ({f['no_fulltext_pct']}%)  -> uninspectable")

    c = s["phase2_caption_match"]
    print(f"\n=== Step 4: Caption keyword match (base: {c['base']} articles with full text) ===")
    print(f"  passed (IF caption match) : {c['passed']} ({c['passed_pct']}%)")
    print(f"  failed (no IF caption)    : {c['failed']} ({c['failed_pct']}%)")

    fin = s["final"]
    print(f"\n=== Final breakdown (base: {fin['base']} articles evaluated) ===")
    print(f"  passed        : {fin['passed']} ({fin['passed_pct']}%)")
    print(f"  failed        : {fin['failed']} ({fin['failed_pct']}%)")
    print(f"  uninspectable : {fin['uninspectable']} ({fin['uninspectable_pct']}%)")


def main(argv=None) -> int:
    args = parse_args(argv)
    config = load_config()
    client = EutilsClient(config)

    print(f"Phase 1: searching PubMed for: {args.keywords!r} (prefilter={'off' if args.no_prefilter else 'on'})")
    result = run_pipeline(
        client,
        keywords=args.keywords,
        apply_if_prefilter=not args.no_prefilter,
        retmax=args.retmax,
        elink_chunk_size=args.elink_chunk_size,
        efetch_chunk_size=args.efetch_chunk_size,
    )

    print(f"  search term: {result.search.term}")
    print(f"  PubMed hits: {result.search.count}" + (" (truncated by --retmax)" if result.search.truncated else ""))
    print(f"  articles carried into Phase 2: {len(result.outcomes)}")

    if not result.outcomes:
        print("No articles to filter. Exiting.")
        return 0

    print("Phase 2: linking to PMC and inspecting figure captions...")

    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["pmid", "pmcid", "status", "reason", "matched_keywords", "sample_caption"])
        for o in result.outcomes:
            writer.writerow(
                [o.pmid, o.pmcid or "", o.status, o.reason, ";".join(o.matched_keywords), o.sample_caption]
            )

    if args.verbose:
        print_verbose_report(args, config, result)
    else:
        summary = result.summary()
        print("\n--- Summary ---")
        print(f"Total articles evaluated:     {summary['total_articles']}")
        print(f"Linked to a PMC record:       {summary['linked_to_pmc']} ({summary['linked_to_pmc_pct']}%)")
        print(f"  passed (IF caption match):  {summary['passed']}")
        print(f"  failed (full text, no IF):  {summary['failed']}")
        print(f"  uninspectable (no OA text): {summary['uninspectable']}")

    print(
        "\nNote: this filter only runs on the PMC open-access subset. Articles not in PMC, "
        "or in PMC without open full text, are reported as 'uninspectable' rather than dropped silently."
    )
    print(f"\nPer-article report written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
