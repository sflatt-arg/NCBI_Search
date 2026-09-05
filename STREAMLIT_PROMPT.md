# Project brief — Streamlit UI for the PubMed → PMC immunofluorescence filter

> Paste this as the opening message in a Claude Code (VS Code) session started in the root of this existing `NCBI` repo. It captures decisions already made so you don't re-derive them — implement directly, no need to re-confirm the choices below.

## Role & objective

You are an expert Python/Streamlit developer. Add a Streamlit web UI on top of the existing pipeline in `src/` (do not rewrite the pipeline logic — `eutils.py`, `search.py`, `filter_pmc.py` stay as they are except for one small, additive change described below). The existing CLI (`python -m src ...`, `src/cli.py`, `src/config.py` reading `.env`) must keep working unchanged — the Streamlit app is a new, separate entry point.

## Why this app will be built this way (context, do not re-litigate)

This app will be deployed publicly on Streamlit Community Cloud, source in a public GitHub repo. That drives two decisions below that would otherwise look unusual:

- **No shared NCBI credentials anywhere in the app or repo.** If the app owner's NCBI email/API key were embedded (even via Streamlit's Secrets manager) and used as a fallback, every anonymous visitor's PubMed queries would run under the owner's identity and rate-limit quota, which is undesirable and against the spirit of NCBI's usage policy (the email is meant to identify who is actually making the requests). Instead, **each visitor supplies their own NCBI email (required) and, optionally, their own free API key**, entered in the UI, held only in that browser session's `st.session_state`, and never logged, persisted to disk, or included in any exported/saved file.
- **The pipeline can take a while** for larger `retmax` values, but a simple blocking spinner is sufficient — no need to build granular step-by-step progress reporting.

## Established decisions (implement as-is)

**Pages (3), via `st.navigation` + `st.Page` — not the implicit `pages/` folder convention:**

1. **Run** — the everyday-use page.
2. **Parameters** — the dedicated settings page holding almost every configurable value, including the mandatory credentials gate.
3. **Results** — dashboard shown after a run completes.

**Credentials handling:**
- The Streamlit app never calls `src/config.py`'s `load_config()` and never reads `.env` or Streamlit Secrets for NCBI credentials. It builds its own `NCBIConfig` (reuse the existing `NCBIConfig` dataclass from `src/config.py`) directly from values the visitor typed into the Parameters page and stored in `st.session_state`.
- Email is required to run anything. API key is optional (rate limit is 3 req/s without one, 10 with — mirror the existing default logic from `config.load_config`).
- Tool name sent to NCBI is a fixed constant, e.g. `"pubmed-if-filter-streamlit"` — not user-configurable.
- These values must never be written to disk, logged, or included in any saved/exported file (see Results page below).

**Progress feedback:** a plain `st.spinner("Running pipeline...")` around the pipeline call. No progress bar, no per-phase callback plumbing.

**IF caption keyword list:** editable in the UI (Parameters page), not fixed in code for a given run.

**Results depth:** a full dashboard (metrics, funnel/breakdown charts, filterable table, per-article detail, CSV download) — not just a plain table.

**Run history:** only the latest run is kept in session state (a new run replaces it). Additionally, a "Save this run" button on the Results page persists the run to local disk — this is understood to be most useful when the app is run locally (Streamlit Community Cloud's filesystem is ephemeral/shared across sessions on that instance, so treat this as a bonus, not a substitute for the download button), but implement it anyway since it costs little.

## Required code change to the existing pipeline

`src/pipeline.py`'s `run_pipeline()` currently calls `find_matching_captions(article_el)` using the hardcoded default `IF_CAPTION_KEYWORDS` from `src/filter_pmc.py`. Add an optional parameter so callers (the Streamlit app) can supply a custom keyword list for a given run:

```python
def run_pipeline(
    client: EutilsClient,
    keywords: str,
    apply_if_prefilter: bool = True,
    retmax: int = 10000,
    elink_chunk_size: int = 200,
    efetch_chunk_size: int = 100,
    if_keywords: list[str] | None = None,   # NEW
) -> PipelineResult:
    ...
    matches = find_matching_captions(article_el, keywords=if_keywords or IF_CAPTION_KEYWORDS)
```

Keep the default behavior identical when `if_keywords` is not passed (the CLI doesn't need to change).

## New files to create

```
streamlit_app.py        # entry point: st.set_page_config, st.navigation with the 3 pages, calls init_session_state()
app_common.py            # session-state schema + helpers shared by all pages
app_pages/
  run.py                 # Page 1
  parameters.py           # Page 2
  results.py              # Page 3
```

(Use whatever exact filenames/layout `st.Page(...)` needs — the structure above is a guide, not a strict requirement. Keep it simple and idiomatic for the Streamlit version in `requirements.txt`.)

### `app_common.py`

- `init_session_state()` — sets sensible defaults once per session for:
  - `credentials`: `{"email": "", "api_key": ""}`
  - `params`: `{"retmax": 1000, "apply_if_prefilter": True, "elink_chunk_size": 200, "efetch_chunk_size": 100, "if_keywords": <copy of IF_CAPTION_KEYWORDS>}`
  - `keywords`: `""`
  - `last_result`: `None` (will hold the `PipelineResult` plus a timestamp and the params/keywords used to produce it)
- A helper to build an `NCBIConfig` from `st.session_state["credentials"]` (fixed tool name, rate limit derived the same way `config.load_config` derives it: 10 if API key present else 3 — allow override only if you think it's warranted, otherwise keep it automatic and simple).
- `save_run_to_disk(run_record)` — writes to `runs/<UTC timestamp>_<slugified keywords>/`:
  - `results.csv` (same columns as the CLI: `pmid, pmcid, status, reason, matched_keywords, sample_caption`)
  - `summary.json` (the result of `PipelineResult.summary()` and `.stepwise_summary()`)
  - `params.json` — **must exclude `credentials` entirely** (only `keywords`, `retmax`, `apply_if_prefilter`, `elink_chunk_size`, `efetch_chunk_size`, `if_keywords`, and the run timestamp)
  - Returns the folder path so the calling page can show a confirmation.

### Page 1 — Run

- Keywords text input, bound to `st.session_state["keywords"]`.
- If `st.session_state["credentials"]["email"]` is empty, show a warning (`st.warning`) telling the visitor to set their NCBI email on the Parameters page, and disable the Run button.
- A compact, read-only recap of current parameters (from `st.session_state["params"]`) with a button/link to the Parameters page.
- Run button: validate keywords non-empty → build the per-session `NCBIConfig` and `EutilsClient` → `st.spinner` around `run_pipeline(...)`, passing all params from session state including `if_keywords` → wrap in try/except to catch `RuntimeError`/`requests` errors and show `st.error` with the message instead of crashing → on success, store a run record (`PipelineResult` + `keywords` + `params` snapshot + UTC timestamp) into `st.session_state["last_result"]` → `st.switch_page` to Results.

### Page 2 — Parameters

Single `st.form`, sections in this order:

1. **Your NCBI credentials** — required email text input, optional password-masked API key input, short explanatory caption (why it's needed, that it's free, that it's session-only and never stored), and a link to `https://www.ncbi.nlm.nih.gov/account/settings/` to get a key. Show the resulting effective rate limit (3 or 10 req/s) as it would be computed.
2. **Search parameters** — `retmax` number input; IF prefilter toggle; below the toggle, a live-updating preview of the effective PubMed search term by calling `search.build_term(keywords, apply_if_prefilter)` with the current keywords from session state (fall back to a placeholder if keywords is empty).
3. **Phase 2 batching** — `elink_chunk_size`, `efetch_chunk_size` number inputs.
4. **IF caption keyword list** — `st.text_area`, one keyword per line, prefilled from current session value (which itself defaults to `filter_pmc.IF_CAPTION_KEYWORDS`); a "Reset to defaults" button outside the form that resets just this field.
5. Submit button ("Apply parameters") that validates the email field is non-empty and writes everything back into `st.session_state["credentials"]` / `["params"]`, with a success toast.

### Page 3 — Results

- If `st.session_state["last_result"]` is `None`: `st.info` pointing back to the Run page.
- Otherwise, using the stored `PipelineResult`:
  - Header: keywords used, search term used, run timestamp, a note if the PubMed search was truncated by `retmax`.
  - `st.metric` row: total articles evaluated, linked to PMC, passed, uninspectable (from `.summary()`).
  - A funnel-style chart of the pipeline stages from `.stepwise_summary()` (PubMed hits → PMIDs retrieved → linked to PMC → full text fetched → passed/failed/uninspectable). A horizontal bar chart via Streamlit's built-in charting (or Altair, which ships with Streamlit) is sufficient — don't add Plotly unless you judge it clearly better, in which case add it to `requirements.txt`.
  - A status breakdown chart (passed/failed/uninspectable).
  - A filterable, sortable `st.dataframe` of all outcomes, with a multiselect to filter by status.
  - A way to inspect one article's full `sample_caption` and `matched_keywords` (e.g. select a PMID from a selectbox, or expanders per row).
  - `st.download_button` for the results as CSV, built in-memory from the outcomes (same columns as the CLI's `results.csv`).
  - "💾 Save this run" button calling `save_run_to_disk(...)`, showing the resulting folder path on success, with a one-line caption noting this is most useful when running the app locally.

## Dependencies

Add to `requirements.txt`: `streamlit>=1.36` (needed for the `st.navigation`/`st.Page` API), plus `altair` only if not already pulled in by Streamlit (it normally is). Leave `requests` and `python-dotenv` as-is for the CLI path.

## Documentation

Add a short "Streamlit app" section to `README.md`:
- How to run it locally: `streamlit run streamlit_app.py`.
- One line stating each user supplies their own free NCBI email/API key in the app's Parameters page — the app itself ships with no embedded credentials.
- One line on deploying to Streamlit Community Cloud (public repo, no secrets to configure for this app).

## What I want you to do now (in order)

1. Make the small `run_pipeline` change in `src/pipeline.py` described above; confirm the CLI (`python -m src --keywords ...`) still behaves identically.
2. Build `app_common.py` with the session-state schema and helpers.
3. Build the three pages and `streamlit_app.py`.
4. Update `requirements.txt` and `README.md` as described.
5. Run the app locally (`streamlit run streamlit_app.py`) and walk through the golden path yourself: enter an email, run a small search (e.g. `retmax=20`), confirm Results renders, confirm CSV download and "Save this run" both work and that `params.json` never contains the email/API key.
