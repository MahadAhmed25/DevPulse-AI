import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(UTC)}
    return str(jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM))


def decode_access_token(token: str) -> str:
    """Decode token and return the subject (user ID). Raises JWTError on failure."""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    subject: str | None = payload.get("sub")
    if subject is None:
        raise JWTError("Token missing subject")
    return subject


def encrypt_token(token: str) -> str:
    """Fernet-encrypt a plaintext token for storage in the database."""
    f = Fernet(settings.FERNET_KEY.encode())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted token retrieved from the database."""
    f = Fernet(settings.FERNET_KEY.encode())
    return f.decrypt(encrypted.encode()).decode()


def verify_github_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verify GitHub's X-Hub-Signature-256 HMAC header."""
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)
