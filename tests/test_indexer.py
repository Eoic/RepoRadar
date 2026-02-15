"""Tests for the IndexingPipeline.

Uses mocked GitHub client, real preprocessor, mock embedder (fixed vectors),
and Qdrant in-memory mode.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client import AsyncQdrantClient

from app.models.domain import RepoMetadata
from app.services.indexer import IndexingPipeline
from app.services.vector_store import VectorStore

VECTOR_DIM = 384
FAKE_VECTOR = [0.1] * VECTOR_DIM

REPO_METADATA = RepoMetadata(
    id=12345,
    full_name="owner/repo",
    url="https://github.com/owner/repo",
    description="A test repository for unit testing",
    topics=["python", "testing"],
    language_primary="Python",
    stars=100,
    forks=10,
    last_updated="2025-06-01T12:00:00Z",
)

SAMPLE_README = (
    "# My Project\n\nA great project for doing things.\n\n## Features\n\n- Fast\n- Simple"
)

SAMPLE_REQUIREMENTS = "flask>=2.0\nrequests\npytest\n"


@pytest.fixture
def mock_github():
    client = AsyncMock()
    client.fetch_repo_metadata = AsyncMock(return_value=REPO_METADATA)
    client.fetch_readme = AsyncMock(return_value=SAMPLE_README)
    client.fetch_languages = AsyncMock(
        return_value={"Python": 80.0, "Shell": 15.0, "Dockerfile": 5.0}
    )
    client.fetch_manifest_files = AsyncMock(
        return_value=[("requirements.txt", SAMPLE_REQUIREMENTS)]
    )
    return client


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed = MagicMock(return_value=FAKE_VECTOR)
    return embedder


@pytest.fixture
async def vector_store():
    client = AsyncQdrantClient(":memory:")
    store = VectorStore(client)
    await store.create_collection()
    return store


@pytest.fixture
def pipeline(mock_github, mock_embedder, vector_store):
    return IndexingPipeline(
        github_client=mock_github,
        embedder=mock_embedder,
        vector_store=vector_store,
        stale_days=7,
    )


async def test_index_single_repo_success(pipeline, vector_store):
    """Should fetch, preprocess, embed, and upsert successfully."""
    result = await pipeline.index_single_repo("owner", "repo")

    assert result.status == "indexed"
    assert result.repo_id == 12345
    assert result.full_name == "owner/repo"

    # Verify repo was stored in vector store
    assert await vector_store.repo_exists(12345) is True


async def test_index_single_repo_calls_embedder(pipeline, mock_embedder):
    """Should call embedder.embed twice (purpose + stack)."""
    await pipeline.index_single_repo("owner", "repo")

    assert mock_embedder.embed.call_count == 2
    calls = mock_embedder.embed.call_args_list

    purpose_text = calls[0][0][0]
    stack_text = calls[1][0][0]

    assert "test repository" in purpose_text
    assert "python, testing" in purpose_text
    assert "Primary language: Python" in stack_text
    assert "flask" in stack_text


async def test_index_single_repo_stores_payload(pipeline, vector_store):
    """Payload should contain repo metadata."""
    await pipeline.index_single_repo("owner", "repo")

    indexed_at = await vector_store.get_repo_indexed_at(12345)
    assert indexed_at is not None


async def test_index_single_repo_skips_recent(pipeline, vector_store, mock_github):
    """Should skip repos indexed recently."""
    # First index
    await pipeline.index_single_repo("owner", "repo")

    # Reset mock call counts
    mock_github.fetch_readme.reset_mock()

    # Second index should skip
    result = await pipeline.index_single_repo("owner", "repo")
    assert result.status == "skipped"


async def test_index_single_repo_force(pipeline, vector_store, mock_github):
    """force=True should re-index even if recently indexed."""
    await pipeline.index_single_repo("owner", "repo")

    result = await pipeline.index_single_repo("owner", "repo", force=True)
    assert result.status == "indexed"


async def test_index_single_repo_github_failure(pipeline, mock_github):
    """Should return failed status on GitHub API error."""
    mock_github.fetch_repo_metadata = AsyncMock(side_effect=Exception("API error"))

    result = await pipeline.index_single_repo("owner", "repo")
    assert result.status == "failed"


async def test_index_batch(pipeline):
    """Should index multiple repos and return batch result."""
    repos = [("owner", "repo")]
    result = await pipeline.index_batch(repos)

    assert result.total == 1
    assert result.indexed == 1
    assert result.failed == 0
    assert result.skipped == 0


async def test_index_batch_with_failure(pipeline, mock_github):
    """Should count failures in batch result."""
    mock_github.fetch_repo_metadata = AsyncMock(side_effect=Exception("API error"))
    mock_github.fetch_readme = AsyncMock(side_effect=Exception("API error"))
    mock_github.fetch_languages = AsyncMock(side_effect=Exception("API error"))
    mock_github.fetch_manifest_files = AsyncMock(side_effect=Exception("API error"))

    repos = [("owner", "bad-repo")]
    result = await pipeline.index_batch(repos)

    assert result.total == 1
    assert result.failed == 1
    assert len(result.errors) == 1
