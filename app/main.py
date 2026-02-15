"""FastAPI application entry point with lifespan management."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import AsyncQdrantClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.auth import router as auth_router
from app.api.routes import router as api_router
from app.config import settings
from app.models.schemas import HealthResponse
from app.rate_limit import limiter
from app.services.embedder import EmbeddingService
from app.services.github_client import GitHubClient
from app.services.indexer import IndexingPipeline
from app.services.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup, clean up on shutdown."""
    logger.info("Initializing services...")

    github_client = GitHubClient(token=settings.github_pat)
    embedder = EmbeddingService(model_name=settings.embedding_model)

    if settings.qdrant_url:
        qdrant_kwargs = {"url": settings.qdrant_url}
    else:
        qdrant_kwargs = {"host": settings.qdrant_host, "port": settings.qdrant_port}
    if settings.qdrant_api_key:
        qdrant_kwargs["api_key"] = settings.qdrant_api_key
    qdrant_client = AsyncQdrantClient(**qdrant_kwargs)

    vector_store = VectorStore(qdrant_client, vector_size=embedder.dimension)
    await vector_store.create_collection()

    pipeline = IndexingPipeline(
        github_client=github_client,
        embedder=embedder,
        vector_store=vector_store,
        stale_days=settings.index_stale_days,
    )

    app.state.github_client = github_client
    app.state.embedder = embedder
    app.state.vector_store = vector_store
    app.state.pipeline = pipeline
    app.state.qdrant_client = qdrant_client

    logger.info("All services initialized.")
    yield

    logger.info("Shutting down services...")
    await github_client.close()
    await qdrant_client.close()
    logger.info("Services shut down.")


app = FastAPI(title="RepoRadar", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(api_router)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log request method, path, and response time."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s — %d (%.1fms)", request.method, request.url.path, response.status_code, elapsed
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return clean JSON for unhandled exceptions."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    qdrant_connected = True
    try:
        stats = await app.state.vector_store.get_collection_stats()
        indexed_repos = stats.get("points_count", 0)
    except Exception:
        indexed_repos = 0
        qdrant_connected = False

    rate_limit = None
    if hasattr(app.state, "github_client"):
        rate_limit = app.state.github_client.rate_limit_remaining

    return HealthResponse(
        status="ok" if qdrant_connected else "degraded",
        indexed_repos=indexed_repos,
        qdrant_connected=qdrant_connected,
        github_rate_limit_remaining=rate_limit,
    )
