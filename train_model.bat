@echo off
REM Regenerate synthetic data and retrain the ML model; prints ROC-AUC / PR-AUC.
set PYTHONUTF8=1
cd /d "%~dp0backend"
.venv\Scripts\python ml\train.py --regen
pause
