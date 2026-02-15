# GitHub Repository Similarity Search — Project Architecture & Implementation Plan

## 1. Project Overview

**Name:** RepoRadar (working title)

**Purpose:** A web service that allows users to discover GitHub repositories similar to their own or to any given repository. Users authenticate via GitHub OAuth, submit a repository URL, and receive a ranked list of similar projects based on semantic similarity of purpose, domain, and technology stack.

**GitHub Developer Program Qualification:** This project integrates directly with the GitHub API to fetch repository metadata, authenticate users, and surface GitHub content. It qualifies as a GitHub API integration suitable for Developer Program membership.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│              (Next.js or static SPA on GitHub Pages)         │
│                                                              │
│   [Search Bar] → Enter repo URL or select from your repos   │
│   [Results]    → Ranked list of similar repos with scores    │
│   [Filters]    → Weight sliders: purpose vs. tech stack      │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API calls
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Backend API                              │
│                   (FastAPI / Python)                          │
│                                                              │
│   /api/search         → Accept repo URL, return similar repos│
│   /api/index          → Trigger indexing of a repo           │
│   /api/auth/github    → GitHub OAuth flow                    │
│   /api/user/repos     → List authenticated user's repos      │
│   /api/health         → Health check                         │
└────┬──────────┬──────────┬──────────────────────────────────┘
     │          │          │
     ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌──────────────┐
│GitHub  │ │Embed-  │ │Vector DB     │
│API     │ │ding    │ │(Qdrant)      │
│Client  │ │Service │ │              │
└────────┘ └────────┘ └──────────────┘
```

---

## 3. Data Model

### 3.1 Repository Document

Each indexed repository is stored as a structured document with the following fields. This document serves as the source of truth before embedding.

```json
{
  "id": "github_repo_id (integer)",
  "full_name": "owner/repo",
  "url": "https://github.com/owner/repo",
  "description": "Short description from GitHub",
  "readme_text": "Cleaned and truncated README content (max 2000 tokens)",
  "topics": ["machine-learning", "python", "computer-vision"],
  "language_primary": "Python",
  "languages": {"Python": 85.2, "Shell": 10.1, "Dockerfile": 4.7},
  "dependencies": ["torch", "numpy", "fastapi"],
  "stars": 1234,
  "forks": 56,
  "last_updated": "2025-01-15T10:30:00Z",
  "indexed_at": "2025-02-10T14:00:00Z"
}
```

### 3.2 Embedding Strategy — Dual Vector Approach

Each repository produces **two separate embedding vectors**, allowing users to control how similarity is defined.

**Vector A — Purpose Embedding (what the project does):**
Constructed from a combined text input:

```
{description}. {topics as comma-separated list}. {first 1500 tokens of cleaned README}
```

This vector captures the semantic meaning, domain, and goals of the project.

**Vector B — Stack Embedding (what it is built with):**
Constructed from:

```
Primary language: {language}. Languages: {language list}. Dependencies: {dependency list}.
```

This vector captures the technology choices and ecosystem.

**Similarity Score Calculation:**

```
final_score = (weight_purpose * cosine_sim(A_query, A_candidate))
            + (weight_stack * cosine_sim(B_query, B_candidate))
```

Default weights: `weight_purpose = 0.7`, `weight_stack = 0.3`. Users can adjust these via the frontend.

### 3.3 Qdrant Collection Schema

Create two Qdrant collections (or one collection with named vectors):

```python
# Preferred: single collection with named vectors
collection_config = {
    "collection_name": "repositories",
    "vectors_config": {
        "purpose": VectorParams(size=384, distance=Distance.COSINE),
        "stack": VectorParams(size=384, distance=Distance.COSINE),
    }
}
```

Payload fields stored alongside vectors:

```python
payload = {
    "full_name": str,
    "description": str,
    "url": str,
    "topics": list[str],
    "language_primary": str,
    "stars": int,
    "last_updated": str,
    "indexed_at": str,
}
```

---

## 4. Component Specifications

### 4.1 GitHub API Client

**Module:** `app/services/github_client.py`

**Responsibilities:**
- Authenticate requests using a GitHub App token or personal access token.
- Fetch repository metadata: `GET /repos/{owner}/{repo}`.
- Fetch repository README: `GET /repos/{owner}/{repo}/readme` (returns base64-encoded content).
- Fetch repository languages: `GET /repos/{owner}/{repo}/languages`.
- Fetch dependency files by attempting to retrieve common manifest files: `package.json`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `pubspec.yaml`, `go.mod`, `Gemfile`, `pom.xml`, `build.gradle`. Use `GET /repos/{owner}/{repo}/contents/{path}` for each.
- Fetch trending/popular repos for seeding: use the search endpoint `GET /search/repositories?q=stars:>100&sort=updated`.
- Handle rate limiting: respect `X-RateLimit-Remaining` headers, implement exponential backoff, and queue requests when limits are approached.
- List authenticated user's repositories: `GET /user/repos`.

**Rate Limit Management:**
- Authenticated requests: 5,000/hour.
- Implement a token bucket or leaky bucket rate limiter.
- Log remaining quota on each response.
- For batch indexing, limit to ~4,000 requests/hour to leave headroom for user-initiated requests.

**Key function signatures:**

```python
async def fetch_repo_metadata(owner: str, repo: str) -> RepoMetadata
async def fetch_readme(owner: str, repo: str) -> str | None
async def fetch_languages(owner: str, repo: str) -> dict[str, float]
async def fetch_dependencies(owner: str, repo: str) -> list[str]
async def search_repositories(query: str, sort: str, per_page: int) -> list[RepoMetadata]
async def get_user_repos(access_token: str) -> list[RepoMetadata]
```

### 4.2 Text Preprocessing Pipeline

**Module:** `app/services/preprocessor.py`

**Responsibilities:**
- Clean README content: strip HTML tags, badge image links, CI status badges, table of contents boilerplate, and license sections. Collapse excessive whitespace.
- Truncate README to a maximum of 1,500 tokens (approximately 6,000 characters) to stay within embedding model input limits and reduce noise from lengthy READMEs.
- Normalize dependency names: lowercase, strip version specifiers (e.g., `torch>=2.0` → `torch`).
- Compose the two text inputs for embedding (purpose text and stack text) as defined in section 3.2.

**README Cleaning Steps (in order):**

1. Decode from base64.
2. Remove HTML tags using a regex or `bleach.clean()`.
3. Remove markdown image links: `![...](...)` patterns.
4. Remove badge lines (lines containing `shields.io`, `badge`, `img.shields`).
5. Remove lines that are only links.
6. Collapse multiple blank lines to a single blank line.
7. Truncate to 1,500 tokens.

**Key function signatures:**

```python
def clean_readme(raw_readme: str) -> str
def extract_dependencies(manifest_content: str, manifest_type: str) -> list[str]
def compose_purpose_text(description: str, topics: list[str], readme: str) -> str
def compose_stack_text(primary_language: str, languages: dict, dependencies: list[str]) -> str
```

### 4.3 Embedding Service

**Module:** `app/services/embedder.py`

**Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, fast inference, good general-purpose quality). This model can run on CPU for a prototype. For production scale, consider upgrading to `all-mpnet-base-v2` (768 dimensions) or using an API-based embedding service.

**Responsibilities:**
- Load the model once at startup and hold it in memory.
- Accept a text string and return a normalized embedding vector.
- Batch-embed multiple texts efficiently.

**Key function signatures:**

```python
class EmbeddingService:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        ...

    def embed(self, text: str) -> list[float]
    def embed_batch(self, texts: list[str]) -> list[list[float]]
```

**Important implementation notes:**
- Normalize vectors to unit length (the model may already do this, but verify).
- Set `torch.no_grad()` during inference.
- For batch operations, use the model's built-in `encode()` method with `batch_size=32`.

### 4.4 Vector Database (Qdrant)

**Module:** `app/services/vector_store.py`

**Deployment:** Run Qdrant via Docker for development (`qdrant/qdrant:latest`). For production, use Qdrant Cloud's free tier (1 GB storage, sufficient for ~100K repos).

**Responsibilities:**
- Create and manage the `repositories` collection with named vectors.
- Upsert repository points (both vectors + payload).
- Perform similarity search with named vector targeting and optional filters.
- Delete points when repos are re-indexed.

**Key function signatures:**

```python
class VectorStore:
    async def create_collection(self) -> None
    async def upsert_repo(self, repo_id: int, purpose_vector: list[float],
                          stack_vector: list[float], payload: dict) -> None
    async def search_similar(self, purpose_vector: list[float], stack_vector: list[float],
                             weight_purpose: float, weight_stack: float,
                             limit: int = 20, min_score: float = 0.3) -> list[SearchResult]
    async def repo_exists(self, repo_id: int) -> bool
    async def delete_repo(self, repo_id: int) -> None
    async def get_collection_stats(self) -> dict
```

**Search implementation detail:** Qdrant does not natively support weighted multi-vector queries in a single call. Implement this by performing two separate searches (one per named vector), then merging and re-ranking results in application code:

```python
async def search_similar(self, purpose_vec, stack_vec, w_purpose, w_stack, limit):
    # Fetch more candidates than needed from each vector space
    fetch_limit = limit * 3

    purpose_results = await self.client.search(
        collection_name="repositories",
        query_vector=("purpose", purpose_vec),
        limit=fetch_limit,
    )
    stack_results = await self.client.search(
        collection_name="repositories",
        query_vector=("stack", stack_vec),
        limit=fetch_limit,
    )

    # Merge: combine scores for repos appearing in both result sets
    scores = {}
    for r in purpose_results:
        scores[r.id] = {"purpose": r.score, "stack": 0.0, "payload": r.payload}
    for r in stack_results:
        if r.id in scores:
            scores[r.id]["stack"] = r.score
        else:
            scores[r.id] = {"purpose": 0.0, "stack": r.score, "payload": r.payload}

    # Compute weighted final score
    ranked = []
    for repo_id, data in scores.items():
        final = w_purpose * data["purpose"] + w_stack * data["stack"]
        if final >= min_score:
            ranked.append(SearchResult(id=repo_id, score=final, payload=data["payload"]))

    ranked.sort(key=lambda x: x.score, reverse=True)
    return ranked[:limit]
```

### 4.5 Indexing Pipeline

**Module:** `app/services/indexer.py`

**Responsibilities:**
- Orchestrate the full pipeline for a single repo: fetch metadata → preprocess → embed → store.
- Handle batch indexing for seeding the database.
- Implement idempotency: skip repos already indexed within the last 7 days.
- Log indexing progress and errors.

**Single repo indexing flow:**

```
1. Check if repo already indexed recently → skip if yes
2. Fetch metadata via GitHub API (repo info, README, languages, dependencies)
3. Clean and preprocess all text fields
4. Compose purpose_text and stack_text
5. Generate both embedding vectors
6. Upsert into Qdrant with payload
7. Return success/failure status
```

**Batch seeding strategy:**

To build an initial corpus of ~10,000 repositories for meaningful search results, use the following seeding sources:

1. GitHub Search API: query for repos with 50+ stars across popular topics (`machine-learning`, `web-framework`, `cli-tool`, `game-engine`, `database`, `mobile-app`, etc.). Use ~30 topic queries × ~100 repos each = 3,000 repos.
2. GitHub trending: scrape or use unofficial APIs for trending repos across all languages.
3. Awesome-lists: fetch well-known curated lists (e.g., `awesome-python`, `awesome-rust`, `awesome-flutter`) and index the repos they link to.

Batch indexing should run as a background task with rate limiting, targeting ~3,000 repos/hour (accounting for multiple API calls per repo).

**Key function signatures:**

```python
class IndexingPipeline:
    async def index_single_repo(self, owner: str, repo: str) -> IndexResult
    async def index_batch(self, repo_list: list[tuple[str, str]]) -> BatchIndexResult
    async def seed_from_search(self, topics: list[str], min_stars: int, per_topic: int) -> None
    async def seed_from_awesome_list(self, awesome_repo: str) -> None
```

### 4.6 API Endpoints

**Framework:** FastAPI

**Module:** `app/api/routes.py`

#### `POST /api/search`

Primary search endpoint.

```python
# Request
{
    "repo_url": "https://github.com/owner/repo",  # or "owner/repo"
    "weight_purpose": 0.7,    # optional, default 0.7
    "weight_stack": 0.3,      # optional, default 0.3
    "limit": 20,              # optional, default 20
    "min_stars": 0             # optional, filter by minimum stars
}

# Response
{
    "query_repo": {
        "full_name": "owner/repo",
        "description": "...",
        "topics": [...],
        "language_primary": "Python"
    },
    "results": [
        {
            "full_name": "other-owner/similar-repo",
            "url": "https://github.com/other-owner/similar-repo",
            "description": "...",
            "topics": [...],
            "language_primary": "Rust",
            "stars": 450,
            "similarity_score": 0.87,
            "purpose_score": 0.91,
            "stack_score": 0.78
        }
    ],
    "indexed_count": 10523,
    "search_time_ms": 45
}
```

**Search flow:**
1. Parse the repo URL to extract owner and repo name.
2. Check if the query repo is already indexed. If not, index it on the fly (this adds ~2-3 seconds latency).
3. Retrieve the query repo's vectors from Qdrant.
4. Perform the dual-vector weighted search.
5. Exclude the query repo itself from results.
6. Return ranked results.

#### `POST /api/index`

Manually trigger indexing of a repo (useful for ensuring fresh data).

```python
# Request
{ "repo_url": "https://github.com/owner/repo" }

# Response
{ "status": "indexed", "repo_id": 12345, "full_name": "owner/repo" }
```

#### `GET /api/auth/github`

Initiates the GitHub OAuth flow. Redirects to GitHub's authorization page.

#### `GET /api/auth/callback`

Handles the OAuth callback. Exchanges the authorization code for an access token. Sets a session cookie or returns a JWT.

#### `GET /api/user/repos`

Returns the authenticated user's repositories (requires OAuth token).

```python
# Response
{
    "repos": [
        { "full_name": "user/repo1", "description": "...", "stars": 10, "indexed": true },
        { "full_name": "user/repo2", "description": "...", "stars": 3, "indexed": false }
    ]
}
```

#### `GET /api/health`

Returns service health, collection stats, and API rate limit status.

### 4.7 Frontend

**Technology:** A single-page application. Two recommended approaches depending on deployment preference:

**Option A — Next.js (recommended for production):** Server-side rendering, API routes can proxy to the backend, easy deployment on Vercel.

**Option B — Static SPA on GitHub Pages (simpler, free hosting):** Use React + Vite or even plain HTML/JS. Calls the backend API directly. Better for Developer Program optics since it lives on GitHub infrastructure.

**UI Components:**

1. **Search input:** A text field accepting a GitHub repo URL or `owner/repo` format. An "Or select from your repos" dropdown that appears after GitHub OAuth login.
2. **Weight sliders:** Two linked sliders (purpose vs. stack) that sum to 1.0. Default position: 70/30.
3. **Results list:** Each result card shows: repo name (linked), description, primary language badge, topic tags, star count, and a similarity score breakdown (overall, purpose, stack) displayed as a small bar or percentage.
4. **Loading state:** A skeleton loader or progress indicator while the backend indexes and searches (may take 3-5 seconds for unindexed repos).
5. **Stats footer:** "Searching across X,XXX indexed repositories."

---

## 5. Project Structure

```
reporadar/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app initialization, lifespan events
│   ├── config.py                # Settings via pydantic-settings (env vars)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── domain.py            # Internal domain models (RepoDocument, SearchResult)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # API endpoint definitions
│   │   ├── auth.py              # GitHub OAuth endpoints
│   │   └── dependencies.py      # FastAPI dependency injection
│   ├── services/
│   │   ├── __init__.py
│   │   ├── github_client.py     # GitHub API interactions
│   │   ├── preprocessor.py      # Text cleaning and composition
│   │   ├── embedder.py          # Embedding model wrapper
│   │   ├── vector_store.py      # Qdrant client wrapper
│   │   └── indexer.py           # Orchestration pipeline
│   └── tasks/
│       ├── __init__.py
│       └── seed.py              # Background seeding scripts
├── frontend/                    # SPA or Next.js app (separate build)
│   ├── index.html
│   ├── src/
│   └── ...
├── scripts/
│   ├── seed_initial.py          # One-time seeding script
│   └── update_stale.py          # Re-index repos older than N days
├── tests/
│   ├── test_preprocessor.py
│   ├── test_embedder.py
│   ├── test_indexer.py
│   └── test_api.py
├── docker-compose.yml           # Qdrant + backend services
├── Dockerfile                   # Backend container
├── pyproject.toml               # Python dependencies
├── .env.example                 # Environment variable template
└── README.md                    # Project documentation
```

---

## 6. Configuration & Environment Variables

All configuration is managed through environment variables, loaded via `pydantic-settings`.

```env
# GitHub OAuth App credentials
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_PAT=...                 # Personal access token for API calls

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=                # Only needed for Qdrant Cloud

# Embedding
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu           # or "cuda" if GPU available

# App
APP_HOST=0.0.0.0
APP_PORT=8000
CORS_ORIGINS=["http://localhost:3000"]
SESSION_SECRET=...             # For signing session cookies

# Indexing
INDEX_STALE_DAYS=7             # Re-index repos older than this
SEED_MIN_STARS=50              # Minimum stars for seeded repos
```

---

## 7. Dependencies

```toml
[project]
name = "reporadar"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "httpx>=0.27",              # Async HTTP client for GitHub API
    "qdrant-client>=1.8",       # Qdrant Python client
    "sentence-transformers>=2.5",
    "pydantic-settings>=2.1",
    "python-jose>=3.3",         # JWT handling for auth
    "beautifulsoup4>=4.12",     # HTML cleaning in READMEs
    "markdown>=3.5",            # Markdown to text conversion
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "httpx",                    # For TestClient
]
```

---

## 8. Docker Compose Setup

```yaml
version: "3.8"
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  backend:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - qdrant
    volumes:
      - ./app:/app/app  # Hot reload in development

volumes:
  qdrant_data:
```

---

## 9. Implementation Order

Follow this sequence. Each phase produces a testable, working increment.

### Phase 1 — Core Pipeline (MVP)

**Goal:** Given a repo URL, fetch its data, embed it, and store it. No search yet, just the indexing path.

1. Set up the project structure, `pyproject.toml`, and Docker Compose with Qdrant.
2. Implement `config.py` with all settings.
3. Implement `github_client.py`: `fetch_repo_metadata`, `fetch_readme`, `fetch_languages`, `fetch_dependencies`. Write tests using mocked HTTP responses.
4. Implement `preprocessor.py`: `clean_readme`, `extract_dependencies`, `compose_purpose_text`, `compose_stack_text`. Write unit tests with sample READMEs.
5. Implement `embedder.py`: load model, `embed()`, `embed_batch()`. Write a smoke test that embeds sample text and verifies output shape.
6. Implement `vector_store.py`: `create_collection`, `upsert_repo`, `repo_exists`. Test against local Qdrant.
7. Implement `indexer.py`: `index_single_repo` that chains all the above. Test end-to-end with a real repo.

### Phase 2 — Search

**Goal:** Accept a query repo and return similar repos.

1. Implement `vector_store.py`: `search_similar` with the dual-vector merge-and-rank logic.
2. Implement the `POST /api/search` endpoint.
3. Write the initial seeding script (`scripts/seed_initial.py`) that indexes ~1,000 repos from popular topics.
4. Run the seeder and test search quality manually. Adjust preprocessing and weights as needed.

### Phase 3 — API & Auth

**Goal:** Complete the REST API with authentication.

1. Implement GitHub OAuth flow (`api/auth.py`): authorization redirect, callback handler, token storage.
2. Implement `GET /api/user/repos` endpoint.
3. Implement `POST /api/index` endpoint.
4. Implement `GET /api/health` endpoint.
5. Add CORS middleware, rate limiting middleware (e.g., `slowapi`), and error handling.

### Phase 4 — Frontend

**Goal:** A functional web UI.

1. Scaffold the frontend (React + Vite or Next.js).
2. Build the search input component with URL parsing and validation.
3. Build the results list with similarity score display.
4. Add the weight sliders.
5. Integrate GitHub OAuth login and the "select from your repos" dropdown.
6. Add loading states and error handling.
7. Deploy frontend to GitHub Pages or Vercel.

### Phase 5 — Scale & Polish

**Goal:** Production readiness.

1. Expand the seed corpus to 10,000+ repos.
2. Add a background job (cron or scheduled task) to re-index stale repos.
3. Add caching: cache embedding results for repos that haven't changed (use `pushed_at` timestamp from GitHub API).
4. Add request logging and basic analytics (most-searched repos, popular topics).
5. Write the project README with screenshots, API docs, and a "How it works" section.
6. Set up a GitHub Pages site as the integration's public landing page (required for Developer Program).
7. Register for the GitHub Developer Program with this project as the integration.

---

## 10. Dependency Parsing Reference

For phase 1, step 4, implement parsers for these common manifest formats:

| File | Language | Parsing Strategy |
|---|---|---|
| `requirements.txt` | Python | Split lines, strip version specs (`>=`, `==`, `~=`), ignore comments and blank lines |
| `pyproject.toml` | Python | Parse TOML, extract `project.dependencies` and `tool.poetry.dependencies` |
| `package.json` | JavaScript | Parse JSON, extract keys from `dependencies` and `devDependencies` |
| `Cargo.toml` | Rust | Parse TOML, extract keys from `[dependencies]` and `[dev-dependencies]` |
| `pubspec.yaml` | Dart/Flutter | Parse YAML, extract keys from `dependencies` and `dev_dependencies` |
| `go.mod` | Go | Regex for `require` block entries |
| `Gemfile` | Ruby | Regex for `gem "name"` lines |
| `pom.xml` | Java | Parse XML, extract `<artifactId>` from `<dependencies>` |
| `build.gradle` | Java/Kotlin | Regex for `implementation`, `compile`, `api` directives |

For each parser, the output should be a flat list of lowercase package/crate/gem names without version information.

---

## 11. Testing Strategy

**Unit tests (Phase 1):**
- `test_preprocessor.py`: Test README cleaning with edge cases (empty README, HTML-heavy README, README with only badges). Test dependency extraction for each manifest format.
- `test_embedder.py`: Verify output dimensions (384), verify that similar texts produce higher cosine similarity than dissimilar texts.

**Integration tests (Phase 2-3):**
- `test_indexer.py`: Test the full pipeline against a running Qdrant instance (use Docker in CI).
- `test_api.py`: Test all endpoints using FastAPI's `TestClient`. Mock the GitHub API responses using `httpx` mocking or `respx`.

**Quality validation (Phase 2):**
- Manually verify search results for known-similar repo pairs. For example: `pallets/flask` should return `django/django`, `fastapi/fastapi`; `tokio-rs/tokio` should return `async-std/async-std`; `flutter/flutter` should return `nicklockwood/SwiftFormat` with low purpose similarity but different stack.
- Iterate on preprocessing and text composition until results feel reasonable.

---

## 12. Deployment Recommendations

**Backend:** Deploy on Railway, Fly.io, or Render (all have free tiers suitable for a prototype). Alternatively, a small VPS with Docker Compose.

**Vector DB:** Use Qdrant Cloud's free tier for up to 1 GB of storage, or self-host alongside the backend.

**Frontend:** GitHub Pages (ideal for Developer Program visibility) or Vercel.

**Domain:** Optional but recommended. A `.dev` domain reinforces the developer tooling positioning. GitHub Pages also works with custom domains.
