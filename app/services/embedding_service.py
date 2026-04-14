import asyncio
import json
import logging

import boto3
import structlog
from botocore.exceptions import ClientError
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()
EMBEDDING_DIM = 1024
MODEL_ID = settings.BEDROCK_EMBEDDING_MODEL_ID


class EmbeddingService:
    """Generate embeddings via Amazon Bedrock Titan Embeddings V2."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
        )
        self._dev_mode = settings.ENVIRONMENT == "development"

    @retry(
        wait=wait_exponential(min=1, max=16),
        stop=stop_after_attempt(4),
        retry=lambda retry_state: (
            isinstance(retry_state.outcome.exception(), ClientError)
            and retry_state.outcome.exception().response["Error"]["Code"] == "ThrottlingException"
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_text(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string."""
        if self._dev_mode:
            return [0.0] * EMBEDDING_DIM

        body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})

        response = await asyncio.to_thread(
            self._client.invoke_model,
            modelId=MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        embedding: list[float] = result["embedding"]
        return embedding

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts sequentially with a delay to stay under Bedrock RPM limits."""
        results = []
        for text in texts:
            results.append(await self.embed_text(text))
            await asyncio.sleep(0.8)
        return results
