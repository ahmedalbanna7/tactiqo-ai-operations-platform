[CmdletBinding()]
param(
    [string[]]$Name = @(),
    [switch]$VerifyOnly,
    [string]$GitExecutable = "git"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..")
)
$manifestPath = Join-Path $repositoryRoot "vendor\upstreams.lock.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

function Invoke-PinnedGit {
    param([string[]]$Arguments)

    $output = & $GitExecutable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
    return $output
}

foreach ($repository in $manifest.repositories) {
    if ($Name.Count -gt 0 -and $repository.name -notin $Name) {
        continue
    }

    $destination = [System.IO.Path]::GetFullPath(
        (Join-Path $repositoryRoot $repository.destination)
    )
    $allowedRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $repositoryRoot "vendor\upstream")
    )
    if (-not $destination.StartsWith(
        $allowedRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unsafe upstream destination: $destination"
    }

    $sparsePaths = @()
    if ($null -ne $repository.sparse_paths) {
        $sparsePaths = @($repository.sparse_paths)
    }

    $created = $false
    if (-not (Test-Path -LiteralPath $destination)) {
        if ($VerifyOnly) {
            throw "Missing upstream checkout: $($repository.name)"
        }
        New-Item -ItemType Directory -Path $allowedRoot -Force | Out-Null
        $cloneArguments = @(
            "clone", "--depth", "1", "--branch", $repository.release,
            "--single-branch"
        )
        if ($sparsePaths.Count -gt 0) {
            $cloneArguments += @("--filter=blob:none", "--sparse")
        }
        $cloneArguments += @($repository.url, $destination)
        Invoke-PinnedGit -Arguments $cloneArguments | Out-Null
        $created = $true
    }

    $origin = Invoke-PinnedGit -Arguments @(
        "-C", $destination, "remote", "get-url", "origin"
    )
    if ($origin.Trim() -ne $repository.url) {
        throw "Unexpected origin for $($repository.name): $origin"
    }

    if (-not $VerifyOnly -and -not $created) {
        Invoke-PinnedGit -Arguments @(
            "-C", $destination, "fetch", "--depth", "1", "origin",
            "refs/tags/$($repository.release)"
        ) | Out-Null
        Invoke-PinnedGit -Arguments @(
            "-C", $destination, "checkout", "--detach", $repository.commit
        ) | Out-Null
    }

    if (-not $VerifyOnly -and $sparsePaths.Count -gt 0) {
        Invoke-PinnedGit -Arguments @(
            "-C", $destination, "sparse-checkout", "init", "--cone"
        ) | Out-Null
        $sparseArguments = @(
            "-C", $destination, "sparse-checkout", "set"
        ) + $sparsePaths
        Invoke-PinnedGit -Arguments $sparseArguments | Out-Null
    }

    $actualCommit = Invoke-PinnedGit -Arguments @(
        "-C", $destination, "rev-parse", "HEAD"
    )
    if ($actualCommit.Trim() -ne $repository.commit) {
        throw "Commit mismatch for $($repository.name): $actualCommit"
    }

    $verificationPath = Join-Path $destination $repository.verification_path
    if (-not (Test-Path -LiteralPath $verificationPath -PathType Leaf)) {
        throw "Missing verification file for $($repository.name): $verificationPath"
    }

    $worktreeStatus = @(Invoke-PinnedGit -Arguments @(
        "-C", $destination, "status", "--porcelain"
    ))
    if ($worktreeStatus.Count -gt 0) {
        throw "Dirty or incomplete upstream checkout: $($repository.name)"
    }

    Write-Output "$($repository.name) $actualCommit"
}
