"""GitHub API client for fetching repository data.

Handles authentication, rate limiting, and provides typed methods
for all GitHub API interactions needed by the indexing pipeline.
"""

import asyncio
import base64
import logging
import time

import httpx

from app.models.domain import RepoMetadata

logger = logging.getLogger(__name__)

MANIFEST_FILES = (
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "pubspec.yaml",
    "go.mod",
    "Gemfile",
    "pom.xml",
    "build.gradle",
)


def _parse_repo_json(data: dict) -> RepoMetadata:
    """Map a GitHub API repository JSON object to a RepoMetadata model."""
    return RepoMetadata(
        id=data["id"],
        full_name=data["full_name"],
        url=data["html_url"],
        description=data.get("description"),
        topics=data.get("topics", []),
        language_primary=data.get("language"),
        stars=data.get("stargazers_count", 0),
        forks=data.get("forks_count", 0),
        last_updated=data.get("updated_at"),
    )


class GitHubClient:
    """Async GitHub API client with rate-limit awareness.

    Parameters
    ----------
    token:
        A GitHub personal access token or GitHub App installation token
        used for authenticating all requests made by this client.
    """

    def __init__(self, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: float | None = None

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_rate_limit(self, response: httpx.Response) -> None:
        """Extract rate-limit headers and store them on the instance."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)
        if reset is not None:
            self.rate_limit_reset = float(reset)

    async def _wait_for_rate_limit(self) -> None:
        """Sleep until the rate-limit window resets when remaining < 10."""
        if (
            self.rate_limit_remaining is not None
            and self.rate_limit_remaining < 10
            and self.rate_limit_reset is not None
        ):
            sleep_seconds = max(self.rate_limit_reset - time.time(), 0) + 1
            logger.warning(
                "Rate limit nearly exhausted (remaining=%d). Sleeping %.1f s until reset.",
                self.rate_limit_remaining,
                sleep_seconds,
            )
            await asyncio.sleep(sleep_seconds)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        client: httpx.AsyncClient | None = None,
        allow_404: bool = False,
        **kwargs,
    ) -> httpx.Response | None:
        """Send a request through *client* (defaults to the app-token client).

        Before every call the method checks whether the rate-limit budget is
        nearly exhausted and, if so, waits until the reset window.

        Parameters
        ----------
        method:
            HTTP method (``"GET"``, ``"POST"``, etc.).
        url:
            Path relative to ``base_url`` (e.g. ``"/repos/owner/repo"``).
        client:
            Optional alternative ``httpx.AsyncClient``.  When *None* the
            instance's default client (authenticated with the app token) is
            used.
        allow_404:
            When *True*, a 404 response returns ``None`` instead of raising.
        **kwargs:
            Forwarded to ``client.request``.

        Returns
        -------
        httpx.Response | None
            The response object, or ``None`` when *allow_404* is set and the
            server returned 404.

        Raises
        ------
        httpx.HTTPStatusError
            For any non-2xx response (unless 404 is explicitly allowed).
        """
        await self._wait_for_rate_limit()

        http_client = client or self._client
        response = await http_client.request(method, url, **kwargs)

        self._update_rate_limit(response)

        if allow_404 and response.status_code == 404:
            return None

        response.raise_for_status()
        return response

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_repo_metadata(self, owner: str, repo: str) -> RepoMetadata:
        """Fetch core metadata for a single repository.

        Calls ``GET /repos/{owner}/{repo}`` and maps the response to a
        :class:`RepoMetadata` instance.
        """
        response = await self._request("GET", f"/repos/{owner}/{repo}")
        return _parse_repo_json(response.json())

    async def fetch_readme(self, owner: str, repo: str) -> str | None:
        """Fetch and base64-decode the default README for a repository.

        Returns ``None`` when the repository has no README (404).
        """
        response = await self._request("GET", f"/repos/{owner}/{repo}/readme", allow_404=True)
        if response is None:
            return None

        content_b64 = response.json()["content"]
        return base64.b64decode(content_b64).decode("utf-8")

    async def fetch_languages(self, owner: str, repo: str) -> dict[str, float]:
        """Fetch language breakdown and normalise byte counts to percentages.

        Returns a dict mapping language names to their share (0-100).
        """
        response = await self._request("GET", f"/repos/{owner}/{repo}/languages")
        raw: dict[str, int] = response.json()

        total = sum(raw.values())
        if total == 0:
            return {}

        return {lang: round(bytes_count / total * 100, 1) for lang, bytes_count in raw.items()}

    async def fetch_manifest_files(self, owner: str, repo: str) -> list[tuple[str, str]]:
        """Fetch known dependency-manifest files from the repo root.

        Attempts to download each of the 9 well-known manifest file names in
        parallel.  Returns a list of ``(filename, decoded_content)`` tuples for
        every file that exists (404s are silently skipped).
        """

        async def _fetch_one(filename: str) -> tuple[str, str] | None:
            response = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{filename}",
                allow_404=True,
            )
            if response is None:
                return None
            content_b64 = response.json()["content"]
            decoded = base64.b64decode(content_b64).decode("utf-8")
            return (filename, decoded)

        results = await asyncio.gather(*[_fetch_one(f) for f in MANIFEST_FILES])
        return [r for r in results if r is not None]

    async def search_repositories(
        self,
        query: str,
        sort: str = "stars",
        per_page: int = 30,
    ) -> list[RepoMetadata]:
        """Search GitHub repositories.

        Wraps ``GET /search/repositories`` and returns a list of
        :class:`RepoMetadata` instances.
        """
        response = await self._request(
            "GET",
            "/search/repositories",
            params={"q": query, "sort": sort, "per_page": per_page},
        )
        items = response.json().get("items", [])
        return [_parse_repo_json(item) for item in items]

    async def get_user_repos(self, access_token: str) -> list[RepoMetadata]:
        """List repositories for the authenticated *user*.

        This creates a **separate** one-shot request using the caller-supplied
        OAuth ``access_token`` rather than the application token so that the
        response reflects the user's own visibility and permissions.
        """
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        ) as user_client:
            response = await self._request(
                "GET",
                "/user/repos",
                client=user_client,
                params={"per_page": 100, "sort": "updated"},
            )
        items = response.json()
        return [_parse_repo_json(item) for item in items]
