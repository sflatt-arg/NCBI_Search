# Project brief — PubMed → PMC immunofluorescence-image filter

> Paste this as the opening message in a fresh Claude session (VS Code / Claude Code) started from an empty folder. It captures decisions already made so you don't re-derive them. **Read the "Open decisions" section and confirm those two points with me before writing the full implementation.**

## Role & objective

You are an expert data scientist working in the biomedical domain. Build, for a company, a Python tool that uses the **NCBI E-utilities** (with an API key) to:

- **Phase 1 — search:** query PubMed by a set of keywords (a user-input parameter) and collect matching articles.
- **Phase 2 — filter:** keep only articles that **contain immunofluorescence (IF) images**.

## Established facts (do not re-litigate — these are settled)

- **PubMed holds metadata only** (title, abstract, authors, dates, DOI, MeSH, publication types). It stores **nothing about figures or images.**
- **Figures live in the full text, which lives in PMC** (PubMed Central) — a *different* Entrez database — and reliably only for the **Open-Access (OA) subset**.
- Therefore "has an IF image" **cannot** be answered from PubMed records alone; it requires crossing into PMC full text.
- Phase-1 per-article retrieval options:
  - `ESearch` returns **PMIDs** + a History handle (`WebEnv` / `query_key`) — keep the handle, don't re-send ID lists.
  - `ESummary` → DocSum (lightweight: title, journal, dates, DOI, pubtype).
  - `EFetch (retmode=xml)` → full MEDLINE record (abstract, **MeSH**, publication types) — where any *textual* IF signal would live.

## Chosen approach: heuristic prefilter (A) → PMC caption inspection (B)

**A. Cheap PubMed prefilter.** Add an IF signal straight into the Phase-1 `term`, e.g. `"Fluorescent Antibody Technique"[MeSH]` or `immunofluorescence[tiab]`. Shrinks the set cheaply. **Caveat:** this detects that the *method was mentioned*, not that an IF *image* exists — mediocre precision and recall on its own.

**B. PMC figure-caption inspection (the real filter).** For survivors of A:
1. `ELink` from `pubmed` → `pmc` to get PMCIDs.
2. `EFetch db=pmc, retmode=xml` to get JATS full text.
3. Parse `<fig>` / `<caption>` elements and keyword-match captions ("immunofluorescence", "stained for", "DAPI", "confocal", antibody markers…).
   This is figure-level, so it's the closest signal to an actual image **without downloading pixels.** **Caveat:** matches caption *text*, not the image itself, and only works for OA full-text articles.

**(Deferred) C. Real image classification.** If caption-matching proves too imprecise: pull figure image files via the **PMC Open Access Web Service** (`.tar.gz` per-article packages) and classify with a vision model. Heaviest; still OA-subset only. Do **not** build this unless we decide B is insufficient.

**Pipeline the survivors on the Entrez History server** (carry `WebEnv`/`query_key`) instead of resending ID lists.

## Hard constraints

- **Cost:** everything above is **free**. No paid tier anywhere in this path.
- **Auth:** free NCBI account + **API key** (raises rate limit ~3→10 requests/sec). **Load the key from an environment variable — never hardcode it.** Also send `tool=` and `email=` on every request (NCBI uses these to warn before blocking).
- **Rate limits / politeness:** ≤3 req/s without key, ≤10 with key; batch via History; schedule large jobs off-peak (9pm–5am ET) per NCBI guidance.
- **Coverage ceiling (critical):** an arbitrary PubMed hit falls into one of three buckets when linked to PMC —
  1. **OA full-text XML** → captions/figures available ✅
  2. **In PMC but access-restricted** → usually metadata only ⚠️
  3. **Not in PMC at all** → nothing ❌
  Real-world gauge: only ~25% of an arbitrary set tends to be OA full text. **The filter therefore runs on the OA slice, not the whole search.** The pipeline must report this explicitly.

## Open decisions — confirm with me before full implementation

1. **Is a PMC-OA-only sample acceptable,** or does the company need paywalled coverage too? (No free E-utilities route reaches paywalled figures — this is a scoping decision, not a coding one.)
2. **What counts as an "immunofluorescence image"** — any figure from an IF protocol, or specifically micrographs? This determines whether caption keyword-matching (B) suffices or we genuinely need image classification (C).

## What I want you to do now (in order)

1. Briefly restate the plan and ask me the two open-decision questions above.
2. Propose a minimal repo layout (e.g. `src/`, config for keys via env, `requirements.txt`, a `README`), and a `.env.example` — do not commit secrets.
3. Implement **Phase 1** (keyword → PMIDs via ESearch with History), with the API key/tool/email plumbing and rate limiting.
4. Implement **Phase 2 option B** (ELink → EFetch PMC XML → caption parse), and for **every** input article report an explicit outcome: `passed` (matched caption), `failed` (full text present, no IF caption), or `uninspectable` (not OA / not in PMC), so the coverage loss is visible.
5. Keep it dependency-light (`requests` + stdlib XML, or Biopython if you justify it). No full image-download/classification unless we jointly decide to add C.

## Endpoint reference

```
esearch.fcgi?db=pubmed&term=<keywords>&usehistory=y&api_key=...&tool=...&email=...
elink.fcgi?dbfrom=pubmed&db=pmc&id=<pmids>            # PMID -> PMCID
efetch.fcgi?db=pmc&id=<pmcid>&retmode=xml            # JATS full text incl. <fig>/<caption>
# base: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
```
