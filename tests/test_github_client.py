"""Tests for the GitHub API client.

All HTTP interactions are mocked via ``respx``.  The test suite uses
``asyncio_mode = "auto"`` (configured in ``pyproject.toml``) so every
``async def test_*`` function is collected automatically by pytest-asyncio.
"""

import base64

import httpx
import pytest
import respx

from app.models.domain import RepoMetadata
from app.services.github_client import GitHubClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_TOKEN = "ghp_test_token_1234567890"


@pytest.fixture
async def client():
    """Create a GitHubClient and ensure it is closed after each test."""
    gh = GitHubClient(token=FAKE_TOKEN)
    yield gh
    await gh.close()


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

REPO_JSON = {
    "id": 12345,
    "full_name": "owner/repo",
    "html_url": "https://github.com/owner/repo",
    "description": "A test repository",
    "topics": ["python", "testing"],
    "language": "Python",
    "stargazers_count": 100,
    "forks_count": 10,
    "updated_at": "2025-06-01T12:00:00Z",
}

SEARCH_JSON = {
    "total_count": 1,
    "incomplete_results": False,
    "items": [REPO_JSON],
}

README_CONTENT = "# Hello World\n\nThis is a test README."
README_B64 = base64.b64encode(README_CONTENT.encode()).decode()

README_JSON = {
    "name": "README.md",
    "content": README_B64,
    "encoding": "base64",
}

LANGUAGES_JSON = {"Python": 8000, "Shell": 1500, "Dockerfile": 500}

MANIFEST_CONTENT = "flask>=2.0\nrequests\n"
MANIFEST_B64 = base64.b64encode(MANIFEST_CONTENT.encode()).decode()

MANIFEST_JSON = {
    "name": "requirements.txt",
    "content": MANIFEST_B64,
    "encoding": "base64",
}

USER_REPOS_JSON = [REPO_JSON]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_repo_metadata(client: GitHubClient):
    """fetch_repo_metadata should return a correctly populated RepoMetadata."""
    respx.get("https://api.github.com/repos/owner/repo").mock(
        return_value=httpx.Response(200, json=REPO_JSON)
    )

    meta = await client.fetch_repo_metadata("owner", "repo")

    assert isinstance(meta, RepoMetadata)
    assert meta.id == 12345
    assert meta.full_name == "owner/repo"
    assert meta.url == "https://github.com/owner/repo"
    assert meta.description == "A test repository"
    assert meta.topics == ["python", "testing"]
    assert meta.language_primary == "Python"
    assert meta.stars == 100
    assert meta.forks == 10


@respx.mock
async def test_fetch_readme_decodes_base64(client: GitHubClient):
    """fetch_readme should base64-decode the content field."""
    respx.get("https://api.github.com/repos/owner/repo/readme").mock(
        return_value=httpx.Response(200, json=README_JSON)
    )

    readme = await client.fetch_readme("owner", "repo")

    assert readme == README_CONTENT


@respx.mock
async def test_fetch_readme_returns_none_on_404(client: GitHubClient):
    """fetch_readme should return None when the repo has no README."""
    respx.get("https://api.github.com/repos/owner/repo/readme").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    readme = await client.fetch_readme("owner", "repo")

    assert readme is None


@respx.mock
async def test_fetch_languages_normalises_to_percentages(client: GitHubClient):
    """fetch_languages should convert byte counts to percentages summing to 100."""
    respx.get("https://api.github.com/repos/owner/repo/languages").mock(
        return_value=httpx.Response(200, json=LANGUAGES_JSON)
    )

    langs = await client.fetch_languages("owner", "repo")

    assert langs["Python"] == 80.0
    assert langs["Shell"] == 15.0
    assert langs["Dockerfile"] == 5.0
    assert sum(langs.values()) == pytest.approx(100.0)


@respx.mock
async def test_fetch_languages_empty_repo(client: GitHubClient):
    """fetch_languages should return an empty dict for repos with no code."""
    respx.get("https://api.github.com/repos/owner/repo/languages").mock(
        return_value=httpx.Response(200, json={})
    )

    langs = await client.fetch_languages("owner", "repo")

    assert langs == {}


@respx.mock
async def test_fetch_manifest_files_returns_existing_only(client: GitHubClient):
    """fetch_manifest_files should return tuples only for files that exist (not 404)."""
    # requirements.txt exists
    respx.get("https://api.github.com/repos/owner/repo/contents/requirements.txt").mock(
        return_value=httpx.Response(200, json=MANIFEST_JSON)
    )

    # All other manifest files return 404
    for filename in (
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "pubspec.yaml",
        "go.mod",
        "Gemfile",
        "pom.xml",
        "build.gradle",
    ):
        respx.get(f"https://api.github.com/repos/owner/repo/contents/{filename}").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )

    manifests = await client.fetch_manifest_files("owner", "repo")

    assert len(manifests) == 1
    filename, content = manifests[0]
    assert filename == "requirements.txt"
    assert content == MANIFEST_CONTENT


@respx.mock
async def test_search_repositories(client: GitHubClient):
    """search_repositories should return a list of RepoMetadata from search results."""
    respx.get("https://api.github.com/search/repositories").mock(
        return_value=httpx.Response(200, json=SEARCH_JSON)
    )

    results = await client.search_repositories("stars:>100", sort="stars", per_page=10)

    assert len(results) == 1
    assert isinstance(results[0], RepoMetadata)
    assert results[0].full_name == "owner/repo"
    assert results[0].stars == 100


@respx.mock
async def test_rate_limit_tracking(client: GitHubClient):
    """The client should parse and store X-RateLimit-* headers from responses."""
    respx.get("https://api.github.com/repos/owner/repo").mock(
        return_value=httpx.Response(
            200,
            json=REPO_JSON,
            headers={
                "X-RateLimit-Remaining": "4200",
                "X-RateLimit-Reset": "1700000000",
            },
        )
    )

    await client.fetch_repo_metadata("owner", "repo")

    assert client.rate_limit_remaining == 4200
    assert client.rate_limit_reset == 1700000000.0


@respx.mock
async def test_rate_limit_updates_across_calls(client: GitHubClient):
    """Rate-limit counters should update with every response."""
    respx.get("https://api.github.com/repos/owner/repo").mock(
        return_value=httpx.Response(
            200,
            json=REPO_JSON,
            headers={"X-RateLimit-Remaining": "500", "X-RateLimit-Reset": "1700000000"},
        )
    )
    respx.get("https://api.github.com/repos/owner/repo/readme").mock(
        return_value=httpx.Response(
            200,
            json=README_JSON,
            headers={"X-RateLimit-Remaining": "499", "X-RateLimit-Reset": "1700000000"},
        )
    )

    await client.fetch_repo_metadata("owner", "repo")
    assert client.rate_limit_remaining == 500

    await client.fetch_readme("owner", "repo")
    assert client.rate_limit_remaining == 499


@respx.mock
async def test_get_user_repos(client: GitHubClient):
    """get_user_repos should use the provided user token, not the app token."""
    user_token = "ghp_user_oauth_token"

    route = respx.get("https://api.github.com/user/repos").mock(
        return_value=httpx.Response(200, json=USER_REPOS_JSON)
    )

    repos = await client.get_user_repos(user_token)

    assert len(repos) == 1
    assert repos[0].full_name == "owner/repo"

    # Verify the request used the user token, not the app token
    sent_request = route.calls.last.request
    assert f"Bearer {user_token}" in sent_request.headers["authorization"]


@respx.mock
async def test_non_2xx_raises(client: GitHubClient):
    """Non-2xx responses (other than allowed 404s) should raise HTTPStatusError."""
    respx.get("https://api.github.com/repos/owner/repo").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client.fetch_repo_metadata("owner", "repo")

    assert exc_info.value.response.status_code == 403
