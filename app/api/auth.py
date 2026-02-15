"""GitHub OAuth flow endpoints."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt

from app.api.dependencies import get_github_client, get_vector_store
from app.config import settings
from app.models.schemas import UserRepoItem, UserReposResponse
from app.services.github_client import GitHubClient
from app.services.vector_store import VectorStore

router = APIRouter(prefix="/api")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
JWT_ALGORITHM = "HS256"

# Server-side token store (maps user_id -> GitHub access token)
_token_store: dict[str, str] = {}


@router.get("/auth/github")
async def github_login():
    """Redirect to GitHub OAuth authorization page."""
    params = {
        "client_id": settings.github_client_id,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return {"redirect_url": f"{GITHUB_AUTHORIZE_URL}?{query}"}


@router.get("/auth/callback")
async def github_callback(code: str):
    """Exchange authorization code for access token and return a JWT."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail=data.get("error_description", "Failed to get access token"),
        )

    # Fetch user info
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch user info")

    user_data = user_resp.json()

    # Store token server-side, keep it out of the JWT
    user_id = str(user_data.get("id"))
    _token_store[user_id] = access_token

    token_payload = {
        "sub": user_id,
        "login": user_data.get("login"),
    }
    token = jwt.encode(token_payload, settings.session_secret, algorithm=JWT_ALGORITHM)

    return {"token": token, "user": {"login": user_data.get("login")}}


def _decode_jwt(request: Request) -> dict:
    """Extract and decode JWT from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = auth[7:]
    try:
        return jwt.decode(token, settings.session_secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/user/repos", response_model=UserReposResponse)
async def user_repos(
    request: Request,
    github: GitHubClient = Depends(get_github_client),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """List authenticated user's repositories with indexed status."""
    claims = _decode_jwt(request)
    access_token = _token_store.get(claims["sub"])
    if not access_token:
        raise HTTPException(status_code=401, detail="Session expired")

    repos = await github.get_user_repos(access_token)

    items: list[UserRepoItem] = []
    for repo in repos:
        indexed = await vector_store.repo_exists(repo.id)
        items.append(
            UserRepoItem(
                full_name=repo.full_name,
                description=repo.description,
                stars=repo.stars,
                indexed=indexed,
            )
        )

    return UserReposResponse(repos=items)
