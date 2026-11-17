@echo off
REM Opens the backend and the frontend in two windows, then the browser.
start "OnaRadar backend" cmd /k "%~dp0run_backend.bat"
start "OnaRadar frontend" cmd /k "%~dp0run_frontend.bat"
echo Waiting for the servers to start...
timeout /t 8 /nobreak >nul
start "" http://localhost:5173
