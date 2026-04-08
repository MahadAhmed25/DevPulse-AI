import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.asyncio
async def test_github_login_redirects(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/github", follow_redirects=False)
    assert response.status_code == 307
    assert "github.com/login/oauth/authorize" in response.headers["location"]


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
