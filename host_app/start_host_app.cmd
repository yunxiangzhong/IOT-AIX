@echo off
setlocal
cd /d "%~dp0"

set "PROJECT_DIR=%~dp0.."
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "MODEL_PYTHON=%PROJECT_DIR%\Models\DepthAnything3\env\python.exe"
set "HOTSPOT_SCRIPT=%~dp0ensure_mobile_hotspot.ps1"
set "SYNC_SCRIPT=%PROJECT_DIR%\AIX\sync_preview_sdkconfig.ps1"

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

if not exist "%HOTSPOT_SCRIPT%" (
  echo [ERROR] Missing Mobile Hotspot helper:
  echo %HOTSPOT_SCRIPT%
  pause
  exit /b 1
)

if not exist "%SYNC_SCRIPT%" (
  echo [ERROR] Missing ESP preview configuration sync helper:
  echo %SYNC_SCRIPT%
  pause
  exit /b 1
)

if /i "%AIX_HOST_DRY_RUN%"=="1" (
  echo [OK] Host app, local model runtime, hotspot helper, and config sync helper are ready.
  exit /b 0
)

echo [INFO] Synchronizing ESP preview Wi-Fi configuration...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SYNC_SCRIPT%"
if errorlevel 1 (
  echo.
  echo [ERROR] ESP preview Wi-Fi configuration could not be synchronized.
  pause
  exit /b 1
)

echo [INFO] Starting Windows Mobile Hotspot...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HOTSPOT_SCRIPT%"
if errorlevel 1 (
  echo.
  echo [ERROR] Mobile Hotspot could not be started automatically.
  echo Open Windows Settings ^> Network and Internet ^> Mobile hotspot, then retry.
  pause
  exit /b 1
)

"%PYTHON%" -m aix_host_app
if errorlevel 1 (
  echo.
  echo [ERROR] Host app exited with an error.
  pause
  exit /b 1
)
