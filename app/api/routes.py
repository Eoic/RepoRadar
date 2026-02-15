"""API route definitions."""

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_pipeline, get_vector_store
from app.models.schemas import (
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    parse_repo_url,
)
from app.rate_limit import limiter
from app.services.indexer import IndexingPipeline
from app.services.vector_store import VectorStore

router = APIRouter(prefix="/api")


@router.post("/search", response_model=SearchResponse)
@limiter.limit("10/minute")
async def search(
    request: Request,
    body: SearchRequest,
    pipeline: IndexingPipeline = Depends(get_pipeline),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """Search for similar repositories."""
    try:
        owner, repo = parse_repo_url(body.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start = time.monotonic()

    # Index on-the-fly if needed
    index_result = await pipeline.index_single_repo(owner, repo)
    if index_result.status == "failed":
        raise HTTPException(status_code=502, detail=f"Failed to index: {index_result.message}")

    # Get query repo's vectors
    vectors = await vector_store.get_repo_vectors(index_result.repo_id)
    if vectors is None:
        raise HTTPException(status_code=404, detail="Repo vectors not found after indexing")

    purpose_vec, stack_vec = vectors

    # Search
    results = await vector_store.search_similar(
        purpose_vector=purpose_vec,
        stack_vector=stack_vec,
        weight_purpose=body.weight_purpose,
        weight_stack=body.weight_stack,
        limit=body.limit + 1,  # Overfetch to allow excluding self
        min_score=0.1,
    )

    # Exclude the query repo itself and apply min_stars filter
    items: list[SearchResultItem] = []
    for r in results:
        if r.id == index_result.repo_id:
            continue
        if body.min_stars and r.payload.get("stars", 0) < body.min_stars:
            continue
        items.append(
            SearchResultItem(
                full_name=r.payload.get("full_name", ""),
                url=r.payload.get("url", ""),
                description=r.payload.get("description"),
                topics=r.payload.get("topics", []),
                language_primary=r.payload.get("language_primary"),
                stars=r.payload.get("stars", 0),
                similarity_score=round(r.score, 4),
                purpose_score=round(r.purpose_score, 4),
                stack_score=round(r.stack_score, 4),
            )
        )
        if len(items) >= body.limit:
            break

    elapsed_ms = (time.monotonic() - start) * 1000

    # Get collection stats for count
    try:
        stats = await vector_store.get_collection_stats()
        indexed_count = stats.get("points_count", 0)
    except Exception:
        indexed_count = 0

    return SearchResponse(
        query_repo={
            "full_name": index_result.full_name,
            "description": index_result.description or "",
        },
        results=items,
        indexed_count=indexed_count,
        search_time_ms=round(elapsed_ms, 1),
    )


@router.post("/index", response_model=IndexResponse)
@limiter.limit("5/minute")
async def index_repo(
    request: Request,
    body: IndexRequest,
    pipeline: IndexingPipeline = Depends(get_pipeline),
):
    """Manually trigger indexing of a repository."""
    try:
        owner, repo = parse_repo_url(body.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await pipeline.index_single_repo(owner, repo, force=True)

    if result.status == "failed":
        raise HTTPException(status_code=502, detail=f"Indexing failed: {result.message}")

    return IndexResponse(
        status=result.status,
        repo_id=result.repo_id,
        full_name=result.full_name,
    )
