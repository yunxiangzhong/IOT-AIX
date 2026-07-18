@echo off
setlocal EnableExtensions

set "HOST_ROOT=%~dp0"
pushd "%HOST_ROOT%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Cannot enter host application directory: "%HOST_ROOT%"
  exit /b 1
)

if not exist "%HOST_ROOT%start_stack.ps1" (
  echo [ERROR] Missing startup script: "%HOST_ROOT%start_stack.ps1"
  popd
  exit /b 1
)

set "DRY_RUN_ARG="
if /i "%AIX_HOST_DRY_RUN%"=="1" set "DRY_RUN_ARG=-DryRun"

echo [AIX] Starting host stack from "%HOST_ROOT%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HOST_ROOT%start_stack.ps1" %DRY_RUN_ARG%
set "STACK_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%STACK_EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] AIX active vision stack exited with code %STACK_EXIT_CODE%.
  if /i not "%AIX_HOST_DRY_RUN%"=="1" pause
)

exit /b %STACK_EXIT_CODE%
