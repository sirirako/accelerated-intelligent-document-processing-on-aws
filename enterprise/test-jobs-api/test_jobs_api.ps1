# IDP Jobs API End-to-End Test (PowerShell)
#
# Usage:
#   .\test_jobs_api.ps1 -ZipFile "test-doc.zip"
#   .\test_jobs_api.ps1 -ZipFile "test-doc.zip" -ConfigVersion "v2"

param(
    [Parameter(Mandatory=$true)]
    [string]$ZipFile,
    [string]$ConfigVersion = ""
)

# --- Load Configuration from .env_api ---
$envFile = Join-Path $PSScriptRoot ".env_api"
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env_api not found. Copy env_api.example to .env_api and fill in values." -ForegroundColor Red
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
$CognitoDomain = $config["COGNITO_DOMAIN"]
$ClientId = $config["CLIENT_ID"]
$ClientSecret = $config["CLIENT_SECRET"]
$ApiEndpoint = $config["API_ENDPOINT"]

if (-not $CognitoDomain -or -not $ClientId -or -not $ClientSecret -or -not $ApiEndpoint) {
    Write-Host "ERROR: .env_api is missing required values." -ForegroundColor Red
    exit 1
}

# --- Step 1: Get Token ---
Write-Host "1. Getting Cognito access token..." -ForegroundColor Cyan
$authBytes = [System.Text.Encoding]::UTF8.GetBytes("${ClientId}:${ClientSecret}")
$authBase64 = [Convert]::ToBase64String($authBytes)

$tokenResponse = Invoke-RestMethod -Uri "$CognitoDomain/oauth2/token" -Method Post `
    -Headers @{ "Authorization" = "Basic $authBase64"; "Content-Type" = "application/x-www-form-urlencoded" } `
    -Body "grant_type=client_credentials&scope=idp-api/jobs.read idp-api/jobs.write"

$token = $tokenResponse.access_token
Write-Host "   OK - token: $($token.Substring(0,30))..." -ForegroundColor Green

# --- Step 2: Submit Job ---
Write-Host "2. Submitting job for: $ZipFile" -ForegroundColor Cyan
$body = @{ fileName = $ZipFile }
if ($ConfigVersion) { $body.configurationVersion = $ConfigVersion }

$submitResponse = Invoke-RestMethod -Uri "$ApiEndpoint/jobs" -Method Post `
    -Headers @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" } `
    -Body ($body | ConvertTo-Json)

$jobId = $submitResponse.jobId
$uploadUrl = $submitResponse.upload.uploadUrl
$requiredHeaders = $submitResponse.upload.requiredHeaders
Write-Host "   OK - jobId: $jobId" -ForegroundColor Green
Write-Host "   Upload URL: $uploadUrl"

# --- Step 3: Upload File ---
Write-Host "3. Uploading file to S3..." -ForegroundColor Cyan

# Build multipart form data
$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"
$bodyLines = ""

# Add all required fields first
foreach ($prop in $requiredHeaders.PSObject.Properties) {
    $bodyLines += "--$boundary$LF"
    $bodyLines += "Content-Disposition: form-data; name=`"$($prop.Name)`"$LF$LF"
    $bodyLines += "$($prop.Value)$LF"
}

# Add file
$fileBytes = [System.IO.File]::ReadAllBytes((Resolve-Path $ZipFile))
$bodyLines += "--$boundary$LF"
$bodyLines += "Content-Disposition: form-data; name=`"file`"; filename=`"$ZipFile`"$LF"
$bodyLines += "Content-Type: application/zip$LF$LF"

$bodyEnd = "$LF--$boundary--$LF"

# Combine: text fields + file bytes + end boundary
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
        -Headers @{ "Authorization" = "Bearer $token" }

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

    # Extract
    $extractDir = "$outputDir\results"
    if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
    Expand-Archive -Path $zipPath -DestinationPath $extractDir
    Write-Host "   Extracted to: $extractDir" -ForegroundColor Green

    # Show structure
    Write-Host "`n   Results structure:" -ForegroundColor Cyan
    Get-ChildItem -Recurse -File $extractDir | ForEach-Object {
        $rel = $_.FullName.Replace((Resolve-Path $extractDir).Path + "\", "")
        Write-Host "     $rel ($($_.Length) bytes)"
    }

    # Show extraction results
    Get-ChildItem -Recurse -Filter "result.json" $extractDir | Where-Object { $_.FullName -match "sections" } | ForEach-Object {
        Write-Host "`n   === $($_.FullName.Replace((Resolve-Path $extractDir).Path + '\', '')) ===" -ForegroundColor Yellow
        $data = Get-Content $_.FullName | ConvertFrom-Json
        Write-Host "   Document class: $($data.document_class.type)"
        $fields = $data.inference_result.PSObject.Properties
        Write-Host "   Extracted fields ($($fields.Count)):"
        $fields | Select-Object -First 10 | ForEach-Object {
            Write-Host "     $($_.Name): $($_.Value)"
        }
        if ($fields.Count -gt 10) {
            Write-Host "     ... and $($fields.Count - 10) more fields"
        }
    }
} else {
    Write-Host "5. No results available (job may have failed)" -ForegroundColor Yellow
}

Write-Host "`nDone!" -ForegroundColor Green
