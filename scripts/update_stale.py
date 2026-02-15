#!/usr/bin/env python3
"""Re-index repositories whose data is older than N days.

Usage:
    python scripts/update_stale.py
    python scripts/update_stale.py --stale-days 14
    python scripts/update_stale.py --dry-run
    python scripts/update_stale.py --limit 50
"""

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from qdrant_client import AsyncQdrantClient
from tqdm import tqdm

from app.config import settings
from app.services.embedder import EmbeddingService
from app.services.github_client import GitHubClient
from app.services.indexer import IndexingPipeline
from app.services.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def find_stale_repos(
    client: AsyncQdrantClient, collection: str, stale_days: int, limit: int | None = None
) -> list[dict]:
    """Scroll through all repos and return those older than stale_days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat()
    stale: list[dict] = []
    offset = None

    while True:
        scroll_kwargs: dict = {
            "collection_name": collection,
            "limit": 100,
            "with_payload": True,
            "with_vectors": False,
        }
        if offset is not None:
            scroll_kwargs["offset"] = offset

        points, next_offset = await client.scroll(**scroll_kwargs)

        for point in points:
            indexed_at = point.payload.get("indexed_at", "")
            if indexed_at < cutoff:
                stale.append(
                    {
                        "id": point.id,
                        "full_name": point.payload.get("full_name", ""),
                        "indexed_at": indexed_at,
                    }
                )

        if next_offset is None or not points:
            break
        offset = next_offset

        if limit and len(stale) >= limit:
            stale = stale[:limit]
            break

    return stale


async def main(stale_days: int = 7, limit: int | None = None, dry_run: bool = False):
    github_client = GitHubClient(token=settings.github_pat)
    embedder = EmbeddingService(model_name=settings.embedding_model)

    if settings.qdrant_url:
        qdrant_kwargs: dict = {"url": settings.qdrant_url}
    else:
        qdrant_kwargs: dict = {"host": settings.qdrant_host, "port": settings.qdrant_port}
    if settings.qdrant_api_key:
        qdrant_kwargs["api_key"] = settings.qdrant_api_key
    qdrant_client = AsyncQdrantClient(**qdrant_kwargs)

    vector_store = VectorStore(qdrant_client)

    pipeline = IndexingPipeline(
        github_client=github_client,
        embedder=embedder,
        vector_store=vector_store,
        stale_days=stale_days,
    )

    logger.info("Finding repos older than %d days...", stale_days)
    stale_repos = await find_stale_repos(
        qdrant_client, vector_store.collection_name, stale_days, limit
    )
    logger.info("Found %d stale repos to re-index.", len(stale_repos))

    if dry_run:
        for repo in stale_repos:
            logger.info(
                "  Would re-index: %s (indexed_at: %s)",
                repo["full_name"],
                repo["indexed_at"],
            )
        await github_client.close()
        await qdrant_client.close()
        return

    indexed = 0
    failed = 0

    pbar = tqdm(stale_repos, desc="Re-indexing repos", unit="repo")
    for repo in pbar:
        full_name = repo["full_name"]
        pbar.set_postfix_str(full_name, refresh=False)
        parts = full_name.split("/")
        if len(parts) != 2:
            logger.warning("Skipping invalid full_name: %s", full_name)
            failed += 1
            continue

        owner, name = parts
        try:
            result = await pipeline.index_single_repo(owner, name, force=True)
            if result.status == "indexed":
                indexed += 1
            else:
                failed += 1
                logger.warning("Failed to re-index %s: %s", full_name, result.message)
        except Exception as e:
            failed += 1
            logger.error("Error re-indexing %s: %s", full_name, e)

    logger.info(
        "Update complete: %d re-indexed, %d failed out of %d stale.",
        indexed,
        failed,
        len(stale_repos),
    )

    await github_client.close()
    await qdrant_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-index stale RepoRadar repos")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=7,
        help="Days before repo is stale",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max repos to re-index")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List stale repos without re-indexing",
    )
    args = parser.parse_args()

    asyncio.run(main(stale_days=args.stale_days, limit=args.limit, dry_run=args.dry_run))
