@echo off
setlocal ENABLEEXTENSIONS

REM ==================================================
REM ISER Food Pricing – Data Cleaning Pipeline (Handoff)
REM ==================================================
REM All paths are defined here (BAT only).
REM This BAT assumes it lives in the DATA_CLEANING_SCRIPTS folder.

REM ---- Script folder (this BAT location) ----
set "SCRIPT_DIR=%~dp0"

REM ---- Python ----
set "PYTHON_EXE=C:\Users\vlcollier\env\Scripts\python.exe"

REM ---- Data roots (EDIT ON NEW MACHINE) ----
set "RAW_ROOT=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA"
set "CLEAN_ROOT=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\CLEANED_DATA"
set "CROSSWALK_PATH=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\CROSSWALKS\Stores_Crosswalk.csv"

REM ---- Logs inside repo ----
set "LOG_ROOT=%SCRIPT_DIR%Cleaning_Logs"
if not exist "%LOG_ROOT%" mkdir "%LOG_ROOT%"

set "RUN_DATE=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%"
set "RUN_TIME=%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "RUN_TIME=%RUN_TIME: =0%"

set "PIPELINE_LOG=%LOG_ROOT%\pipeline_run_%RUN_DATE%_%RUN_TIME%.txt"

echo Running pipeline...
echo Log file:
echo %PIPELINE_LOG%

REM ---- Run central runner (orchestration) ----
echo PIPELINE_LOG=%PIPELINE_LOG%

"%PYTHON_EXE%" "%SCRIPT_DIR%\central_runner.py" ^
  --raw-root "%RAW_ROOT%" ^
  --clean-root "%CLEAN_ROOT%" ^
  --crosswalk "%CROSSWALK_PATH%" ^
  --log "%PIPELINE_LOG%"


echo.
echo Pipeline complete.
echo See log file:
echo %PIPELINE_LOG%

endlocal
pause
