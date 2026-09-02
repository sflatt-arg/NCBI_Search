"""Phase 2 (option B): ELink pubmed->pmc, EFetch JATS XML, caption keyword match.

Figure-level caption text is the closest signal to an actual IF image we can
get without downloading pixels. It matches caption *text*, not the image
itself, and only works for the PMC Open-Access subset -- see coverage notes
in the README.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from .eutils import EutilsClient
from .utils import chunk_list

# Heuristic, editable keyword list. Broad substrings (e.g. "stained for") are
# deliberately left out because they also match non-IF stains (H&E, etc.) and
# would flood results with false positives.
IF_CAPTION_KEYWORDS = [
    "immunofluorescence",
    "immunofluorescent",
    "immuno-fluorescence",
    "if staining",
    "if image",
    "if microscopy",
    "confocal microscopy",
    "confocal image",
    "confocal laser scanning",
    "dapi",
    "hoechst",
    "alexa fluor",
    "fitc-conjugated",
    "fitc conjugated",
    "tritc",
    "cy3",
    "cy5",
    "secondary antibody",
    "immunostaining",
    "immunolabeling",
    "immunolabelling",
    "co-localization",
    "colocalization",
    "fluorescently labeled",
    "fluorescently labelled",
    "fluorescence microscopy",
]


def link_pmids_to_pmcids(
    client: EutilsClient,
    pmids: List[str],
    chunk_size: int = 200,
) -> Dict[str, Optional[str]]:
    """Maps each PMID to a PMCID, or None if it has no PMC link."""
    mapping: Dict[str, Optional[str]] = {}
    for chunk in chunk_list(pmids, chunk_size):
        resp = client.elink(dbfrom="pubmed", db="pmc", ids=chunk, retmode="xml")
        root = ET.fromstring(resp.content)
        for linkset in root.findall("LinkSet"):
            pmid = linkset.findtext("IdList/Id")
            if not pmid:
                continue
            pmcid = None
            linksetdb = linkset.find("LinkSetDb")
            if linksetdb is not None:
                id_el = linksetdb.find("Link/Id")
                if id_el is not None and id_el.text:
                    pmcid = f"PMC{id_el.text}"
            mapping[pmid] = pmcid
    return mapping


def _extract_pmcid(article_el: ET.Element) -> Optional[str]:
    for aid in article_el.findall(".//article-id"):
        if aid.get("pub-id-type") in ("pmc", "pmcid") and aid.text:
            value = aid.text.strip()
            return value if value.upper().startswith("PMC") else f"PMC{value}"
    return None


def fetch_pmc_articles(
    client: EutilsClient,
    pmcids: List[str],
    chunk_size: int = 100,
) -> Dict[str, ET.Element]:
    """Fetches JATS full text for each PMCID. Missing keys mean EFetch didn't
    return that article (e.g. it's in PMC but access-restricted)."""
    articles: Dict[str, ET.Element] = {}
    numeric_ids = [pmcid.replace("PMC", "") for pmcid in pmcids]
    for chunk in chunk_list(numeric_ids, chunk_size):
        resp = client.efetch(db="pmc", ids=chunk, retmode="xml")
        root = ET.fromstring(resp.content)
        for article_el in root.findall("article"):
            pmcid = _extract_pmcid(article_el)
            if pmcid:
                articles[pmcid] = article_el
    return articles


def find_matching_captions(
    article_el: ET.Element,
    keywords: List[str] = IF_CAPTION_KEYWORDS,
) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    for fig in article_el.findall(".//fig"):
        caption_el = fig.find("caption")
        if caption_el is None:
            continue
        text = " ".join(t.strip() for t in caption_el.itertext() if t.strip())
        text_lower = text.lower()
        hit_keywords = [kw for kw in keywords if kw in text_lower]
        if hit_keywords:
            matches.append({"caption": text, "keywords": hit_keywords})
    return matches
