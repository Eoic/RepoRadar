"""Tests for the VectorStore service using Qdrant in-memory mode."""

import pytest
from qdrant_client import AsyncQdrantClient

from app.services.vector_store import VectorStore

VECTOR_DIM = 384


def _make_vector(seed: int) -> list[float]:
    """Create a deterministic 384-d vector from a seed value."""
    return [float((i + seed) % 10) / 10.0 for i in range(VECTOR_DIM)]


def _make_payload(name: str, indexed_at: str = "2025-06-01T00:00:00Z") -> dict:
    """Create a minimal test payload."""
    return {
        "full_name": name,
        "description": f"Description for {name}",
        "url": f"https://github.com/{name}",
        "topics": ["test"],
        "language_primary": "Python",
        "stars": 100,
        "last_updated": "2025-05-01T00:00:00Z",
        "indexed_at": indexed_at,
    }


@pytest.fixture
async def vector_store():
    client = AsyncQdrantClient(":memory:")
    store = VectorStore(client, vector_size=VECTOR_DIM)
    await store.create_collection()
    return store


async def test_create_collection_idempotent(vector_store: VectorStore):
    """Calling create_collection a second time should not raise."""
    await vector_store.create_collection()
    # If we reach here without exception, idempotency works.
    stats = await vector_store.get_collection_stats()
    assert stats["collection_name"] == "repositories"


async def test_upsert_and_exists(vector_store: VectorStore):
    """Upserting a repo should make repo_exists return True."""
    repo_id = 1001
    await vector_store.upsert_repo(
        repo_id=repo_id,
        purpose_vector=_make_vector(0),
        stack_vector=_make_vector(1),
        payload=_make_payload("owner/repo-a"),
    )
    assert await vector_store.repo_exists(repo_id) is True


async def test_repo_not_exists(vector_store: VectorStore):
    """repo_exists should return False for an ID that was never inserted."""
    assert await vector_store.repo_exists(99999) is False


async def test_get_repo_indexed_at(vector_store: VectorStore):
    """get_repo_indexed_at should return the stored indexed_at value."""
    repo_id = 2001
    expected_ts = "2025-08-15T12:00:00Z"
    await vector_store.upsert_repo(
        repo_id=repo_id,
        purpose_vector=_make_vector(2),
        stack_vector=_make_vector(3),
        payload=_make_payload("owner/repo-b", indexed_at=expected_ts),
    )
    result = await vector_store.get_repo_indexed_at(repo_id)
    assert result == expected_ts


async def test_get_repo_indexed_at_not_found(vector_store: VectorStore):
    """get_repo_indexed_at should return None for an unknown ID."""
    result = await vector_store.get_repo_indexed_at(88888)
    assert result is None


async def test_delete_repo(vector_store: VectorStore):
    """After deleting a repo, repo_exists should return False."""
    repo_id = 3001
    await vector_store.upsert_repo(
        repo_id=repo_id,
        purpose_vector=_make_vector(4),
        stack_vector=_make_vector(5),
        payload=_make_payload("owner/repo-c"),
    )
    assert await vector_store.repo_exists(repo_id) is True

    await vector_store.delete_repo(repo_id)
    assert await vector_store.repo_exists(repo_id) is False


async def test_get_collection_stats(vector_store: VectorStore):
    """After upserting 3 repos, stats should show a points_count of 3."""
    for i, repo_id in enumerate([4001, 4002, 4003]):
        await vector_store.upsert_repo(
            repo_id=repo_id,
            purpose_vector=_make_vector(i * 2),
            stack_vector=_make_vector(i * 2 + 1),
            payload=_make_payload(f"owner/repo-{i}"),
        )

    stats = await vector_store.get_collection_stats()
    assert stats["points_count"] == 3


async def test_get_repo_vectors(vector_store: VectorStore):
    """Retrieved vectors should have the right shape and be retrievable."""
    repo_id = 5001
    purpose_vec = _make_vector(10)
    stack_vec = _make_vector(20)

    await vector_store.upsert_repo(
        repo_id=repo_id,
        purpose_vector=purpose_vec,
        stack_vector=stack_vec,
        payload=_make_payload("owner/repo-d"),
    )

    result = await vector_store.get_repo_vectors(repo_id)
    assert result is not None

    retrieved_purpose, retrieved_stack = result
    assert len(retrieved_purpose) == VECTOR_DIM
    assert len(retrieved_stack) == VECTOR_DIM


async def test_get_repo_vectors_not_found(vector_store: VectorStore):
    """get_repo_vectors should return None for an unknown ID."""
    result = await vector_store.get_repo_vectors(77777)
    assert result is None
