# IDP Jobs API End-to-End Test (PowerShell + Ping Auth)
#
# Usage:
#   .\test_jobs_api_ping.ps1 -ZipFile "test-doc.zip"
#   .\test_jobs_api_ping.ps1 -ZipFile "test-doc.zip" -ConfigVersion "v2"
#   .\test_jobs_api_ping.ps1 -ZipFile "test-doc.zip" -Token "<pre-fetched-token>"

param(
    [Parameter(Mandatory=$true)]
    [string]$ZipFile,
    [string]$ConfigVersion = "",
    [string]$Token = ""
)

# --- Load Configuration from .env_api_ping ---
$envFile = Join-Path $PSScriptRoot ".env_api_ping"
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env_api_ping not found. Copy env_api_ping.example to .env_api_ping and fill in values." -ForegroundColor Red
    exit 1
}
$config = @{}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        $key, $value = $line -split "=", 2
        $config[$key.Trim()] = $value.Trim()
    }
}
$ApiEndpoint = $config["API_ENDPOINT"]
$TokenEndpoint = $config["TOKEN_ENDPOINT"]
$ClientId = $config["CLIENT_ID"]
$ClientSecret = $config["CLIENT_SECRET"]
$Username = $config["USERNAME"]
$Password = $config["PASSWORD"]
$Scope = $config["SCOPE"]
$ValidatorId = $config["VALIDATOR_ID"]
$GrantType = if ($config["GRANT_TYPE"]) { $config["GRANT_TYPE"] } else { "password" }

if (-not $ApiEndpoint) {
    Write-Host "ERROR: .env_api_ping is missing API_ENDPOINT." -ForegroundColor Red
    exit 1
}

# --- Step 1: Get Token (skip if pre-fetched) ---
if (-not $Token) {
    Write-Host "1. Getting Ping access token..." -ForegroundColor Cyan

    if (-not $TokenEndpoint -or -not $ClientId -or -not $ClientSecret) {
        Write-Host "ERROR: .env_api_ping is missing TOKEN_ENDPOINT, CLIENT_ID, or CLIENT_SECRET." -ForegroundColor Red
        exit 1
    }

    $body = @{
        grant_type    = $GrantType
        client_id     = $ClientId
        client_secret = $ClientSecret
    }
    if ($Scope) { $body.scope = $Scope }
    if ($GrantType -eq "password") {
        if (-not $Username -or -not $Password) {
            Write-Host "ERROR: Username and Password required for password grant." -ForegroundColor Red
            exit 1
        }
        $body.username = $Username
        $body.password = $Password
        if ($ValidatorId) { $body.validator_id = $ValidatorId }
    }

    try {
        $tokenResponse = Invoke-RestMethod -Uri $TokenEndpoint -Method POST -Body $body -ContentType "application/x-www-form-urlencoded"
        $Token = $tokenResponse.access_token
    } catch {
        Write-Host "ERROR: Token request failed: $_" -ForegroundColor Red
        exit 1
    }

    Write-Host "   OK - token: $($Token.Substring(0, [Math]::Min(30, $Token.Length)))..." -ForegroundColor Green
} else {
    Write-Host "1. Using pre-fetched token: $($Token.Substring(0, [Math]::Min(30, $Token.Length)))..." -ForegroundColor Cyan
}

# --- Step 2: Submit Job ---
Write-Host "2. Submitting job for: $ZipFile" -ForegroundColor Cyan
$body = @{ fileName = $ZipFile }
if ($ConfigVersion) { $body.configurationVersion = $ConfigVersion }

try {
    $submitResponse = Invoke-RestMethod -Uri "$ApiEndpoint/jobs" -Method Post `
        -Headers @{ "Authorization" = "Bearer $Token"; "Content-Type" = "application/json" } `
        -Body ($body | ConvertTo-Json)
} catch {
    Write-Host "ERROR: Submit failed: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd() -ForegroundColor Red
    }
    exit 1
}

$jobId = $submitResponse.jobId
$uploadUrl = $submitResponse.upload.uploadUrl
$requiredHeaders = $submitResponse.upload.requiredHeaders
Write-Host "   OK - jobId: $jobId" -ForegroundColor Green

# --- Step 3: Upload File ---
Write-Host "3. Uploading file to S3..." -ForegroundColor Cyan

$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"
$bodyLines = ""

foreach ($prop in $requiredHeaders.PSObject.Properties) {
    $bodyLines += "--$boundary$LF"
    $bodyLines += "Content-Disposition: form-data; name=`"$($prop.Name)`"$LF$LF"
    $bodyLines += "$($prop.Value)$LF"
}

$fileBytes = [System.IO.File]::ReadAllBytes((Resolve-Path $ZipFile))
$bodyLines += "--$boundary$LF"
$bodyLines += "Content-Disposition: form-data; name=`"file`"; filename=`"$ZipFile`"$LF"
$bodyLines += "Content-Type: application/zip$LF$LF"

$bodyEnd = "$LF--$boundary--$LF"

$encoding = [System.Text.Encoding]::UTF8
$bodyStart = $encoding.GetBytes($bodyLines)
$bodyEndBytes = $encoding.GetBytes($bodyEnd)
$requestBody = New-Object byte[] ($bodyStart.Length + $fileBytes.Length + $bodyEndBytes.Length)
[System.Buffer]::BlockCopy($bodyStart, 0, $requestBody, 0, $bodyStart.Length)
[System.Buffer]::BlockCopy($fileBytes, 0, $requestBody, $bodyStart.Length, $fileBytes.Length)
[System.Buffer]::BlockCopy($bodyEndBytes, 0, $requestBody, $bodyStart.Length + $fileBytes.Length, $bodyEndBytes.Length)

$uploadResponse = Invoke-WebRequest -Uri $uploadUrl -Method Post `
    -ContentType "multipart/form-data; boundary=$boundary" `
    -Body $requestBody

Write-Host "   OK - upload complete (status: $($uploadResponse.StatusCode))" -ForegroundColor Green

# --- Step 4: Poll Status ---
Write-Host "4. Polling job status..." -ForegroundColor Cyan
$timeout = 300
$interval = 5
$start = Get-Date

do {
    $statusResponse = Invoke-RestMethod -Uri "$ApiEndpoint/jobs/$jobId" -Method Get `
        -Headers @{ "Authorization" = "Bearer $Token" }

    $status = $statusResponse.status
    $elapsed = [int]((Get-Date) - $start).TotalSeconds
    Write-Host "   [${elapsed}s] Status: $status"

    if ($status -in @("SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "ABORTED")) {
        Write-Host "`n   Final status: $status" -ForegroundColor $(if ($status -eq "SUCCEEDED") { "Green" } else { "Yellow" })
        break
    }

    Start-Sleep -Seconds $interval
} while ($elapsed -lt $timeout)

# --- Step 5: Download Results ---
if ($statusResponse.result) {
    Write-Host "5. Downloading results..." -ForegroundColor Cyan
    $downloadUrl = $statusResponse.result.downloadUrl

    $outputDir = ".\output"
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    $zipPath = "$outputDir\results.zip"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath
    Write-Host "   Saved: $zipPath ($((Get-Item $zipPath).Length) bytes)" -ForegroundColor Green

    $extractDir = "$outputDir\results"
    if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
    Expand-Archive -Path $zipPath -DestinationPath $extractDir
    Write-Host "   Extracted to: $extractDir" -ForegroundColor Green

    Write-Host "`n   Results structure:" -ForegroundColor Cyan
    Get-ChildItem -Recurse -File $extractDir | ForEach-Object {
        $rel = $_.FullName.Replace((Resolve-Path $extractDir).Path + "\", "")
        Write-Host "     $rel ($($_.Length) bytes)"
    }
} else {
    Write-Host "5. No results available (job may have failed)" -ForegroundColor Yellow
}

Write-Host "`nDone!" -ForegroundColor Green
