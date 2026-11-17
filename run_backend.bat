@echo off
REM OnaRadar backend: creates the venv, installs deps, trains the model and seeds the DB if needed,
REM then starts the API on http://localhost:8000 (Swagger: /docs).
setlocal
set PYTHONUTF8=1
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe (
  echo [OnaRadar] Creating virtual environment...
  python -m venv .venv || goto :error
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt || goto :error
)
if not exist .env (
  echo [OnaRadar] backend\.env not found - copy backend\.env.example to backend\.env and fill in JWT_SECRET and FERNET_KEY.
  goto :error
)
if not exist ml\artifacts\model.joblib (
  echo [OnaRadar] Training the ML model ^(first run, ~1 min^)...
  .venv\Scripts\python ml\train.py || goto :error
)
if not exist onaradar.db (
  echo [OnaRadar] Seeding the demo database...
  .venv\Scripts\python -m app.seed || goto :error
)
echo [OnaRadar] API: http://localhost:8000   Swagger: http://localhost:8000/docs
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof
:error
echo [OnaRadar] Backend failed to start.
pause
exit /b 1
