"""Page 3 -- dashboard for the most recent run held in session state."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from app_common import (
    RUN_PAGE,
    result_rows,
    rows_to_csv,
    save_run_to_disk,
)
from src.pipeline import STATUS_FAILED, STATUS_PASSED, STATUS_UNINSPECTABLE

STATUS_COLORS = {
    STATUS_PASSED: "#2e7d32",
    STATUS_FAILED: "#b26500",
    STATUS_UNINSPECTABLE: "#8e8e8e",
}

st.title("📊 Results")

run = st.session_state["last_result"]
if run is None:
    st.info("No run yet. Head to the Run page and start one.")
    st.page_link(RUN_PAGE, label="Go to Run", icon="▶️")
    st.stop()

result = run["result"]
summary = result.summary()
stepwise = result.stepwise_summary()

st.markdown(f"**Keywords:** `{run['keywords']}`")
st.markdown("**Search term used:**")
st.code(result.search.term, language="text")
st.caption(f"Run finished {run['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}")

if result.search.truncated:
    st.warning(
        f"PubMed matched {result.search.count} articles but only the first "
        f"{len(result.search.pmids)} were retrieved (retmax = {run['params']['retmax']}). "
        "Raise retmax on the Parameters page to cover the whole result set."
    )

# --- Headline metrics -------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Articles evaluated", summary["total_articles"])
c2.metric("Linked to PMC", summary["linked_to_pmc"], f"{summary['linked_to_pmc_pct']}% of evaluated")
c3.metric("Passed (IF caption)", summary["passed"])
c4.metric("Uninspectable", summary["uninspectable"])

if not result.outcomes:
    st.info("The search returned no articles, so there is nothing to break down.")
    st.stop()

# --- Charts -----------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Pipeline funnel")
    funnel = pd.DataFrame(
        [
            {"stage": "PubMed hits", "count": stepwise["phase1_search"]["pubmed_hits"]},
            {"stage": "PMIDs retrieved", "count": stepwise["phase1_search"]["pmids_retrieved"]},
            {"stage": "Linked to PMC", "count": stepwise["phase2_elink"]["linked_to_pmc"]},
            {"stage": "Full text fetched", "count": stepwise["phase2_efetch"]["fetched_fulltext"]},
            {"stage": "Passed", "count": stepwise["final"]["passed"]},
        ]
    )
    funnel_chart = (
        alt.Chart(funnel)
        .mark_bar(color="#4c78a8")
        .encode(
            x=alt.X("count:Q", title="Articles"),
            y=alt.Y("stage:N", sort=list(funnel["stage"]), title=None),
            tooltip=["stage", "count"],
        )
    )
    labels = funnel_chart.mark_text(align="left", dx=4).encode(text="count:Q")
    st.altair_chart(funnel_chart + labels, width="stretch")
    st.caption(
        "Each stage is a subset of the one above it. The drop from *PubMed hits* to "
        "*PMIDs retrieved* is retmax; the drop to *Linked to PMC* and *Full text "
        "fetched* is open-access coverage, not a filtering decision."
    )

with right:
    st.subheader("Final status")
    status_df = pd.DataFrame(
        [
            {"status": STATUS_PASSED, "count": summary["passed"]},
            {"status": STATUS_FAILED, "count": summary["failed"]},
            {"status": STATUS_UNINSPECTABLE, "count": summary["uninspectable"]},
        ]
    )
    status_chart = (
        alt.Chart(status_df)
        .mark_bar()
        .encode(
            x=alt.X("count:Q", title="Articles"),
            y=alt.Y("status:N", sort=list(status_df["status"]), title=None),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values())),
                legend=None,
            ),
            tooltip=["status", "count"],
        )
    )
    status_labels = status_chart.mark_text(align="left", dx=4).encode(text="count:Q")
    st.altair_chart(status_chart + status_labels, width="stretch")

with st.expander("Step-by-step percentages"):
    st.json(stepwise)

# --- Per-article table ------------------------------------------------------
st.subheader("Per-article outcomes")

rows = result_rows(result)
frame = pd.DataFrame(rows)

present_statuses = [s for s in STATUS_COLORS if s in set(frame["status"])]
selected = st.multiselect("Filter by status", present_statuses, default=present_statuses)
filtered = frame[frame["status"].isin(selected)] if selected else frame.iloc[0:0]

st.caption(f"Showing {len(filtered)} of {len(frame)} articles. Click a column header to sort.")
st.dataframe(filtered, width="stretch", hide_index=True)

# --- Single-article detail --------------------------------------------------
st.subheader("Inspect one article")
if filtered.empty:
    st.caption("No articles match the current filter.")
else:
    pmid = st.selectbox(
        "PMID",
        filtered["pmid"].tolist(),
        format_func=lambda p: f"{p} — {frame.loc[frame['pmid'] == p, 'status'].iloc[0]}",
    )
    row = frame.loc[frame["pmid"] == pmid].iloc[0]
    detail_left, detail_right = st.columns(2)
    detail_left.markdown(f"**PMID:** [{row['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/)")
    if row["pmcid"]:
        detail_right.markdown(
            f"**PMCID:** [{row['pmcid']}](https://www.ncbi.nlm.nih.gov/pmc/articles/{row['pmcid']}/)"
        )
    else:
        detail_right.markdown("**PMCID:** —")
    st.markdown(f"**Status:** `{row['status']}` &nbsp;&nbsp; **Reason:** `{row['reason']}`")
    st.markdown(f"**Matched keywords:** {row['matched_keywords'] or '—'}")
    st.markdown("**Sample caption:**")
    st.write(row["sample_caption"] or "_No caption recorded for this article._")

# --- Export -----------------------------------------------------------------
st.subheader("Export")
export_left, export_right = st.columns(2)

with export_left:
    st.download_button(
        "⬇️ Download results.csv",
        data=rows_to_csv(rows),
        file_name="results.csv",
        mime="text/csv",
    )

with export_right:
    if st.button("💾 Save this run"):
        try:
            folder = save_run_to_disk(run)
        except OSError as exc:
            st.error(f"Could not save the run: {exc}")
        else:
            st.success(f"Saved to `{folder.resolve()}`")

st.caption(
    "Saving writes results.csv, summary.json and params.json to the machine running "
    "the app — most useful locally, since Streamlit Community Cloud's filesystem is "
    "ephemeral. Your NCBI email and API key are never included in any of these files."
)
