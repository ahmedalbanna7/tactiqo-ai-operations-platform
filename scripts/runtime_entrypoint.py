"""Assemble runtime database configuration and start the container command."""

from __future__ import annotations

import os
import sys
from urllib.parse import quote, urlsplit, urlunsplit


def _database_url() -> str:
    """Build an async PostgreSQL DSN from secret-injected environment fields."""
    existing = os.environ.get("TACTIQO_DATABASE_URL", "").strip()
    if existing:
        return existing
    names = (
        "TACTIQO_DATABASE_HOST",
        "TACTIQO_DATABASE_NAME",
        "TACTIQO_DATABASE_USER",
        "TACTIQO_DATABASE_PASSWORD",
    )
    values = {name: os.environ.get(name, "") for name in names}
    if not all(value for value in values.values()):
        raise RuntimeError("Database URL or complete RDS connection fields are required.")
    host = values["TACTIQO_DATABASE_HOST"]
    port = os.environ.get("TACTIQO_DATABASE_PORT", "5432")
    database = quote(values["TACTIQO_DATABASE_NAME"], safe="")
    username = quote(values["TACTIQO_DATABASE_USER"], safe="")
    password = quote(values["TACTIQO_DATABASE_PASSWORD"], safe="")
    return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"


def _redis_url() -> str | None:
    """Build a TLS Redis URL when ECS injects ElastiCache connection parts."""
    if os.environ.get("TACTIQO_REDIS_URL", "").strip():
        return None
    host = os.environ.get("TACTIQO_REDIS_HOST", "").strip()
    password = os.environ.get("TACTIQO_REDIS_PASSWORD", "")
    if not host or not password:
        return None
    port = os.environ.get("TACTIQO_REDIS_PORT", "6379")
    return f"rediss://:{quote(password, safe='')}@{host}:{port}/0"


def _rabbitmq_url() -> str | None:
    """Build an AMQPS URL from Amazon MQ endpoint and injected credentials."""
    if os.environ.get("TACTIQO_RABBITMQ_URL", "").strip():
        return None
    endpoint = os.environ.get("TACTIQO_RABBITMQ_ENDPOINT", "").strip()
    username = os.environ.get("TACTIQO_RABBITMQ_USERNAME", "")
    password = os.environ.get("TACTIQO_RABBITMQ_PASSWORD", "")
    if not endpoint or not username or not password:
        return None
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"amqp+ssl", "amqps"} or parsed.hostname is None:
        raise RuntimeError("Amazon MQ must provide a TLS AMQP endpoint.")
    host = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    authority = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}"
    return urlunsplit(("amqps", authority, "/", "", ""))


def main() -> None:
    """Set validated runtime configuration and replace this process."""
    command = sys.argv[1:]
    if not command:
        raise RuntimeError("Container command is required.")
    os.environ["TACTIQO_DATABASE_URL"] = _database_url()
    redis_url = _redis_url()
    if redis_url is not None:
        os.environ["TACTIQO_REDIS_URL"] = redis_url
    rabbitmq_url = _rabbitmq_url()
    if rabbitmq_url is not None:
        os.environ["TACTIQO_RABBITMQ_URL"] = rabbitmq_url
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
