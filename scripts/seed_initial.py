#!/usr/bin/env python3
"""Seed the vector database with repos from GitHub search.

Usage:
    python scripts/seed_initial.py
    python scripts/seed_initial.py --limit 20
    python scripts/seed_initial.py --dry-run
"""

import argparse
import asyncio
import logging

from qdrant_client import AsyncQdrantClient
from tqdm import tqdm

from app.config import settings
from app.services.embedder import EmbeddingService
from app.services.github_client import GitHubClient
from app.services.indexer import IndexingPipeline
from app.services.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEED_TOPICS = [
    # Original 30
    "web-framework",
    "machine-learning",
    "cli-tool",
    "database",
    "game-engine",
    "mobile-app",
    "devops",
    "data-science",
    "api",
    "testing",
    "security",
    "blockchain",
    "compiler",
    "networking",
    "gui",
    "text-editor",
    "package-manager",
    "static-site-generator",
    "orm",
    "message-queue",
    "monitoring",
    "container",
    "search-engine",
    "http-client",
    "image-processing",
    "nlp",
    "embedded",
    "terminal",
    "linter",
    "build-tool",
    # Expanded topics for 10k+ coverage
    "deep-learning",
    "computer-vision",
    "reinforcement-learning",
    "chatbot",
    "llm",
    "generative-ai",
    "transformer",
    "pytorch",
    "tensorflow",
    "kubernetes",
    "docker",
    "terraform",
    "ansible",
    "ci-cd",
    "microservices",
    "graphql",
    "rest-api",
    "websocket",
    "grpc",
    "authentication",
    "oauth",
    "jwt",
    "encryption",
    "proxy",
    "load-balancer",
    "reverse-proxy",
    "web-scraping",
    "crawler",
    "automation",
    "bot",
    "discord-bot",
    "slack-bot",
    "telegram-bot",
    "react",
    "vue",
    "svelte",
    "nextjs",
    "tailwindcss",
    "css-framework",
    "component-library",
    "design-system",
    "icon",
    "font",
    "animation",
    "3d",
    "webgl",
    "game",
    "physics-engine",
    "audio",
    "video",
    "streaming",
    "media-player",
    "pdf",
    "markdown",
    "documentation",
    "wiki",
    "cms",
    "blog",
    "e-commerce",
    "payment",
    "email",
    "notification",
    "calendar",
    "dashboard",
    "admin-panel",
    "analytics",
    "logging",
    "tracing",
    "profiler",
    "debugger",
    "code-editor",
    "ide",
    "language-server",
    "syntax-highlighting",
    "code-formatter",
    "type-checker",
    "bundler",
    "transpiler",
    "interpreter",
    "virtual-machine",
    "operating-system",
    "filesystem",
    "distributed-system",
    "consensus",
    "raft",
    "cache",
    "redis",
    "sqlite",
    "postgresql",
    "mongodb",
    "elasticsearch",
    "time-series",
    "graph-database",
    "key-value-store",
    "data-pipeline",
    "etl",
    "data-visualization",
    "charting",
    "plotting",
    "geospatial",
    "maps",
    "gps",
    "iot",
    "robotics",
    "drone",
    "self-driving",
    "simulation",
    "scientific-computing",
    "bioinformatics",
    "quantum-computing",
    "cryptography",
    "hashing",
    "vpn",
    "firewall",
    "malware-analysis",
    "penetration-testing",
    "vulnerability-scanner",
    "password-manager",
    "blockchain-ethereum",
    "smart-contracts",
    "defi",
    "nft",
    "cryptocurrency",
    "wallet",
    "cross-platform",
    "flutter",
    "react-native",
    "electron",
    "tauri",
    "wasm",
    "serverless",
    "lambda",
    "edge-computing",
    "cdn",
    "dns",
    "http-server",
    "web-server",
    "rate-limiting",
    "queue",
    "task-scheduler",
    "cron",
    "workflow-engine",
    "state-machine",
    "parser",
    "serialization",
    "protobuf",
    "json",
    "yaml",
    "xml",
    "csv",
    "regex",
    "math",
    "statistics",
    "linear-algebra",
    "optimization",
    "genetic-algorithm",
    "neural-network",
    "speech-recognition",
    "text-to-speech",
    "translation",
    "sentiment-analysis",
    "recommendation-system",
    "collaborative-filtering",
    "feature-engineering",
    "model-serving",
    "mlops",
    "jupyter",
    "notebook",
]


async def main(limit: int | None = None, dry_run: bool = False):
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
    await vector_store.create_collection()

    pipeline = IndexingPipeline(
        github_client=github_client,
        embedder=embedder,
        vector_store=vector_store,
        stale_days=settings.index_stale_days,
    )

    repos_to_index: list[tuple[str, str]] = []
    per_topic = 30

    for topic in tqdm(SEED_TOPICS, desc="Discovering repos", unit="topic"):
        query = f"topic:{topic} stars:>{settings.seed_min_stars}"
        try:
            results = await github_client.search_repositories(
                query=query, sort="stars", per_page=per_topic
            )
            for meta in results:
                parts = meta.full_name.split("/")
                if len(parts) == 2:
                    repos_to_index.append((parts[0], parts[1]))
        except Exception as e:
            logger.warning("Failed to search topic '%s': %s", topic, e)

        # Brief pause between search queries
        await asyncio.sleep(0.5)

    # Deduplicate
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for owner, repo in repos_to_index:
        key = f"{owner}/{repo}"
        if key not in seen:
            seen.add(key)
            unique.append((owner, repo))
    repos_to_index = unique

    if limit:
        repos_to_index = repos_to_index[:limit]

    logger.info("Total unique repos to index: %d", len(repos_to_index))

    if dry_run:
        for owner, repo in repos_to_index:
            logger.info("  Would index: %s/%s", owner, repo)
        return

    indexed = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    pbar = tqdm(repos_to_index, desc="Indexing repos", unit="repo")
    for owner, repo in pbar:
        pbar.set_postfix_str(f"{owner}/{repo}", refresh=False)
        try:
            result = await pipeline.index_single_repo(owner, repo)
            if result.status == "indexed":
                indexed += 1
            elif result.status == "skipped":
                skipped += 1
            else:
                failed += 1
                errors.append(f"{owner}/{repo}: {result.message}")
        except Exception as e:
            failed += 1
            errors.append(f"{owner}/{repo}: {e}")

    logger.info(
        "Seeding complete: %d indexed, %d skipped, %d failed out of %d total",
        indexed,
        skipped,
        failed,
        len(repos_to_index),
    )
    if errors:
        for err in errors[:10]:
            logger.warning("  Error: %s", err)

    await github_client.close()
    await qdrant_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the RepoRadar database")
    parser.add_argument("--limit", type=int, default=None, help="Max repos to index")
    parser.add_argument("--dry-run", action="store_true", help="List repos without indexing")
    args = parser.parse_args()

    asyncio.run(main(limit=args.limit, dry_run=args.dry_run))
