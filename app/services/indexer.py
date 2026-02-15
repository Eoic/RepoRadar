"""Indexing pipeline that orchestrates fetching, preprocessing, embedding, and storage."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.models.domain import BatchIndexResult, IndexResult
from app.services.embedder import EmbeddingService
from app.services.github_client import GitHubClient
from app.services.preprocessor import (
    clean_readme,
    compose_purpose_text,
    compose_stack_text,
    extract_dependencies,
)
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

_HTTP_ERROR_MESSAGES: dict[int, str] = {
    401: "GitHub API authentication failed.",
    403: "GitHub API rate limit exceeded or access denied.",
    404: "Repository not found. Check the URL and make sure the repo is public.",
    451: "Repository is unavailable due to a legal request.",
}


def _friendly_http_error(full_name: str, exc: httpx.HTTPStatusError) -> str:
    """Turn an httpx status error into a short, user-facing message."""
    code = exc.response.status_code
    if code in _HTTP_ERROR_MESSAGES:
        return _HTTP_ERROR_MESSAGES[code]
    return f"GitHub API returned {code} while fetching {full_name}"


class IndexingPipeline:
    def __init__(
        self,
        github_client: GitHubClient,
        embedder: EmbeddingService,
        vector_store: VectorStore,
        stale_days: int = 7,
    ) -> None:
        self.github = github_client
        self.embedder = embedder
        self.vector_store = vector_store
        self.stale_days = stale_days

    def _is_stale(self, indexed_at: str | None) -> bool:
        """Check if a repo needs re-indexing based on its indexed_at timestamp."""
        if indexed_at is None:
            return True
        try:
            indexed_dt = datetime.fromisoformat(indexed_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) - indexed_dt > timedelta(days=self.stale_days)
        except (ValueError, TypeError):
            return True

    async def index_single_repo(self, owner: str, repo: str, *, force: bool = False) -> IndexResult:
        """Index a single repository through the full pipeline.

        1. Check staleness → skip if recently indexed (unless force=True)
        2. Fetch metadata, readme, languages, manifests in parallel
        3. Preprocess and compose embedding texts
        4. Embed via asyncio.to_thread (CPU-bound)
        5. Upsert into vector store
        """
        full_name = f"{owner}/{repo}"

        # Step 1: Check staleness
        if not force:
            try:
                metadata = await self.github.fetch_repo_metadata(owner, repo)
                indexed_at = await self.vector_store.get_repo_indexed_at(metadata.id)
                if not self._is_stale(indexed_at):
                    logger.info("Skipping %s — indexed recently.", full_name)
                    return IndexResult(
                        status="skipped",
                        repo_id=metadata.id,
                        full_name=full_name,
                        description=metadata.description,
                        message="Recently indexed",
                    )
            except Exception:
                pass  # Proceed to fetch if check fails

        # Step 2: Fetch everything in parallel
        try:
            metadata, readme, languages, manifests = await asyncio.gather(
                self.github.fetch_repo_metadata(owner, repo),
                self.github.fetch_readme(owner, repo),
                self.github.fetch_languages(owner, repo),
                self.github.fetch_manifest_files(owner, repo),
            )
        except httpx.HTTPStatusError as e:
            msg = _friendly_http_error(full_name, e)
            logger.error("Failed to fetch data for %s: %s", full_name, e)
            return IndexResult(status="failed", repo_id=0, full_name=full_name, message=msg)
        except Exception as e:
            logger.error("Failed to fetch data for %s: %s", full_name, e)
            return IndexResult(status="failed", repo_id=0, full_name=full_name, message=str(e))

        # Step 3: Preprocess
        cleaned_readme = clean_readme(readme or "")

        all_deps: list[str] = []
        for filename, content in manifests:
            all_deps.extend(extract_dependencies(content, filename))
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_deps: list[str] = []
        for dep in all_deps:
            if dep not in seen:
                seen.add(dep)
                unique_deps.append(dep)

        purpose_text = compose_purpose_text(metadata.description, metadata.topics, cleaned_readme)
        stack_text = compose_stack_text(metadata.language_primary, languages, unique_deps)

        # Step 4: Embed (CPU-bound, run in thread)
        purpose_vec, stack_vec = await asyncio.to_thread(
            lambda: (self.embedder.embed(purpose_text), self.embedder.embed(stack_text))
        )

        # Step 5: Upsert
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "full_name": metadata.full_name,
            "description": metadata.description or "",
            "url": metadata.url,
            "topics": metadata.topics,
            "language_primary": metadata.language_primary or "",
            "stars": metadata.stars,
            "last_updated": metadata.last_updated.isoformat() if metadata.last_updated else "",
            "indexed_at": now,
        }

        await self.vector_store.upsert_repo(
            repo_id=metadata.id,
            purpose_vector=purpose_vec,
            stack_vector=stack_vec,
            payload=payload,
        )

        logger.info("Indexed %s (id=%d)", full_name, metadata.id)
        return IndexResult(
            status="indexed",
            repo_id=metadata.id,
            full_name=full_name,
            description=metadata.description,
        )

    async def index_batch(self, repo_list: list[tuple[str, str]]) -> BatchIndexResult:
        """Index a list of (owner, repo) tuples sequentially with rate limiting."""
        total = len(repo_list)
        indexed = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        for owner, repo in repo_list:
            try:
                result = await self.index_single_repo(owner, repo)
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
                logger.error("Batch indexing error for %s/%s: %s", owner, repo, e)

        return BatchIndexResult(
            total=total, indexed=indexed, skipped=skipped, failed=failed, errors=errors
        )
