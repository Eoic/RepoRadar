"""Tests for main.py: health edge cases and global exception handler."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.models.domain import IndexResult
from app.services.vector_store import VectorStore

VECTOR_DIM = 384
FAKE_VECTOR = [0.1] * VECTOR_DIM


@pytest.fixture
def app():
    from app.main import app as fastapi_app

    mock_github = AsyncMock()
    mock_github.rate_limit_remaining = 4999

    mock_vector_store = AsyncMock(spec=VectorStore)
    mock_vector_store.get_collection_stats = AsyncMock(return_value={"points_count": 50})

    mock_pipeline = AsyncMock()
    mock_pipeline.index_single_repo = AsyncMock(
        return_value=IndexResult(status="indexed", repo_id=1, full_name="o/r")
    )

    fastapi_app.state.github_client = mock_github
    fastapi_app.state.vector_store = mock_vector_store
    fastapi_app.state.pipeline = mock_pipeline

    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_health_stats_failure_returns_zero(client, app):
    """When get_collection_stats raises, indexed_repos should default to 0 and status degraded."""
    app.state.vector_store.get_collection_stats = AsyncMock(
        side_effect=RuntimeError("Qdrant unreachable")
    )
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexed_repos"] == 0
    assert data["qdrant_connected"] is False
    assert data["status"] == "degraded"


def test_health_includes_rate_limit(client, app):
    """Health response should include the github rate limit from the client."""
    app.state.github_client.rate_limit_remaining = 3500
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["github_rate_limit_remaining"] == 3500


def test_global_exception_handler_returns_500(client, app):
    """Unhandled exception in a route should return a clean 500 JSON response."""
    app.state.vector_store.get_repo_vectors = AsyncMock(return_value=(FAKE_VECTOR, FAKE_VECTOR))
    app.state.vector_store.search_similar = AsyncMock(side_effect=RuntimeError("Unexpected boom"))
    resp = client.post("/api/search", json={"repo_url": "owner/repo"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"
