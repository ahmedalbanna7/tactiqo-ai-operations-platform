# Pinned Upstream Components

The platform records approved upstream source references in
`vendor/upstreams.lock.json`. Local source checkouts live under
`vendor/upstream/` and are intentionally ignored by the Tactiqo repository.

## Why source is not copied into business modules

- Unstructured is a parser implementation behind `DocumentParser` in isolated
  RabbitMQ workers.
- LangGraph and LangChain are libraries for a later approved orchestration
  design. Their source does not define platform permissions or business truth.

This prevents accidental forks, vendor object leakage, and direct imports from
large upstream codebases.

## Pinned releases

| Component | Release | Intended activation |
|---|---:|---|
| Unstructured | `0.24.1` | Phase 3 parsing workers; sparse source checkout |
| LangGraph | `1.2.9` | Phase 4 approved agent workflows |
| LangChain Core | `1.4.9` | Phase 4 approved abstractions |

The complete commit SHAs and official GitHub URLs are stored in the manifest.

## Download and verify

```powershell
pwsh -File scripts/vendor/sync-upstreams.ps1
pwsh -File scripts/vendor/sync-upstreams.ps1 -VerifyOnly
```

When the workstation's system Git cannot reach GitHub, pass the approved Git
executable explicitly:

```powershell
pwsh -File scripts/vendor/sync-upstreams.ps1 -GitExecutable "C:\path\to\git.exe"
```

To select only the repository needed for document parsing:

```powershell
pwsh -File scripts/vendor/sync-upstreams.ps1 -Name unstructured
```

The script fails if a checkout has the wrong origin, commit, required
verification file, or a dirty/incomplete worktree. The manifest defines a
sparse checkout for Unstructured's package source so large example and test
fixtures are not downloaded as runtime inputs.

## Unstructured configuration boundary

The source checkout is for audit, compatibility review, and reproducible local
development. Runtime installation will use a pinned package/container in the
isolated parser worker. The worker must normalize output to
`CanonicalDocumentElement`; Unstructured-specific objects cannot cross the
adapter boundary.

## Upgrade process

1. Record the candidate release and full commit in a review branch.
2. Review release notes, license, security advisories, and migrations.
3. Run adapter contract, access-control, data-migration, and quality evaluations.
4. Test rollback using representative non-sensitive data.
5. Obtain approval and update the manifest and ADR/runbook together.
