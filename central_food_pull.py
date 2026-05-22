#!/usr/bin/env python3
"""
ISER FOOD DATA PIPELINE — Central Runner (Python)

- Replaces central_food_pull.R
- Orchestrates ACC, CS, FM, WM store pulls
- Uses external store scripts:
    - ACC: PROJ/DATA_PULL_SCRIPTS/ACC/*.py (newest)
    - CS : PROJ/DATA_PULL_SCRIPTS/CS/*.py  (newest)
    - FM : PROJ/DATA_PULL_SCRIPTS/FM/*.py  (newest; e.g. FM9_vc.py)
    - WM : PROJ/DATA_PULL_SCRIPTS/WM/Bright_Data/Scripts/*.py (newest)
- Respects RUN_ACC / RUN_CS / RUN_FM / RUN_WM env flags.
- Ensures:
    - KROGER_CLIENT_ID / KROGER_CLIENT_SECRET are available for FM
    - WM_API_KEY is available for WM
- Writes per-store logs into LOG_DIR (from SCRAPE_LOG_DIR or default).

Expected environment (typically set by run_food_pull.bat):

    RUN_ACC, RUN_CS, RUN_FM, RUN_WM        (TRUE/FALSE or 1/0)
    KROGER_CLIENT_ID, KROGER_CLIENT_SECRET (or SECRETS files; see below)
    WM_API_KEY
    SCRAPE_LOG_DIR                         (optional override)

Kroger creds are resolved in this order:
    1. Env vars: KROGER_CLIENT_ID / KROGER_CLIENT_SECRET
    2. CSV  : PROJ/SECRETS/kroger_creds.csv
              columns: client_id, client_secret (or CLIENT_ID / KROGER_CLIENT_ID, etc.)
    3. JSON : PROJ/SECRETS/kroger_creds.json
              keys: client_id/client_secret or KROGER_CLIENT_ID/KROGER_CLIENT_SECRET

If none found and RUN_FM=TRUE, the runner exits with a clear error.
"""

import os
import sys
import time
import json
import csv
import traceback
from pathlib import Path


# ---------------------- Basic helpers ----------------------------------------
RUN_DATE = time.strftime("%Y-%m-%d")


def timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")




def fmt_secs(seconds: float) -> str:
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = int(round(seconds % 60))
    return f"{mins}m {secs:02d}s"


def parse_bool(val: str, default: bool) -> bool:
    if val is None:
        return default
    v = str(val).strip().upper()
    if v in ("FALSE", "0", "NO", "N", ""):
        return False
    if v in ("TRUE", "1", "YES", "Y"):
        return True
    # Fallback: anything else -> default
    return default


# ---------------------- Project paths & log directory -------------------------


# Root / project paths (mirror the R script)
GROOT = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
PROJ = os.path.join(
    GROOT,
    r"Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
)

# LOG_DIR: prefer SCRAPE_LOG_DIR from BAT, otherwise default under DATA_PULL_SCRIPTS
log_dir_env = os.getenv("SCRAPE_LOG_DIR", "").strip()
if log_dir_env:
    LOG_DIR = os.path.normpath(log_dir_env)
else:
    LOG_DIR = os.path.join(PROJ, "DATA_PULL_SCRIPTS", "Scraping_Logs")

os.makedirs(LOG_DIR, exist_ok=True)

CENTRAL_LOG = os.path.join(LOG_DIR, f"central_{time.strftime('%Y%m%d_%H%M%S')}.log")

def central_log(*parts):
    line = "[" + timestamp() + "] " + " ".join(str(p) for p in parts)
    with open(CENTRAL_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def log_path_for(store: str) -> str:
    date_str = time.strftime("%Y%m%d")
    return os.path.join(LOG_DIR, f"{store}_{date_str}.log")


def log_line(store: str, *parts: str) -> None:
    line = "[" + timestamp() + "] " + " ".join(str(p) for p in parts)
    path = log_path_for(store)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


print(f"LOG_DIR (Python) => {LOG_DIR}")
print(
    "FM log path =>",
    os.path.join(LOG_DIR, f"FM_{time.strftime('%Y%m%d')}.log"),
    flush=True,
)


# ---------------------- Script paths (PINNED) ---------------------

REPO_ROOT = r"C:\Users\vlcollier\GITHUB_PUSH\Alaska_Food"
DPS = os.path.join(REPO_ROOT, "DATA_PULL_SCRIPTS")

acc_script = os.path.join(DPS, "ACC", "ACC_PULL_CURRENT.py")
cs_script  = os.path.join(DPS, "CS",  "CS_PULL_CURRENT.py")
fm_script  = os.path.join(DPS, "FM",  "FM_PULL_CURRENT.py")

wm_mode = os.getenv("WM_MODE", "PULL").strip().upper()

if wm_mode == "DOWNLOAD":
    wm_script = os.path.join(DPS, "WM", "WM_download_snapshot.py")
elif wm_mode == "IMPORT_MANUAL":
    wm_script = os.path.join(DPS, "WM", "WM_import_manual_download.py")
else:
    wm_script = os.path.join(DPS, "WM", "WM_PULL_CURRENT.py")



print("Resolved scripts:")
print("  ACC:", acc_script)
print("  CS :", cs_script)
print("  FM :", fm_script)
print("  WM :", wm_script)


# ---------------------- Credential loading -----------------------------------


def load_kroger_creds(proj_root: str) -> tuple[str, str]:
    """
    Resolve Kroger API credentials in order:

    1) Env vars:
         KROGER_CLIENT_ID, KROGER_CLIENT_SECRET
    2) CSV  at proj_root/SECRETS/kroger_creds.csv
    3) JSON at proj_root/SECRETS/kroger_creds.json

    Returns (client_id, client_secret) or raises RuntimeError with a helpful message.
    """
    # 1) Env vars
    env_id = os.getenv("KROGER_CLIENT_ID", "").strip()
    env_sec = os.getenv("KROGER_CLIENT_SECRET", "").strip()
    if env_id and env_sec:
        return env_id, env_sec

    secrets_dir = Path(proj_root) / "SECRETS"

    # 2) CSV
    csv_path = secrets_dir / "kroger_creds.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            row = next(reader, None)
        if row:
            # Accept multiple column name variants
            id_keys = ["client_id", "CLIENT_ID", "KROGER_CLIENT_ID"]
            sec_keys = ["client_secret", "CLIENT_SECRET", "KROGER_CLIENT_SECRET"]
            cid = None
            csec = None
            for k in id_keys:
                if k in row and row[k]:
                    cid = row[k].strip()
                    break
            for k in sec_keys:
                if k in row and row[k]:
                    csec = row[k].strip()
                    break
            if cid and csec:
                return cid, csec

    # 3) JSON
    json_path = secrets_dir / "kroger_creds.json"
    if json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as f:
                j = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to parse {json_path}: {e}") from e

        # Allow flat object or list[object]
        cand = None
        if isinstance(j, dict):
            cand = j
        elif isinstance(j, list) and j and isinstance(j[0], dict):
            cand = j[0]

        if isinstance(cand, dict):
            id_keys = ["client_id", "CLIENT_ID", "KROGER_CLIENT_ID"]
            sec_keys = ["client_secret", "CLIENT_SECRET", "KROGER_CLIENT_SECRET"]
            cid = None
            csec = None
            for k in id_keys:
                val = cand.get(k)
                if val:
                    cid = str(val).strip()
                    break
            for k in sec_keys:
                val = cand.get(k)
                if val:
                    csec = str(val).strip()
                    break
            if cid and csec:
                return cid, csec

    raise RuntimeError(
        "Kroger credentials not provided.\n"
        "Provide one of:\n"
        "  * Env vars KROGER_CLIENT_ID / KROGER_CLIENT_SECRET (e.g. from run_food_pull.bat), OR\n"
        "  * CSV at SECRETS/kroger_creds.csv with columns: client_id, client_secret, OR\n"
        "  * JSON at SECRETS/kroger_creds.json with keys: client_id/client_secret.\n"
        "FM cannot run without these."
    )


def mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "<empty>"
    return s[:6] + "…" if len(s) > 6 else s


# ---------------------- Python file runner ------------------------------------


def run_python_file(store: str, py_file: str, extra_env: dict | None = None) -> bool:
    """
    Execute a Python file in-process, temporarily applying extra_env to os.environ.
    Logs exceptions + traceback to store log.
    """
    import runpy  # imported inside to keep top-level imports tidy

    extra_env = extra_env or {}
    log_line(store, "START:", py_file)

    # Save old env values for keys we overwrite
    old_vals = {k: os.environ.get(k) for k in extra_env}
    try:
        for k, v in extra_env.items():
            os.environ[k] = v

        runpy.run_path(py_file, run_name="__main__")
        log_line(store, "SUCCESS.")
        return True
    except SystemExit as e:
        # Allow underlying script to call sys.exit(...) and treat non-zero as failure
        code = e.code if isinstance(e.code, int) else 1
        if code == 0:
            log_line(store, "SUCCESS (sys.exit(0)).")
            return True
        log_line(store, f"ERROR: script exited with code {code}")
        tb = traceback.format_exc()
        with open(log_path_for(store), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp()}] PY_TRACEBACK:\n{tb}\n")
        print("See log for full Python traceback:", log_path_for(store))
        return False
    except Exception:
        log_line(store, "ERROR: exception while running script.")
        tb = traceback.format_exc()
        with open(log_path_for(store), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp()}] PY_TRACEBACK:\n{tb}\n")
        print("See log for full Python traceback:", log_path_for(store))
        return False
    finally:
        # Restore previous env values (or unset keys that were previously absent)
        for k, old in old_vals.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


# ---------------------- Main orchestration ------------------------------------


def main() -> int:
    central_log("Central runner started")
    central_log("RUN_DATE =", RUN_DATE)
    central_log("SCRAPE_LOG_DIR =", LOG_DIR)

    def env_flag(name: str) -> bool:
        val = os.getenv(name)
        if val is None:
            return False
        return val.strip().upper() in ("1", "TRUE", "YES", "Y")

    RUN_ACC = env_flag("RUN_ACC")
    RUN_CS  = env_flag("RUN_CS")
    RUN_FM  = env_flag("RUN_FM")
    RUN_WM  = env_flag("RUN_WM")

    central_log(
        f"Toggles: RUN_ACC={RUN_ACC}, RUN_CS={RUN_CS}, "
        f"RUN_FM={RUN_FM}, RUN_WM={RUN_WM}"
    )




    # FM creds: ALWAYS load from OS environment
    kroger_client_id = ""
    kroger_client_secret = ""

    if RUN_FM:
        # Force reading ONLY from .bat environment variables
        kroger_client_id = os.getenv("KROGER_CLIENT_ID", "").strip()
        kroger_client_secret = os.getenv("KROGER_CLIENT_SECRET", "").strip()

    # Fail fast if missing
        if not kroger_client_id or not kroger_client_secret:
            print("[FM ERROR] Kroger credentials not found in environment.")
            print("KROGER_CLIENT_ID =", kroger_client_id)
            print("KROGER_CLIENT_SECRET =", kroger_client_secret)
            return 1


    # WM creds + runtime controls (names match Walmart_Bright_Data*.py expectations)
    wm_env = {}
    if RUN_WM:
        bright_key = os.getenv("WM_API_KEY", "").strip()
        if not bright_key:
            print(
                "ERROR: WM_API_KEY is not set, but RUN_WM=TRUE.\n"
                "Set WM_API_KEY in run_food_pull.bat or OS env before running.",
                file=sys.stderr,
            )
            return 1

        # Read tuning from environment, but provide sane defaults
        snapshot_id = os.getenv("WM_SNAPSHOT_ID", "").strip()
        use_last = os.getenv("WM_USE_LAST", "1")
        max_wait = str(int(os.getenv("WM_MAX_WAIT_MIN", "420")))
        poll_every = os.getenv("WM_POLL_EVERY_S", "120")
        dataset_id = os.getenv("WM_DATASET_ID", "gd_m693oc1r1gebnayxq")
  

        wm_env = {
            "STORE": "WM",
            "RUN_DATE": RUN_DATE,
            "WM_API_KEY": bright_key,
            "WM_USE_LAST": use_last,
            "WM_MAX_WAIT_MIN": max_wait,
            "WM_POLL_EVERY_S": poll_every,
            "WM_DATASET_ID": dataset_id,
            "WM_MODE": os.getenv("WM_MODE", "PULL"),

        
        }

        # Only pass WM_SNAPSHOT_ID if explicitly set in the environment / BAT
        if snapshot_id:
            wm_env["WM_SNAPSHOT_ID"] = snapshot_id


        print(
            "WM env: WM_API_KEY=",
            mask(bright_key),
            file=sys.stdout,
            flush=True,
        )


    # Build jobs list (in the same order as the R runner)
    jobs: list[dict] = []

    if RUN_ACC:
        if acc_script and Path(acc_script).is_file():
            jobs.append(
                {
                    "store": "ACC",
                    "py": acc_script,
                    "env": {
                        "STORE": "ACC",
                        "RUN_DATE": RUN_DATE,
                    },
                }
            )
        else:
            print("RUN_ACC=TRUE but ACC script not found.", file=sys.stderr)
            return 1

    if RUN_CS:
        if cs_script and Path(cs_script).is_file():
            jobs.append(
                {
                    "store": "CS",
                    "py": cs_script,
                    "env": {
                        "STORE": "CS",
                        "RUN_DATE": RUN_DATE,
                    },
                }
            )
        else:
            print("RUN_CS=TRUE but CS script not found.", file=sys.stderr)
            return 1

    if RUN_FM:
        if fm_script and Path(fm_script).is_file():
            env = {
                "STORE": "FM",
                "RUN_DATE": RUN_DATE,
                "KROGER_CLIENT_ID": kroger_client_id,
                "KROGER_CLIENT_SECRET": kroger_client_secret,
            }
            jobs.append(
                {
                    "store": "FM",
                    "py": fm_script,
                    "env": env,
                }
            )
        else:
            print("RUN_FM=TRUE but FM script not found.", file=sys.stderr)
            return 1

    if RUN_WM:
        if wm_script and Path(wm_script).is_file():
            jobs.append(
                {
                    "store": "WM",
                    "py": wm_script,
                    "env": wm_env,
                }
            )
        else:
            print("RUN_WM=TRUE but WM script not found.", file=sys.stderr)
            return 1

    if not jobs:
        print("No jobs to run. Set one or more RUN_* environment variables to TRUE.", file=sys.stderr)
        return 1

    # Execute jobs sequentially with a simple progress indicator
    total = len(jobs)
    print(f"\n---- Food Pull (Python): {total} job(s) ----", flush=True)

    all_ok = True
    for idx, job in enumerate(jobs, start=1):
        store = job["store"]
        py_file = job["py"]
        env = job["env"]

        print(f"({idx}/{total}) {store} — starting", flush=True)
        t0 = time.time()
        ok = run_python_file(store, py_file, extra_env=env)
        dt = time.time() - t0
        status = "✔" if ok else "✖"
        print(f"   {status} {store} — {fmt_secs(dt)}", flush=True)
        all_ok = all_ok and ok

    if not all_ok:
        print("\nOne or more pulls failed. Check logs in:", LOG_DIR, file=sys.stderr)
        return 1

    print("\nAll pulls completed successfully.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        with open(CENTRAL_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp()}] FATAL ERROR\n{tb}\n")
        raise

#!/usr/bin/env python3
"""
ISER FOOD DATA PIPELINE — Central Runner (Python)

- Orchestrates ACC, CS, FM, WM store pulls
- Respects RUN_ACC / RUN_CS / RUN_FM / RUN_WM env flags.
- Ensures:
    - KROGER_CLIENT_ID / KROGER_CLIENT_SECRET are available for FM (if RUN_FM=TRUE)
    - WM_API_KEY is available for WM (if RUN_WM=TRUE)
- Writes per-store logs into LOG_DIR (from SCRAPE_LOG_DIR or default).

IMPORTANT:
- Output paths are NOT set here.
- Output paths must be provided by the BAT via:
    ACC_RAW_ROOT, CS_RAW_ROOT, FM_RAW_ROOT, WM_RAW_ROOT
"""

import os
import sys
import time
import json
import csv
import traceback
from pathlib import Path

RUN_DATE = time.strftime("%Y-%m-%d")


def timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def fmt_secs(seconds: float) -> str:
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = int(round(seconds % 60))
    return f"{mins}m {secs:02d}s"


def parse_bool(val: str, default: bool) -> bool:
    if val is None:
        return default
    v = str(val).strip().upper()
    if v in ("FALSE", "0", "NO", "N", ""):
        return False
    if v in ("TRUE", "1", "YES", "Y"):
        return True
    return default


GROOT = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
PROJ = os.path.join(
    GROOT,
    r"Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
)

log_dir_env = os.getenv("SCRAPE_LOG_DIR", "").strip()
if log_dir_env:
    LOG_DIR = os.path.normpath(log_dir_env)
else:
    LOG_DIR = os.path.join(PROJ, "DATA_PULL_SCRIPTS", "Scraping_Logs")

os.makedirs(LOG_DIR, exist_ok=True)

CENTRAL_LOG = os.path.join(LOG_DIR, f"central_{time.strftime('%Y%m%d_%H%M%S')}.log")


def central_log(*parts):
    line = "[" + timestamp() + "] " + " ".join(str(p) for p in parts)
    with open(CENTRAL_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def log_path_for(store: str) -> str:
    date_str = time.strftime("%Y%m%d")
    return os.path.join(LOG_DIR, f"{store}_{date_str}.log")


def log_line(store: str, *parts: str) -> None:
    line = "[" + timestamp() + "] " + " ".join(str(p) for p in parts)
    path = log_path_for(store)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


print(f"LOG_DIR (Python) => {LOG_DIR}", flush=True)
print("FM log path =>", os.path.join(LOG_DIR, f"FM_{time.strftime('%Y%m%d')}.log"), flush=True)


REPO_ROOT = r"C:\Users\vlcollier\GITHUB_PUSH\Alaska_Food"
DPS = os.path.join(REPO_ROOT, "DATA_PULL_SCRIPTS")

acc_script = os.path.join(DPS, "ACC", "ACC_PULL_CURRENT.py")
cs_script = os.path.join(DPS, "CS", "CS_PULL_CURRENT.py")
fm_script = os.path.join(DPS, "FM", "FM_PULL_CURRENT.py")

wm_mode = os.getenv("WM_MODE", "PULL").strip().upper()
if wm_mode == "DOWNLOAD":
    wm_script = os.path.join(DPS, "WM", "WM_download_snapshot.py")
else:
    wm_script = os.path.join(DPS, "WM", "WM_PULL_CURRENT.py")

print("Resolved scripts:", flush=True)
print("  ACC:", acc_script, flush=True)
print("  CS :", cs_script, flush=True)
print("  FM :", fm_script, flush=True)
print("  WM :", wm_script, flush=True)


def load_kroger_creds(proj_root: str) -> tuple[str, str]:
    env_id = os.getenv("KROGER_CLIENT_ID", "").strip()
    env_sec = os.getenv("KROGER_CLIENT_SECRET", "").strip()
    if env_id and env_sec:
        return env_id, env_sec

    secrets_dir = Path(proj_root) / "SECRETS"

    csv_path = secrets_dir / "kroger_creds.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            row = next(reader, None)
        if row:
            id_keys = ["client_id", "CLIENT_ID", "KROGER_CLIENT_ID"]
            sec_keys = ["client_secret", "CLIENT_SECRET", "KROGER_CLIENT_SECRET"]
            cid = None
            csec = None
            for k in id_keys:
                if k in row and row[k]:
                    cid = row[k].strip()
                    break
            for k in sec_keys:
                if k in row and row[k]:
                    csec = row[k].strip()
                    break
            if cid and csec:
                return cid, csec

    json_path = secrets_dir / "kroger_creds.json"
    if json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as f:
                j = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to parse {json_path}: {e}") from e

        cand = None
        if isinstance(j, dict):
            cand = j
        if isinstance(j, list) and j and isinstance(j[0], dict):
            cand = j[0]

        if isinstance(cand, dict):
            id_keys = ["client_id", "CLIENT_ID", "KROGER_CLIENT_ID"]
            sec_keys = ["client_secret", "CLIENT_SECRET", "KROGER_CLIENT_SECRET"]
            cid = None
            csec = None
            for k in id_keys:
                val = cand.get(k)
                if val:
                    cid = str(val).strip()
                    break
            for k in sec_keys:
                val = cand.get(k)
                if val:
                    csec = str(val).strip()
                    break
            if cid and csec:
                return cid, csec

    raise RuntimeError(
        "Kroger credentials not provided.\n"
        "Provide env vars KROGER_CLIENT_ID / KROGER_CLIENT_SECRET.\n"
        "FM cannot run without these."
    )


def mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "<empty>"
    if len(s) <= 6:
        return s
    return s[:6] + "…"


def run_python_file(store: str, py_file: str, extra_env: dict | None = None) -> bool:
    import runpy

    extra_env = extra_env or {}
    log_line(store, "START:", py_file)

    old_vals = {k: os.environ.get(k) for k in extra_env}
    try:
        for k, v in extra_env.items():
            os.environ[k] = v

        runpy.run_path(py_file, run_name="__main__")
        log_line(store, "SUCCESS.")
        return True
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        if code == 0:
            log_line(store, "SUCCESS (sys.exit(0)).")
            return True
        log_line(store, f"ERROR: script exited with code {code}")
        tb = traceback.format_exc()
        with open(log_path_for(store), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp()}] PY_TRACEBACK:\n{tb}\n")
        print("See log for full Python traceback:", log_path_for(store), flush=True)
        return False
    except Exception:
        log_line(store, "ERROR: exception while running script.")
        tb = traceback.format_exc()
        with open(log_path_for(store), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp()}] PY_TRACEBACK:\n{tb}\n")
        print("See log for full Python traceback:", log_path_for(store), flush=True)
        return False
    finally:
        for k, old in old_vals.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def main() -> int:
    central_log("Central runner started")
    central_log("RUN_DATE =", RUN_DATE)
    central_log("SCRAPE_LOG_DIR =", LOG_DIR)

    def env_flag(name: str) -> bool:
        val = os.getenv(name)
        if val is None:
            return False
        return val.strip().upper() in ("1", "TRUE", "YES", "Y")

    RUN_ACC = env_flag("RUN_ACC")
    RUN_CS = env_flag("RUN_CS")
    RUN_FM = env_flag("RUN_FM")
    RUN_WM = env_flag("RUN_WM")

    central_log(
        f"Toggles: RUN_ACC={RUN_ACC}, RUN_CS={RUN_CS}, "
        f"RUN_FM={RUN_FM}, RUN_WM={RUN_WM}"
    )

    kroger_client_id = ""
    kroger_client_secret = ""

    if RUN_FM:
        kroger_client_id = os.getenv("KROGER_CLIENT_ID", "").strip()
        kroger_client_secret = os.getenv("KROGER_CLIENT_SECRET", "").strip()
        if not kroger_client_id or not kroger_client_secret:
            print("[FM ERROR] Kroger credentials not found in environment.", flush=True)
            print("KROGER_CLIENT_ID =", kroger_client_id, flush=True)
            print("KROGER_CLIENT_SECRET =", kroger_client_secret, flush=True)
            return 1

    wm_env = {}
    if RUN_WM:
        bright_key = os.getenv("WM_API_KEY", "").strip()
        if not bright_key:
            print(
                "ERROR: WM_API_KEY is not set, but RUN_WM=TRUE.\n"
                "Set WM_API_KEY in run_food_pull.bat before running.",
                file=sys.stderr,
            )
            return 1

        dataset_id = os.getenv("WM_DATASET_ID", "gd_m693oc1r1gebnayxq").strip()
        snapshot_id = os.getenv("WM_SNAPSHOT_ID", "").strip()
        raw_root = os.getenv("WM_RAW_ROOT", "").strip()
        wm_mode_local = os.getenv("WM_MODE", "PULL").strip().upper()

        wm_env = {
            "STORE": "WM",
            "RUN_DATE": RUN_DATE,
            "WM_API_KEY": bright_key,
            "WM_DATASET_ID": dataset_id,
            "WM_MODE": wm_mode_local,
            "WM_RAW_ROOT": raw_root,
            "WM_SEARCH_FILE": os.getenv("WM_SEARCH_FILE", "").strip(),
        }

        if snapshot_id:
            wm_env["WM_SNAPSHOT_ID"] = snapshot_id

        print("WM env: WM_API_KEY=", mask(bright_key), flush=True)

    jobs: list[dict] = []

    acc_raw_root = os.getenv("ACC_RAW_ROOT", "").strip()
    cs_raw_root = os.getenv("CS_RAW_ROOT", "").strip()
    fm_raw_root = os.getenv("FM_RAW_ROOT", "").strip()

    if RUN_ACC:
        if acc_script and Path(acc_script).is_file():
            jobs.append(
                {
                    "store": "ACC",
                    "py": acc_script,
                    "env": {
                        "STORE": "ACC",
                        "RUN_DATE": RUN_DATE,
                        "ACC_RAW_ROOT": acc_raw_root,
                    },
                }
            )
        else:
            print("RUN_ACC=TRUE but ACC script not found.", file=sys.stderr)
            return 1

    if RUN_CS:
        if cs_script and Path(cs_script).is_file():
            jobs.append(
                {
                    "store": "CS",
                    "py": cs_script,
                    "env": {
                        "STORE": "CS",
                        "RUN_DATE": RUN_DATE,
                        "CS_RAW_ROOT": cs_raw_root,
                    },
                }
            )
        else:
            print("RUN_CS=TRUE but CS script not found.", file=sys.stderr)
            return 1

    if RUN_FM:
        if fm_script and Path(fm_script).is_file():
            env = {
                "STORE": "FM",
                "RUN_DATE": RUN_DATE,
                "KROGER_CLIENT_ID": kroger_client_id,
                "KROGER_CLIENT_SECRET": kroger_client_secret,
                "FM_RAW_ROOT": fm_raw_root,
            }
            jobs.append(
                {
                    "store": "FM",
                    "py": fm_script,
                    "env": env,
                }
            )
        else:
            print("RUN_FM=TRUE but FM script not found.", file=sys.stderr)
            return 1

    if RUN_WM:
        if wm_script and Path(wm_script).is_file():
            jobs.append(
                {
                    "store": "WM",
                    "py": wm_script,
                    "env": wm_env,
                }
            )
        else:
            print("RUN_WM=TRUE but WM script not found.", file=sys.stderr)
            return 1

    if not jobs:
        print("No jobs to run. Set one or more RUN_* environment variables to TRUE.", file=sys.stderr)
        return 1

    total = len(jobs)
    print(f"\n---- Food Pull (Python): {total} job(s) ----", flush=True)

    all_ok = True
    for idx, job in enumerate(jobs, start=1):
        store = job["store"]
        py_file = job["py"]
        env = job["env"]

        print(f"({idx}/{total}) {store} — starting", flush=True)
        t0 = time.time()
        ok = run_python_file(store, py_file, extra_env=env)
        dt = time.time() - t0
        status = "✔" if ok else "✖"
        print(f"   {status} {store} — {fmt_secs(dt)}", flush=True)
        all_ok = all_ok and ok

    if not all_ok:
        print("\nOne or more pulls failed. Check logs in:", LOG_DIR, file=sys.stderr)
        return 1

    print("\nAll pulls completed successfully.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        with open(CENTRAL_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp()}] FATAL ERROR\n{tb}\n")
        raise
