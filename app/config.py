from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # AWS
    # -------------------------------------------------------------------------
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str
    BEDROCK_EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    DATABASE_URL: PostgresDsn

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    REDIS_URL: RedisDsn

    # -------------------------------------------------------------------------
    # Anthropic
    # -------------------------------------------------------------------------
    ANTHROPIC_API_KEY: str

    # -------------------------------------------------------------------------
    # GitHub
    # -------------------------------------------------------------------------
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_WEBHOOK_SECRET: str

    # -------------------------------------------------------------------------
    # Auth (JWT + Fernet)
    # -------------------------------------------------------------------------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 10080  # 7 days
    # 32-byte URL-safe base64-encoded key — generate with: Fernet.generate_key().decode()
    FERNET_KEY: str

    # -------------------------------------------------------------------------
    # Stripe
    # -------------------------------------------------------------------------
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    STRIPE_PRICE_PRO: str
    STRIPE_PRICE_TEAM: str

    # -------------------------------------------------------------------------
    # CloudWatch
    # -------------------------------------------------------------------------
    CLOUDWATCH_LOG_GROUP: str = "/devpulse/api"

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    FRONTEND_URL: str = "http://localhost:3000"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # -------------------------------------------------------------------------
    # Derived helpers
    # -------------------------------------------------------------------------
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        # Ensure the driver is asyncpg for async SQLAlchemy
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def database_url_str(self) -> str:
        return str(self.DATABASE_URL)

    @property
    def redis_url_str(self) -> str:
        return str(self.REDIS_URL)


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Call this everywhere via dependency injection."""
    return Settings()  # type: ignore[call-arg]
