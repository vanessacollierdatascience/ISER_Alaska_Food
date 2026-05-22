#!/usr/bin/env python3

"""
Central data cleaning runner bootstrap.

- Loads libraries and shared helpers
- Defines roots and logging
- Provides shared utilities used by store-specific runners
- Runs store-specific runners if they exist (acc_runner, cs_runner, fm_runner, wm_runner)

Reentrancy protection:
- Wrapped in main() + __name__ guard
- File lock in LOG_ROOT to prevent accidental double-runs (e.g., autoreload)
"""
# Note: future must always be at the top
from __future__ import annotations

import os


from schema import MASTER_COLS

import argparse
import time
import traceback
import csv
import json
import re
import importlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# NEW IMPORT ---------------------------------------------------------
from prebuild_missing_store_months import ensure_cleaned_for_all_raw

# Absolute path to this script (for debugging which copy is being executed)
CENTRAL_RUNNER_PATH = Path(__file__).resolve()

# --------------------------------------------------------------------

# ---------- Roots and logging (configured in main via BAT args) ----------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ISER Food Pricing central runner")
    p.add_argument("--raw-root", required=True)
    p.add_argument("--clean-root", required=True)
    p.add_argument("--crosswalk", required=True)
    p.add_argument("--log", required=False)
    args = p.parse_args()

    # Fallback to BAT-provided PIPELINE_LOG if --log not passed
    if args.log is None:
        env_log = os.environ.get("PIPELINE_LOG")
        if not env_log:
            raise RuntimeError(
                "No log file provided. Pass --log or set PIPELINE_LOG in the BAT."
            )
        args.log = env_log

    return args




def log_line(path: Path, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{msg}"
    print(line)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {line}\n")
    except Exception:
        pass


def _now() -> float:
    return time.perf_counter()


def _fmt_secs(sec: float) -> str:
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}m {s:05.2f}s"


# --------------------------------------------------------------------
# (existing helpers omitted for brevity—unchanged)
# --------------------------------------------------------------------


# ---------- IO helpers ----------

def read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for enc in ["utf-8", "latin-1"]:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                rdr = csv.DictReader(f)
                if rdr.fieldnames is None:
                    continue
                for r in rdr:
                    rows.append(dict(r))
            return rows
        except UnicodeDecodeError:
            continue
        except Exception:
            break
    return rows


def read_json_rows(path: Path) -> List[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1", errors="ignore")

    raw_lines = [ln for ln in raw.splitlines() if ln.strip()]
    if len(raw_lines) > 1:
        parsed = 0
        for ln in raw_lines[:10]:
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    parsed += 1
            except Exception:
                parsed = parsed
        if parsed > 3:
            rows = []
            for ln in raw_lines:
                try:
                    obj = json.loads(ln)
                    if isinstance(obj, dict):
                        rows.append(obj)
                except Exception:
                    continue
            return rows

    try:
        data = json.loads(raw)
    except Exception:
        return []

    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ["items", "data", "rows", "results", "Records", "RECORDS", "Items", "Data"]:
            if key in data and isinstance(data[key], list):
                return [r for r in data[key] if isinstance(r, dict)]
        return [data]
    return []


def write_csv(path: Path, rows: List[Dict[str, Any]], header: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


# ---------- header utilities ----------

def upper_headers(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(rows) == 0:
        return rows
    out = []
    for r in rows:
        new_r = {}
        for k, v in r.items():
            k2 = "" if k is None else str(k).strip().upper()
            new_r[k2] = v
        out.append(new_r)
    return out


# ---------- crosswalk ----------

def read_crosswalk_generic(path: Path, log_path: Path) -> Dict[Tuple[str, str], Dict[str, str]]:
    rows = read_csv_rows(path)
    rows = upper_headers(rows)
    xmap: Dict[Tuple[str, str], Dict[str, str]] = {}
    for r in rows:
        home = str(r.get("HOME_STORE_NAME", "")).strip().upper()
        sid = str(r.get("STORE_ID", "")).strip()
        if len(home) == 0 or len(sid) == 0:
            continue
        xmap[(home, sid)] = {
            "STORE_NAME": str(r.get("STORE_NAME", "")).strip(),
            "ADDRESS": str(r.get("ADDRESS", "")).strip(),
            "CITY": str(r.get("CITY", "")).strip().title(),
            "STATE": str(r.get("STATE", "")).strip(),
            "ZIP": str(r.get("ZIP", "")).strip()[:5],
            "STORE_REGION": str(r.get("STORE_REGION", "")).strip(),
            "LONGITUDE": str(r.get("LONGITUDE", "")).strip(),
            "LATITUDE": str(r.get("LATITUDE", "")).strip()
        }
    log_line(log_path, f"[XWALK] Loaded rows: {len(rows)} keys: {len(xmap)}")
    return xmap


# ---------- folder tag and pull-date ----------

TAG_PATTERNS = [
    re.compile(r"^(?P<store>[A-Z]{2})_(?P<yy>\d{2})_(?P<mm>\d{2})$", re.IGNORECASE),
    re.compile(r"^(?P<store>[A-Z]{2})_(?P<yyyy>\d{4})_(?P<mm>\d{2})$", re.IGNORECASE)
]

def parse_folder_tag(name: str, expect_store: str) -> Optional[str]:
    for pat in TAG_PATTERNS:
        m = pat.match(name)
        if m is None:
            continue
        store = m.group("store").upper()
        if store != expect_store.upper():
            continue
        if "yy" in m.groupdict():
            yy = m.group("yy")
            mm = m.group("mm")
            return f"{yy}_{mm}"
        yyyy = m.group("yyyy")
        mm = m.group("mm")
        yy = yyyy[-2:]
        return f"{yy}_{mm}"
    return None


def pull_date_from_folder_tag(tag: str) -> str:
    parts = tag.split("_")
    if len(parts) == 3 and len(parts[1]) == 2:
        yy = parts[1]
        mm = parts[2]
        return f"{yy}-{mm}-15"
    if len(parts) == 3 and len(parts[1]) == 4:
        yy = parts[1][-2:]
        mm = parts[2]
        return f"{yy}-{mm}-15"
    return ""


def ensure_pull_date(rows: List[Dict[str, Any]], file_path: Path, override_value: str) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        r["PULL_DATE"] = override_value
        out.append(r)
    return out


# ---------- field post-processing ----------


SIZE_PAT = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*(OZ|FL\s*OZ|LB|L|ML|G|KG|CT|EA|QT|PT|GAL))"
    r"|(?:(\d+)\s*(PK|PKG|PACK))"
    r"|(?:(\d+)\s*[xX]\s*(\d+(?:\.\d+)?)(?:\s*(OZ|FL\s*OZ|LB|L|ML|G|KG|CT|EA|QT|PT|GAL))?)",
    re.IGNORECASE
)

SKU_ALIASES = [
    "SKU",
    "PRODUCT.ID",
    "PRODUCT_ID",
    "ITEM_ID",
    "PRODUCT.ITEM_ID",
    "SKU_CODE",
    "ITEMNBR",
    "ITEM_NBR",
    "ITEM"
]


def coalesce(*vals: Any) -> str:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if len(s) > 0:
            return s
    return ""


def maybe_extract_size(desc: str) -> str:
    if desc is None:
        return ""
    m = SIZE_PAT.search(str(desc))
    if m is None:
        return ""
    return m.group(0).strip()


def finalize_common_fields(row: Dict[str, Any],
                           original_headers_upper: List[str],
                           store_code: str,
                           crosswalk: Dict[Tuple[str, str], Dict[str, str]],
                           force_state_code: Optional[str]) -> None:
    # Always use the canonical store code (ACC, CS, FM, WM)
    store_code = store_code.upper()
    row["HOME_STORE_NAME"] = store_code

    sid = coalesce(row.get("STORE_ID", ""))
    cw = crosswalk.get((store_code, sid), {})
    if len(cw) > 0:
        row["STORE_NAME"] = coalesce(row.get("STORE_NAME", ""), cw.get("STORE_NAME", ""))
        row["ADDRESS"] = coalesce(row.get("ADDRESS", ""), cw.get("ADDRESS", ""))
        row["CITY"] = coalesce(row.get("CITY", ""), cw.get("CITY", ""))
        row["STATE"] = coalesce(row.get("STATE", ""), cw.get("STATE", ""))
        row["ZIP"] = coalesce(row.get("ZIP", ""), cw.get("ZIP", ""))
        row["STORE_REGION"] = coalesce(row.get("STORE_REGION", ""), cw.get("STORE_REGION", ""))
        row["LONGITUDE"] = coalesce(row.get("LONGITUDE", ""), cw.get("LONGITUDE", ""))
        row["LATITUDE"] = coalesce(row.get("LATITUDE", ""), cw.get("LATITUDE", ""))

    if force_state_code is not None and len(force_state_code) > 0:
        row["STATE"] = force_state_code

    row["UPC"] = coalesce(row.get("UPC", ""), row.get("PRIMARY_UPC", ""))

    sku_val = ""
    for a in SKU_ALIASES:
        if a in original_headers_upper and len(sku_val) == 0:
            sku_val = coalesce(row.get(a, ""))
    if len(sku_val) == 0:
        sku_val = row.get("SKU", "")
    if len(sku_val) == 0:
        sku_val = row.get("UPC", "")
    row["SKU"] = sku_val

    desc = coalesce(row.get("SKU_DESCRIPTION", ""), row.get("E_COMM_DESCRIPTION_AND_SIZE", ""))
    row["SKU_DESCRIPTION"] = desc

    if len(coalesce(row.get("SIZE", ""))) == 0:
        row["SIZE"] = maybe_extract_size(desc)

    row["PRIMARY_STORE_KEY"] = ""
    if len(row.get("HOME_STORE_NAME", "")) > 0 and len(row.get("CITY", "")) > 0 and len(row.get("ZIP", "")) > 0:
        row["PRIMARY_STORE_KEY"] = f"{row['HOME_STORE_NAME']}_{row['CITY']}-{row['ZIP']}"

    row["PRIMARY_KEY"] = ""
    if len(row["PRIMARY_STORE_KEY"]) > 0 and len(row.get("SKU", "")) > 0:
        row["PRIMARY_KEY"] = f"{row['PRIMARY_STORE_KEY']}_{row['SKU']}"
    elif len(row["PRIMARY_STORE_KEY"]) > 0 and len(row.get("UPC", "")) > 0:
        row["PRIMARY_KEY"] = f"{row['PRIMARY_STORE_KEY']}_{row['UPC']}"

    pd = coalesce(row.get("PULL_DATE", ""))
    if re.match(r"^\d{2}-\d{2}-\d{2}$", pd) is None and re.match(r"^\d{2}-\d{2}-\d{2,4}$", pd) is None:
        row["MONTH"] = ""
        row["YEAR"] = ""
        row["MONTH_YEAR"] = ""
    else:
        parts = pd.split("-")
        if len(parts) == 3:
            yy = parts[0]
            mm = parts[1]
            row["MONTH"] = mm
            row["YEAR"] = f"20{yy}"
            row["MONTH_YEAR"] = f"{yy}-{mm}"

    if store_code.upper() != "ACC":
        row["SALES_TAX_CITY_FLAG"] = ""
        row["SALES_TAX_FED_FLAG"] = ""
        row["SALES_TAX_MUNI_FLAG"] = ""
        row["SALES_TAX_FLAT_FLAG"] = ""
        row["SNAP_FLAG"] = ""
        row["ITEM_WEIGHT"] = ""
        row["FREIGHT_TYPE"] = ""


# ---------- dynamic runner execution ----------

def _try_run(module_name: str,
             func_name: str,
             log_root: Path,
             raw_root: Path,
             clean_root: Path,
             crosswalk_path: Path,
             central_log_path: Path) -> tuple[bool, float]:
    phase = module_name.upper()
    start = _now()
    log_line(central_log_path, f"[{phase}] START")
    try:
        mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name)
        fn(log_root, raw_root, clean_root, crosswalk_path, central_log_path)
        elapsed = _now() - start
        log_line(central_log_path, f"[{phase}] SUCCESS elapsed={_fmt_secs(elapsed)}")
        return True, elapsed
    except Exception as e:
        elapsed = _now() - start
        log_line(central_log_path, f"[{phase}] FAIL elapsed={_fmt_secs(elapsed)} error={e.__class__.__name__}: {e}")
        tb = traceback.format_exc()
        log_line(central_log_path, f"[{phase}] TRACEBACK >>>")
        for line in tb.splitlines():
            log_line(central_log_path, f"[{phase}] {line}")
        log_line(central_log_path, f"[{phase}] TRACEBACK <<<")
        return False, elapsed




def main() -> None:
    import sys

    args = parse_args()

    RAW_ROOT = Path(args.raw_root)
    CLEAN_ROOT = Path(args.clean_root)
    CROSSWALK_PATH = Path(args.crosswalk)
    CENTRAL_LOG = Path(args.log)

    # Confirm which central_runner.py is actually being executed
    log_line(CENTRAL_LOG, f"central_runner file: {CENTRAL_RUNNER_PATH}")

    LOG_ROOT = CENTRAL_LOG.parent
    LOG_ROOT.mkdir(parents = True, exist_ok = True)
    CLEAN_ROOT.mkdir(parents = True, exist_ok = True)

    LOCK_PATH = LOG_ROOT / "central_runner.lock"

    log_line(CENTRAL_LOG, f"Python interpreter: {sys.executable}")
    log_line(CENTRAL_LOG, f"Central runner start: {datetime.now()}")
    log_line(CENTRAL_LOG, f"RAW_ROOT: {RAW_ROOT}")
    log_line(CENTRAL_LOG, f"CLEAN_ROOT: {CLEAN_ROOT}")
    log_line(CENTRAL_LOG, f"CROSSWALK_PATH: {CROSSWALK_PATH}")
    log_line(CENTRAL_LOG, "Central roots initialized")

    # -------------------------------------------------------------
    # NEW STEP 0 — ENSURE RAW FILES ARE IMPORTED IF CLEANED MISSING
    # -------------------------------------------------------------
    log_line(CENTRAL_LOG, "[PRECHECK] Ensuring RAW files -> CLEANED equivalents")

    try:
        ensure_cleaned_for_all_raw(RAW_ROOT, CLEAN_ROOT, CENTRAL_LOG)
    except Exception as e:
        log_line(CENTRAL_LOG, f"[PRECHECK][ERROR] RAW→CLEAN check failed: {e}")

    # -------------------------------------------------------------

    if LOCK_PATH.exists():
        log_line(CENTRAL_LOG, "[LOCK] Another central_runner appears to be running. Exiting.")
        return
    try:
        with LOCK_PATH.open("x", encoding="utf-8") as f:
            f.write(datetime.now().isoformat())
    except FileExistsError:
        log_line(CENTRAL_LOG, "[LOCK] Another central_runner appears to be running. Exiting.")
        return

    try:
        total_start = _now()
        log_line(CENTRAL_LOG, "[PIPELINE] START")

        acc_ok, acc_t = _try_run("acc_runner", "run_acc", LOG_ROOT, RAW_ROOT, CLEAN_ROOT, CROSSWALK_PATH, CENTRAL_LOG)
        cs_ok, cs_t = _try_run("cs_runner", "run_cs", LOG_ROOT, RAW_ROOT, CLEAN_ROOT, CROSSWALK_PATH, CENTRAL_LOG)
        fm_ok, fm_t = _try_run("fm_runner", "run_fm", LOG_ROOT, RAW_ROOT, CLEAN_ROOT, CROSSWALK_PATH, CENTRAL_LOG)
        wm_ok, wm_t = _try_run("wm_runner", "run_wm", LOG_ROOT, RAW_ROOT, CLEAN_ROOT, CROSSWALK_PATH, CENTRAL_LOG)

        log_line(CENTRAL_LOG, "Attempting MASTER assembly")
        master_ok, master_t = _try_run("master_assembly", "run_master", LOG_ROOT, RAW_ROOT, CLEAN_ROOT, CROSSWALK_PATH, CENTRAL_LOG)

        summary = [
            f"ACC:{'OK' if acc_ok else 'X'}({_fmt_secs(acc_t)})",
            f"CS:{'OK' if cs_ok else 'X'}({_fmt_secs(cs_t)})",
            f"FM:{'OK' if fm_ok else 'X'}({_fmt_secs(fm_t)})",
            f"WM:{'OK' if wm_ok else 'X'}({_fmt_secs(wm_t)})",
            f"MASTER:{'OK' if master_ok else 'X'}({_fmt_secs(master_t)})"
        ]
        log_line(CENTRAL_LOG, "[PIPELINE] SUMMARY " + " ".join(summary))

        total_elapsed = _now() - total_start
        log_line(CENTRAL_LOG, f"[PIPELINE] COMPLETE elapsed={_fmt_secs(total_elapsed)}")

    finally:
        try:
            LOCK_PATH.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()

    
