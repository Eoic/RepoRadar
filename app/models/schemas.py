import re

from pydantic import BaseModel, Field, field_validator, model_validator


def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo from a GitHub URL or 'owner/repo' string."""
    url = url.strip().rstrip("/")
    # Match full URLs
    match = re.match(r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if match:
        return match.group(1), match.group(2)
    # Match owner/repo format
    match = re.match(r"^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)$", url)
    if match:
        return match.group(1), match.group(2)
    raise ValueError(f"Invalid repo URL or identifier: {url}")


class SearchRequest(BaseModel):
    repo_url: str
    weight_purpose: float = 0.7
    weight_stack: float = 0.3
    limit: int = Field(default=20, ge=1, le=100)
    min_stars: int = 0

    @field_validator("weight_purpose")
    @classmethod
    def validate_weights(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("weight_purpose must be between 0 and 1")
        return v

    @field_validator("weight_stack")
    @classmethod
    def validate_stack_weight(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("weight_stack must be between 0 and 1")
        return v

    @model_validator(mode="after")
    def validate_weight_sum(self) -> "SearchRequest":
        total = self.weight_purpose + self.weight_stack
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"weight_purpose + weight_stack must equal 1.0, got {total}")
        return self


class SearchResultItem(BaseModel):
    full_name: str
    url: str
    description: str | None = None
    topics: list[str] = []
    language_primary: str | None = None
    stars: int = 0
    similarity_score: float
    purpose_score: float
    stack_score: float


class SearchResponse(BaseModel):
    query_repo: dict
    results: list[SearchResultItem]
    indexed_count: int = 0
    search_time_ms: float = 0


class IndexRequest(BaseModel):
    repo_url: str


class IndexResponse(BaseModel):
    status: str
    repo_id: int
    full_name: str


class HealthResponse(BaseModel):
    status: str
    qdrant_collections: int = 0
    indexed_repos: int = 0
    qdrant_connected: bool = True
    github_rate_limit_remaining: int | None = None


class UserRepoItem(BaseModel):
    full_name: str
    description: str | None = None
    stars: int = 0
    indexed: bool = False


class UserReposResponse(BaseModel):
    repos: list[UserRepoItem]
