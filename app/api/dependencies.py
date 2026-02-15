"""FastAPI dependency injection providers."""

from fastapi import Request

from app.services.github_client import GitHubClient
from app.services.indexer import IndexingPipeline
from app.services.vector_store import VectorStore


def get_vector_store(request: Request) -> VectorStore:
    return request.app.state.vector_store


def get_github_client(request: Request) -> GitHubClient:
    return request.app.state.github_client


def get_pipeline(request: Request) -> IndexingPipeline:
    return request.app.state.pipeline
