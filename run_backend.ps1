# OnaRadar backend: creates the venv, installs deps, creates backend\.env, trains the model and seeds the DB
# if needed, then starts the API on http://localhost:8000 (Swagger: /docs).
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
Set-Location (Join-Path $PSScriptRoot "backend")
$py = ".venv\Scripts\python.exe"

function Invoke-Step([string]$Message, [scriptblock]$Action) {
    Write-Host "[OnaRadar] $Message"
    & $Action
    if ($LASTEXITCODE -ne 0) { Write-Host "[OnaRadar] Backend failed to start." -ForegroundColor Red; exit 1 }
}

if (-not (Test-Path $py)) {
    Invoke-Step "Creating virtual environment..." { python -m venv .venv }
    Invoke-Step "Installing packages (first run, a few minutes)..." {
        & $py -m pip install --upgrade pip
        & $py -m pip install -r requirements-dev.txt
    }
}
if (-not (Test-Path ".env")) {
    Invoke-Step "Creating backend\.env with fresh secrets (add GEMINI_API_KEY for the AI summary)..." { & $py -m app.make_env }
}
if (-not (Test-Path "ml\artifacts\model.joblib")) {
    Invoke-Step "Training the ML model (first run, ~1 min)..." { & $py ml\train.py }
}
if (-not (Test-Path "onaradar.db")) {
    Invoke-Step "Seeding the demo database..." { & $py -m app.seed }
}
Write-Host "[OnaRadar] API: http://localhost:8000   Swagger: http://localhost:8000/docs"
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
