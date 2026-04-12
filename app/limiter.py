from fastapi import Request
from jose import JWTError
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.utils.security import decode_access_token


def _user_key_func(request: Request) -> str:
    """Rate-limit key: JWT subject (user ID) if present, else remote IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            return decode_access_token(auth[7:])
        except JWTError:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=get_remote_address)
