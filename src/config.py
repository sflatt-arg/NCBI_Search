"""Loads NCBI credentials and rate-limit settings from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class NCBIConfig:
    email: str
    tool: str
    api_key: str | None
    max_requests_per_second: float


def load_config() -> NCBIConfig:
    email = os.environ.get("NCBI_EMAIL", "").strip()
    if not email:
        raise RuntimeError(
            "NCBI_EMAIL is not set. Copy .env.example to .env and fill it in "
            "-- NCBI requires an email on every request."
        )

    api_key = os.environ.get("NCBI_API_KEY", "").strip() or None
    tool = os.environ.get("NCBI_TOOL", "").strip() or "pubmed-if-filter"

    default_rps = 10.0 if api_key else 3.0
    max_rps_raw = os.environ.get("NCBI_MAX_RPS", "").strip()
    max_rps = float(max_rps_raw) if max_rps_raw else default_rps

    return NCBIConfig(
        email=email,
        tool=tool,
        api_key=api_key,
        max_requests_per_second=max_rps,
    )
