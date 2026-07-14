@echo off
setlocal
cd /d "%~dp0"

set "DRY_RUN_ARG="
if /i "%AIX_HOST_DRY_RUN%"=="1" set "DRY_RUN_ARG=-DryRun"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_stack.ps1" %DRY_RUN_ARG%
if errorlevel 1 (
  echo.
  echo [ERROR] AIX active vision stack exited with an error.
  if /i not "%AIX_HOST_DRY_RUN%"=="1" pause
  exit /b 1
)

exit /b 0
