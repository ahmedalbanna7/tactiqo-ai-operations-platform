"""Require an ADR when a change touches material architecture boundaries."""

from __future__ import annotations

import os
import subprocess
import sys

PROTECTED_PREFIXES = (
    "backend/src/tactiqo/agents/",
    "backend/src/tactiqo/shared/",
    "backend/src/tactiqo/integrations/",
    "backend/src/tactiqo/tools/",
    "backend/src/tactiqo/knowledge/",
    "migrations/",
    "infra/",
    "docker-compose.yml",
    "pyproject.toml",
)
ADR_PREFIX = "docs/adr/"
ZERO_SHA = "0" * 40


def changed_files(base_sha: str | None) -> tuple[str, ...]:
    """Return files changed from a valid CI base, or from the previous commit."""
    base = base_sha if base_sha and base_sha != ZERO_SHA else "HEAD^"
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "show", "--pretty=format:", "--name-only", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    return tuple(
        line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()
    )


def main() -> int:
    """Fail when protected boundaries change without an accompanying ADR."""
    files = changed_files(os.environ.get("BASE_SHA"))
    material = tuple(path for path in files if path.startswith(PROTECTED_PREFIXES))
    has_adr = any(path.startswith(ADR_PREFIX) and path.endswith(".md") for path in files)
    if material and not has_adr:
        print("Material architecture files changed without a new or updated docs/adr/*.md:")
        for path in material:
            print(f"- {path}")
        return 1
    print("Architecture change policy passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
