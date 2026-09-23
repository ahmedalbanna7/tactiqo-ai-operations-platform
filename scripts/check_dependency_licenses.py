"""Fail an SPDX SBOM containing dependency licenses forbidden by policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FORBIDDEN_LICENSE_MARKERS = (
    "AGPL-",
    "GPL-",
    "SSPL-",
    "BUSL-",
    "Commons-Clause",
)
EXPECTED_ARGUMENT_COUNT = 2


def _license_values(package: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("licenseConcluded", "licenseDeclared"):
        value = package.get(key)
        if isinstance(value, str) and value not in {"NOASSERTION", "NONE"}:
            values.append(value)
    return tuple(values)


def main(path: str) -> int:
    """Evaluate known package licenses while retaining unknowns in the SBOM for review."""
    document: object = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("packages"), list):
        print("Invalid SPDX JSON: packages list is missing.")
        return 2
    violations: list[str] = []
    reviewed = 0
    for raw_package in document["packages"]:
        if not isinstance(raw_package, dict):
            continue
        licenses = _license_values(raw_package)
        reviewed += bool(licenses)
        violations.extend(
            f"{raw_package.get('name', '<unknown>')}: {license_expression}"
            for license_expression in licenses
            if any(
                marker.casefold() in license_expression.casefold()
                for marker in FORBIDDEN_LICENSE_MARKERS
            )
        )
    if violations:
        print("Forbidden dependency licenses detected:")
        for violation in sorted(violations):
            print(f"- {violation}")
        return 1
    print(f"Dependency license policy passed; {reviewed} packages had declared licenses.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != EXPECTED_ARGUMENT_COUNT:
        print("Usage: check_dependency_licenses.py <spdx-json>")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
