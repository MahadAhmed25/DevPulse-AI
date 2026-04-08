import json
import uuid
from typing import Any

import boto3
import structlog
from botocore.exceptions import ClientError

from app.config import get_settings

logger = structlog.get_logger(__name__)


class S3ServiceError(Exception):
    """Raised when an S3 operation fails."""


def diff_key(pr_id: uuid.UUID) -> str:
    return f"diffs/{pr_id}/diff.txt"


def review_key(review_id: uuid.UUID) -> str:
    return f"reviews/{review_id}/review.json"


class S3Service:
    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.S3_BUCKET_NAME
        self._client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
        )

    def upload_diff(self, pr_id: uuid.UUID, diff_content: str) -> str:
        """Upload a PR diff to S3. Returns the S3 key."""
        key = diff_key(pr_id)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=diff_content.encode("utf-8"),
                ContentType="text/plain",
            )
        except ClientError as exc:
            raise S3ServiceError(f"Failed to upload diff for PR {pr_id}: {exc}") from exc
        logger.info("Diff uploaded to S3", bucket=self._bucket, key=key)
        return key

    def download_diff(self, s3_key: str) -> str:
        """Download and return a PR diff from S3 as a string."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
            return response["Body"].read().decode("utf-8")  # type: ignore[no-any-return]
        except ClientError as exc:
            raise S3ServiceError(f"Failed to download diff at {s3_key}: {exc}") from exc

    def upload_review(self, review_id: uuid.UUID, review_data: dict[str, Any]) -> str:
        """Serialise review_data to JSON and upload to S3. Returns the S3 key."""
        key = review_key(review_id)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=json.dumps(review_data).encode("utf-8"),
                ContentType="application/json",
            )
        except ClientError as exc:
            raise S3ServiceError(f"Failed to upload review {review_id}: {exc}") from exc
        logger.info("Review uploaded to S3", bucket=self._bucket, key=key)
        return key

    def download_review(self, s3_key: str) -> dict[str, Any]:
        """Download and parse a review JSON object from S3."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
            return json.loads(response["Body"].read().decode("utf-8"))  # type: ignore[no-any-return]
        except ClientError as exc:
            raise S3ServiceError(f"Failed to download review at {s3_key}: {exc}") from exc

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise S3ServiceError(f"Failed to delete S3 object {key}: {exc}") from exc
