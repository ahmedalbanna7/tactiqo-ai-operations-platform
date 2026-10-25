"""Infrastructure readiness adapters for the approved local core."""

from dataclasses import dataclass, field
from typing import Any

import aio_pika
import anyio
import boto3
import httpx
from botocore.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@dataclass(frozen=True, slots=True)
class PostgreSQLProbe:
    """Check PostgreSQL connectivity without holding a transaction open."""

    dsn: str
    timeout_seconds: float
    name: str = "postgresql"

    async def check(self) -> None:
        """Connect, run a constant query, and dispose the temporary engine."""
        engine = create_async_engine(
            self.dsn,
            poolclass=NullPool,
            connect_args={"timeout": self.timeout_seconds},
        )
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        finally:
            await engine.dispose()


@dataclass(frozen=True, slots=True)
class RedisProbe:
    """Check the configured Redis endpoint with a bounded ping."""

    url: str
    timeout_seconds: float
    name: str = "redis"

    async def check(self) -> None:
        """Ping Redis and close the temporary client."""
        client = Redis.from_url(
            self.url,
            socket_connect_timeout=self.timeout_seconds,
            socket_timeout=self.timeout_seconds,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()


@dataclass(frozen=True, slots=True)
class RabbitMQProbe:
    """Check AMQP connectivity without declaring queues or exchanges."""

    url: str
    timeout_seconds: float
    name: str = "rabbitmq"

    async def check(self) -> None:
        """Open and immediately close a bounded AMQP connection."""
        connection = await aio_pika.connect(self.url, timeout=self.timeout_seconds)
        await connection.close()


@dataclass(frozen=True, slots=True)
class MinIOProbe:
    """Check the MinIO liveness endpoint without using object credentials."""

    endpoint: str
    timeout_seconds: float
    name: str = "minio"

    async def check(self) -> None:
        """Call the public local liveness endpoint and require success."""
        health_url = f"{self.endpoint.rstrip('/')}/minio/health/live"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(health_url)
            response.raise_for_status()


@dataclass(frozen=True, slots=True)
class S3Probe:
    """Check task-role access to the configured S3 bucket."""

    region: str
    bucket: str
    timeout_seconds: float
    name: str = "s3"
    _client: Any = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Reuse one bounded client for repeated health checks."""
        object.__setattr__(
            self,
            "_client",
            boto3.client(
                "s3",
                region_name=self.region,
                config=Config(
                    connect_timeout=self.timeout_seconds,
                    read_timeout=self.timeout_seconds,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            ),
        )

    async def check(self) -> None:
        """Verify bucket access without reading object contents."""
        await anyio.to_thread.run_sync(
            lambda: self._client.head_bucket(Bucket=self.bucket)
        )
