"""Vector store service wrapping Qdrant for dual-vector repository storage."""

import asyncio
import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointIdsList,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)

from app.models.domain import SearchResult

logger = logging.getLogger(__name__)


class VectorStore:
    """Manages the Qdrant 'repositories' collection with named purpose/stack vectors."""

    def __init__(self, client: AsyncQdrantClient, vector_size: int = 384) -> None:
        self.client = client
        self.vector_size = vector_size
        self.collection_name = "repositories"

    async def create_collection(self) -> None:
        """Create the repositories collection if it doesn't exist. Idempotent."""
        try:
            await self.client.get_collection(self.collection_name)
            logger.info("Collection '%s' already exists, skipping creation.", self.collection_name)
            return
        except Exception:
            # Collection does not exist — proceed to create it
            pass

        await self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "purpose": VectorParams(size=self.vector_size, distance=Distance.COSINE),
                "stack": VectorParams(size=self.vector_size, distance=Distance.COSINE),
            },
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    always_ram=True,
                ),
            ),
        )
        logger.info("Created collection '%s' with named vectors.", self.collection_name)

    async def upsert_repo(
        self,
        repo_id: int,
        purpose_vector: list[float],
        stack_vector: list[float],
        payload: dict,
    ) -> None:
        """Upsert a repository with both vectors and payload."""
        point = PointStruct(
            id=repo_id,
            vector={
                "purpose": purpose_vector,
                "stack": stack_vector,
            },
            payload=payload,
        )
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )
        logger.debug("Upserted repo %d into collection '%s'.", repo_id, self.collection_name)

    async def repo_exists(self, repo_id: int) -> bool:
        """Check if a repo point exists in the collection."""
        results = await self.client.retrieve(
            collection_name=self.collection_name,
            ids=[repo_id],
        )
        return len(results) > 0

    async def get_repo_indexed_at(self, repo_id: int) -> str | None:
        """Get the indexed_at timestamp for a repo, or None if not found."""
        results = await self.client.retrieve(
            collection_name=self.collection_name,
            ids=[repo_id],
        )
        if not results:
            return None
        return results[0].payload.get("indexed_at")

    async def delete_repo(self, repo_id: int) -> None:
        """Delete a repo point from the collection."""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[repo_id]),
        )
        logger.debug("Deleted repo %d from collection '%s'.", repo_id, self.collection_name)

    async def get_collection_stats(self) -> dict:
        """Get collection info: points count, status, etc."""
        info = await self.client.get_collection(self.collection_name)
        return {
            "points_count": info.points_count,
            "status": info.status.value if info.status else None,
            "collection_name": self.collection_name,
        }

    async def get_repo_vectors(self, repo_id: int) -> tuple[list[float], list[float]] | None:
        """Retrieve stored purpose and stack vectors for a repo. Returns None if not found."""
        results = await self.client.retrieve(
            collection_name=self.collection_name,
            ids=[repo_id],
            with_vectors=True,
        )
        if not results:
            return None
        vectors = results[0].vector
        return (vectors["purpose"], vectors["stack"])

    async def search_similar(
        self,
        purpose_vector: list[float],
        stack_vector: list[float],
        weight_purpose: float = 0.7,
        weight_stack: float = 0.3,
        limit: int = 20,
        min_score: float = 0.3,
    ) -> list[SearchResult]:
        """Dual-vector weighted search: merge purpose + stack results."""
        fetch_limit = limit * 3

        purpose_results, stack_results = await asyncio.gather(
            self.client.query_points(
                collection_name=self.collection_name,
                query=purpose_vector,
                using="purpose",
                limit=fetch_limit,
                with_payload=True,
            ),
            self.client.query_points(
                collection_name=self.collection_name,
                query=stack_vector,
                using="stack",
                limit=fetch_limit,
                with_payload=True,
            ),
        )

        # Merge scores from both result sets
        scores: dict[int, dict] = {}
        for r in purpose_results.points:
            scores[r.id] = {
                "purpose": r.score,
                "stack": 0.0,
                "payload": r.payload,
            }
        for r in stack_results.points:
            if r.id in scores:
                scores[r.id]["stack"] = r.score
            else:
                scores[r.id] = {
                    "purpose": 0.0,
                    "stack": r.score,
                    "payload": r.payload,
                }

        # Compute weighted final score and filter
        ranked: list[SearchResult] = []
        for repo_id, data in scores.items():
            final = weight_purpose * data["purpose"] + weight_stack * data["stack"]
            if final >= min_score:
                ranked.append(
                    SearchResult(
                        id=repo_id,
                        score=final,
                        purpose_score=data["purpose"],
                        stack_score=data["stack"],
                        payload=data["payload"],
                    )
                )

        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[:limit]
