# PubMed → PMC immunofluorescence-image filter

Searches PubMed by keyword, then filters the results down to articles that
appear to contain an **immunofluorescence (IF) image**, using NCBI's free
E-utilities.

## Why this only covers part of PubMed

PubMed stores metadata only (title, abstract, MeSH, dates) — never figures.
Figures live in the full text, which lives in PMC, and reliably only for the
**open-access (OA) subset**. In practice only ~25% of an arbitrary PubMed
search tends to have OA full text. This tool cannot see figures for the rest,
and says so explicitly for every article rather than silently dropping them
(see the `uninspectable` status below).

## How it works

**Phase 1 — search (`src/search.py`).** `ESearch` on PubMed with your
keywords, plus a cheap IF prefilter added to the term
(`"Fluorescent Antibody Technique"[MeSH Terms] OR immunofluorescence[tiab]`).
This only detects that the method was *mentioned*, not that an image exists —
it just shrinks the set before the expensive step.

**Phase 2 — PMC caption inspection (`src/filter_pmc.py`, `src/pipeline.py`).**
For each surviving PMID:
1. `ELink` (pubmed → pmc) to find a PMCID, if any.
2. `EFetch` (`db=pmc`, `retmode=xml`) for the JATS full text.
3. Parse every `<fig>/<caption>` and keyword-match against a curated IF term
   list (immunofluorescence, DAPI, confocal, Alexa Fluor, secondary antibody,
   etc. — see `IF_CAPTION_KEYWORDS` in `src/filter_pmc.py`).

Every input article gets exactly one of three outcomes:

| status | meaning |
|---|---|
| `passed` | OA full text found, at least one figure caption matched an IF keyword |
| `failed` | OA full text found, no caption matched |
| `uninspectable` | not in PMC, or in PMC but full text wasn't retrievable (access-restricted) |

This is a **caption keyword match**, not image classification — it detects
that a figure's caption mentions IF, not that the pixels show a micrograph.
Precision/recall are heuristic; tune `IF_CAPTION_KEYWORDS` as needed. If this
proves too imprecise, the documented next step (not built here) is
downloading figure images via the PMC OA Web Service and running a vision
classifier — deliberately deferred.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in NCBI_EMAIL, and NCBI_API_KEY if you have one
```

Get a free API key at https://www.ncbi.nlm.nih.gov/account/settings/ — it
raises the rate limit from ~3 to ~10 requests/sec. The key is read from the
environment only; it is never hardcoded or logged.

## Usage

```bash
python -m src --keywords "breast cancer AND organoid" --retmax 500
```

Options:

- `--keywords` (required) — PubMed search term.
- `--retmax` — max PMIDs to pull from Phase 1 (default 1000).
- `--no-prefilter` — search on `--keywords` alone, skip the IF term/MeSH prefilter.
- `--output` — CSV path for the per-article report (default `results.csv`).
- `--elink-chunk-size`, `--efetch-chunk-size` — batch sizes for Phase 2 calls (default 200 / 100).
- `--verbose` — print all parameters used plus a quantified breakdown of every pipeline step (PubMed hits → PMIDs retrieved → PMC-linked → full text fetched → caption match → final passed/failed/uninspectable), each as a percentage of the stage before it.

Output: a console summary (hit counts, PMC coverage, pass/fail/uninspectable
breakdown) and a `results.csv` with one row per article:
`pmid, pmcid, status, reason, matched_keywords, sample_caption`.

## Streamlit app

The same pipeline is also available as a web UI:

```bash
streamlit run streamlit_app.py
```

Each visitor supplies their **own** free NCBI email (required) and API key
(optional) on the app's **Parameters** page — the app ships with no embedded
credentials, and what you type is kept in your browser session only: never
logged, never written to disk, and never included in a downloaded or saved
file.

Three pages: **Run** (keywords + go), **Parameters** (credentials, retmax,
prefilter, batch sizes, editable IF caption keyword list), and **Results**
(metrics, funnel and status charts, filterable table, per-article detail, CSV
download, and a "Save this run" button that writes `results.csv`,
`summary.json` and `params.json` under `runs/`).

To deploy: push the repo to GitHub and point Streamlit Community Cloud at
`streamlit_app.py`. There are no secrets to configure — credentials come from
whoever is using the app.

The CLI is unaffected: it still reads `.env` via `src/config.py`.

## Tests

```bash
pip install -r requirements-dev.txt

pytest                  # fast, no network (~2s)
pytest --run-network    # also runs the live end-to-end test against NCBI
```

`pytest` covers the pipeline's `if_keywords` argument and the app's behaviour
via Streamlit's `AppTest` — the credentials gate, form validation, error
handling, the Results dashboard, and the guarantee that a saved run contains
no email or API key. `--run-network` adds one test that walks the whole golden
path against the live NCBI API; it reads `NCBI_EMAIL` from your `.env` and is
skipped if that isn't set.

## Repo layout

```
src/
  config.py      # env var loading (email/api_key/tool/rate limit)
  eutils.py       # rate-limited E-utilities HTTP client
  search.py       # Phase 1: ESearch + IF prefilter
  filter_pmc.py   # Phase 2: ELink -> EFetch PMC XML -> caption match
  pipeline.py     # orchestrates both phases, builds per-article outcomes
  cli.py          # command-line entry point
streamlit_app.py  # Streamlit entry point (st.navigation over the 3 pages)
app_common.py     # session-state schema + shared helpers for the app
app_pages/
  run.py          # keywords + Run button
  parameters.py   # credentials, search params, IF keyword list
  results.py      # dashboard for the latest run
.env.example
requirements.txt
```

## Scope (confirmed)

- **Coverage:** PMC open-access only. No free E-utilities route reaches
  paywalled figures, so non-OA articles are reported as `uninspectable`
  rather than pursued further.
- **"IF image" definition:** any figure whose caption matches the IF keyword
  list — not restricted to micrographs specifically, and not verified against
  actual pixels.
