from datetime import datetime

from pydantic import BaseModel


class RepoMetadata(BaseModel):
    id: int
    full_name: str
    url: str
    description: str | None = None
    topics: list[str] = []
    language_primary: str | None = None
    stars: int = 0
    forks: int = 0
    last_updated: datetime | None = None


class RepoDocument(BaseModel):
    id: int
    full_name: str
    url: str
    description: str | None = None
    readme_text: str = ""
    topics: list[str] = []
    language_primary: str | None = None
    languages: dict[str, float] = {}
    dependencies: list[str] = []
    stars: int = 0
    forks: int = 0
    last_updated: datetime | None = None
    indexed_at: datetime | None = None


class EmbeddingPair(BaseModel):
    purpose: list[float]
    stack: list[float]


class SearchResult(BaseModel):
    id: int
    score: float
    purpose_score: float = 0.0
    stack_score: float = 0.0
    payload: dict = {}


class IndexResult(BaseModel):
    status: str
    repo_id: int
    full_name: str
    description: str | None = None
    message: str = ""


class BatchIndexResult(BaseModel):
    total: int
    indexed: int
    skipped: int
    failed: int
    errors: list[str] = []
