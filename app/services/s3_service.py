import boto3
import structlog
from botocore.exceptions import ClientError

from app.config import get_settings

logger = structlog.get_logger(__name__)


class S3Service:
    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.S3_BUCKET_NAME
        self._client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
        )

    def upload_diff(self, key: str, content: str) -> str:
        """Upload a PR diff to S3. Returns the S3 key."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/plain",
        )
        logger.info("Diff uploaded to S3", bucket=self._bucket, key=key)
        return key

    def download_diff(self, key: str) -> str:
        """Download and return a PR diff from S3 as a string."""
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read().decode("utf-8")

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            logger.warning("Failed to delete S3 object", key=key, error=str(exc))
