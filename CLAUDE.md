# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**RepoRadar** — a web service for discovering similar GitHub repositories using dual-vector semantic search. Users submit a repo URL and get ranked similar projects based on purpose and tech stack similarity.

The full architecture spec lives in `PLAN.md`. No source code exists yet; the project is greenfield.

## Architecture

```
Frontend (React/Next.js SPA)
  → REST API →
Backend (FastAPI / Python 3.11+)
  ├── GitHub API Client (httpx) — fetches repo metadata, README, languages, dependencies
  ├── Text Preprocessor — cleans README, composes embedding inputs
  ├── Embedding Service (sentence-transformers/all-MiniLM-L6-v2, 384d)
  └── Vector Store (Qdrant) — single collection with named vectors ("purpose" + "stack")
```

**Dual-vector search**: each repo gets two embeddings — "purpose" (what it does: description + topics + README) and "stack" (what it's built with: languages + dependencies). Final similarity = weighted sum (default 0.7 purpose / 0.3 stack). Qdrant doesn't support weighted multi-vector queries natively, so the app does two separate searches and merges/re-ranks in application code.

## Planned Commands

```bash
# Dependencies
pip install -e ".[dev]"

# Run backend
uvicorn app.main:app --reload

# Run Qdrant
docker compose up -d qdrant

# Tests
pytest
pytest tests/test_preprocessor.py::test_clean_readme  # single test

# Lint & format
ruff check .
ruff format .

# Seed initial repos
python scripts/seed_initial.py
```

## Key Conventions

- **Async everywhere**: all I/O (GitHub API, Qdrant, embeddings) uses async/await
- **Pydantic models**: request/response validation via schemas, config via pydantic-settings
- **FastAPI dependency injection**: shared services injected via `dependencies.py`
- **Idempotent indexing**: repos indexed within 7 days are skipped
- **Rate limiting**: GitHub API capped at ~4,000 req/hour for batch, leaving headroom for user requests

## Implementation Phases

Follow the 5-phase order in `PLAN.md`: Core Pipeline → Search → API & Auth → Frontend → Scale & Polish. Each phase produces a testable increment.
