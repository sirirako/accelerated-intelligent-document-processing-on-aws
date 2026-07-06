# warm-node.ps1 — Warm JFrog npm remote cache by downloading all Node packages.
#
# This triggers JFrog to fetch packages from upstream npmjs.org and cache them
# locally, making them available for air-gapped builds.
#
# Prerequisites:
#   - .npmrc configured pointing at JFrog remote/virtual npm repo
#   - Can run on any OS (Node packages are platform-agnostic)
#
# Usage:
#   .\warm-node.ps1 -ManifestFile node-packages.txt

param(
    [string]$ManifestFile = "node-packages.txt",
    [switch]$SkipSslValidation,
    [string]$OutputDir = "."
)

$ErrorActionPreference = "Continue"

if (!(Test-Path $ManifestFile)) {
    Write-Host "ERROR: Manifest not found: $ManifestFile" -ForegroundColor Red
    Write-Host "Generate it with: make dep-manifest"
    exit 1
}

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$tempDir = Join-Path $env:TEMP "jfrog-warm-node-$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

if ($SkipSslValidation) {
    Write-Host "WARNING: SSL validation disabled (strict-ssl=false)" -ForegroundColor Yellow
    npm config set strict-ssl false
}

$packages = Get-Content $ManifestFile | Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' }
$total = $packages.Count
$success = 0
$failed = @()

Write-Host "=== Warming $total Node packages ===" -ForegroundColor Cyan
Write-Host "Temp dir: $tempDir"
Write-Host ""

Push-Location $tempDir
try {
    for ($i = 0; $i -lt $total; $i++) {
        $pkg = $packages[$i].Trim()
        $pct = [math]::Round(($i + 1) / $total * 100)
        $display = $pkg.PadRight(50).Substring(0, 50)
        Write-Host "[$($pct.ToString().PadLeft(3))%] ($($i+1)/$total) $display " -NoNewline

        try {
            $result = & npm pack $pkg 2>&1
        } catch {
            # Swallow — check $LASTEXITCODE below
        }

        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK" -ForegroundColor Green
            $success++
        } else {
            Write-Host "FAILED" -ForegroundColor Red
            $failed += $pkg
        }
    }
} finally {
    Pop-Location
}

if ($SkipSslValidation) {
    npm config delete strict-ssl
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total:   $total"
Write-Host "Success: $success"
Write-Host "Failed:  $($failed.Count)"

if ($failed.Count -gt 0) {
    $failFile = Join-Path $OutputDir "node-warm-failures.txt"
    try {
        $failed | Out-File -FilePath $failFile -Encoding utf8 -Force
        Write-Host ""
        Write-Host "Failed packages saved to: $failFile" -ForegroundColor Yellow
    } catch {
        Write-Host ""
        Write-Host "WARNING: Could not write failure file to $failFile" -ForegroundColor Yellow
        Write-Host "Failed packages:" -ForegroundColor Yellow
        $failed | ForEach-Object { Write-Host "  $_" }
    }
    Write-Host ""
    Write-Host "Re-run this script to retry (cached packages return instantly)."
    Write-Host ""
    Write-Host "If failures persist, check:"
    Write-Host "  - JFrog remote repo metadata cache (ask admin to 'Zap Caches')"
    Write-Host "  - Package version exists on npmjs.org"
    Write-Host "  - .npmrc auth token is valid and has read access to the remote repo"
    Write-Host "  - For SELF_SIGNED_CERT_IN_CHAIN: use -SkipSslValidation flag or"
    Write-Host "    set NODE_EXTRA_CA_CERTS env var to your corporate CA cert"
}

Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
