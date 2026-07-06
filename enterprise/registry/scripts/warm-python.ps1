# warm-python.ps1 — Warm JFrog PyPI remote cache by downloading all Python packages.
#
# This triggers JFrog to fetch packages from upstream PyPI and cache them locally,
# making them available for air-gapped builds.
#
# Prerequisites:
#   - pip configured (pip.ini or PIP_INDEX_URL env var) pointing at JFrog remote/virtual repo
#   - OR pass -IndexUrl parameter
#   - For correct platform wheels (Linux/Lambda), run on EC2 instead.
#     On Windows, use -Platform flag to download Linux wheels.
#
# Usage:
#   .\warm-python.ps1 -ManifestFile python-packages.txt
#   .\warm-python.ps1 -ManifestFile python-packages.txt -IndexUrl "https://user:token@jfrog.company.com/artifactory/api/pypi/pypi-remote/simple"
#   .\warm-python.ps1 -ManifestFile python-packages.txt -Platform linux

param(
    [Parameter(Position=0)]
    [string]$ManifestFile = "python-packages.txt",
    [string]$IndexUrl = "",
    [ValidateSet("", "linux", "windows")]
    [string]$Platform = "",
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

$tempDir = Join-Path $env:TEMP "jfrog-warm-python-$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

$indexArgs = @()
if ($IndexUrl) {
    $indexArgs = @("--index-url", $IndexUrl)
}

$platformArgs = @()
if ($Platform -eq "linux") {
    $platformArgs = @(
        "--platform", "manylinux2014_x86_64",
        "--python-version", "312",
        "--only-binary=:all:"
    )
}

$packages = Get-Content $ManifestFile | Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' }
$total = $packages.Count
$success = 0
$failed = @()

Write-Host "=== Warming $total Python packages ===" -ForegroundColor Cyan
Write-Host "Temp dir: $tempDir"
Write-Host ""

for ($i = 0; $i -lt $total; $i++) {
    $pkg = $packages[$i].Trim()
    $pct = [math]::Round(($i + 1) / $total * 100)
    $display = $pkg.PadRight(50).Substring(0, 50)
    Write-Host "[$($pct.ToString().PadLeft(3))%] ($($i+1)/$total) $display " -NoNewline

    $allArgs = @("download", "--no-deps", "--dest", $tempDir) + $indexArgs + $platformArgs + @($pkg)
    try {
        $result = & pip @allArgs 2>&1
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

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total:   $total"
Write-Host "Success: $success"
Write-Host "Failed:  $($failed.Count)"

if ($failed.Count -gt 0) {
    $failFile = Join-Path $OutputDir "python-warm-failures.txt"
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
    Write-Host "  - Package version exists on pypi.org"
    Write-Host "  - Network connectivity from JFrog to upstream pypi.org"
    Write-Host "  - On Windows: use -Platform linux to download Linux wheels"
}

Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
