# Opens the backend and the frontend in two PowerShell windows, then the browser.
$root = $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$root\run_backend.ps1`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$root\run_frontend.ps1`""
Write-Host "Waiting for the servers to start..."
Start-Sleep -Seconds 8
Start-Process "http://localhost:5173"
