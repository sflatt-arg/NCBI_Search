"""Puts the repo root on sys.path for the tests and defines the `network` marker.

Tests marked `network` hit the live NCBI E-utilities and are skipped unless
you pass `--run-network`.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="also run the tests that call the live NCBI E-utilities API",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "network: hits the live NCBI API (needs NCBI_EMAIL)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip = pytest.mark.skip(reason="needs --run-network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
