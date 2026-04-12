import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository
from app.models.user import User


def _sign_payload(payload: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


async def _make_user(db: AsyncSession, *, github_id: int, username: str) -> User:
    user = User(
        email=f"{username}@example.com",
        github_id=github_id,
        github_username=username,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_repo(db: AsyncSession, owner: User, *, github_repo_id: int) -> Repository:
    repo = Repository(
        owner_id=owner.id,
        github_repo_id=github_repo_id,
        full_name="testowner/testrepo",
        default_branch="main",
        index_status="complete",
    )
    db.add(repo)
    await db.flush()
    return repo


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(client: AsyncClient) -> None:
    payload = json.dumps({"action": "opened"}).encode()
    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": "sha256=invalidsig",
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_ignores_non_pr_events(client: AsyncClient) -> None:
    from app.config import get_settings

    settings = get_settings()

    payload = json.dumps({"action": "opened"}).encode()
    sig = _sign_payload(payload, settings.GITHUB_WEBHOOK_SECRET)

    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "push",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_ping_returns_pong(client: AsyncClient) -> None:
    from app.config import get_settings

    settings = get_settings()

    payload = json.dumps({"zen": "Keep it logically awesome."}).encode()
    sig = _sign_payload(payload, settings.GITHUB_WEBHOOK_SECRET)

    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "ping",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}


@pytest.mark.asyncio
async def test_webhook_valid_pr_event_queues_task(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.config import get_settings

    settings = get_settings()

    user = await _make_user(db_session, github_id=50001, username="wh_pr_user")
    repo = await _make_repo(db_session, user, github_repo_id=88001)

    payload = json.dumps(
        {
            "action": "opened",
            "repository": {"id": repo.github_repo_id},
            "pull_request": {
                "number": 42,
                "title": "Add feature X",
                "user": {"login": "wh_pr_user"},
                "base": {"ref": "main"},
                "head": {"ref": "feature/x"},
            },
        }
    ).encode()
    sig = _sign_payload(payload, settings.GITHUB_WEBHOOK_SECRET)

    with patch("app.api.v1.webhooks.run_pr_review") as mock_task:
        mock_task.delay = MagicMock()
        response = await client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    mock_task.delay.assert_called_once()
    pr_id_arg = mock_task.delay.call_args[0][0]
    uuid.UUID(pr_id_arg)  # raises ValueError if not a valid UUID string


@pytest.mark.asyncio
async def test_webhook_unregistered_repo_returns_200(client: AsyncClient) -> None:
    from app.config import get_settings

    settings = get_settings()

    payload = json.dumps(
        {
            "action": "opened",
            "repository": {"id": 99999999},
            "pull_request": {
                "number": 1,
                "title": "Test PR",
                "user": {"login": "testuser"},
                "base": {"ref": "main"},
                "head": {"ref": "feature/test"},
            },
        }
    ).encode()
    sig = _sign_payload(payload, settings.GITHUB_WEBHOOK_SECRET)

    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    assert "ignored" in response.text
