"""Embedding service for generating semantic vectors from text.

Uses sentence-transformers to produce normalized vectors whose dimension is
determined by the loaded model.  This module is intentionally synchronous
(CPU-bound).  Callers should use ``asyncio.to_thread(embedder.embed, text)``
to avoid blocking the event loop.
"""

from __future__ import annotations

import torch


class EmbeddingService:
    """Thin wrapper around a SentenceTransformer model.

    The model is loaded once on instantiation and held in memory for the
    lifetime of the service.  All returned vectors are L2-normalised so that
    dot-product equals cosine similarity.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.dimension: int = self.model.get_sentence_embedding_dimension()  # type: ignore[assignment]

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Returns a normalised vector of ``self.dimension`` floats.
        """
        with torch.no_grad():
            vector = self.model.encode(
                text,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return vector.tolist()  # type: ignore[union-attr]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently.

        Uses ``batch_size=32`` internally for balanced throughput/memory usage.
        Returns a list of normalised vectors, one per input text.
        """
        with torch.no_grad():
            vectors = self.model.encode(
                texts,
                batch_size=32,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return vectors.tolist()  # type: ignore[union-attr]
