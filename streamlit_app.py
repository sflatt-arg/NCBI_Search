"""Streamlit entry point for the PubMed -> PMC immunofluorescence filter.

Run with:  streamlit run streamlit_app.py

This is a separate entry point from the CLI (`python -m src ...`), which keeps
using `.env` via `src/config.py`. The app itself ships with no NCBI
credentials -- each visitor enters their own on the Parameters page.
"""

from __future__ import annotations

import streamlit as st

from app_common import PARAMETERS_PAGE, RESULTS_PAGE, RUN_PAGE, init_session_state

st.set_page_config(
    page_title="PubMed IF filter",
    page_icon="🔬",
    layout="wide",
)

init_session_state()

navigation = st.navigation(
    [
        st.Page(RUN_PAGE, title="Run", icon="▶️", default=True),
        st.Page(PARAMETERS_PAGE, title="Parameters", icon="⚙️"),
        st.Page(RESULTS_PAGE, title="Results", icon="📊"),
    ]
)

navigation.run()
