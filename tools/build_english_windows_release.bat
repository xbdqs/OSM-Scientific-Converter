@echo off
setlocal
cd /d "%~dp0\.."

where conda >nul 2>nul
if errorlevel 1 (
  echo ERROR: conda was not found. Run this file from Anaconda Prompt.
  pause
  exit /b 1
)

call conda activate osm-scientific-converter-phase3
if errorlevel 1 (
  echo ERROR: Could not activate osm-scientific-converter-phase3.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\tools\build_english_windows_release.ps1"
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo.
  echo BUILD OR PACKAGED-STARTUP TEST FAILED. Review the error above.
  pause
  exit /b %RC%
)

echo.
echo BUILD AND PACKAGED-STARTUP TEST SUCCEEDED.
echo Output: dist_english_v041\dist\OSMScientificConverter_v0.4.1
echo ZIP:    dist_english_v041\OSMScientificConverter_v0.4.1_Windows_x64_English.zip
echo Smoke:  dist_english_v041\WINDOWS_ENGLISH_STARTUP_SMOKE.json
pause
