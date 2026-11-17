# OnaRadar frontend: installs npm packages if needed, then starts Vite on http://localhost:5173
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "frontend")
if (-not (Test-Path "node_modules")) {
    Write-Host "[OnaRadar] Installing npm packages..."
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Write-Host "[OnaRadar] Frontend failed to start." -ForegroundColor Red; exit 1 }
}
Write-Host "[OnaRadar] Web app: http://localhost:5173"
npm run dev
