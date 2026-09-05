"""The full golden path against the live NCBI API.

Skipped by default -- run with:  pytest --run-network
Needs NCBI_EMAIL in your .env (the same one the CLI uses).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

import app_common

pytestmark = pytest.mark.network

load_dotenv()
EMAIL = os.environ.get("NCBI_EMAIL", "").strip()
API_KEY = os.environ.get("NCBI_API_KEY", "").strip()


@pytest.mark.skipif(not EMAIL, reason="NCBI_EMAIL is not set in .env")
def test_golden_path(tmp_path, monkeypatch):
    monkeypatch.setattr(app_common, "RUNS_DIR", tmp_path / "runs")

    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "streamlit_app.py"), default_timeout=300)
    at.run()
    assert not at.exception

    # The Run page gates on a missing email.
    assert at.warning
    assert [b for b in at.button if "Run pipeline" in b.label][0].disabled

    # Enter credentials and a small retmax on the Parameters page.
    at.switch_page("app_pages/parameters.py").run()
    at.text_input(key="cred_email").set_value(EMAIL)
    if API_KEY:
        at.text_input(key="cred_api_key").set_value(API_KEY)
    at.number_input(key="param_retmax").set_value(20)
    [b for b in at.button if b.label == "Apply parameters"][0].click().run()
    assert at.success
    assert at.session_state["params"]["retmax"] == 20

    # Run a real search.
    at.switch_page("app_pages/run.py").run()
    at.text_input(key="keywords").set_value("hepatocyte organoid")
    [b for b in at.button if "Run pipeline" in b.label][0].click().run()
    assert not at.exception

    record = at.session_state["last_result"]
    assert record is not None
    summary = record["result"].summary()
    assert summary["total_articles"] > 0
    assert summary["passed"] + summary["failed"] + summary["uninspectable"] == summary["total_articles"]

    # AppTest reverts to the default page on the next .run() after
    # st.switch_page, so re-select Results explicitly.
    at.switch_page("app_pages/results.py").run()
    assert len(at.metric) == 4
    assert len(at.get("vega_lite_chart")) == 2
    assert len(at.dataframe) == 1
    assert at.download_button

    csv_text = app_common.rows_to_csv(app_common.result_rows(record["result"]))
    assert csv_text.splitlines()[0] == "pmid,pmcid,status,reason,matched_keywords,sample_caption"
    assert len(csv_text.splitlines()) - 1 == summary["total_articles"]

    [b for b in at.button if "Save this run" in b.label][0].click().run()
    assert at.success and not at.exception

    folder = next((tmp_path / "runs").iterdir())
    blob = "".join((folder / n).read_text() for n in ("params.json", "summary.json", "results.csv"))
    assert EMAIL not in blob, "the visitor's email must never reach the disk"
    if API_KEY:
        assert API_KEY not in blob, "the visitor's API key must never reach the disk"

    params = json.loads((folder / "params.json").read_text())
    assert "credentials" not in params and "email" not in params and "api_key" not in params
    assert len((folder / "results.csv").read_text().splitlines()) - 1 == summary["total_articles"]
