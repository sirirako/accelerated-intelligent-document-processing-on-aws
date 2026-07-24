# Get a JWT token from PingFederate (client credentials flow)
# Usage: .\Get-PingToken.ps1 -TokenEndpoint "https://..." -ClientId "..." -ClientSecret "..."

param(
    [Parameter(Mandatory=$true)]
    [string]$TokenEndpoint,

    [Parameter(Mandatory=$true)]
    [string]$ClientId,

    [Parameter(Mandatory=$true)]
    [string]$ClientSecret,

    [string]$Scope = ""
)

$body = @{
    grant_type    = "client_credentials"
    client_id     = $ClientId
    client_secret = $ClientSecret
}

if ($Scope) {
    $body.scope = $Scope
}

try {
    $response = Invoke-RestMethod -Uri $TokenEndpoint -Method POST -Body $body -ContentType "application/x-www-form-urlencoded"

    Write-Host "[OK] Token retrieved successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access Token:"
    Write-Host $response.access_token
    Write-Host ""
    Write-Host "Expires in: $($response.expires_in) seconds"
    Write-Host "Token type: $($response.token_type)"

    # Decode payload (base64 middle section) for inspection
    $parts = $response.access_token.Split(".")
    if ($parts.Length -ge 2) {
        $payload = $parts[1]
        # Fix base64 padding
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
