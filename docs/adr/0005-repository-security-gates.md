# ADR 0005: Repository security and quality gates

- Status: Accepted
- Date: 2026-09-11

## Context

Tactiqo is intended to operate as a multi-tenant SaaS platform with privileged
connectors and agentic execution. A defect or compromised dependency can cross
tenant and tool boundaries, so repository controls must be automated before the
runtime surface grows.

## Decision

The repository enforces the following pull-request gates:

- formatting, linting, static typing, tests, migration graph validation, and
  frontend production builds;
- full-history secret scanning;
- Python and Node production dependency vulnerability audits;
- SPDX SBOM generation and a deny-list license policy;
- CODEOWNERS review for security-sensitive paths;
- an ADR requirement for material architecture changes;
- automated dependency update proposals.

Dependency audits use the committed lockfiles. Python requirements are exported
as a fully pinned graph, then audited without invoking `pip`, keeping the result
deterministic and avoiding platform-specific source builds.

## Consequences

- Pull requests fail when a required quality or security gate fails.
- Material architecture changes must include a decision record.
- Vulnerable dependency upgrades become normal maintenance, not deferred work.
- GitHub branch protection must require these checks before merge; that remote
  setting is applied separately because it depends on repository authorization.
