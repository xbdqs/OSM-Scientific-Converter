@echo off
setlocal
cd /d "%~dp0\.."
where powershell >nul 2>nul
if errorlevel 1 ( echo PowerShell missing & exit /b 1 )
powershell -NoProfile -ExecutionPolicy Bypass -File ".\tools\build_windows_v042.ps1"
if errorlevel 1 ( echo FAILED - see errors and RELEASE_VALIDATION_CHECKLIST_CN.md & exit /b 1 )
echo Build and packaged self-tests PASSED. Inspect dist_windows_v042.
