@echo off
REM Restore the demo state (re-seeds the SQLite DB; takes ~10 s). Stop the backend first if it is running.
set PYTHONUTF8=1
cd /d "%~dp0backend"
.venv\Scripts\python -m app.seed
echo.
echo [OnaRadar] Demo data restored. RESTART THE BACKEND now (run_backend.bat) so it reloads the data and
echo            re-generates the DEMO1-DEMO4 AI summaries. Then run check_demo.ps1 to verify.
pause
