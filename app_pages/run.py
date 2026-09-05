"""Page 1 -- the everyday-use page: type keywords, press Run."""

from __future__ import annotations

import copy

import streamlit as st
from requests import RequestException

from app_common import (
    PARAMETERS_PAGE,
    RESULTS_PAGE,
    build_ncbi_config,
    has_email,
    utc_now,
)
from src.eutils import EutilsClient
from src.pipeline import run_pipeline
from src.search import build_term

st.title("🔬 Run a search")
st.caption(
    "Searches PubMed for your keywords, then inspects PMC open-access figure "
    "captions for immunofluorescence signals."
)

st.text_input(
    "Keywords",
    key="keywords",
    placeholder="breast cancer AND organoid",
    help="A PubMed search term. Boolean operators and field tags work here.",
)

params = st.session_state["params"]
credentials_missing = not has_email()

if credentials_missing:
    st.warning(
        "Set your NCBI email on the **Parameters** page before running — NCBI "
        "requires an email on every request."
    )
    st.page_link(PARAMETERS_PAGE, label="Go to Parameters", icon="⚙️")

with st.container(border=True):
    st.markdown("**Current parameters**")
    left, middle, right = st.columns(3)
    left.markdown(f"retmax\n\n**{params['retmax']}**")
    middle.markdown(f"IF prefilter\n\n**{'on' if params['apply_if_prefilter'] else 'off'}**")
    right.markdown(f"IF caption keywords\n\n**{len(params['if_keywords'])}**")

    left, middle, right = st.columns(3)
    left.markdown(f"ELink chunk size\n\n**{params['elink_chunk_size']}**")
    middle.markdown(f"EFetch chunk size\n\n**{params['efetch_chunk_size']}**")

    # Live: this sits outside any form, so it redraws as you type and as soon
    # as parameters are applied.
    preview_keywords = st.session_state["keywords"].strip() or "<your keywords>"
    st.caption("Effective PubMed search term:")
    st.code(build_term(preview_keywords, params["apply_if_prefilter"]), language="text")

    st.page_link(PARAMETERS_PAGE, label="Change parameters", icon="⚙️")

run_clicked = st.button(
    "▶️ Run pipeline",
    type="primary",
    disabled=credentials_missing,
    help="Set your NCBI email first" if credentials_missing else None,
)

if run_clicked:
    keywords = st.session_state["keywords"].strip()
    if not keywords:
        st.error("Enter some keywords first.")
        st.stop()

    try:
        client = EutilsClient(build_ncbi_config())
        with st.spinner("Running pipeline..."):
            result = run_pipeline(
                client,
                keywords=keywords,
                apply_if_prefilter=params["apply_if_prefilter"],
                retmax=params["retmax"],
                elink_chunk_size=params["elink_chunk_size"],
                efetch_chunk_size=params["efetch_chunk_size"],
                if_keywords=params["if_keywords"],
            )
    except (RuntimeError, RequestException) as exc:
        st.error(f"The run failed: {exc}")
    else:
        st.session_state["last_result"] = {
            "result": result,
            "keywords": keywords,
            "params": copy.deepcopy(params),
            "timestamp": utc_now(),
        }
        st.switch_page(RESULTS_PAGE)
