"""MinIO object-storage adapter for original document bytes."""

from io import BytesIO

import anyio
from minio import Minio


class MinioObjectStorage:
    """Store originals in one private bucket using the S3-compatible API."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        """Configure a private S3-compatible object bucket."""
        secure = endpoint.startswith("https://")
        host = endpoint.removeprefix("https://").removeprefix("http://")
        self._client = Minio(host, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        """Create the bucket if needed and upload bytes idempotently."""
        await anyio.to_thread.run_sync(self._ensure_bucket)
        await anyio.to_thread.run_sync(
            lambda: self._client.put_object(
                self._bucket,
                key,
                BytesIO(content),
                len(content),
                content_type=content_type,
            )
        )

    async def get(self, key: str) -> bytes:
        """Read and close one object response safely."""

        def _read() -> bytes:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await anyio.to_thread.run_sync(_read)

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
