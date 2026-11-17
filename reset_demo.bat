@echo off
REM Restore the demo state (re-seeds the SQLite DB; takes ~10 s). Stop the backend first if it is running.
set PYTHONUTF8=1
cd /d "%~dp0backend"
.venv\Scripts\python -m app.seed
pause
