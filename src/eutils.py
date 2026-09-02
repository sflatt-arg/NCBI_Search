"""Thin, rate-limited client for the NCBI E-utilities."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

from .config import NCBIConfig

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


class RateLimiter:
    """Sleeps as needed so calls never exceed max_per_second."""

    def __init__(self, max_per_second: float):
        self._min_interval = 1.0 / max_per_second
        self._last_call = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        remaining = self._min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()


class EutilsClient:
    def __init__(self, config: NCBIConfig, session: Optional[requests.Session] = None):
        self.config = config
        self.session = session or requests.Session()
        self.rate_limiter = RateLimiter(config.max_requests_per_second)

    def _get(self, endpoint: str, params: Dict[str, Any], retries: int = 3) -> requests.Response:
        full_params = dict(params)
        full_params["tool"] = self.config.tool
        full_params["email"] = self.config.email
        if self.config.api_key:
            full_params["api_key"] = self.config.api_key

        last_error: Optional[Exception] = None
        for attempt in range(retries):
            self.rate_limiter.wait()
            try:
                resp = self.session.get(BASE_URL + endpoint, params=full_params, timeout=60)
                if resp.status_code == 429:
                    time.sleep(1.0 + attempt)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(1.0 + attempt)
        raise RuntimeError(f"E-utilities request to {endpoint} failed after {retries} attempts") from last_error

    def esearch(self, db: str, term: str, **kwargs: Any) -> requests.Response:
        params = {"db": db, "term": term, **kwargs}
        return self._get("esearch.fcgi", params)

    def elink(self, dbfrom: str, db: str, ids: List[str], **kwargs: Any) -> requests.Response:
        # NCBI merges linksets when `id` is a single comma-joined value; passing
        # it as a repeated parameter keeps one LinkSet per source ID, which we
        # need to map each PMID back to its PMCID (or lack of one).
        params = {"dbfrom": dbfrom, "db": db, "id": ids, **kwargs}
        return self._get("elink.fcgi", params)

    def efetch(self, db: str, ids: List[str], **kwargs: Any) -> requests.Response:
        params = {"db": db, "id": ",".join(ids), **kwargs}
        return self._get("efetch.fcgi", params)
