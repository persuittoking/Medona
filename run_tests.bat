@echo off
set PYTHONUTF8=1
cd /d "%~dp0backend"
.venv\Scripts\python -m pytest tests -q
pause
