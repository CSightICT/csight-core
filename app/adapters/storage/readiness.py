"""MinIO bucket readiness adapter."""

from minio import Minio
from urllib3 import PoolManager, Timeout


class MinioReadinessProbe:
    name = "minio"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
        timeout_seconds: float,
    ) -> None:
        http_client = PoolManager(
            timeout=Timeout(connect=timeout_seconds, read=timeout_seconds),
            retries=False,
        )
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            http_client=http_client,
        )
        self._bucket = bucket

    def check(self) -> bool:
        return self._client.bucket_exists(self._bucket)
