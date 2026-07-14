@echo off
setlocal
cd /d "%~dp0"

set "PROJECT_DIR=%~dp0.."
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "MODEL_PYTHON=%PROJECT_DIR%\Models\DepthAnything3\env\python.exe"

if not exist "%PYTHON%" (
  echo [ERROR] Missing host environment:
  echo %PYTHON%
  pause
  exit /b 1
)

if not exist "%MODEL_PYTHON%" (
  echo [ERROR] Missing local vision model environment:
  echo %MODEL_PYTHON%
  echo Run Models\DepthAnything3\install.ps1 first.
  pause
  exit /b 1
)

if /i "%AIX_HOST_DRY_RUN%"=="1" (
  echo [OK] Host app and local model runtime are ready.
  exit /b 0
)

"%PYTHON%" -m aix_host_app
if errorlevel 1 (
  echo.
  echo [ERROR] Host app exited with an error.
  pause
  exit /b 1
)
