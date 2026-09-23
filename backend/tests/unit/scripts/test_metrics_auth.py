"""Local scrape credentials are generated privately and remain stable by default."""

from pathlib import Path

from scripts.init_metrics_auth import TOKEN_FILE_MODE, ensure_metrics_auth_token

MINIMUM_TOKEN_LENGTH = 64
TOKEN_FILE_PERMISSION_BITS = 0o777


def test_metrics_token_is_generated_without_output_and_reused(tmp_path: Path) -> None:
    """A random token is persisted for local Compose without being logged or rotated."""
    token_path = tmp_path / "metrics-token"

    generated = ensure_metrics_auth_token(token_path)
    reused = ensure_metrics_auth_token(token_path)

    assert len(generated) >= MINIMUM_TOKEN_LENGTH
    assert generated == reused
    assert token_path.read_text(encoding="utf-8") == generated
    assert token_path.stat().st_mode & TOKEN_FILE_PERMISSION_BITS == TOKEN_FILE_MODE


def test_explicit_token_replaces_generated_token(tmp_path: Path) -> None:
    """An explicitly managed deployment token is synchronized to the shared volume."""
    token_path = tmp_path / "metrics-token"
    ensure_metrics_auth_token(token_path)

    supplied = "externally-managed-secret-token"
    assert ensure_metrics_auth_token(token_path, supplied) == supplied
    assert token_path.read_text(encoding="utf-8") == supplied
