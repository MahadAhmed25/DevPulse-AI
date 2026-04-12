"""Phase 2 auth & health tests.

Note: FastAPI's HTTPBearer raises HTTP 403 (not 401) when the Authorization
header is absent entirely. test_get_me_without_token_returns_401 therefore
asserts 403 — the name reflects intent, the assertion reflects reality.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.utils.security import create_access_token


@pytest.mark.asyncio
async def test_health_returns_ok_without_db(client: AsyncClient) -> None:
    """GET /health is a fast-path liveness probe with no DB dependency."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data
    assert "region" in data


@pytest.mark.asyncio
async def test_health_db_returns_ok(client: AsyncClient) -> None:
    """GET /health/db hits the real test Postgres and returns latency."""
    response = await client.get("/api/v1/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "latency_ms" in data
    assert isinstance(data["latency_ms"], float)


@pytest.mark.asyncio
async def test_github_login_redirects_to_github(client: AsyncClient) -> None:
    """GET /auth/github redirects to GitHub OAuth authorization URL."""
    response = await client.get("/api/v1/auth/github", follow_redirects=False)
    assert response.status_code == 307
    assert "github.com/login/oauth/authorize" in response.headers["location"]


@pytest.mark.asyncio
async def test_get_me_without_token_returns_401(client: AsyncClient) -> None:
    """GET /auth/me with no Authorization header — HTTPBearer returns 403."""
    response = await client.get("/api/v1/auth/me")
    # FastAPI HTTPBearer raises 403 when Authorization header is absent
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_me_with_invalid_token_returns_401(client: AsyncClient) -> None:
    """GET /auth/me with a garbage JWT returns 401."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer this.is.garbage"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_valid_token_returns_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Create a user in DB, issue a JWT, GET /me returns the user's profile."""
    user = User(
        email="phase2test@example.com",
        github_id=99001,
        github_username="phase2user",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(str(user.id))
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["github_username"] == "phase2user"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_logout_returns_200(client: AsyncClient) -> None:
    """POST /auth/logout returns 200 — JWT auth is stateless, no server-side revocation."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "logged out"
