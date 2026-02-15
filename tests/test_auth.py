"""Tests for GitHub OAuth flow and user repos endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.models.domain import IndexResult
from app.services.vector_store import VectorStore

VECTOR_DIM = 384
FAKE_VECTOR = [0.1] * VECTOR_DIM
SESSION_SECRET = "test-secret"
JWT_ALGORITHM = "HS256"


def _make_jwt(claims: dict) -> str:
    return jwt.encode(claims, SESSION_SECRET, algorithm=JWT_ALGORITHM)


class _FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Async context-manager returning pre-configured responses."""

    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, *args, **kwargs):
        return self._response

    async def get(self, *args, **kwargs):
        return self._response


@pytest.fixture
def app():
    from app.main import app as fastapi_app

    mock_github = AsyncMock()
    mock_github.rate_limit_remaining = 4999

    mock_vector_store = AsyncMock(spec=VectorStore)
    mock_vector_store.get_collection_stats = AsyncMock(return_value={"points_count": 10})
    mock_vector_store.repo_exists = AsyncMock(return_value=False)

    mock_pipeline = AsyncMock()
    mock_pipeline.index_single_repo = AsyncMock(
        return_value=IndexResult(status="indexed", repo_id=1, full_name="o/r")
    )

    fastapi_app.state.github_client = mock_github
    fastapi_app.state.vector_store = mock_vector_store
    fastapi_app.state.pipeline = mock_pipeline

    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# --- /api/auth/github ---


@patch("app.api.auth.settings")
def test_github_login_returns_redirect_url(mock_settings, client):
    mock_settings.github_client_id = "test-client-id"
    resp = client.get("/api/auth/github")
    assert resp.status_code == 200
    data = resp.json()
    assert "redirect_url" in data
    assert "test-client-id" in data["redirect_url"]
    assert "read:user" in data["redirect_url"]


# --- /api/auth/callback ---


@patch("app.api.auth.settings")
@patch("app.api.auth.httpx.AsyncClient")
def test_github_callback_success(mock_async_client, mock_settings, client):
    mock_settings.github_client_id = "cid"
    mock_settings.github_client_secret = "csecret"
    mock_settings.session_secret = SESSION_SECRET

    token_resp = _FakeResponse(200, {"access_token": "gho_testtoken"})
    user_resp = _FakeResponse(200, {"id": 42, "login": "testuser"})

    mock_async_client.side_effect = [
        _FakeAsyncClient(token_resp),
        _FakeAsyncClient(user_resp),
    ]

    resp = client.get("/api/auth/callback?code=abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["login"] == "testuser"

    # Verify JWT claims — access_token must NOT be in the JWT
    claims = jwt.decode(data["token"], SESSION_SECRET, algorithms=[JWT_ALGORITHM])
    assert claims["sub"] == "42"
    assert claims["login"] == "testuser"
    assert "access_token" not in claims


@patch("app.api.auth.settings")
@patch("app.api.auth.httpx.AsyncClient")
def test_github_callback_token_exchange_non_200(mock_async_client, mock_settings, client):
    mock_settings.github_client_id = "cid"
    mock_settings.github_client_secret = "csecret"

    mock_async_client.return_value = _FakeAsyncClient(_FakeResponse(500, {"error": "server_error"}))

    resp = client.get("/api/auth/callback?code=bad")
    assert resp.status_code == 502
    assert "token exchange failed" in resp.json()["detail"]


@patch("app.api.auth.settings")
@patch("app.api.auth.httpx.AsyncClient")
def test_github_callback_no_access_token(mock_async_client, mock_settings, client):
    mock_settings.github_client_id = "cid"
    mock_settings.github_client_secret = "csecret"

    mock_async_client.return_value = _FakeAsyncClient(
        _FakeResponse(200, {"error": "bad_verification_code", "error_description": "Bad code"})
    )

    resp = client.get("/api/auth/callback?code=expired")
    assert resp.status_code == 400
    assert "Bad code" in resp.json()["detail"]


@patch("app.api.auth.settings")
@patch("app.api.auth.httpx.AsyncClient")
def test_github_callback_user_info_fails(mock_async_client, mock_settings, client):
    mock_settings.github_client_id = "cid"
    mock_settings.github_client_secret = "csecret"

    token_resp = _FakeResponse(200, {"access_token": "gho_ok"})
    user_resp = _FakeResponse(403, {"message": "forbidden"})

    mock_async_client.side_effect = [
        _FakeAsyncClient(token_resp),
        _FakeAsyncClient(user_resp),
    ]

    resp = client.get("/api/auth/callback?code=abc123")
    assert resp.status_code == 502
    assert "user info" in resp.json()["detail"].lower()


# --- /api/user/repos ---


@patch("app.api.auth._token_store", {"42": "gho_tok"})
@patch("app.api.auth.settings")
def test_user_repos_success(mock_settings, client, app):
    mock_settings.session_secret = SESSION_SECRET
    token = _make_jwt({"sub": "42", "login": "testuser"})

    app.state.github_client.get_user_repos = AsyncMock(
        return_value=[
            MagicMock(id=1, full_name="testuser/repo1", description="Desc", stars=10),
        ]
    )

    resp = client.get("/api/user/repos", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["repos"]) == 1
    assert data["repos"][0]["full_name"] == "testuser/repo1"


def test_user_repos_missing_auth_header(client):
    resp = client.get("/api/user/repos")
    assert resp.status_code == 401
    assert "Missing" in resp.json()["detail"]


@patch("app.api.auth.settings")
def test_user_repos_invalid_jwt(mock_settings, client):
    mock_settings.session_secret = SESSION_SECRET
    resp = client.get("/api/user/repos", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401
    assert "Invalid token" in resp.json()["detail"]


@patch("app.api.auth._token_store", {})
@patch("app.api.auth.settings")
def test_user_repos_session_expired(mock_settings, client):
    mock_settings.session_secret = SESSION_SECRET
    token = _make_jwt({"sub": "42", "login": "testuser"})
    resp = client.get("/api/user/repos", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "Session expired" in resp.json()["detail"]
