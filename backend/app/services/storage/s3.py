import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.services.storage.base import StorageService, StoredObject


def s3_client(endpoint_url: str | None = None, region: str | None = None, access_key_id: str | None = None,
              secret_access_key: str | None = None, addressing_style: str | None = None, quick: bool = False):
    """boto3 client for any S3-compatible backend (SeaweedFS, AWS S3, DigitalOcean Spaces, Garage, Ceph RGW).
    Signature v4 always; addressing style from S3_ADDRESSING_STYLE (path for self-hosted, virtual for Spaces/AWS).
    quick=True: short timeouts and 2 attempts, for diagnosis probes."""
    style = (addressing_style or "path").lower()
    if style not in ("path", "virtual", "auto"):
        raise RuntimeError("S3_ADDRESSING_STYLE must be path, virtual or auto")
    extra = {"connect_timeout": 5, "read_timeout": 20} if quick else {}
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        region_name=region or None,
        aws_access_key_id=access_key_id or None,
        aws_secret_access_key=secret_access_key or None,
        config=Config(signature_version="s3v4", s3={"addressing_style": style},
                      retries={"max_attempts": 2 if quick else 5, "mode": "standard"}, **extra),
    )


class S3Storage(StorageService):
    """S3-compatible driver (SeaweedFS, AWS S3, DigitalOcean Spaces, Garage, Ceph RGW)."""

    driver = "s3"

    def __init__(self, bucket: str | None, endpoint_url: str | None = None, region: str | None = None,
                 access_key_id: str | None = None, secret_access_key: str | None = None, addressing_style: str | None = None):
        if not bucket:
            raise RuntimeError("S3_BUCKET is required for the s3 storage driver")
        self.bucket = bucket
        self.client = s3_client(endpoint_url, region, access_key_id, secret_access_key, addressing_style)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredObject:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return self._meta(key, data, content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
