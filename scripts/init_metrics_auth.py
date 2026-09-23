"""Create or persist the local metrics scrape credential in a Docker-mounted volume."""

import os
import secrets
import tempfile
from pathlib import Path

TOKEN_FILE_MODE = 0o444


def ensure_metrics_auth_token(token_path: Path, configured_token: str | None = None) -> str:
    """Return configured/existing token or create a random one without printing it."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token = (configured_token or "").strip()
    if not token:
        try:
            token = token_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            token = ""
    if not token:
        token = secrets.token_urlsafe(48)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix="metrics-token-",
        suffix=".tmp",
        dir=token_path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(token)
        if token_path.exists():
            token_path.chmod(0o600)
        Path(temporary_name).replace(token_path)
        token_path.chmod(TOKEN_FILE_MODE)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return token


def main() -> None:
    """Ensure the shared token exists; the credential itself is never logged."""
    token_path_value = os.environ.get(
        "TACTIQO_METRICS_AUTH_TOKEN_FILE", "/run/tactiqo-metrics/metrics-token"
    )
    ensure_metrics_auth_token(
        Path(token_path_value),
        os.environ.get("TACTIQO_METRICS_AUTH_TOKEN"),
    )


if __name__ == "__main__":
    main()
