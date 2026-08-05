@echo off
setlocal
if "%~4"=="" (
  echo Usage: capture_publication_gui_english.bat EXE_PATH BERLIN_PROJECT OUTPUT_DIR FIGURE_CODE_DIR
  exit /b 2
)
set EXE=%~1
set PROJECT=%~2
set OUT=%~3
set FIGCODE=%~4
if not exist "%OUT%" mkdir "%OUT%"
set OSM_SCI_CLEAN_ENV=1
set PYTHONPATH=
"%EXE%" --gui-acceptance-case berlin_power --gui-acceptance-project "%PROJECT%" --gui-acceptance-output-dir "%OUT%\exports" --gui-acceptance-report "%OUT%\gui_acceptance_report.json" --gui-acceptance-screenshots "%OUT%\screenshots"
if errorlevel 1 exit /b %errorlevel%
python "%FIGCODE%\figure_2_actual_english_gui.py" --screenshots "%OUT%\screenshots" --output "%OUT%\Figure_2_actual_english_gui_workflow.png"
echo Created actual English GUI screenshots and Figure 2 in %OUT%
endlocal
