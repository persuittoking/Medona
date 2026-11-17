@echo off
REM OnaRadar frontend: installs npm packages if needed, then starts Vite on http://localhost:5173
cd /d "%~dp0frontend"
if not exist node_modules (
  echo [OnaRadar] Installing npm packages...
  call npm install --no-audit --no-fund || goto :error
)
echo [OnaRadar] Web app: http://localhost:5173
call npm run dev
goto :eof
:error
echo [OnaRadar] Frontend failed to start.
pause
exit /b 1
