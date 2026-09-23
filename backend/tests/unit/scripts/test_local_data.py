"""Safety tests for local data lifecycle commands."""

from pathlib import Path

import pytest
from scripts.local_data import (
    LocalDataError,
    _safe_object_path,
    require_confirmation,
    require_development_tenant,
    require_safe_environment,
)


@pytest.mark.parametrize("environment", ["local", "development", "test", " LOCAL "])
def test_safe_local_environments_are_accepted(environment: str) -> None:
    """Local-only environment names are normalized and accepted."""
    assert require_safe_environment(environment) in {"local", "development", "test"}


@pytest.mark.parametrize("environment", ["production", "staging", "", "prod"])
def test_shared_environments_are_rejected(environment: str) -> None:
    """Shared and production-like environments are rejected."""
    with pytest.raises(LocalDataError, match="forbidden"):
        require_safe_environment(environment)


def test_tenant_must_be_explicitly_development_scoped() -> None:
    """Only strict development tenant identifiers pass validation."""
    assert require_development_tenant("dev-finance-team") == "dev-finance-team"
    for unsafe in ("customer", "prod-acme", "dev-", "dev-Acme", "dev_acme"):
        with pytest.raises(LocalDataError, match="beginning with 'dev-'"):
            require_development_tenant(unsafe)


def test_confirmation_is_exact_and_case_sensitive() -> None:
    """Destructive confirmation cannot be approximated."""
    require_confirmation("dev-acme", "dev-acme")
    with pytest.raises(LocalDataError, match="exact confirmation"):
        require_confirmation("DEV-ACME", "dev-acme")


def test_backup_object_path_cannot_escape_root(tmp_path: Path) -> None:
    """An object key cannot traverse outside its backup root."""
    assert _safe_object_path(tmp_path, "dev-acme/report.pdf").is_relative_to(tmp_path)
    with pytest.raises(LocalDataError, match="Unsafe object key"):
        _safe_object_path(tmp_path, "../outside.txt")
