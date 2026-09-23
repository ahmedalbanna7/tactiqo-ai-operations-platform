"""Safe lifecycle commands for deterministic local Tactiqo data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from minio import Minio

from tactiqo.shared.infrastructure.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Sequence

SAFE_ENVIRONMENTS = frozenset({"local", "development", "test"})
TENANT_PATTERN = re.compile(r"dev-[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
RESTORE_CONFIRMATION = "RESTORE LOCAL DATA"


class LocalDataError(RuntimeError):
    """Raised when a lifecycle safety rule or external command fails."""


def require_safe_environment(environment: str) -> str:
    """Return a normalized environment only when local mutation is allowed."""
    normalized = environment.strip().lower()
    if normalized not in SAFE_ENVIRONMENTS:
        message = f"Local data commands are forbidden in environment: {normalized or '<empty>'}."
        raise LocalDataError(message)
    return normalized


def require_development_tenant(organization_id: str) -> str:
    """Validate an explicit development-only organization identifier."""
    normalized = organization_id.strip()
    if normalized != normalized.lower() or not TENANT_PATTERN.fullmatch(normalized):
        message = "Organization ID must be a lowercase development ID beginning with 'dev-'."
        raise LocalDataError(message)
    return normalized


def require_confirmation(actual: str | None, expected: str) -> None:
    """Reject destructive commands without an exact, case-sensitive confirmation."""
    if actual != expected:
        message = f"Destructive command requires exact confirmation: {expected}"
        raise LocalDataError(message)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _config(name: str, default: str) -> str:
    """Read one local setting from process environment or the root .env file."""
    process_value = os.environ.get(name)
    if process_value is not None:
        return process_value
    env_path = Path(".env")
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if separator and key.strip() == name:
                return value.strip().strip('"').strip("'")
    return default


def _settings() -> Settings:
    """Load the same validated configuration used by runtime services."""
    return Settings(
        database_url=_config(
            "TACTIQO_DATABASE_URL",
            "postgresql+asyncpg://tactiqo_app:change-me@postgres:5432/tactiqo",
        ),
        redis_url=_config("TACTIQO_REDIS_URL", "redis://redis:6379/0"),
        rabbitmq_url=_config("TACTIQO_RABBITMQ_URL", "amqp://tactiqo_app:change-me@rabbitmq:5672/"),
        minio_endpoint=_config("TACTIQO_MINIO_ENDPOINT", "http://minio:9000"),
        minio_access_key=_config("TACTIQO_MINIO_ACCESS_KEY", "change-me"),
        minio_secret_key=_config("TACTIQO_MINIO_SECRET_KEY", "change-me"),
    )


def _postgres_identity() -> tuple[str, str]:
    parsed = urlparse(_settings().database_url.get_secret_value())
    if not parsed.username or not parsed.path.strip("/"):
        message = "Configured PostgreSQL URL is missing user or database."
        raise LocalDataError(message)
    return parsed.username, parsed.path.strip("/")


def _compose(command: Sequence[str], *, stdin: bytes | None = None) -> bytes:
    process = subprocess.run(
        ["docker", "compose", *command],
        input=stdin,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise LocalDataError(detail or f"Docker Compose command failed: {' '.join(command)}")
    return process.stdout


def _psql(sql: str, variables: dict[str, str] | None = None) -> bytes:
    user, database = _postgres_identity()
    command = ["exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command.extend(["-v", f"{key}={value}"])
    command.extend(["-U", user, "-d", database])
    return _compose(command, stdin=sql.encode())


def _minio_client() -> tuple[Minio, str]:
    settings = _settings()
    configured = _env("TACTIQO_BACKUP_MINIO_ENDPOINT", "").strip()
    if not configured:
        parsed_runtime = urlparse(settings.minio_endpoint)
        if parsed_runtime.hostname in {"minio", "localhost", "127.0.0.1"}:
            port = _config("TACTIQO_MINIO_HOST_PORT", "19000")
            configured = f"http://127.0.0.1:{port}"
        else:
            configured = settings.minio_endpoint
    parsed = urlparse(configured if "://" in configured else f"http://{configured}")
    if not parsed.hostname:
        message = "Invalid local MinIO endpoint."
        raise LocalDataError(message)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        message = "Local data commands require a loopback MinIO endpoint."
        raise LocalDataError(message)
    endpoint = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    access_key = settings.minio_access_key.get_secret_value()
    secret_key = settings.minio_secret_key.get_secret_value()
    bucket = settings.minio_bucket
    return Minio(
        endpoint, access_key=access_key, secret_key=secret_key, secure=parsed.scheme == "https"
    ), bucket


def _safe_object_path(root: Path, key: str) -> Path:
    """Map an object key below a backup root without path traversal."""
    destination = (root / Path(key)).resolve()
    resolved_root = root.resolve()
    if destination == resolved_root or resolved_root not in destination.parents:
        message = f"Unsafe object key in backup: {key}"
        raise LocalDataError(message)
    return destination


def seed(organization_id: str) -> None:
    """Create one deterministic, idempotent local conversation."""
    tenant = require_development_tenant(organization_id)
    conversation_id = str(uuid5(NAMESPACE_URL, f"tactiqo:{tenant}:welcome-conversation"))
    message_id = str(uuid5(NAMESPACE_URL, f"tactiqo:{tenant}:welcome-message"))
    sql = """
BEGIN;
INSERT INTO chat_conversations
    (id, title, actor_id, organization_id, classification, policy_version, created_at, updated_at)
VALUES
    (:'conversation_id', 'Tactiqo local verification', 'dev-owner', :'organization_id',
     'internal', 'dev-seed-v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP;
INSERT INTO chat_messages (id, conversation_id, role, content, created_at)
VALUES (:'message_id', :'conversation_id', 'assistant',
        'Deterministic local tenant is ready.', CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""
    _psql(
        sql,
        {
            "organization_id": tenant,
            "conversation_id": conversation_id,
            "message_id": message_id,
        },
    )
    print(f"Seeded development tenant: {tenant}")


def teardown(organization_id: str, confirmation: str | None) -> None:
    """Remove records and objects for exactly one development tenant."""
    tenant = require_development_tenant(organization_id)
    require_confirmation(confirmation, tenant)
    client, bucket = _minio_client()
    if client.bucket_exists(bucket):
        for item in client.list_objects(bucket, prefix=f"{tenant}/", recursive=True):
            client.remove_object(bucket, item.object_name)
    sql = """
BEGIN;
DELETE FROM integration_connections WHERE organization_id = :'organization_id';
DELETE FROM knowledge_documents WHERE organization_id = :'organization_id';
DELETE FROM chat_conversations WHERE organization_id = :'organization_id';
COMMIT;
"""
    _psql(sql, {"organization_id": tenant})
    print(f"Removed development tenant: {tenant}")


def backup(output_root: Path) -> Path:
    """Create a timestamped PostgreSQL and MinIO local backup."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = output_root.resolve() / stamp
    target.mkdir(parents=True, exist_ok=False)
    user, database = _postgres_identity()
    dump = _compose(
        [
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            user,
            "-d",
            database,
            "--format=custom",
            "--no-owner",
        ]
    )
    database_path = target / "postgres.dump"
    database_path.write_bytes(dump)

    client, bucket = _minio_client()
    object_records: list[dict[str, str | int]] = []
    object_root = target / "minio"
    if client.bucket_exists(bucket):
        for item in client.list_objects(bucket, recursive=True):
            key = item.object_name
            if not key:
                continue
            destination = _safe_object_path(object_root, key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            client.fget_object(bucket, item.object_name, str(destination))
            object_records.append(
                {
                    "key": key,
                    "size": destination.stat().st_size,
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                }
            )
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "environment": _settings().environment.value,
        "database": database_path.name,
        "database_sha256": hashlib.sha256(dump).hexdigest(),
        "minio_bucket": bucket,
        "objects": object_records,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Backup created: {target}")
    return target


def verify_backup(backup_path: Path) -> None:
    """Validate manifest, PostgreSQL archive, and every object without mutation."""
    source = backup_path.resolve()
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        message = "Backup manifest was not found."
        raise LocalDataError(message)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        message = "Unsupported backup format."
        raise LocalDataError(message)
    dump = (source / str(manifest["database"])).read_bytes()
    if hashlib.sha256(dump).hexdigest() != manifest.get("database_sha256"):
        message = "PostgreSQL backup checksum mismatch."
        raise LocalDataError(message)
    _compose(["exec", "-T", "postgres", "pg_restore", "--list"], stdin=dump)
    _, configured_bucket = _minio_client()
    if str(manifest["minio_bucket"]) != configured_bucket:
        message = "Backup bucket does not match the configured local bucket."
        raise LocalDataError(message)
    for record in manifest.get("objects", []):
        key = str(record["key"])
        local_path = _safe_object_path(source / "minio", key)
        if hashlib.sha256(local_path.read_bytes()).hexdigest() != record["sha256"]:
            message = f"Object checksum mismatch: {key}"
            raise LocalDataError(message)
    print(f"Backup verified: {source}")


def restore(backup_path: Path, confirmation: str | None) -> None:
    """Replace local PostgreSQL and MinIO content from a validated backup."""
    require_confirmation(confirmation, RESTORE_CONFIRMATION)
    verify_backup(backup_path)
    source = backup_path.resolve()
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        message = "Backup manifest was not found."
        raise LocalDataError(message)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        message = "Unsupported backup format."
        raise LocalDataError(message)
    dump = (source / str(manifest["database"])).read_bytes()
    if hashlib.sha256(dump).hexdigest() != manifest.get("database_sha256"):
        message = "PostgreSQL backup checksum mismatch."
        raise LocalDataError(message)
    user, database = _postgres_identity()
    _compose(
        [
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            user,
            "-d",
            database,
            "--clean",
            "--if-exists",
            "--no-owner",
        ],
        stdin=dump,
    )

    client, configured_bucket = _minio_client()
    bucket = str(manifest["minio_bucket"])
    if bucket != configured_bucket:
        message = "Backup bucket does not match the configured local bucket."
        raise LocalDataError(message)
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    for item in client.list_objects(bucket, recursive=True):
        client.remove_object(bucket, item.object_name)
    for record in manifest.get("objects", []):
        key = str(record["key"])
        local_path = _safe_object_path(source / "minio", key)
        if hashlib.sha256(local_path.read_bytes()).hexdigest() != record["sha256"]:
            message = f"Object checksum mismatch: {key}"
            raise LocalDataError(message)
        client.fput_object(bucket, key, str(local_path))
    print(f"Backup restored: {source}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "teardown"):
        command = subparsers.add_parser(name)
        command.add_argument("--organization-id", required=True)
        if name == "teardown":
            command.add_argument("--confirm")
    backup_command = subparsers.add_parser("backup")
    backup_command.add_argument(
        "--output",
        type=Path,
        default=Path(_config("TACTIQO_BACKUP_DIRECTORY", ".local/backups")),
    )
    verify_command = subparsers.add_parser("verify")
    verify_command.add_argument("--backup", type=Path, required=True)
    restore_command = subparsers.add_parser("restore")
    restore_command.add_argument("--backup", type=Path, required=True)
    restore_command.add_argument("--confirm")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one guarded local data lifecycle command."""
    options = _parser().parse_args(arguments)
    require_safe_environment(_settings().environment.value)
    if options.command == "seed":
        seed(options.organization_id)
    elif options.command == "teardown":
        teardown(options.organization_id, options.confirm)
    elif options.command == "backup":
        backup(options.output)
    elif options.command == "verify":
        verify_backup(options.backup)
    else:
        restore(options.backup, options.confirm)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LocalDataError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
