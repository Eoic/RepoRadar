"""Tests for VectorStore.search_similar using Qdrant in-memory mode."""

import math

import pytest
from qdrant_client import AsyncQdrantClient

from app.services.vector_store import VectorStore

VECTOR_SIZE = 384

# --- Helpers ---


def _normalize(v: list[float]) -> list[float]:
    """L2-normalize a vector so cosine similarity = dot product."""
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v] if norm > 0 else v


def _base_vector() -> list[float]:
    """A reference direction used as the query vector."""
    raw = [1.0] * 64 + [0.0] * (VECTOR_SIZE - 64)
    return _normalize(raw)


def _orthogonal_vector() -> list[float]:
    """A vector orthogonal to _base_vector (near-zero cosine similarity)."""
    raw = [0.0] * 64 + [1.0] * 64 + [0.0] * (VECTOR_SIZE - 128)
    return _normalize(raw)


def _moderate_vector() -> list[float]:
    """A vector that partially overlaps with _base_vector."""
    raw = [1.0] * 32 + [0.0] * 32 + [1.0] * 32 + [0.0] * (VECTOR_SIZE - 96)
    return _normalize(raw)


QUERY_PURPOSE = _base_vector()
QUERY_STACK = _base_vector()


def _payload(name: str, stars: int = 100) -> dict:
    return {
        "full_name": name,
        "url": f"https://github.com/{name}",
        "description": f"Description of {name}",
        "stars": stars,
    }


# --- Fixtures ---


@pytest.fixture
async def store_with_repos():
    """Create an in-memory VectorStore and upsert 5 test repos."""
    client = AsyncQdrantClient(":memory:")
    store = VectorStore(client, vector_size=VECTOR_SIZE)
    await store.create_collection()

    repos = [
        # Exact match: both purpose and stack align with query
        (1, QUERY_PURPOSE, QUERY_STACK, _payload("exact/match", stars=500)),
        # Purpose-only match: purpose aligns, stack is orthogonal
        (2, QUERY_PURPOSE, _orthogonal_vector(), _payload("purpose/only", stars=200)),
        # Stack-only match: purpose is orthogonal, stack aligns
        (3, _orthogonal_vector(), QUERY_STACK, _payload("stack/only", stars=150)),
        # Moderate match: partially overlapping vectors
        (4, _moderate_vector(), _moderate_vector(), _payload("moderate/match", stars=100)),
        # Unrelated: orthogonal in both spaces
        (5, _orthogonal_vector(), _orthogonal_vector(), _payload("unrelated/repo", stars=50)),
    ]

    for repo_id, purpose_vec, stack_vec, payload in repos:
        await store.upsert_repo(
            repo_id=repo_id,
            purpose_vector=purpose_vec,
            stack_vector=stack_vec,
            payload=payload,
        )

    return store


# --- Tests ---


async def test_search_returns_sorted_by_weighted_score(store_with_repos: VectorStore):
    results = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, weight_purpose=0.7, weight_stack=0.3, min_score=0.0
    )
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].id == 1  # exact match should be first


async def test_purpose_only_result_scores(store_with_repos: VectorStore):
    results = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, weight_purpose=0.7, weight_stack=0.3, min_score=0.0
    )
    purpose_only = next(r for r in results if r.id == 2)
    assert purpose_only.purpose_score > 0.9
    assert purpose_only.stack_score < 0.3


async def test_stack_only_result_scores(store_with_repos: VectorStore):
    results = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, weight_purpose=0.7, weight_stack=0.3, min_score=0.0
    )
    stack_only = next(r for r in results if r.id == 3)
    assert stack_only.stack_score > 0.9
    assert stack_only.purpose_score < 0.3


async def test_merge_combines_scores_from_both_spaces(store_with_repos: VectorStore):
    wp, ws = 0.7, 0.3
    results = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, weight_purpose=wp, weight_stack=ws, min_score=0.0
    )
    for r in results:
        expected = wp * r.purpose_score + ws * r.stack_score
        assert abs(r.score - expected) < 0.01


async def test_min_score_filtering(store_with_repos: VectorStore):
    results = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, weight_purpose=0.7, weight_stack=0.3, min_score=0.9
    )
    # Only the exact match should pass a 0.9 threshold
    assert all(r.score >= 0.9 for r in results)
    assert len(results) <= 2  # at most exact match + maybe purpose-only


async def test_limit_parameter_respected(store_with_repos: VectorStore):
    results = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, limit=2, min_score=0.0
    )
    assert len(results) <= 2


async def test_custom_weights_change_ranking(store_with_repos: VectorStore):
    """Switching weights between purpose-heavy and stack-heavy should reorder results."""
    purpose_heavy = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, weight_purpose=1.0, weight_stack=0.0, min_score=0.0
    )
    stack_heavy = await store_with_repos.search_similar(
        QUERY_PURPOSE, QUERY_STACK, weight_purpose=0.0, weight_stack=1.0, min_score=0.0
    )

    purpose_ids = [r.id for r in purpose_heavy]
    stack_ids = [r.id for r in stack_heavy]

    # purpose-only (id=2) should rank higher in purpose_heavy,
    # stack-only (id=3) should rank higher in stack_heavy
    assert purpose_ids.index(2) < purpose_ids.index(3)
    assert stack_ids.index(3) < stack_ids.index(2)


async def test_empty_collection_returns_empty_list():
    client = AsyncQdrantClient(":memory:")
    store = VectorStore(client, vector_size=VECTOR_SIZE)
    await store.create_collection()
    results = await store.search_similar(QUERY_PURPOSE, QUERY_STACK, min_score=0.0)
    assert results == []
