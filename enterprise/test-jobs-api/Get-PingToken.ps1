# Get a JWT token from PingFederate
# Supports both password grant and client_credentials grant
#
# Password grant:
#   .\Get-PingToken.ps1 -TokenEndpoint "https://ping.example.com/as/token.oauth2" -ClientId "..." -ClientSecret "..." -Username "..." -Password "..."
#
# Client credentials grant:
#   .\Get-PingToken.ps1 -TokenEndpoint "https://ping.example.com/as/token.oauth2" -ClientId "..." -ClientSecret "..." -GrantType client_credentials

param(
    [Parameter(Mandatory=$true)]
    [string]$TokenEndpoint,

    [Parameter(Mandatory=$true)]
    [string]$ClientId,

    [Parameter(Mandatory=$true)]
    [string]$ClientSecret,

    [string]$Username = "",

    [string]$Password = "",

    [ValidateSet("password", "client_credentials")]
    [string]$GrantType = "password",

    [string]$Scope = "edit",

    [string]$ValidatorId = ""
)

$body = @{
    grant_type    = $GrantType
    client_id     = $ClientId
    client_secret = $ClientSecret
}

if ($Scope) {
    $body.scope = $Scope
}

if ($GrantType -eq "password") {
    if (-not $Username -or -not $Password) {
        Write-Host "[ERROR] Username and Password are required for password grant" -ForegroundColor Red
        exit 1
    }
    $body.username = $Username
    $body.password = $Password
    if ($ValidatorId) {
        $body.validator_id = $ValidatorId
    }
}

try {
    $response = Invoke-RestMethod -Uri $TokenEndpoint -Method POST -Body $body -ContentType "application/x-www-form-urlencoded"

    Write-Host "[OK] Token retrieved successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access Token:"
    Write-Host $response.access_token
    Write-Host ""
    if ($response.expires_in) {
        Write-Host "Expires in: $($response.expires_in) seconds"
    }
    if ($response.token_type) {
        Write-Host "Token type: $($response.token_type)"
    }

    # Decode payload (base64 middle section) for inspection
    $parts = $response.access_token.Split(".")
    if ($parts.Length -ge 2) {
        $payload = $parts[1]
        # Fix base64url padding
        $payload = $payload.Replace("-", "+").Replace("_", "/")
        $padding = 4 - ($payload.Length % 4)
        if ($padding -ne 4) { $payload += "=" * $padding }
        $decoded = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($payload))
        $json = $decoded | ConvertFrom-Json

        Write-Host ""
        Write-Host "Token claims:" -ForegroundColor Cyan
        Write-Host "  iss: $($json.iss)"
        Write-Host "  sub: $($json.sub)"
        Write-Host "  exp: $($json.exp)"
        if ($json.userRoles) { Write-Host "  userRoles: $($json.userRoles -join ', ')" }
        if ($json.memberOf) { Write-Host "  memberOf: $($json.memberOf -join ', ')" }
        if ($json.scope) { Write-Host "  scope: $($json.scope)" }
    }

    # Copy to clipboard
    $response.access_token | Set-Clipboard
    Write-Host ""
    Write-Host "[COPIED] Token copied to clipboard" -ForegroundColor Yellow

} catch {
    Write-Host "[ERROR] Failed to get token: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd()
    }
}
