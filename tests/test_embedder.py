"""Integration / smoke tests for the EmbeddingService.

These tests load the actual sentence-transformers model so they are slower
than pure unit tests.  They are marked with ``@pytest.mark.slow`` and can be
excluded in fast CI runs with ``pytest -m "not slow"``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services.embedder import EmbeddingService

EXPECTED_DIM = 384


@pytest.fixture(scope="module")
def embedder() -> EmbeddingService:
    """Load the model once and share it across all tests in this module."""
    return EmbeddingService()


@pytest.mark.slow
def test_embed_output_shape(embedder: EmbeddingService) -> None:
    """embed() should return a list of exactly 384 floats."""
    vector = embedder.embed("Hello, world!")

    assert isinstance(vector, list)
    assert len(vector) == EXPECTED_DIM
    assert all(isinstance(v, float) for v in vector)


@pytest.mark.slow
def test_embed_normalized(embedder: EmbeddingService) -> None:
    """The returned vector should be unit-length (L2 norm approximately 1.0)."""
    vector = embedder.embed("Normalisation check")
    norm = math.sqrt(sum(v * v for v in vector))

    assert norm == pytest.approx(1.0, abs=1e-4)


@pytest.mark.slow
def test_embed_batch(embedder: EmbeddingService) -> None:
    """embed_batch() should return one 384-d vector per input text."""
    texts = [
        "First sentence",
        "Second sentence",
        "Third sentence",
    ]
    vectors = embedder.embed_batch(texts)

    assert isinstance(vectors, list)
    assert len(vectors) == len(texts)

    for vec in vectors:
        assert isinstance(vec, list)
        assert len(vec) == EXPECTED_DIM
        # each vector should also be normalised
        norm = math.sqrt(sum(v * v for v in vec))
        assert norm == pytest.approx(1.0, abs=1e-4)


@pytest.mark.slow
def test_semantic_similarity(embedder: EmbeddingService) -> None:
    """Semantically related texts should have higher cosine similarity.

    Because the vectors are already normalised, cosine similarity equals
    the dot product.
    """
    text_a = "Python web framework for building APIs"
    text_b = "Flask Django FastAPI web development"
    text_c = "Quantum physics research paper"

    vec_a = np.array(embedder.embed(text_a))
    vec_b = np.array(embedder.embed(text_b))
    vec_c = np.array(embedder.embed(text_c))

    sim_ab = float(np.dot(vec_a, vec_b))
    sim_ac = float(np.dot(vec_a, vec_c))

    # Related texts should have meaningful similarity
    assert sim_ab > 0.5, f"Expected cosine similarity > 0.5 for related texts, got {sim_ab:.4f}"

    # Unrelated text should score notably lower than the related pair
    assert sim_ab > sim_ac, (
        f"Related pair similarity ({sim_ab:.4f}) should exceed "
        f"unrelated pair similarity ({sim_ac:.4f})"
    )


@pytest.mark.slow
def test_empty_text(embedder: EmbeddingService) -> None:
    """Embedding an empty string should not crash and should return a 384-d vector."""
    vector = embedder.embed("")

    assert isinstance(vector, list)
    assert len(vector) == EXPECTED_DIM
