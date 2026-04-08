import json

import boto3
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

# Titan Embeddings V2 returns 1024-dimensional vectors by default
EMBEDDING_DIMENSION = 1024


class EmbeddingService:
    """Generate embeddings via Amazon Bedrock Titan Embeddings V2."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model_id = settings.BEDROCK_EMBEDDING_MODEL_ID
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
        )

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string."""
        body = json.dumps({"inputText": text})
        response = self._client.invoke_model(
            modelId=self._model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        embedding: list[float] = result["embedding"]
        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Bedrock Titan does not support batch natively,
        so we call embed() per item. For large batches consider parallelising
        with a thread pool executor."""
        return [self.embed(t) for t in texts]
