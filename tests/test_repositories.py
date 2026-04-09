"""Phase 3 repository API tests."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository
from app.models.user import User
from app.services.embedding_service import EmbeddingService
from app.utils.security import create_access_token, encrypt_token


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db: AsyncSession, *, github_id: int, username: str) -> User:
    user = User(
        email=f"{username}@example.com",
        github_id=github_id,
        github_username=username,
        is_active=True,
        github_access_token=encrypt_token("fake-gh-token"),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_repo(db: AsyncSession, owner: User, *, github_repo_id: int, full_name: str) -> Repository:
    repo = Repository(
        owner_id=owner.id,
        github_repo_id=github_repo_id,
        full_name=full_name,
        default_branch="main",
        index_status="pending",
    )
    db.add(repo)
    await db.flush()
    return repo


@pytest.mark.asyncio
async def test_connect_repo_enqueues_celery_task(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /repositories creates the repo and enqueues an index_repository Celery task."""
    user = await _make_user(db_session, github_id=30001, username="repo_user_a")

    with patch("app.api.v1.repositories.index_repository") as mock_task:
        mock_task.delay = AsyncMock()
        response = await client.post(
            "/api/v1/repositories",
            json={
                "github_repo_id": 9900001,
                "full_name": "repo_user_a/myrepo",
                "default_branch": "main",
            },
            headers=_auth_headers(user),
        )

    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "repo_user_a/myrepo"
    assert data["index_status"] == "indexing"
    mock_task.delay.assert_called_once()
    call_args = mock_task.delay.call_args[0]
    assert call_args[1] == "repo_user_a/myrepo"  # full_name
    # encrypted_token is passed as-is (not decrypted here)
    assert call_args[2] == user.github_access_token


@pytest.mark.asyncio
async def test_list_repos_returns_only_current_user_repos(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /repositories returns only repos owned by the authenticated user."""
    user_a = await _make_user(db_session, github_id=30002, username="list_user_a")
    user_b = await _make_user(db_session, github_id=30003, username="list_user_b")

    await _make_repo(db_session, user_a, github_repo_id=9900002, full_name="list_user_a/repo1")
    await _make_repo(db_session, user_b, github_repo_id=9900003, full_name="list_user_b/repo1")

    response = await client.get("/api/v1/repositories", headers=_auth_headers(user_a))

    assert response.status_code == 200
    data = response.json()
    full_names = [r["full_name"] for r in data["items"]]
    assert "list_user_a/repo1" in full_names
    assert "list_user_b/repo1" not in full_names


@pytest.mark.asyncio
async def test_get_repo_detail_returns_correct_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /repositories/{repo_id} returns 200 with index_status present."""
    user = await _make_user(db_session, github_id=30004, username="detail_user_a")
    repo = await _make_repo(db_session, user, github_repo_id=9900004, full_name="detail_user_a/repo")

    response = await client.get(
        f"/api/v1/repositories/{repo.id}", headers=_auth_headers(user)
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(repo.id)
    assert "index_status" in data
    assert data["index_status"] == "pending"


@pytest.mark.asyncio
async def test_get_repo_detail_404_for_other_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /repositories/{repo_id} returns 404 when the repo belongs to another user."""
    user_a = await _make_user(db_session, github_id=30005, username="owner_404_a")
    user_b = await _make_user(db_session, github_id=30006, username="requester_404_b")
    repo_b = await _make_repo(db_session, user_b, github_repo_id=9900005, full_name="owner_404_b/secret")

    response = await client.get(
        f"/api/v1/repositories/{repo_b.id}", headers=_auth_headers(user_a)
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_embedding_dev_mock_returns_correct_dimension() -> None:
    """EmbeddingService in dev mode returns exactly 1024 zero-floats."""
    with patch("app.services.embedding_service.settings") as mock_settings:
        mock_settings.ENVIRONMENT = "development"
        mock_settings.AWS_REGION = "us-east-1"
        service = EmbeddingService.__new__(EmbeddingService)
        service._dev_mode = True

        result = await service.embed_text("hello")

    assert len(result) == 1024
    assert all(v == 0.0 for v in result)
    assert all(isinstance(v, float) for v in result)


@pytest.mark.asyncio
async def test_reindex_enqueues_task(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /repositories/{repo_id}/reindex returns 202 and enqueues Celery task."""
    user = await _make_user(db_session, github_id=30007, username="reindex_user")
    repo = await _make_repo(db_session, user, github_repo_id=9900006, full_name="reindex_user/repo")

    with patch("app.api.v1.repositories.index_repository") as mock_task:
        mock_task.delay = AsyncMock()
        response = await client.post(
            f"/api/v1/repositories/{repo.id}/reindex",
            headers=_auth_headers(user),
        )

    assert response.status_code == 202
    data = response.json()
    assert data["message"] == "Reindex queued"
    assert data["repo_id"] == str(repo.id)
    mock_task.delay.assert_called_once()
