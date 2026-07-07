@echo off
setlocal
set "HOST_APP_DIR=%~dp0"
set "PROJECT_DIR=%HOST_APP_DIR%.."
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Missing project virtual environment: %PYTHON%
  exit /b 1
)

cd /d "%HOST_APP_DIR%"
"%PYTHON%" -m aix_host_app
