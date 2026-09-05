"""Page 2 -- every configurable value, including the credentials gate.

Credentials entered here stay in `st.session_state` for this browser session
only. They are never written to disk, logged, or included in an export.
"""

from __future__ import annotations

import streamlit as st

from app_common import RUN_PAGE, effective_rate_limit
from src.filter_pmc import IF_CAPTION_KEYWORDS

API_KEY_URL = "https://www.ncbi.nlm.nih.gov/account/settings/"


def _reset_if_keywords() -> None:
    """Restores the default keyword list. Runs as a widget callback, i.e.
    before the text_area is instantiated on the next run -- assigning to a
    widget key from the script body after render is not allowed."""
    st.session_state["param_if_keywords_text"] = "\n".join(IF_CAPTION_KEYWORDS)


st.title("⚙️ Parameters")

credentials = st.session_state["credentials"]
params = st.session_state["params"]

# Widget state is seeded once per session from the applied values; the form
# writes it back into `credentials` / `params` on submit.
st.session_state.setdefault("cred_email", credentials["email"])
st.session_state.setdefault("cred_api_key", credentials["api_key"])
st.session_state.setdefault("param_retmax", params["retmax"])
st.session_state.setdefault("param_prefilter", params["apply_if_prefilter"])
st.session_state.setdefault("param_elink_chunk", params["elink_chunk_size"])
st.session_state.setdefault("param_efetch_chunk", params["efetch_chunk_size"])
st.session_state.setdefault("param_if_keywords_text", "\n".join(params["if_keywords"]))

with st.form("parameters_form"):
    st.subheader("Your NCBI credentials")
    st.caption(
        "NCBI requires an email address on every E-utilities request so they can "
        "identify who is making them. This app ships with no credentials of its "
        "own, so please use yours. An API key is free and optional — it raises "
        "the rate limit from 3 to 10 requests/second. Both values are kept in "
        "this browser session only: never stored on the server, never logged, "
        "and never included in a downloaded or saved file."
    )
    st.text_input("NCBI email (required)", key="cred_email", placeholder="you@example.org")
    st.text_input("NCBI API key (optional)", key="cred_api_key", type="password")
    st.caption(f"Get a free API key at {API_KEY_URL}")
    st.info(
        f"Effective rate limit in force: **{effective_rate_limit(credentials['api_key']):.0f} requests/second** "
        "— 3/s without an API key, 10/s with one."
    )

    st.divider()
    st.subheader("Search parameters")
    st.number_input(
        "retmax — max PMIDs to pull from Phase 1",
        min_value=1,
        max_value=10000,
        step=10,
        key="param_retmax",
        help="Larger values mean longer runs. PubMed caps this at 10000 per ESearch.",
    )
    st.toggle(
        "Apply the IF prefilter to the PubMed search",
        key="param_prefilter",
        help='Adds ("Fluorescent Antibody Technique"[MeSH] OR immunofluorescence[tiab]) to the term.',
    )

    st.caption(
        "The effective PubMed search term is shown live on the Run page, once "
        "these parameters are applied."
    )

    st.divider()
    st.subheader("Phase 2 batching")
    st.caption("How many IDs are sent per ELink / EFetch call. Defaults are fine for most runs.")
    left, right = st.columns(2)
    with left:
        st.number_input("ELink chunk size", min_value=1, max_value=500, step=10, key="param_elink_chunk")
    with right:
        st.number_input("EFetch chunk size", min_value=1, max_value=500, step=10, key="param_efetch_chunk")

    st.divider()
    st.subheader("IF caption keyword list")
    st.caption(
        "One keyword per line, lowercase. A figure passes if its caption contains "
        "any of these as a substring."
    )
    st.text_area("Keywords", key="param_if_keywords_text", height=260, label_visibility="collapsed")

    submitted = st.form_submit_button("Apply parameters", type="primary")

st.button("↩️ Reset keyword list to defaults", on_click=_reset_if_keywords)
st.caption("Resets only the IF caption keyword list above — press *Apply parameters* to keep it.")

if submitted:
    email = st.session_state["cred_email"].strip()
    if_keywords = [line.strip() for line in st.session_state["param_if_keywords_text"].splitlines() if line.strip()]

    if not email:
        st.error("An NCBI email is required — nothing was applied.")
    elif not if_keywords:
        st.error("The IF caption keyword list cannot be empty — nothing was applied.")
    else:
        st.session_state["credentials"] = {
            "email": email,
            "api_key": st.session_state["cred_api_key"].strip(),
        }
        st.session_state["params"] = {
            "retmax": int(st.session_state["param_retmax"]),
            "apply_if_prefilter": bool(st.session_state["param_prefilter"]),
            "elink_chunk_size": int(st.session_state["param_elink_chunk"]),
            "efetch_chunk_size": int(st.session_state["param_efetch_chunk"]),
            "if_keywords": if_keywords,
        }
        st.toast("Parameters applied ✅")
        st.success("Parameters applied.")

st.page_link(RUN_PAGE, label="Back to Run", icon="▶️")
