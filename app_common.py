"""Session-state schema and helpers shared by the Streamlit pages.

Deliberately does *not* use `src.config.load_config()`: the app is meant to be
deployed publicly, so it ships with no NCBI credentials of its own. Each
visitor supplies their own email (and optionally their own API key) on the
Parameters page; those values live only in `st.session_state` for that browser
session and are never logged, persisted, or written into any exported file.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from src.config import NCBIConfig
from src.filter_pmc import IF_CAPTION_KEYWORDS
from src.pipeline import PipelineResult

# Fixed: NCBI's `tool` parameter identifies the software, not the user.
TOOL_NAME = "pubmed-if-filter-streamlit"

RPS_WITH_API_KEY = 10.0
RPS_WITHOUT_API_KEY = 3.0

RUNS_DIR = Path("runs")

CSV_COLUMNS = ["pmid", "pmcid", "status", "reason", "matched_keywords", "sample_caption"]

# Page paths, so pages can link/switch to each other without hardcoding
# strings in three places.
RUN_PAGE = "app_pages/run.py"
PARAMETERS_PAGE = "app_pages/parameters.py"
RESULTS_PAGE = "app_pages/results.py"


def default_params() -> Dict[str, Any]:
    return {
        "retmax": 1000,
        "apply_if_prefilter": True,
        "elink_chunk_size": 200,
        "efetch_chunk_size": 100,
        "if_keywords": list(IF_CAPTION_KEYWORDS),
    }


def init_session_state() -> None:
    """Seeds defaults once per browser session."""
    st.session_state.setdefault("credentials", {"email": "", "api_key": ""})
    st.session_state.setdefault("params", default_params())
    st.session_state.setdefault("keywords", "")
    st.session_state.setdefault("last_result", None)


def effective_rate_limit(api_key: str | None) -> float:
    """Mirrors `config.load_config`: 10 req/s with a key, 3 without."""
    return RPS_WITH_API_KEY if (api_key or "").strip() else RPS_WITHOUT_API_KEY


def has_email() -> bool:
    return bool(st.session_state["credentials"]["email"].strip())


def build_ncbi_config() -> NCBIConfig:
    """Builds an NCBIConfig from this session's credentials only."""
    creds = st.session_state["credentials"]
    email = creds["email"].strip()
    if not email:
        raise RuntimeError("No NCBI email set. Add one on the Parameters page before running.")
    api_key = creds["api_key"].strip() or None
    return NCBIConfig(
        email=email,
        tool=TOOL_NAME,
        api_key=api_key,
        max_requests_per_second=effective_rate_limit(api_key),
    )


def result_rows(result: PipelineResult) -> List[Dict[str, Any]]:
    """One row per article, same columns as the CLI's results.csv."""
    return [
        {
            "pmid": o.pmid,
            "pmcid": o.pmcid or "",
            "status": o.status,
            "reason": o.reason,
            "matched_keywords": ";".join(o.matched_keywords),
            "sample_caption": o.sample_caption,
        }
        for o in result.outcomes
    ]


def rows_to_csv(rows: List[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _slugify(text: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length] or "run"


def save_run_to_disk(run_record: Dict[str, Any], runs_dir: Path | None = None) -> Path:
    """Writes results.csv, summary.json and params.json under
    `runs/<UTC timestamp>_<slugified keywords>/` and returns the folder.

    params.json deliberately carries no credentials -- see module docstring.
    """
    runs_dir = runs_dir if runs_dir is not None else RUNS_DIR

    result: PipelineResult = run_record["result"]
    keywords: str = run_record["keywords"]
    params: Dict[str, Any] = run_record["params"]
    timestamp: datetime = run_record["timestamp"]

    folder = runs_dir / f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{_slugify(keywords)}"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "results.csv").write_text(rows_to_csv(result_rows(result)))

    (folder / "summary.json").write_text(
        json.dumps(
            {"summary": result.summary(), "stepwise_summary": result.stepwise_summary()},
            indent=2,
        )
    )

    (folder / "params.json").write_text(
        json.dumps(
            {
                "keywords": keywords,
                "retmax": params["retmax"],
                "apply_if_prefilter": params["apply_if_prefilter"],
                "elink_chunk_size": params["elink_chunk_size"],
                "efetch_chunk_size": params["efetch_chunk_size"],
                "if_keywords": params["if_keywords"],
                "timestamp": timestamp.isoformat(),
            },
            indent=2,
        )
    )

    return folder


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
