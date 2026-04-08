import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserRead
from app.services import github_service
from app.services.github_service import GitHubAPIError
from app.utils.security import create_access_token, encrypt_token

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


@router.get("/github")
async def github_login() -> RedirectResponse:
    """Redirect the user to GitHub OAuth authorization."""
    params = f"client_id={settings.GITHUB_CLIENT_ID}&scope=repo,read:user,user:email"
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{params}")


@router.get("/github/callback")
async def github_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Exchange GitHub OAuth code, upsert user, issue JWT, redirect to frontend."""
    error_url = f"{settings.FRONTEND_URL}/auth/error?reason=oauth_failed"

    try:
        github_access_token = await github_service.exchange_code_for_token(code)
        github_user = await github_service.get_github_user(github_access_token)
    except GitHubAPIError as exc:
        logger.warning("GitHub OAuth failed", error=str(exc))
        return RedirectResponse(error_url, status_code=302)
    except Exception as exc:
        logger.error("Unexpected error during GitHub OAuth", error=str(exc))
        return RedirectResponse(error_url, status_code=302)

    github_id: int = github_user["id"]
    github_username: str = github_user["login"]
    email: str | None = github_user.get("email")
    avatar_url: str | None = github_user.get("avatar_url")
    encrypted_token = encrypt_token(github_access_token)

    try:
        result = await db.execute(select(User).where(User.github_id == github_id))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=email or f"{github_username}@github.local",
                github_id=github_id,
                github_username=github_username,
                github_access_token=encrypted_token,
                avatar_url=avatar_url,
                is_active=True,
            )
            db.add(user)
        else:
            user.github_username = github_username
            user.github_access_token = encrypted_token
            user.avatar_url = avatar_url
            user.is_active = True

        await db.flush()
    except Exception as exc:
        logger.error("DB upsert failed during GitHub OAuth", error=str(exc))
        return RedirectResponse(error_url, status_code=302)

    jwt = create_access_token(subject=str(user.id))
    logger.info(
        "User authenticated via GitHub",
        user_id=str(user.id),
        github_username=github_username,
    )
    return RedirectResponse(
        f"{settings.FRONTEND_URL}/auth/callback?token={jwt}",
        status_code=302,
    )


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout")
async def logout() -> dict:
    return {"message": "logged out"}
