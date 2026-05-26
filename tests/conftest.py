"""Shared fixtures. The e2e suite needs a live DB + LLM/embedding keys; when
those aren't configured (or the DB isn't migrated) the whole module is
skipped with a clear reason rather than failing red."""
from __future__ import annotations

import asyncio

import pytest

from llm_lawyer.bench.harness import preflight


@pytest.fixture(scope="session")
def preflight_result():
    return asyncio.run(preflight())


@pytest.fixture(scope="session")
def require_live(preflight_result):
    if not preflight_result.ok:
        pytest.skip(
            "live infra unavailable: "
            + "; ".join(preflight_result.problems)
        )
    return True
