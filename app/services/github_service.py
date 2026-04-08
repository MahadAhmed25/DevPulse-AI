import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

BASE_URL = "https://api.github.com"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubAPIError(Exception):
    """Raised on 4xx/5xx responses from the GitHub API."""


class GitHubRateLimitError(GitHubAPIError):
    """Raised when GitHub returns 403 with X-RateLimit-Remaining: 0."""


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        raise GitHubRateLimitError(
            f"GitHub rate limit exceeded: {response.text}"
        )
    if response.is_error:
        raise GitHubAPIError(
            f"GitHub API error {response.status_code}: {response.text}"
        )


async def exchange_code_for_token(code: str) -> str:
    """Exchange a GitHub OAuth code for an access token string."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
    _raise_for_status(response)
    data = response.json()
    token: str | None = data.get("access_token")
    if not token:
        raise GitHubAPIError(f"No access_token in response: {data}")
    logger.info("Exchanged OAuth code for GitHub access token")
    return token


async def get_github_user(access_token: str) -> dict:
    """Return the authenticated user's GitHub profile as a dict."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BASE_URL}/user", headers=_headers(access_token))
    _raise_for_status(response)
    data: dict = response.json()
    logger.info("Fetched GitHub user profile", login=data.get("login"))
    return data


async def list_user_repos(access_token: str) -> list[dict]:
    """Return repos owned by the authenticated user (up to 100)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/user/repos",
            headers=_headers(access_token),
            params={"type": "owner", "per_page": 100},
        )
    _raise_for_status(response)
    repos: list[dict] = response.json()
    result = [
        {
            "github_repo_id": r["id"],
            "full_name": r["full_name"],
            "default_branch": r["default_branch"],
            "private": r["private"],
        }
        for r in repos
    ]
    logger.info("Listed user repos", count=len(result))
    return result


async def get_pr_diff(access_token: str, full_name: str, pr_number: int) -> str:
    """Return the raw unified diff for a pull request."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/repos/{full_name}/pulls/{pr_number}",
            headers=headers,
        )
    _raise_for_status(response)
    logger.info("Fetched PR diff", repo=full_name, pr_number=pr_number)
    return response.text


async def get_repo_contents(
    access_token: str, full_name: str, path: str = ""
) -> list[dict]:
    """Return the contents of a repository path."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/repos/{full_name}/contents/{path}",
            headers=_headers(access_token),
        )
    _raise_for_status(response)
    contents: list[dict] = response.json()
    logger.info("Fetched repo contents", repo=full_name, path=path)
    return contents


async def post_pr_review(
    access_token: str,
    full_name: str,
    pr_number: int,
    body: str,
    comments: list[dict],
) -> int:
    """Post an inline review to a PR. Returns the GitHub review ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/repos/{full_name}/pulls/{pr_number}/reviews",
            headers=_headers(access_token),
            json={"body": body, "event": "COMMENT", "comments": comments},
        )
    _raise_for_status(response)
    review_id: int = response.json()["id"]
    logger.info("Posted PR review", repo=full_name, pr_number=pr_number, review_id=review_id)
    return review_id


async def create_webhook(
    access_token: str, full_name: str, webhook_url: str, secret: str
) -> int:
    """Register a pull_request webhook on the repo. Returns the hook ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/repos/{full_name}/hooks",
            headers=_headers(access_token),
            json={
                "name": "web",
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": secret,
                },
                "events": ["pull_request"],
                "active": True,
            },
        )
    _raise_for_status(response)
    hook_id: int = response.json()["id"]
    logger.info("Created webhook", repo=full_name, hook_id=hook_id)
    return hook_id


async def delete_webhook(access_token: str, full_name: str, hook_id: int) -> None:
    """Delete a webhook from the repo."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(
            f"{BASE_URL}/repos/{full_name}/hooks/{hook_id}",
            headers=_headers(access_token),
        )
    _raise_for_status(response)
    logger.info("Deleted webhook", repo=full_name, hook_id=hook_id)
