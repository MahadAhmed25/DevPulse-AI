import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient


def _sign_payload(payload: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


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
