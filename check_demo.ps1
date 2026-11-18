# OnaRadar demo readiness check. Prints PASS / FAIL / INFO per line; never prints secret values.
# Usage (repo root, backend running):  powershell -ExecutionPolicy Bypass -File .\check_demo.ps1 [-Api http://127.0.0.1:8000]
param([string]$Api = "http://127.0.0.1:8000")

$ErrorActionPreference = "Continue"
$script:failed = 0

function Write-Result([string]$status, [string]$text) {
    $color = @{ PASS = "Green"; FAIL = "Red"; INFO = "Cyan" }[$status]
    Write-Host ("[{0}] {1}" -f $status, $text) -ForegroundColor $color
    if ($status -eq "FAIL") { $script:failed++ }
}

# ---- 1. backend/.env (values are read but never printed) ----
$envPath = Join-Path $PSScriptRoot "backend\.env"
$envVars = @{}
if (Test-Path $envPath) {
    Write-Result "PASS" "backend\.env exists"
    foreach ($line in Get-Content $envPath -Encoding UTF8) {
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=(.*)$') { $envVars[$Matches[1]] = $Matches[2].Trim() }
    }
} else {
    Write-Result "FAIL" "backend\.env is missing (run run_backend.bat once: it creates it with fresh secrets)"
}
foreach ($key in "JWT_SECRET", "FERNET_KEY") {
    if ($envVars[$key]) { Write-Result "PASS" "$key is set (value not shown)" }
    else { Write-Result "FAIL" "$key is empty" }
}
if ($envVars["PINFL_HASH_SECRET"]) {
    if ($envVars["PINFL_HASH_SECRET"] -eq $envVars["JWT_SECRET"]) { Write-Result "FAIL" "PINFL_HASH_SECRET equals JWT_SECRET" }
    else { Write-Result "PASS" "PINFL_HASH_SECRET is set and differs from JWT_SECRET" }
} else {
    Write-Result "INFO" "PINFL_HASH_SECRET is empty (allowed only with DEMO_MODE=true; falls back to JWT_SECRET)"
}
if ($envVars["GEMINI_API_KEY"]) { Write-Result "INFO" "GEMINI_API_KEY is set: AI summaries via Gemini (value not shown)" }
else { Write-Result "INFO" "GEMINI_API_KEY is empty: AI summaries use the template fallback ('Shablon')" }

# ---- 2. backend health ----
try {
    $health = Invoke-RestMethod -Uri "$Api/api/health" -TimeoutSec 10
    Write-Result "PASS" ("GET /api/health -> ok (demo_mode={0})" -f $health.demo_mode)
} catch {
    Write-Result "FAIL" "GET /api/health failed: is the backend running on $Api ? ($($_.Exception.Message))"
}

# ---- 3. LLM health (admin login, aggregates only) ----
try {
    $body = @{ polyclinic_code = $null; username = "region.admin"; password = "demo1234" } | ConvertTo-Json
    $login = Invoke-RestMethod -Uri "$Api/api/auth/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 10
    $headers = @{ Authorization = "Bearer $($login.access_token)" }
    $llm = Invoke-RestMethod -Uri "$Api/api/llm/health" -Headers $headers -TimeoutSec 15
    Write-Result "PASS" ("GET /api/llm/health -> mode={0}, key_present={1}, model={2}, last_call={3}" -f `
        $llm.mode, $llm.key_present, $llm.configured_model, $(if ($llm.last_call) { $llm.last_call } else { "none yet" }))
    if ($llm.last_call -eq "failed") { Write-Result "INFO" "last Gemini call failed: the template fallback is used" }
    $d = $llm.demo_summaries
    if ($d.total -gt 0 -and $d.cached -eq $d.total) {
        Write-Result "PASS" ("DEMO summaries cached: {0}/{1} (AI {2}, template {3})" -f $d.cached, $d.total, $d.ai, $d.template)
    } elseif ($llm.mode -eq "template") {
        Write-Result "INFO" ("DEMO summaries cached: {0}/{1} - template mode builds them instantly on first view" -f $d.cached, $d.total)
    } else {
        Write-Result "FAIL" ("DEMO summaries cached: {0}/{1} - wait ~15 s after backend start (pre-warm) and re-run" -f $d.cached, $d.total)
    }
} catch {
    Write-Result "FAIL" "LLM health check failed: $($_.Exception.Message)"
}

Write-Host ""
if ($script:failed -eq 0) { Write-Host "DEMO READY: all checks passed." -ForegroundColor Green; exit 0 }
Write-Host "$($script:failed) check(s) FAILED - fix them before the pitch." -ForegroundColor Red
exit 1
