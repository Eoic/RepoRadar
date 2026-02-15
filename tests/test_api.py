"""Tests for API endpoints using mocked services."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models.domain import IndexResult, SearchResult
from app.services.vector_store import VectorStore

VECTOR_DIM = 384
FAKE_VECTOR = [0.1] * VECTOR_DIM


@pytest.fixture
def app():
    """Create a test app with mocked services in app.state."""
    from app.main import app as fastapi_app

    # Mock services
    mock_github = AsyncMock()
    mock_github.rate_limit_remaining = 4999

    mock_embedder = MagicMock()
    mock_embedder.embed = MagicMock(return_value=FAKE_VECTOR)

    mock_pipeline = AsyncMock()
    mock_pipeline.index_single_repo = AsyncMock(
        return_value=IndexResult(
            status="indexed", repo_id=12345, full_name="owner/repo", description="Repo description"
        )
    )

    mock_vector_store = AsyncMock(spec=VectorStore)
    mock_vector_store.get_repo_vectors = AsyncMock(return_value=(FAKE_VECTOR, FAKE_VECTOR))
    mock_vector_store.search_similar = AsyncMock(
        return_value=[
            SearchResult(
                id=99999,
                score=0.85,
                purpose_score=0.9,
                stack_score=0.7,
                payload={
                    "full_name": "other/similar-repo",
                    "url": "https://github.com/other/similar-repo",
                    "description": "A similar repo",
                    "topics": ["python"],
                    "language_primary": "Python",
                    "stars": 200,
                },
            ),
        ]
    )
    mock_vector_store.get_collection_stats = AsyncMock(
        return_value={"points_count": 100, "collection_name": "repositories"}
    )

    fastapi_app.state.github_client = mock_github
    fastapi_app.state.embedder = mock_embedder
    fastapi_app.state.pipeline = mock_pipeline
    fastapi_app.state.vector_store = mock_vector_store

    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["indexed_repos"] == 100


def test_search_success(client):
    resp = client.post(
        "/api/search",
        json={"repo_url": "owner/repo", "weight_purpose": 0.7, "weight_stack": 0.3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["full_name"] == "other/similar-repo"
    assert data["results"][0]["similarity_score"] == 0.85
    assert data["search_time_ms"] > 0


def test_search_invalid_url(client):
    resp = client.post("/api/search", json={"repo_url": "not-a-valid-url!!!"})
    assert resp.status_code == 400


def test_search_excludes_self(client, app):
    """Self-repo should be excluded from results."""
    # Make search return the query repo itself
    app.state.vector_store.search_similar = AsyncMock(
        return_value=[
            SearchResult(
                id=12345,  # Same as query repo
                score=1.0,
                purpose_score=1.0,
                stack_score=1.0,
                payload={
                    "full_name": "owner/repo",
                    "url": "https://github.com/owner/repo",
                    "description": "Self",
                    "topics": [],
                    "language_primary": "Python",
                    "stars": 50,
                },
            ),
        ]
    )

    resp = client.post("/api/search", json={"repo_url": "owner/repo"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 0


def test_index_endpoint(client):
    resp = client.post("/api/index", json={"repo_url": "owner/repo"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "indexed"
    assert data["repo_id"] == 12345


def test_index_invalid_url(client):
    resp = client.post("/api/index", json={"repo_url": "bad!!url"})
    assert resp.status_code == 400


def test_search_returns_502_when_indexing_fails(client, app):
    """Pipeline returning status='failed' should yield a 502."""
    app.state.pipeline.index_single_repo = AsyncMock(
        return_value=IndexResult(
            status="failed", repo_id=0, full_name="owner/repo", message="GitHub 500"
        )
    )
    resp = client.post("/api/search", json={"repo_url": "owner/repo"})
    assert resp.status_code == 502
    assert "Failed to index" in resp.json()["detail"]


def test_search_returns_404_when_vectors_missing(client, app):
    """get_repo_vectors returning None should yield a 404."""
    app.state.vector_store.get_repo_vectors = AsyncMock(return_value=None)
    resp = client.post("/api/search", json={"repo_url": "owner/repo"})
    assert resp.status_code == 404
    assert "vectors not found" in resp.json()["detail"]


def test_search_min_stars_filter(client, app):
    """Repos below min_stars should be excluded from results."""
    app.state.vector_store.search_similar = AsyncMock(
        return_value=[
            SearchResult(
                id=99999,
                score=0.85,
                purpose_score=0.9,
                stack_score=0.7,
                payload={
                    "full_name": "low/stars",
                    "url": "https://github.com/low/stars",
                    "description": "Low stars repo",
                    "stars": 5,
                },
            ),
            SearchResult(
                id=99998,
                score=0.80,
                purpose_score=0.85,
                stack_score=0.65,
                payload={
                    "full_name": "high/stars",
                    "url": "https://github.com/high/stars",
                    "description": "High stars repo",
                    "stars": 500,
                },
            ),
        ]
    )
    resp = client.post("/api/search", json={"repo_url": "owner/repo", "min_stars": 100})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["full_name"] == "high/stars"


def test_search_stats_exception_returns_zero_count(client, app):
    """get_collection_stats raising should fall back to indexed_count=0."""
    app.state.vector_store.get_collection_stats = AsyncMock(side_effect=RuntimeError("Qdrant down"))
    resp = client.post("/api/search", json={"repo_url": "owner/repo"})
    assert resp.status_code == 200
    assert resp.json()["indexed_count"] == 0


def test_index_returns_502_on_failure(client, app):
    """Pipeline failure on /api/index should return 502."""
    app.state.pipeline.index_single_repo = AsyncMock(
        return_value=IndexResult(
            status="failed", repo_id=0, full_name="owner/repo", message="Timeout"
        )
    )
    resp = client.post("/api/index", json={"repo_url": "owner/repo"})
    assert resp.status_code == 502
    assert "Indexing failed" in resp.json()["detail"]


def test_search_empty_results_returns_query_description(client, app):
    """When search returns no results, query_repo.description should come from index_result."""
    app.state.pipeline.index_single_repo = AsyncMock(
        return_value=IndexResult(
            status="indexed",
            repo_id=12345,
            full_name="owner/repo",
            description="My repo description",
        )
    )
    app.state.vector_store.search_similar = AsyncMock(return_value=[])

    resp = client.post("/api/search", json={"repo_url": "owner/repo"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query_repo"]["description"] == "My repo description"
    assert len(data["results"]) == 0
