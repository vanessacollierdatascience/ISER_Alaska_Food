@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ===============================================================
REM ISER / Alaska_Food – MASTER FOOD SCRAPE LAUNCHER (PYTHON)
REM ===============================================================

REM ---------- PATH SETUP (CODE REPO) -----------------------------

set "REPO_ROOT=C:\Users\vlcollier\GITHUB_PUSH\Alaska_Food"
set "DATA_PULL=%REPO_ROOT%\DATA_PULL_SCRIPTS"
set "CENTRAL_PY=%DATA_PULL%\central_food_pull.py"

REM ---------- RAW DATA ROOT (NOT GIT-TRACKED) --------------------

set "RAW_DATA_ROOT=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA"

REM Store parent folders (must exist under RAW_DATA_ROOT)
set "ACC_RAW_ROOT=%RAW_DATA_ROOT%\ACC_RAW"
set "CS_RAW_ROOT=%RAW_DATA_ROOT%\CS_RAW"
set "FM_RAW_ROOT=%RAW_DATA_ROOT%\FM_RAW"
set "WM_RAW_ROOT=%RAW_DATA_ROOT%\WM_RAW"

REM ---------- LOGGING --------------------------------------------

set "RUN_LOG=%DATA_PULL%\run_food_pull_master.log"

set "SCRAPE_LOG_DIR=%DATA_PULL%\Scraping_Logs"
if not exist "%SCRAPE_LOG_DIR%" mkdir "%SCRAPE_LOG_DIR%"

REM Optional: a second logs root on the shared drive (uncomment if your Python uses it)
REM set "PIPELINE_LOG_ROOT=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\LOGS"
REM if not exist "%PIPELINE_LOG_ROOT%" mkdir "%PIPELINE_LOG_ROOT%"

echo ==== run_food_pull.bat started %DATE% %TIME% ====>>"%RUN_LOG%"
echo [BAT] REPO_ROOT=%REPO_ROOT%>>"%RUN_LOG%"
echo [BAT] DATA_PULL=%DATA_PULL%>>"%RUN_LOG%"
echo [BAT] CENTRAL_PY=%CENTRAL_PY%>>"%RUN_LOG%"
echo [BAT] RAW_DATA_ROOT=%RAW_DATA_ROOT%>>"%RUN_LOG%"
echo [BAT] ACC_RAW_ROOT=%ACC_RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] CS_RAW_ROOT=%CS_RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] FM_RAW_ROOT=%FM_RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] WM_RAW_ROOT=%WM_RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] SCRAPE_LOG_DIR=%SCRAPE_LOG_DIR%>>"%RUN_LOG%"

REM Create RAW roots if missing
if not exist "%RAW_DATA_ROOT%" mkdir "%RAW_DATA_ROOT%"
if not exist "%ACC_RAW_ROOT%" mkdir "%ACC_RAW_ROOT%"
if not exist "%CS_RAW_ROOT%" mkdir "%CS_RAW_ROOT%"
if not exist "%FM_RAW_ROOT%" mkdir "%FM_RAW_ROOT%"
if not exist "%WM_RAW_ROOT%" mkdir "%WM_RAW_ROOT%"

REM ---------- PYTHON VENV ACTIVATION -----------------------------

call "%USERPROFILE%\.venvs\FP_env\Scripts\activate.bat"
if errorlevel 1 (
    echo [BAT-ERROR] Failed to activate FP_env>>"%RUN_LOG%"
    echo Failed to activate FP_env
    pause
    exit /b 1
)

REM ===============================================================
REM STORE SWITCHES (BAT CONTROLS WHAT RUNS)
REM ===============================================================

set "RUN_ACC=FALSE"
set "RUN_CS=FALSE"
set "RUN_FM=FALSE"
set "RUN_WM=TRUE"

REM ===============================================================
REM  WALMART MODE (CHOOSE ONE)
REM   PULL          = trigger new Bright Data snapshot
REM   DOWNLOAD      = download snapshot via Bright Data API
REM   IMPORT_MANUAL = clean/merge manually downloaded CSV+JSON
REM ===============================================================

set "WM_MODE=DOWNLOAD"
set WM_SNAPSHOT_FORMAT=csv


REM ---------- KROGER CREDENTIALS (ONLY NEEDED IF RUN_FM=TRUE) ----

set "KROGER_CLIENT_ID=uaaeconomicresearch-1c9930e136aa1ca8bdee7c8f336ed77a5021264682018960484"
set "KROGER_CLIENT_SECRET=gUnOOBLmuXR0zSIc8NhUMsL2db3ODrxES9vk9Tv4"

REM ---------- BRIGHT DATA (WALMART) ------------------------------

set "WM_API_KEY=5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3"
set "WM_DATASET_ID=gd_m693oc1r1gebnayxq"

REM If WM_MODE=DOWNLOAD, you may specify a snapshot id (optional if your downloader selects latest ready)
set "WM_SNAPSHOT_ID=sd_mjc2uwzoro56qxt8e"

REM Search list used by WM pull script when WM_MODE=PULL
set "WM_SEARCH_FILE=%DATA_PULL%\WM\WM_search_list.txt"

REM Optional polling knobs (only used if your WM scripts read them)
set "WM_MAX_WAIT_MIN=360"
set "WM_POLL_EVERY_S=120"
set "WM_USE_LAST=0"

REM Manual import inputs (only used if WM_MODE=IMPORT_MANUAL and your script reads them)
REM These must point to the manually downloaded files.
REM set "WM_MANUAL_CSV=%WM_RAW_ROOT%\WM_25_12\sd_mjc2uwzoro56qxt8e.csv"
REM set "WM_MANUAL_JSON=%WM_RAW_ROOT%\WM_25_12\sd_mjc2uwzoro56qxt8e.json"

REM ---------- RUN PIPELINE --------------------------------------

echo [BAT] RUN_ACC=%RUN_ACC% RUN_CS=%RUN_CS% RUN_FM=%RUN_FM% RUN_WM=%RUN_WM%>>"%RUN_LOG%"
echo [BAT] WM_MODE=%WM_MODE% WM_SNAPSHOT_ID=%WM_SNAPSHOT_ID%>>"%RUN_LOG%"
echo [BAT] Launching central_food_pull.py>>"%RUN_LOG%"

python "%CENTRAL_PY%"
set "PY_EXIT=%ERRORLEVEL%"

echo [BAT] EXIT CODE=%PY_EXIT%>>"%RUN_LOG%"

echo.
echo Batch finished with ERRORLEVEL %PY_EXIT%
echo Logs:
echo   Master: %RUN_LOG%
echo   Store logs: %SCRAPE_LOG_DIR%
pause

endlocal & exit /b %PY_EXIT%
