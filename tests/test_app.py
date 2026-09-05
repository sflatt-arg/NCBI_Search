"""App behavior without touching the network: the credentials gate, error
handling, and the guarantee that a saved run carries no credentials."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import requests

import app_common
from src.pipeline import ArticleOutcome, PipelineResult
from src.search import SearchResult

RESULTS = "app_pages/results.py"
PARAMETERS = "app_pages/parameters.py"
RUN = "app_pages/run.py"


def _click(at, label):
    return [b for b in at.button if label in b.label][0].click().run()


# --- credentials gate -------------------------------------------------------

def test_run_button_disabled_without_email(app):
    at = app(with_credentials=False)
    assert at.warning, "expected a warning telling the visitor to set an email"
    assert [b for b in at.button if "Run pipeline" in b.label][0].disabled


def test_run_button_enabled_once_email_is_set(app):
    at = app()
    at.switch_page(RUN).run()
    assert not [b for b in at.button if "Run pipeline" in b.label][0].disabled


def test_parameters_form_rejects_a_blank_email(app):
    at = app(with_credentials=False)
    at.switch_page(PARAMETERS).run()
    _click(at, "Apply parameters")
    assert at.error
    assert at.session_state["credentials"]["email"] == ""


def test_parameters_form_rejects_an_empty_keyword_list(app):
    at = app(with_credentials=False)
    at.switch_page(PARAMETERS).run()
    at.text_input(key="cred_email").set_value("tester@example.org")
    at.text_area(key="param_if_keywords_text").set_value("  \n\n")
    _click(at, "Apply parameters")
    assert at.error
    assert at.session_state["credentials"]["email"] == ""


def test_applying_parameters_writes_them_to_session_state(app):
    at = app(with_credentials=False)
    at.switch_page(PARAMETERS).run()
    at.text_input(key="cred_email").set_value("tester@example.org")
    at.number_input(key="param_retmax").set_value(20)
    at.toggle(key="param_prefilter").set_value(False)
    _click(at, "Apply parameters")
    assert at.session_state["credentials"]["email"] == "tester@example.org"
    assert at.session_state["params"]["retmax"] == 20
    assert at.session_state["params"]["apply_if_prefilter"] is False


def test_reset_restores_the_default_keyword_list(app):
    at = app()
    at.switch_page(PARAMETERS).run()
    at.text_area(key="param_if_keywords_text").set_value("only-one")
    _click(at, "Reset keyword list")
    lines = at.text_area(key="param_if_keywords_text").value.splitlines()
    assert lines == list(app_common.IF_CAPTION_KEYWORDS)


# --- run page error handling ------------------------------------------------

def test_blank_keywords_are_rejected(app):
    at = app()
    at.switch_page(RUN).run()
    at.text_input(key="keywords").set_value("   ")
    _click(at, "Run pipeline")
    assert at.error
    assert at.session_state["last_result"] is None


@pytest.mark.parametrize(
    "error",
    [RuntimeError("E-utilities request to esearch.fcgi failed"), requests.ConnectionError("no network")],
)
def test_pipeline_failures_surface_as_an_error_not_a_crash(app, error):
    at = app()
    at.session_state["keywords"] = "anything"
    at.switch_page(RUN).run()
    with patch("src.pipeline.run_pipeline", side_effect=error):
        _click(at, "Run pipeline")
    assert at.error, "the failure should be shown via st.error"
    assert not at.exception, "the page must not crash"
    assert at.session_state["last_result"] is None


# --- results page -----------------------------------------------------------

def test_results_page_points_back_when_there_is_no_run(app):
    at = app()
    at.switch_page(RESULTS).run()
    assert at.info and not at.exception


def test_results_page_handles_a_search_with_zero_hits(app, run_record):
    at = app()
    at.switch_page(RESULTS)
    at.session_state["last_result"] = run_record(outcomes=[], count=0, pmids=[])
    at.run()
    assert not at.exception
    assert len(at.metric) == 4


def test_results_page_renders_the_dashboard(app, run_record):
    at = app()
    at.switch_page(RESULTS)
    at.session_state["last_result"] = run_record()
    at.run()
    assert not at.exception
    assert len(at.metric) == 4
    assert len(at.get("vega_lite_chart")) == 2, "funnel + status breakdown"
    assert len(at.dataframe) == 1
    assert at.download_button


def test_clearing_the_status_filter_does_not_crash(app, run_record):
    at = app()
    at.switch_page(RESULTS)
    at.session_state["last_result"] = run_record()
    at.run()
    at.multiselect[0].set_value([]).run()
    assert not at.exception


def test_truncation_warning_shown_when_retmax_cut_the_search(app, run_record):
    at = app()
    at.switch_page(RESULTS)
    at.session_state["last_result"] = run_record(count=999)  # 999 hits, 2 pmids
    at.run()
    assert any("retmax" in w.value for w in at.warning)


# --- saving -----------------------------------------------------------------

def test_saved_run_contains_no_credentials(app, run_record, tmp_path, monkeypatch):
    """The whole reason the app builds its own NCBIConfig: nothing a visitor
    types may ever reach the disk."""
    monkeypatch.setattr(app_common, "RUNS_DIR", tmp_path / "runs")
    at = app()
    at.session_state["credentials"] = {"email": "secret@example.org", "api_key": "sup3rs3cr3t"}
    at.switch_page(RESULTS)
    at.session_state["last_result"] = run_record()
    at.run()
    _click(at, "Save this run")
    assert at.success and not at.exception

    folder = next((tmp_path / "runs").iterdir())
    assert sorted(f.name for f in folder.iterdir()) == ["params.json", "results.csv", "summary.json"]

    blob = "".join((folder / name).read_text() for name in ("params.json", "summary.json", "results.csv"))
    assert "secret@example.org" not in blob
    assert "sup3rs3cr3t" not in blob

    params = json.loads((folder / "params.json").read_text())
    assert set(params) == {
        "keywords", "retmax", "apply_if_prefilter",
        "elink_chunk_size", "efetch_chunk_size", "if_keywords", "timestamp",
    }


def test_saved_csv_matches_the_cli_columns(run_record):
    record = run_record()
    csv_text = app_common.rows_to_csv(app_common.result_rows(record["result"]))
    header, *rows = csv_text.splitlines()
    assert header == "pmid,pmcid,status,reason,matched_keywords,sample_caption"
    assert len(rows) == len(record["result"].outcomes)


# --- config -----------------------------------------------------------------

def test_rate_limit_mirrors_load_config():
    assert app_common.effective_rate_limit("") == 3.0
    assert app_common.effective_rate_limit(None) == 3.0
    assert app_common.effective_rate_limit("a-key") == 10.0


def test_client_uses_session_credentials_not_the_environment(app, monkeypatch):
    """Even with NCBI_* set in the environment (as the CLI would use), the app
    must send the visitor's own session credentials -- and pass the session's
    IF keyword list through to the pipeline."""
    monkeypatch.setenv("NCBI_EMAIL", "owner@example.org")
    monkeypatch.setenv("NCBI_API_KEY", "owner-key")

    at = app()
    at.session_state["credentials"] = {"email": "visitor@example.org", "api_key": ""}
    at.session_state["params"] = {**at.session_state["params"], "if_keywords": ["dapi"], "retmax": 7}
    at.session_state["keywords"] = "anything"
    at.switch_page(RUN).run()

    captured = {}

    def fake_run_pipeline(client, **kwargs):
        captured["config"] = client.config
        captured["kwargs"] = kwargs
        return PipelineResult(SearchResult("t", 0, "", "", []), [])

    with patch("src.pipeline.run_pipeline", side_effect=fake_run_pipeline):
        _click(at, "Run pipeline")

    config = captured["config"]
    assert config.email == "visitor@example.org", "must not fall back to NCBI_EMAIL"
    assert config.api_key is None, "must not fall back to NCBI_API_KEY"
    assert config.tool == app_common.TOOL_NAME
    assert config.max_requests_per_second == 3.0
    assert captured["kwargs"]["if_keywords"] == ["dapi"]
    assert captured["kwargs"]["retmax"] == 7
