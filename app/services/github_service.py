import structlog
from github import Github
from github.Repository import Repository as GithubRepo

logger = structlog.get_logger(__name__)


class GitHubService:
    def __init__(self, access_token: str) -> None:
        self._client = Github(access_token)

    def get_repo(self, full_name: str) -> GithubRepo:
        return self._client.get_repo(full_name)

    def get_pull_request_diff(self, full_name: str, pr_number: int) -> str:
        """Return the unified diff for a pull request."""
        import httpx

        repo = self.get_repo(full_name)
        pr = repo.get_pull(pr_number)
        # PyGithub doesn't expose the raw diff directly; use the compare API
        response = httpx.get(
            pr.diff_url,
            headers={
                "Accept": "application/vnd.github.v3.diff",
                "Authorization": f"Bearer {self._client.get_user().login}",
            },
        )
        response.raise_for_status()
        return response.text

    def post_review_comments(
        self,
        full_name: str,
        pr_number: int,
        comments: list[dict],
        summary: str,
    ) -> int:
        """Post inline review comments and a summary review body to a PR.

        Each comment dict must have: path, line, body.
        Returns the GitHub review ID.
        """
        repo = self.get_repo(full_name)
        pr = repo.get_pull(pr_number)
        head_sha = pr.head.sha

        # GitHub requires at least one comment or a body for create_review
        review = pr.create_review(
            body=summary,
            event="COMMENT",
            comments=[
                {
                    "path": c["path"],
                    "line": c["line"],
                    "body": c["body"],
                    "side": "RIGHT",
                }
                for c in comments
            ],
            commit=repo.get_commit(head_sha),
        )
        logger.info(
            "Review posted to GitHub",
            repo=full_name,
            pr_number=pr_number,
            review_id=review.id,
        )
        return review.id

    def install_webhook(self, full_name: str, webhook_url: str, secret: str) -> int:
        """Register a pull_request webhook on the repo. Returns the webhook ID."""
        repo = self.get_repo(full_name)
        hook = repo.create_hook(
            name="web",
            config={"url": webhook_url, "content_type": "json", "secret": secret},
            events=["pull_request"],
            active=True,
        )
        return hook.id

    def list_user_repos(self) -> list[dict]:
        """Return a list of repos the authenticated user has access to."""
        user = self._client.get_user()
        return [
            {
                "github_repo_id": repo.id,
                "full_name": repo.full_name,
                "default_branch": repo.default_branch,
                "private": repo.private,
            }
            for repo in user.get_repos(type="owner")
        ]
