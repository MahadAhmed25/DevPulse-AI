import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserRead
from app.utils.security import create_access_token

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/github")
async def github_login() -> RedirectResponse:
    """Redirect the user to GitHub OAuth authorization."""
    params = f"client_id={settings.GITHUB_CLIENT_ID}&scope=repo,read:user,user:email"
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{params}")


@router.get("/github/callback")
async def github_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Exchange GitHub OAuth code for an access token, upsert user, return JWT."""
    async with httpx.AsyncClient() as client:
        # Exchange code for GitHub access token
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_response.json()

    github_token = token_data.get("access_token")
    if not github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to obtain GitHub access token",
        )

    # Fetch GitHub user profile
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {github_token}"},
        )
        github_user = user_response.json()

    github_id: int = github_user["id"]
    github_username: str = github_user["login"]
    email: str = github_user.get("email") or f"{github_username}@github.local"

    # Upsert user
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            github_id=github_id,
            github_username=github_username,
            github_access_token=github_token,
        )
        db.add(user)
    else:
        user.github_access_token = github_token
        user.github_username = github_username

    await db.flush()

    access_token = create_access_token(subject=str(user.id))
    logger.info("User authenticated via GitHub", user_id=str(user.id), github_username=github_username)

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
async def get_me(db: AsyncSession = Depends(get_db)) -> User:
    """Return the current authenticated user (placeholder — deps.py wires auth)."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Use auth dependency")
