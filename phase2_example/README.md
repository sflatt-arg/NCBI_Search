# Phase 2 worked example

Output of a single run, kept here so you can inspect it directly.

Command used:
```
python -m src --keywords "organoid AND breast cancer" --retmax 5 --output ./phase2_example/results.csv --verbose
```

## Files

- **run_log.txt** — full console output of that run, including the `--verbose`
  step-by-step quantification (parameters, Phase 1 hit count, ELink/EFetch/caption-match
  funnel, final breakdown).
- **results.csv** — the per-article report: one row per PMID with its
  `status` (`passed` / `failed` / `uninspectable`), `reason`, matched keywords,
  and a sample caption snippet.
- **PMC13085594_full_jats.xml** — the raw JATS XML fetched from PMC (via `EFetch`)
  for the one article in this run that passed (PMID 41803986). This is the
  actual full text Phase 2 parses — ~106 KB, includes `<front>` (metadata),
  `<body>` (article sections), `<back>` (references), and 7 `<fig>` elements.
- **all_figures_and_matches.txt** — every `<fig>` in that article with its
  caption text and whether it matched an IF keyword. Of 7 figures, 3 matched
  (Fig. 4, 5, 7), all on the keyword `immunofluorescence`.

## How to explore further

- Open `PMC13085594_full_jats.xml` in the editor and search for `<fig` to jump
  between figures, or `<caption>` to see just the caption text in context.
- Compare `all_figures_and_matches.txt` against `IF_CAPTION_KEYWORDS` in
  `src/filter_pmc.py` to see exactly which keyword triggered each match.
- Re-run the command above with a different `--keywords` value to generate a
  fresh example (this will overwrite `results.csv` and `run_log.txt`, but not
  this README).
